"""Structural settings protocols.

Core infra functions read only the attributes they need from a settings object
— never the whole settings (least privilege, security guardrail #4). These
Protocols describe those minimal capability surfaces. ``BaseMcpSettings`` (Phase
2) and the per-server subclasses satisfy them structurally; nothing in core
imports a concrete ``Settings`` class.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import HttpUrl, SecretStr


class RateLimitSettings(Protocol):
    """Attributes the rate-limit middleware factory reads."""

    rate_limiter_enabled: bool
    rate_limiter_max_requests_per_second: float
    rate_limiter_burst_capacity: int | None
    rate_limiter_global: bool
    rate_limiter_trusted_proxy_hops: int


class StorageSettings(Protocol):
    """Attributes the encrypted OAuth-state store factory reads."""

    auth_redis_url: str | None
    auth_storage_encryption_key: SecretStr | None
    auth_jwt_signing_key: SecretStr
    auth_disk_storage_path: str


class OidcSettings(StorageSettings, Protocol):
    """Attributes the generic OIDC provider builder reads (incl. storage)."""

    public_base_url: HttpUrl
    oidc_client_id: str | None
    oidc_client_secret: SecretStr | None
    oidc_scopes: str
    oidc_discovery_url: str | None
    oidc_issuer: str | None
    oidc_auth_uri: str | None
    oidc_token_uri: str | None
    oidc_jwks_uri: str | None


class PersistenceSettings(Protocol):
    """Attributes the shared fail-closed persistence validator reads.

    Read-only properties (not plain attributes) so a concrete settings class
    whose ``environment`` / ``auth_mode`` are StrEnum subtypes still satisfies
    the protocol (covariant read).
    """

    @property
    def environment(self) -> str: ...
    @property
    def auth_mode(self) -> str: ...
    @property
    def auth_jwt_signing_key(self) -> SecretStr: ...
    @property
    def auth_redis_url(self) -> str | None: ...
    @property
    def auth_storage_encryption_key(self) -> SecretStr | None: ...
