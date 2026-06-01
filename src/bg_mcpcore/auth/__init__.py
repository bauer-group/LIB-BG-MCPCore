"""Auth building blocks shared across servers.

Inbound provider modes (none/oidc here; entra/google in the [oauth-providers]
extra) and outbound resolvers are registered via entry points in Phase 3.
"""

from __future__ import annotations

from .generic_oidc import OIDCDiscoveryError, build_generic_oidc_provider, discover_endpoints
from .resolvers import (
    AuthHeaderSource,
    BearerEnvResolver,
    NoAuthResolver,
    StaticHeaderResolver,
)
from .storage import build_client_storage

__all__ = [
    "AuthHeaderSource",
    "BearerEnvResolver",
    "NoAuthResolver",
    "OIDCDiscoveryError",
    "StaticHeaderResolver",
    "build_client_storage",
    "build_generic_oidc_provider",
    "discover_endpoints",
]
