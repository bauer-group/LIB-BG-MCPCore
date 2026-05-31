"""Composable settings field groups.

Each mixin is a plain pydantic ``BaseModel`` carrying one cross-cutting field
group. ``BaseMcpSettings`` composes them; a server can also pick individual
mixins if it wants a bespoke base. The field definitions are lifted verbatim
from the two servers (identical there).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, SecretStr

from .enums import Environment


class GeneralSettingsMixin(BaseModel):
    environment: Environment = Environment.PRODUCTION
    public_base_url: HttpUrl = Field(
        default="http://localhost:8000",  # type: ignore[assignment]  # coerced by pydantic
        description="Public origin used in OAuth redirect URIs - MUST match IdP registration",
    )
    log_format: Literal["console", "json"] = "json"
    log_level: str = "INFO"


class McpTransportMixin(BaseModel):
    mcp_transport: Literal["streamable-http", "stdio"] = "streamable-http"
    # Empty = bind to any stack, any interface (dual-stack). Pin explicitly to
    # "0.0.0.0" / "::" / "127.0.0.1" / "::1".
    mcp_host: str = ""
    mcp_port: int = Field(default=8000, ge=1, le=65535)


class McpIdentityMixin(BaseModel):
    # No shared default: each server MUST set its own display name so two
    # deployments never both render "BAUER GROUP" on the consent screen.
    mcp_display_name: str = Field(
        description="Friendly name shown on the OAuth consent screen."
    )
    mcp_icon_url: str | None = Field(
        default=None,
        description="Absolute URL to the consent-screen icon. Unset -> ${PUBLIC_BASE_URL}/logo.svg.",
    )
    mcp_website_url: str | None = Field(
        default="https://go.bauer-group.com/mcp-server",
        description="Website link behind the server name on the consent screen.",
    )


class AuthPersistenceMixin(BaseModel):
    auth_jwt_signing_key: SecretStr = Field(
        default=SecretStr(""),
        description="32-byte hex key used to sign FastMCP-issued JWTs.",
    )
    auth_redis_url: str | None = None
    auth_storage_encryption_key: SecretStr | None = None
    auth_disk_storage_path: str = Field(
        default="/app/data/oauth-storage",
        description="Filesystem path for the encrypted OAuth state store when AUTH_REDIS_URL is unset.",
    )


class OidcSettingsMixin(BaseModel):
    oidc_discovery_url: str | None = None
    oidc_issuer: str | None = None
    oidc_auth_uri: str | None = None
    oidc_token_uri: str | None = None
    oidc_jwks_uri: str | None = None
    oidc_userinfo_uri: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_scopes: str = "openid profile email"
    oidc_username_claim: str = "preferred_username"


class RateLimiterMixin(BaseModel):
    rate_limiter_enabled: bool = True
    rate_limiter_max_requests_per_second: float = Field(
        default=10.0, gt=0.0, description="Sustained throughput per client."
    )
    rate_limiter_burst_capacity: int | None = Field(
        default=None, ge=1, description="Max burst per client. None -> 2x sustained rate."
    )
    rate_limiter_global: bool = Field(
        default=False, description="If true, one bucket for the whole server (DoS shield)."
    )
    rate_limiter_trusted_proxy_hops: int = Field(
        default=1,
        ge=0,
        le=10,
        description="Trusted reverse-proxy hops in front of this server (for X-Forwarded-For).",
    )


class ObservabilityMixin(BaseModel):
    sentry_dsn: str | None = None
    sentry_environment: str | None = None
    sentry_traces_sample_rate: float = Field(default=0.05, ge=0.0, le=1.0)


__all__ = [
    "AuthPersistenceMixin",
    "GeneralSettingsMixin",
    "McpIdentityMixin",
    "McpTransportMixin",
    "ObservabilityMixin",
    "OidcSettingsMixin",
    "RateLimiterMixin",
]
