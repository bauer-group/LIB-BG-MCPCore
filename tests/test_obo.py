"""Per-user OBO resolver: claim/storage resolution, static fallback, fail-closed."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from bg_mcpcore.auth.obo import (
    MissingUpstreamToken,
    PerUserTokenResolver,
    _extract_access_token,
    build_per_user_resolver,
)
from bg_mcpcore.profile.models import OutboundAuthConfig


def _patch_token(monkeypatch: pytest.MonkeyPatch, claims: dict[str, Any] | None) -> None:
    import fastmcp.server.dependencies as deps

    token = None if claims is None else SimpleNamespace(claims=claims)
    monkeypatch.setattr(deps, "get_access_token", lambda: token)


def _patch_storage(monkeypatch: pytest.MonkeyPatch, storage: Any) -> None:
    monkeypatch.setattr("bg_mcpcore.auth.obo._resolve_client_storage_from_context", lambda: storage)


def test_default_headers_empty() -> None:
    # Per-call only — never bake a per-user credential.
    assert PerUserTokenResolver().default_headers() == {}


@pytest.mark.asyncio
async def test_per_user_from_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_token(monkeypatch, {"upstream_access_token": "tok-123"})
    assert await PerUserTokenResolver().auth_headers(None) == {"Authorization": "Bearer tok-123"}


@pytest.mark.asyncio
async def test_custom_scheme_and_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_token(monkeypatch, {"zammad_access_token": "z"})
    resolver = PerUserTokenResolver(scheme="Token", claims=["zammad_access_token"])
    assert await resolver.auth_headers(None) == {"Authorization": "Token z"}


@pytest.mark.asyncio
async def test_fail_closed_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_token(monkeypatch, {"sub": "u1"})  # no token claim
    _patch_storage(monkeypatch, None)
    with pytest.raises(MissingUpstreamToken):
        await PerUserTokenResolver().auth_headers(None)


@pytest.mark.asyncio
async def test_static_fallback_with_template(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_token(monkeypatch, None)  # no auth context at all
    resolver = PerUserTokenResolver(
        static_fallback="static-pat", static_fallback_template="Token token={token}"
    )
    assert await resolver.auth_headers(None) == {"Authorization": "Token token=static-pat"}


@pytest.mark.asyncio
async def test_storage_lookup_by_jti(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_token(monkeypatch, {"jti": "j1"})

    class _Store:
        async def get(self, key: str) -> Any:
            return {"access_token": "from-storage"} if key == "upstream_tokens/j1" else None

    _patch_storage(monkeypatch, _Store())
    assert await PerUserTokenResolver().auth_headers(None) == {"Authorization": "Bearer from-storage"}


def test_factory_reads_config() -> None:
    cfg = OutboundAuthConfig(
        type="per_user_token",
        header="X-Auth",
        scheme="Token",
        static_fallback_env="PAT",
        static_fallback_template="Token token={token}",
    )
    resolver = build_per_user_resolver(cfg, env={"PAT": "static-x"})
    assert resolver._header == "X-Auth"
    assert resolver._scheme == "Token"
    assert resolver._static_fallback == "static-x"
    assert resolver._static_template == "Token token={token}"


def test_extract_access_token_shapes() -> None:
    assert _extract_access_token({"access_token": "a"}) == "a"
    assert _extract_access_token({"token": "b"}) == "b"
    assert _extract_access_token("raw") == "raw"
    assert _extract_access_token({"nope": 1}) is None
    assert _extract_access_token(None) is None
