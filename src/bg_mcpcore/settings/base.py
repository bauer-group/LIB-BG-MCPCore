"""``BaseMcpSettings`` — the composed, cross-cutting settings base.

Servers subclass this, add their backend block (e.g. ``zammad_url`` /
``shlink_api_key``), narrow ``auth_mode`` to their own StrEnum, and implement
``validate_provider_auth`` for per-mode credential checks. The fail-closed
persistence invariants run in core FIRST and cannot be relaxed by a subclass.

No ``env_prefix`` is configured: env var names map 1:1 to snake_case field
names (PUBLIC_BASE_URL -> public_base_url). Backend fields therefore stay on the
subclass; they must not live on this shared base.
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .enums import Environment
from .helpers import validate_persistence
from .mixins import (
    AuthPersistenceMixin,
    GeneralSettingsMixin,
    McpIdentityMixin,
    McpTransportMixin,
    ObservabilityMixin,
    OidcSettingsMixin,
    RateLimiterMixin,
)


class BaseMcpSettings(
    GeneralSettingsMixin,
    McpTransportMixin,
    McpIdentityMixin,
    AuthPersistenceMixin,
    OidcSettingsMixin,
    RateLimiterMixin,
    ObservabilityMixin,
    BaseSettings,
):
    """Cross-cutting settings shared by every REST-API MCP server."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Generic discriminator. Subclasses narrow this to their own StrEnum (whose
    # members compare equal to these strings). Core only needs to recognise
    # "none"; the auth-provider registry (Phase 3) rejects unknown modes.
    auth_mode: str = "none"

    def validate_provider_auth(self) -> None:
        """Hook: subclasses enforce per-mode credential requirements here.

        Called AFTER the universal fail-closed invariants. Default is a no-op.
        """

    @model_validator(mode="after")
    def _validate(self) -> BaseMcpSettings:
        # Non-negotiable invariants first (cannot be skipped by a subclass)...
        validate_persistence(self)
        # ...then provider-specific checks the subclass owns.
        self.validate_provider_auth()
        return self

    @property
    def is_development(self) -> bool:
        return self.environment is Environment.DEVELOPMENT


__all__ = ["BaseMcpSettings"]
