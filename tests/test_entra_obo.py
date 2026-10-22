"""The `entra_obo` outbound resolver — the native Entra on-behalf-of exchange.

Prefer this over `per_user_token` on the Entra auth modes: it delegates to
FastMCP's `EntraOBOToken`, a supported API backed by azure-identity's
`OnBehalfOfCredential`, instead of reading a token out of FastMCP's OAuth-state
storage internals. It can also request scopes the caller's own token never
carried.

Like every per-call resolver it must FAIL CLOSED (security guardrail #3): a
failed exchange raises rather than returning {}, which would let the request go
upstream unauthenticated.
"""

from __future__ import annotations

from typing import Any

import pytest

from bg_mcpcore.auth.obo import (
    EntraOboResolver,
    MissingUpstreamToken,
    build_entra_obo_resolver,
)
from bg_mcpcore.profile.loader import ProfileError
from bg_mcpcore.profile.models import OutboundAuthConfig

SCOPES = ["https://graph.microsoft.com/.default"]


class _FakeDependency:
    """Stands in for FastMCP's EntraOBOToken dependency (an async context manager)."""

    def __init__(self, token: str | None = None, raises: BaseException | None = None) -> None:
        self._token = token
        self._raises = raises

    async def __aenter__(self) -> str | None:
        if self._raises is not None:
            raise self._raises
        return self._token

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _patch_token(monkeypatch: pytest.MonkeyPatch, dependency: _FakeDependency) -> list[list[str]]:
    """Replace EntraOBOToken and record the scopes it was asked for."""
    import fastmcp.server.auth.providers.azure as azure

    seen: list[list[str]] = []

    def _factory(scopes: list[str]) -> Any:
        seen.append(list(scopes))
        return dependency

    monkeypatch.setattr(azure, "EntraOBOToken", _factory)
    return seen


# ── the guardrail ────────────────────────────────────────────────────────────


def test_default_headers_are_empty() -> None:
    """Per-call only: a per-user credential must never be baked into the client."""
    assert EntraOboResolver(scopes=SCOPES).default_headers() == {}


def test_empty_scopes_are_rejected_at_construction() -> None:
    """An OBO exchange with no scope is meaningless — fail at boot, not per request."""
    with pytest.raises(ProfileError, match="non-empty 'scopes'"):
        EntraOboResolver(scopes=[])


# ── the happy path ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exchanged_token_becomes_a_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_token(monkeypatch, _FakeDependency(token="graph-tok"))
    headers = await EntraOboResolver(scopes=SCOPES).auth_headers(None)
    assert headers == {"Authorization": "Bearer graph-tok"}
    assert seen == [SCOPES], "the configured scopes must reach the exchange verbatim"


@pytest.mark.asyncio
async def test_header_and_scheme_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_token(monkeypatch, _FakeDependency(token="t"))
    resolver = EntraOboResolver(scopes=SCOPES, header="X-Upstream-Auth", scheme="Token")
    assert await resolver.auth_headers(None) == {"X-Upstream-Auth": "Token t"}


# ── fail closed ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        "No access token available. Cannot perform OBO exchange.",
        "EntraOBOToken requires an AzureProvider as the auth provider.",
        "OBO exchange failed",
    ],
)
async def test_a_failed_exchange_raises(monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    """No caller token, a non-Azure provider, or a rejected exchange — never {}."""
    _patch_token(monkeypatch, _FakeDependency(raises=RuntimeError(reason)))
    with pytest.raises(MissingUpstreamToken, match="Entra OBO exchange failed"):
        await EntraOboResolver(scopes=SCOPES).auth_headers(None)


@pytest.mark.asyncio
async def test_an_empty_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty string would produce a bare 'Bearer' header — refuse it."""
    _patch_token(monkeypatch, _FakeDependency(token=""))
    with pytest.raises(MissingUpstreamToken):
        await EntraOboResolver(scopes=SCOPES).auth_headers(None)


# ── profile wiring ───────────────────────────────────────────────────────────


def test_builder_reads_scopes_from_the_profile() -> None:
    cfg = OutboundAuthConfig.model_validate({"type": "entra_obo", "scopes": SCOPES})
    resolver = build_entra_obo_resolver(cfg, {})
    assert isinstance(resolver, EntraOboResolver)


@pytest.mark.parametrize("scopes", [None, "not-a-list", [1, 2], []])
def test_builder_rejects_a_bad_scopes_value(scopes: object) -> None:
    payload: dict[str, Any] = {"type": "entra_obo"}
    if scopes is not None:
        payload["scopes"] = scopes
    cfg = OutboundAuthConfig.model_validate(payload)
    with pytest.raises(ProfileError, match="scopes"):
        build_entra_obo_resolver(cfg, {})


def test_dispatch_from_plugins() -> None:
    from bg_mcpcore.plugins import build_outbound_resolver

    cfg = OutboundAuthConfig.model_validate({"type": "entra_obo", "scopes": SCOPES})
    assert isinstance(build_outbound_resolver(cfg, env={}), EntraOboResolver)


def test_it_satisfies_the_outbound_protocol() -> None:
    from bg_mcpcore import AuthHeaderSource

    assert isinstance(EntraOboResolver(scopes=SCOPES), AuthHeaderSource)
