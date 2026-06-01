"""Cloud-IdP inbound providers ([oauth-providers] extra): Entra + Google.

FastMCP ships AzureProvider/GoogleProvider, so this extra has no extra deps - it
groups the wrappers + the tenant-allowlist middleware, registered via the
bg_mcpcore.auth_providers / bg_mcpcore.auth_middleware entry points.
"""

from __future__ import annotations

from .entra import build_entra_provider, is_tenant_allowed
from .google import build_google_provider
from .middleware import TenantAllowlistMiddleware, TenantNotAllowedError, build_tenant_middleware

__all__ = [
    "TenantAllowlistMiddleware",
    "TenantNotAllowedError",
    "build_entra_provider",
    "build_google_provider",
    "build_tenant_middleware",
    "is_tenant_allowed",
]
