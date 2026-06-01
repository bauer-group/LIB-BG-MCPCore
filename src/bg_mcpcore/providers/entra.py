"""Microsoft Entra ID inbound provider ([oauth-providers] extra).

Both single- and multi-tenant use FastMCP's AzureProvider. Multi-tenant requires
a post-issuance allowlist check on the `tid` claim (see middleware.py), wired
config-driven via the bg_mcpcore.auth_middleware entry point. Ported from
bg-shlink-mcp; typed against the EntraSettings protocol.
"""

from __future__ import annotations

from typing import Any

from ..observability import get_logger
from .protocols import EntraSettings

logger = get_logger("bg-mcpcore.auth.entra")

# OIDC scopes are requested during authorization (so the consent screen lists
# them) but never appear in the access token's scp claim - hence not validatable.
_OIDC_AUTHORIZE_SCOPES: tuple[str, ...] = ("openid", "profile", "email")


def build_entra_provider(settings: EntraSettings) -> Any:
    """Return a configured AzureProvider (entry point: entra-single / entra-multi)."""
    from fastmcp.server.auth.providers.azure import AzureProvider

    from ..auth.storage import build_client_storage

    if not settings.entra_client_id or not settings.entra_client_secret or not settings.entra_tenant_id:
        raise ValueError("Entra provider requires client_id, client_secret, tenant_id")

    api_scopes = list(settings.entra_api_scopes)
    if not api_scopes:
        raise ValueError(
            "entra_api_scopes must contain at least one custom API scope (e.g. "
            "'access_as_user') exposed under 'Expose an API' in the app registration"
        )

    additional_authorize_scopes = list(_OIDC_AUTHORIZE_SCOPES) + list(settings.entra_extra_scopes)
    tenant_id = settings.entra_tenant_id

    if str(settings.auth_mode) == "entra-multi" and tenant_id not in (
        "common",
        "organizations",
        "consumers",
    ):
        logger.warning(
            "auth.entra_multi_with_specific_tenant",
            tenant_id=tenant_id,
            hint="set ENTRA_TENANT_ID=organizations or common for true multi-tenant",
        )

    provider = AzureProvider(
        client_id=settings.entra_client_id,
        client_secret=settings.entra_client_secret.get_secret_value(),
        tenant_id=tenant_id,
        base_url=str(settings.public_base_url),
        required_scopes=api_scopes,
        additional_authorize_scopes=additional_authorize_scopes,
        client_storage=build_client_storage(settings),
        jwt_signing_key=settings.auth_jwt_signing_key.get_secret_value(),
    )
    logger.info(
        "auth.entra_configured",
        mode=str(settings.auth_mode),
        tenant_id=tenant_id,
        allowed_tenants=settings.entra_allowed_tenants or None,
        api_scopes=api_scopes,
    )
    return provider


def is_tenant_allowed(token_claims: dict[str, Any], allowed_tenants: list[str]) -> bool:
    """True if the allowlist is empty, or the token's `tid` is on it."""
    if not allowed_tenants:
        return True
    tid = token_claims.get("tid") or token_claims.get("tenant_id")
    if not tid:
        return False
    return tid in allowed_tenants


__all__ = ["build_entra_provider", "is_tenant_allowed"]
