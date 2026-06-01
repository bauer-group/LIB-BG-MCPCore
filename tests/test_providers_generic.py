"""Tests for the spec-driven first-class IdP providers (full FastMCP parity).

Validation paths only — we never construct a real provider (that would hit the
IdP's network endpoints). These prove routing + the profile-config contract:
required keys missing -> ProfileError before any provider is built.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from types import SimpleNamespace

import pytest

from bg_mcpcore.plugins import build_auth_provider
from bg_mcpcore.profile.loader import ProfileError
from bg_mcpcore.providers.generic import build_auth0, build_github, build_keycloak


def _settings(mode: str) -> SimpleNamespace:
    return SimpleNamespace(
        auth_mode=mode,
        public_base_url="https://mcp.test",
        auth_jwt_signing_key=SimpleNamespace(get_secret_value=lambda: "x" * 40),
    )


def _inbound(config: dict) -> SimpleNamespace:
    return SimpleNamespace(config=config)


def test_keycloak_requires_realm_url() -> None:
    with pytest.raises(ProfileError, match="realm_url"):
        build_keycloak(_settings("keycloak"), _inbound({}))


def test_github_requires_client_id() -> None:
    with pytest.raises(ProfileError, match="client_id"):
        build_github(_settings("github"), _inbound({}))


def test_auth0_secret_must_be_referenced_by_env_key() -> None:
    # All non-secret keys present, but the secret must come via `<key>_env`.
    with pytest.raises(ProfileError, match="client_secret_env"):
        build_auth0(
            _settings("auth0"),
            _inbound({"config_url": "https://x", "client_id": "id", "audience": "aud"}),
        )


def test_build_auth_provider_routes_to_spec_driven_mode() -> None:
    # AUTH_MODE=keycloak resolves the entry point and runs the spec builder,
    # which rejects the empty config — proving the routing reaches it.
    with pytest.raises(ProfileError, match="realm_url"):
        build_auth_provider(_settings("keycloak"), _inbound({}))


def test_full_fastmcp_provider_parity_is_registered() -> None:
    names = {ep.name for ep in entry_points(group="bg_mcpcore.auth_providers")}
    expected = {
        "entra-single", "entra-multi", "google",
        "auth0", "aws-cognito", "clerk", "descope", "discord", "github",
        "keycloak", "oci", "propelauth", "scalekit", "supabase", "workos",
    }
    missing = expected - names
    assert not missing, f"missing provider modes: {sorted(missing)}"
