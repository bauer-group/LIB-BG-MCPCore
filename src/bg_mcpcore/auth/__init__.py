"""Auth building blocks shared across servers.

Inbound provider modes (none/oidc here; entra/google in the [oauth-providers]
extra) and outbound resolvers are registered via entry points in Phase 3.
"""

from __future__ import annotations

from .client_credentials import (
    ClientCredentialsError,
    ClientCredentialsResolver,
    build_client_credentials_resolver,
)
from .generic_oidc import OIDCDiscoveryError, build_generic_oidc_provider, discover_endpoints
from .obo import (
    EntraOboResolver,
    MissingUpstreamToken,
    PerUserTokenResolver,
    build_entra_obo_resolver,
    build_per_user_resolver,
)
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
    "ClientCredentialsError",
    "ClientCredentialsResolver",
    "EntraOboResolver",
    "MissingUpstreamToken",
    "NoAuthResolver",
    "OIDCDiscoveryError",
    "PerUserTokenResolver",
    "StaticHeaderResolver",
    "build_client_credentials_resolver",
    "build_client_storage",
    "build_entra_obo_resolver",
    "build_generic_oidc_provider",
    "build_per_user_resolver",
    "discover_endpoints",
]
