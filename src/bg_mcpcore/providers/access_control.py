"""Declarative role/claim access gate (the profile ``access_control`` block).

A coarse allowlist on every authenticated request: compare the roles in the
verified token against ``MCP_ALLOWED_ROLES`` and reject (or, in audit-only mode,
log + pass) a request whose roles don't match. Generalised from bg-zammad-mcp's
role middleware; the claim name is configurable (``roles_claim``) so it fits any
IdP that attaches roles to the access token.

Trust + semantics:

* Roles come from the verified token's claims — NOT from anything the MCP client
  supplies, so a client cannot self-elevate.
* **Claim absent → pass.** If the token has no ``roles_claim`` at all (an auth
  mode that carries no role info), the gate defers to the upstream's own
  authorization. It is therefore a no-op in such modes — enforcement only kicks
  in where roles are actually present.
* **Claim present, no overlap → deny** (or audit-log + pass).
* **Empty allowlist → disabled** (any authenticated user is accepted).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from ..observability import get_logger

if TYPE_CHECKING:
    from ..profile.models import AccessControlConfig

logger = get_logger("bg-mcpcore.auth.access_control")


class RoleNotAllowedError(PermissionError):
    """Raised when a request's user roles are not on the allowlist.

    PermissionError so MCP clients see an authz failure; FastMCP serialises the
    raised exception's class name into the JSON-RPC error payload.
    """


def _extract_role_names(raw: Any) -> set[str]:
    """Role names from a claim value: a list of strings or of ``{"name": ...}``.

    Returned lowercased for case-insensitive matching (IdPs use "Admin"; env
    allowlists often use "admin").
    """
    out: set[str] = set()
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.add(item.strip().lower())
            elif isinstance(item, dict):
                name = item.get("name")
                if isinstance(name, str) and name.strip():
                    out.add(name.strip().lower())
    return out


class RoleAllowlistMiddleware(Middleware):
    """Enforce an allowlist of roles (read from ``roles_claim``) on every request."""

    def __init__(
        self,
        *,
        allowed_roles: list[str],
        roles_claim: str = "roles",
        audit_only: bool = False,
    ) -> None:
        self._allowed = {r.strip().lower() for r in allowed_roles if r.strip()}
        self._roles_claim = roles_claim
        self._audit_only = audit_only

    async def on_request(
        self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]
    ) -> Any:
        from fastmcp.server.dependencies import get_access_token

        token = get_access_token()
        # No token (the provider rejects unauthenticated calls first) or an empty
        # allowlist (gate disabled) → nothing to enforce.
        if token is None or not self._allowed:
            return await call_next(context)

        raw = token.claims.get(self._roles_claim)
        if raw is None:
            # Claim absent: this mode carries no roles — defer to the upstream.
            return await call_next(context)

        user_roles = _extract_role_names(raw)
        if user_roles & self._allowed:
            return await call_next(context)
        return await self._handle_disallowed(user_roles, token.claims, context, call_next)

    async def _handle_disallowed(
        self,
        user_roles: set[str],
        claims: dict[str, Any],
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        # Log sub + roles + method, never the full claims (no PII bleed).
        log_kwargs = {
            "sub": claims.get("sub"),
            "user_roles": sorted(user_roles),
            "allowed_roles": sorted(self._allowed),
            "method": context.method,
        }
        if self._audit_only:
            logger.warning("auth.role_denied_audit_only_passing_through", **log_kwargs)
            return await call_next(context)
        logger.warning("auth.role_denied", **log_kwargs)
        raise RoleNotAllowedError(
            f"User roles {sorted(user_roles)!r} are not on the allowlist "
            f"{sorted(self._allowed)!r} for this MCP server"
        )


def build_access_control_middleware(
    access_control: AccessControlConfig, settings: Any
) -> Middleware | None:
    """Build the gate from the profile block + settings allowlist (None if off).

    The allowlist + audit toggle come from settings (``MCP_ALLOWED_ROLES`` /
    ``MCP_ROLE_CHECK_AUDIT_ONLY``, env-tunable); the profile contributes only the
    ``roles_claim``. An empty allowlist disables the gate (warned at boot).
    """
    allowed = list(getattr(settings, "mcp_allowed_roles", []) or [])
    if not allowed:
        logger.warning(
            "auth.role_allowlist_disabled",
            note="MCP_ALLOWED_ROLES is empty - any authenticated user can call this MCP",
        )
        return None
    audit_only = bool(getattr(settings, "mcp_role_check_audit_only", False))
    logger.info(
        "auth.role_allowlist_active",
        allowed_roles=sorted({r.strip().lower() for r in allowed if r.strip()}),
        roles_claim=access_control.roles_claim,
        audit_only=audit_only,
    )
    return RoleAllowlistMiddleware(
        allowed_roles=allowed,
        roles_claim=access_control.roles_claim,
        audit_only=audit_only,
    )


__all__ = [
    "RoleAllowlistMiddleware",
    "RoleNotAllowedError",
    "build_access_control_middleware",
]
