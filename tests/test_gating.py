"""The access-gate enforcement scope, pinned across both FastMCP 4 protocol eras.

FastMCP 4 changed which methods reach ``Middleware.on_request``: the modern
``2026-07-28`` era added ``server/discover`` and dropped ``initialize``, while
the handshake era still sends ``initialize``. Both now pass through the deny
gates, where in FastMCP 3 neither did.

The chosen policy is "allow discovery, deny the rest": a disallowed principal
completes the connection and is denied on its first real operation. These tests
pin both halves of that, and pin the dispatch facts the policy rests on — so a
future FastMCP release that reroutes a method fails here rather than silently
widening or narrowing what the fleet enforces.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from bg_mcpcore.providers.gating import DISCOVERY_METHODS, should_gate

# ── the policy itself ────────────────────────────────────────────────────────


@pytest.mark.parametrize("method", sorted(DISCOVERY_METHODS))
def test_discovery_is_not_gated(method: str) -> None:
    """A disallowed principal may establish the connection."""
    assert should_gate(method) is False


@pytest.mark.parametrize(
    "method",
    ["tools/call", "tools/list", "resources/read", "resources/list", "prompts/get", "prompts/list"],
)
def test_everything_else_is_gated(method: str) -> None:
    """...and may do nothing else — listing included, so the surface stays hidden."""
    assert should_gate(method) is True


def test_unknown_method_is_gated() -> None:
    """Fail closed: a method this policy has never seen is denied, not allowed."""
    assert should_gate("some/future-method") is True
    assert should_gate(None) is True


# ── the dispatch facts the policy depends on ─────────────────────────────────


async def _methods_seen_by_on_request(mode: str) -> list[str]:
    from fastmcp import Client, FastMCP
    from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

    seen: list[str] = []

    class _Probe(Middleware):
        async def on_request(
            self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]
        ) -> Any:
            seen.append(str(context.method))
            return await call_next(context)

    mcp = FastMCP("probe")
    mcp.add_middleware(_Probe())

    @mcp.tool
    def ping() -> str:
        return "pong"

    async with Client(mcp, mode=mode) as client:
        await client.list_tools()
        await client.call_tool("ping", {})
    return seen


@pytest.mark.asyncio
async def test_modern_era_routes_discovery_through_on_request() -> None:
    seen = await _methods_seen_by_on_request("auto")
    assert "server/discover" in seen, seen
    assert "tools/call" in seen and "tools/list" in seen, seen
    # The modern era has no handshake, so this must NOT appear.
    assert "initialize" not in seen, seen


@pytest.mark.asyncio
async def test_legacy_era_routes_initialize_through_on_request() -> None:
    seen = await _methods_seen_by_on_request("legacy")
    assert "initialize" in seen, seen
    assert "tools/call" in seen and "tools/list" in seen, seen


@pytest.mark.asyncio
async def test_notifications_do_not_reach_on_request() -> None:
    """Only on_message sees every message; the gates must not see notifications."""
    seen = await _methods_seen_by_on_request("legacy")
    assert not [m for m in seen if m.startswith("notifications/")], seen


# ── the gates honour the policy ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tenant_gate_allows_discovery_but_denies_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    import fastmcp.server.dependencies as deps

    from bg_mcpcore.providers.middleware import (
        TenantAllowlistMiddleware,
        TenantNotAllowedError,
    )

    class _Token:
        claims: ClassVar[dict[str, Any]] = {"tid": "other-tenant", "sub": "u1"}

    monkeypatch.setattr(deps, "get_access_token", lambda: _Token())
    gate = TenantAllowlistMiddleware(allowed_tenants=["allowed-tenant"])

    async def _call_next(_ctx: Any) -> str:
        return "reached"

    class _Ctx:
        def __init__(self, method: str) -> None:
            self.method = method

    assert await gate.on_request(_Ctx("server/discover"), _call_next) == "reached"
    assert await gate.on_request(_Ctx("initialize"), _call_next) == "reached"
    with pytest.raises(TenantNotAllowedError):
        await gate.on_request(_Ctx("tools/call"), _call_next)
    with pytest.raises(TenantNotAllowedError):
        await gate.on_request(_Ctx("tools/list"), _call_next)


@pytest.mark.asyncio
async def test_role_gate_allows_discovery_but_denies_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    import fastmcp.server.dependencies as deps

    from bg_mcpcore.providers.access_control import (
        RoleAllowlistMiddleware,
        RoleNotAllowedError,
    )

    class _Token:
        claims: ClassVar[dict[str, Any]] = {"roles": ["guest"], "sub": "u1"}

    monkeypatch.setattr(deps, "get_access_token", lambda: _Token())
    gate = RoleAllowlistMiddleware(allowed_roles=["admin"])

    async def _call_next(_ctx: Any) -> str:
        return "reached"

    class _Ctx:
        def __init__(self, method: str) -> None:
            self.method = method

    assert await gate.on_request(_Ctx("server/discover"), _call_next) == "reached"
    with pytest.raises(RoleNotAllowedError):
        await gate.on_request(_Ctx("tools/call"), _call_next)
