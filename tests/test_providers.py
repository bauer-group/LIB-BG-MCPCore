"""Tests for the [oauth-providers] extra: Entra/Google builders + tenant gate."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from bg_mcpcore.plugins import build_auth_middleware, build_auth_provider
from bg_mcpcore.profile.loader import ProfileError
from bg_mcpcore.providers.entra import build_entra_provider, is_tenant_allowed
from bg_mcpcore.providers.google import build_google_provider
from bg_mcpcore.providers.middleware import TenantAllowlistMiddleware, build_tenant_middleware

# ── is_tenant_allowed ────────────────────────────────────────────────────────


def test_empty_allowlist_permits_any_tenant() -> None:
    assert is_tenant_allowed({"tid": "anything"}, []) is True


def test_tenant_on_allowlist_permitted() -> None:
    assert is_tenant_allowed({"tid": "t-1"}, ["t-1", "t-2"]) is True


def test_tenant_off_allowlist_denied() -> None:
    assert is_tenant_allowed({"tid": "t-9"}, ["t-1"]) is False


def test_missing_tid_denied_when_allowlist_set() -> None:
    assert is_tenant_allowed({"sub": "u1"}, ["t-1"]) is False


# ── provider builders (validation paths, no real provider construction) ───────


def test_entra_requires_credentials() -> None:
    settings = SimpleNamespace(entra_client_id=None, entra_client_secret=None, entra_tenant_id=None)
    with pytest.raises(ValueError, match="client_id, client_secret, tenant_id"):
        build_entra_provider(settings)  # type: ignore[arg-type]


def test_google_requires_credentials() -> None:
    settings = SimpleNamespace(google_client_id=None, google_client_secret=None)
    with pytest.raises(ValueError, match="client_id"):
        build_google_provider(settings)  # type: ignore[arg-type]


# ── tenant middleware factory ────────────────────────────────────────────────


def test_build_tenant_middleware_none_when_no_allowlist() -> None:
    assert build_tenant_middleware(SimpleNamespace(entra_allowed_tenants=[])) is None


def test_build_tenant_middleware_returns_middleware_when_set() -> None:
    mw = build_tenant_middleware(SimpleNamespace(entra_allowed_tenants=["t-1"]))
    assert isinstance(mw, TenantAllowlistMiddleware)


# ── entry-point wiring (requires the package's entry points to be installed) ──


def test_auth_provider_routes_to_google_builder() -> None:
    # Routing reaches build_google_provider, which rejects missing creds.
    settings = SimpleNamespace(auth_mode="google", google_client_id=None, google_client_secret=None)
    with pytest.raises(ValueError, match="client_id"):
        build_auth_provider(settings)


def test_auth_provider_routes_to_entra_builder() -> None:
    settings = SimpleNamespace(
        auth_mode="entra-multi",
        entra_client_id=None,
        entra_client_secret=None,
        entra_tenant_id=None,
    )
    with pytest.raises(ValueError, match="client_id, client_secret, tenant_id"):
        build_auth_provider(settings)


def test_unknown_mode_still_rejected() -> None:
    with pytest.raises(ProfileError, match="Unknown AUTH_MODE"):
        build_auth_provider(SimpleNamespace(auth_mode="saml-made-up"))


def test_auth_middleware_wired_for_entra_multi() -> None:
    mws = build_auth_middleware(SimpleNamespace(auth_mode="entra-multi", entra_allowed_tenants=["t-1"]))
    assert len(mws) == 1
    assert isinstance(mws[0], TenantAllowlistMiddleware)


def test_auth_middleware_empty_for_none_mode() -> None:
    assert build_auth_middleware(SimpleNamespace(auth_mode="none")) == []


# ── generic OIDC (core) ──────────────────────────────────────────────────────


def test_generic_oidc_explicit_endpoints_require_issuer(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Explicit-endpoint mode cannot derive the issuer from the authorize URL, so
    # an unset OIDC_ISSUER must fail fast rather than mint a verifier that silently
    # rejects every token (regression for the old wrong string-chop fallback).
    from bg_mcpcore.auth.generic_oidc import build_generic_oidc_provider

    settings = SimpleNamespace(
        oidc_client_id="cid",
        oidc_client_secret=SecretStr("csecret"),
        oidc_scopes="openid",
        public_base_url="https://mcp.example.com",
        auth_jwt_signing_key=SecretStr("a-strong-32-byte-signing-key-value-123456"),
        auth_redis_url=None,
        auth_storage_encryption_key=None,
        auth_disk_storage_path=str(tmp_path / "oauth"),
        oidc_discovery_url=None,
        oidc_auth_uri="https://idp/realms/r/protocol/openid-connect/auth",
        oidc_token_uri="https://idp/realms/r/protocol/openid-connect/token",
        oidc_jwks_uri="https://idp/realms/r/protocol/openid-connect/certs",
        oidc_issuer=None,
    )
    with pytest.raises(ValueError, match="OIDC_ISSUER"):
        build_generic_oidc_provider(settings)  # type: ignore[arg-type]
