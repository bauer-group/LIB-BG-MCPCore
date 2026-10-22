"""Identity assertion (SEP-990 ID-JAG) wiring on the OIDC inbound modes.

An enterprise IdP signs an assertion that an agent presents at the token
endpoint; the server exchanges it for a short-lived access token carrying the
employee's identity, with no browser flow. Enabling it is a security decision,
so the trusted-issuer list is the switch: empty means the ``jwt-bearer`` grant
stays rejected as unsupported.

The provider-support matrix is pinned below because it is the non-obvious part:
only OIDCProxy/OAuthProxy accept the argument in FastMCP 4.0.0.
"""

from __future__ import annotations

import inspect

import pytest

from bg_mcpcore.auth.generic_oidc import _build_identity_assertion


class _Settings:
    """Minimal stand-in for the identity-assertion slice of BaseMcpSettings."""

    def __init__(self, **over: object) -> None:
        self.oidc_identity_assertion_issuers: list[str] = []
        self.oidc_identity_assertion_audience: str | None = None
        self.oidc_identity_assertion_algorithm: str = "RS256"
        for key, value in over.items():
            setattr(self, key, value)


def test_disabled_by_default() -> None:
    """No trusted issuers configured => the grant stays unsupported."""
    assert _build_identity_assertion(_Settings()) is None


def test_empty_issuer_list_does_not_enable_it() -> None:
    assert _build_identity_assertion(_Settings(oidc_identity_assertion_issuers=[])) is None


def test_issuers_enable_it() -> None:
    assertion = _build_identity_assertion(
        _Settings(oidc_identity_assertion_issuers=["https://login.acme.example"])
    )
    assert assertion is not None
    assert list(assertion.trusted_issuers) == ["https://login.acme.example"]
    assert assertion.algorithm == "RS256"


def test_audience_is_pinned_when_given() -> None:
    """Pinning aud survives an issuer_url change without re-minting assertions."""
    assertion = _build_identity_assertion(
        _Settings(
            oidc_identity_assertion_issuers=["https://login.acme.example"],
            oidc_identity_assertion_audience="https://mcp.acme.example",
        )
    )
    assert assertion is not None
    assert assertion.audience == "https://mcp.acme.example"


def test_algorithm_is_configurable() -> None:
    assertion = _build_identity_assertion(
        _Settings(
            oidc_identity_assertion_issuers=["https://sso.acme.example"],
            oidc_identity_assertion_algorithm="ES256",
        )
    )
    assert assertion is not None
    assert assertion.algorithm == "ES256"


def test_settings_parse_the_issuer_csv() -> None:
    from bg_mcpcore import BaseMcpSettings

    settings = BaseMcpSettings(
        environment="development",  # type: ignore[arg-type]
        auth_mode="none",  # type: ignore[arg-type]
        mcp_display_name="T",
        public_base_url="http://localhost:8000",
        oidc_identity_assertion_issuers="https://a.example, https://b.example",  # type: ignore[arg-type]
    )
    assert settings.oidc_identity_assertion_issuers == ["https://a.example", "https://b.example"]


# ── the provider-support matrix this wiring depends on ───────────────────────


def test_oidc_and_oauth_proxies_accept_identity_assertion() -> None:
    from fastmcp.server.auth.oauth_proxy import OAuthProxy
    from fastmcp.server.auth.oidc_proxy import OIDCProxy

    for cls in (OAuthProxy, OIDCProxy):
        assert "identity_assertion" in inspect.signature(cls.__init__).parameters, cls


@pytest.mark.parametrize(
    ("module", "cls_name"),
    [("azure", "AzureProvider"), ("google", "GoogleProvider"), ("auth0", "Auth0Provider")],
)
def test_cloud_idp_providers_reject_identity_assertion(module: str, cls_name: str) -> None:
    """Pin the limitation: an Entra deployment needs AUTH_MODE=oidc for ID-JAG.

    These subclass OAuthProxy but neither declare ``identity_assertion`` nor
    accept ``**kwargs``, so passing it raises TypeError. If a future FastMCP
    forwards it, this test fails and the entra-* modes can gain the feature.
    """
    import importlib

    cls = getattr(importlib.import_module(f"fastmcp.server.auth.providers.{module}"), cls_name)
    params = inspect.signature(cls.__init__).parameters
    assert "identity_assertion" not in params
    assert not any(p.kind is p.VAR_KEYWORD for p in params.values())
