"""Structural settings protocols for the cloud-IdP providers.

These describe the entra_* / google_* fields a server adds on its own Settings
subclass (they are NOT on BaseMcpSettings). A server's Settings satisfies them
structurally; the providers never import a concrete Settings.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import HttpUrl, SecretStr

from .._config_protocols import StorageSettings


class EntraSettings(StorageSettings, Protocol):
    public_base_url: HttpUrl
    auth_mode: str
    entra_client_id: str | None
    entra_client_secret: SecretStr | None
    entra_tenant_id: str | None
    entra_api_scopes: list[str]
    entra_extra_scopes: list[str]
    entra_allowed_tenants: list[str]


class GoogleSettings(StorageSettings, Protocol):
    public_base_url: HttpUrl
    google_client_id: str | None
    google_client_secret: SecretStr | None
    google_allowed_domains: list[str]
