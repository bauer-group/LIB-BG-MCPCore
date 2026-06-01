"""Tenant-allowlist middleware for AUTH_MODE=entra-multi ([oauth-providers] extra).

AzureProvider validates JWT signatures against Microsoft's multi-tenant JWKS but
does NOT check WHICH tenant issued the token. This middleware gates the `tid`
claim against the allowlist. Wired config-driven via the bg_mcpcore.auth_middleware
entry point (build_tenant_middleware), so the core assembler adds it automatically
when AUTH_MODE=entra-multi and entra_allowed_tenants is set - no per-server wiring.
"""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from ..observability import get_logger
from .entra import is_tenant_allowed

logger = get_logger("bg-mcpcore.auth.tenant")


class TenantNotAllowedError(PermissionError):
    """Raised when a request's token tenant is not on the allowlist."""


class TenantAllowlistMiddleware(Middleware):
    """Enforce the Entra tenant allowlist on every authenticated request."""

    def __init__(self, allowed_tenants: list[str], *, audit_only: bool = False) -> None:
        self._allowed_tenants = list(allowed_tenants)
        self._audit_only = audit_only

    async def on_request(
        self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]
    ) -> Any:
        from fastmcp.server.dependencies import get_access_token

        token = get_access_token()
        if token is None:
            return await call_next(context)
        if is_tenant_allowed(token.claims, self._allowed_tenants):
            return await call_next(context)
        return await self._handle_disallowed(token.claims, context, call_next)

    async def _handle_disallowed(
        self,
        claims: dict[str, Any],
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        # Log payload omits full claims to keep PII out of logs - only tid + sub +
        # method, enough to correlate.
        tid = claims.get("tid")
        log_kwargs = {
            "tid": tid,
            "sub": claims.get("sub"),
            "method": context.method,
            "allowed_tenants": self._allowed_tenants,
        }
        if self._audit_only:
            logger.warning("auth.tenant_denied_audit_only_passing_through", **log_kwargs)
            return await call_next(context)
        logger.warning("auth.tenant_denied", **log_kwargs)
        raise TenantNotAllowedError(f"Tenant {tid!r} is not on the allowlist for this MCP server")


def build_tenant_middleware(settings: Any) -> Middleware | None:
    """Entry-point factory (bg_mcpcore.auth_middleware: entra-multi).

    Returns the middleware when entra_allowed_tenants is non-empty, else None
    ("intentionally any tenant" - single-tenant or first-party apps).
    """
    allowed = list(getattr(settings, "entra_allowed_tenants", []) or [])
    if not allowed:
        return None
    return TenantAllowlistMiddleware(allowed_tenants=allowed)


__all__ = ["TenantAllowlistMiddleware", "TenantNotAllowedError", "build_tenant_middleware"]
