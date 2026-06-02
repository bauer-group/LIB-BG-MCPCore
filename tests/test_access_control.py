"""Declarative access gate: role extraction, the factory, and on_request behaviour."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from bg_mcpcore.profile.models import AccessControlConfig
from bg_mcpcore.providers.access_control import (
    RoleAllowlistMiddleware,
    RoleNotAllowedError,
    _extract_role_names,
    build_access_control_middleware,
)

# ── role extraction ───────────────────────────────────────────────────────────


def test_extract_role_names_variants() -> None:
    assert _extract_role_names(["Admin", "Agent"]) == {"admin", "agent"}
    assert _extract_role_names([{"name": "Admin"}, {"name": "X"}]) == {"admin", "x"}
    assert _extract_role_names(None) == set()
    assert _extract_role_names("admin") == set()  # a bare string is not a role list
    assert _extract_role_names([]) == set()


# ── factory ───────────────────────────────────────────────────────────────────


def test_build_returns_none_on_empty_allowlist() -> None:
    settings = SimpleNamespace(mcp_allowed_roles=[], mcp_role_check_audit_only=False)
    assert build_access_control_middleware(AccessControlConfig(), settings) is None


def test_build_returns_configured_middleware() -> None:
    settings = SimpleNamespace(mcp_allowed_roles=["Admin"], mcp_role_check_audit_only=True)
    mw = build_access_control_middleware(AccessControlConfig(roles_claim="groups"), settings)
    assert isinstance(mw, RoleAllowlistMiddleware)
    assert mw._roles_claim == "groups"
    assert mw._audit_only is True
    assert mw._allowed == {"admin"}


# ── on_request behaviour (monkeypatch the access-token dependency) ─────────────


def _patch_token(monkeypatch: pytest.MonkeyPatch, claims: dict[str, Any] | None) -> None:
    import fastmcp.server.dependencies as deps

    token = None if claims is None else SimpleNamespace(claims=claims)
    monkeypatch.setattr(deps, "get_access_token", lambda: token)


async def _run(mw: RoleAllowlistMiddleware, monkeypatch: pytest.MonkeyPatch, claims: Any) -> bool:
    _patch_token(monkeypatch, claims)
    passed = {"next": False}

    async def call_next(_ctx: Any) -> str:
        passed["next"] = True
        return "passed"

    await mw.on_request(SimpleNamespace(method="tools/call"), call_next)
    return passed["next"]


@pytest.mark.asyncio
async def test_pass_when_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    mw = RoleAllowlistMiddleware(allowed_roles=["admin"])
    assert await _run(mw, monkeypatch, None) is True


@pytest.mark.asyncio
async def test_pass_when_roles_claim_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # No roles claim -> this auth mode carries no roles -> defer to upstream.
    mw = RoleAllowlistMiddleware(allowed_roles=["admin"], roles_claim="roles")
    assert await _run(mw, monkeypatch, {"sub": "u1"}) is True


@pytest.mark.asyncio
async def test_pass_when_role_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    mw = RoleAllowlistMiddleware(allowed_roles=["Admin", "Agent"], roles_claim="roles")
    assert await _run(mw, monkeypatch, {"roles": ["agent"]}) is True


@pytest.mark.asyncio
async def test_deny_when_present_but_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    mw = RoleAllowlistMiddleware(allowed_roles=["admin"], roles_claim="roles")
    _patch_token(monkeypatch, {"roles": ["customer"], "sub": "u9"})

    async def call_next(_ctx: Any) -> str:
        return "passed"

    with pytest.raises(RoleNotAllowedError):
        await mw.on_request(SimpleNamespace(method="tools/call"), call_next)


@pytest.mark.asyncio
async def test_audit_only_passes_on_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    mw = RoleAllowlistMiddleware(allowed_roles=["admin"], roles_claim="roles", audit_only=True)
    assert await _run(mw, monkeypatch, {"roles": ["customer"]}) is True


@pytest.mark.asyncio
async def test_custom_roles_claim_with_object_items(monkeypatch: pytest.MonkeyPatch) -> None:
    mw = RoleAllowlistMiddleware(allowed_roles=["admin"], roles_claim="groups")
    assert await _run(mw, monkeypatch, {"groups": [{"name": "Admin"}]}) is True


# ── settings field (CSV parsing on the base) ───────────────────────────────────


def test_base_settings_parse_allowed_roles_csv() -> None:
    from bg_mcpcore import BaseMcpSettings

    class _S(BaseMcpSettings):
        mcp_display_name: str = "Demo"

    s = _S(environment="development", auth_mode="none", mcp_allowed_roles="Admin, Agent ,Customer")
    assert s.mcp_allowed_roles == ["Admin", "Agent", "Customer"]
    assert s.mcp_role_check_audit_only is False
