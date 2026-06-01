"""Google Workspace inbound provider ([oauth-providers] extra).

GoogleProvider handles the `hd` hosted-domain allowlist itself. Ported from
bg-shlink-mcp; typed against the GoogleSettings protocol.
"""

from __future__ import annotations

from typing import Any

from ..observability import get_logger
from .protocols import GoogleSettings

logger = get_logger("bg-mcpcore.auth.google")


def build_google_provider(settings: GoogleSettings, inbound: Any | None = None) -> Any:
    """Return a configured GoogleProvider (entry point: google).

    Reads its config from ``settings`` (env-driven); ``inbound`` is accepted for
    the uniform builder contract but unused.
    """
    from fastmcp.server.auth.providers.google import GoogleProvider

    from ..auth.storage import build_client_storage

    if not settings.google_client_id or not settings.google_client_secret:
        raise ValueError("Google provider requires client_id + client_secret")

    kwargs: dict[str, Any] = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret.get_secret_value(),
        "base_url": str(settings.public_base_url),
        "required_scopes": ["openid", "email", "profile"],
        "client_storage": build_client_storage(settings),
        "jwt_signing_key": settings.auth_jwt_signing_key.get_secret_value(),
    }
    if settings.google_allowed_domains:
        kwargs["allowed_domains"] = settings.google_allowed_domains

    provider = GoogleProvider(**kwargs)
    logger.info("auth.google_configured", allowed_domains=settings.google_allowed_domains or None)
    return provider


__all__ = ["build_google_provider"]
