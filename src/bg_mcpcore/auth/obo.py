"""Per-user on-behalf-of outbound auth — the ``per_user_token`` resolver.

Forwards the CALLER's upstream token to the backend per request, fail-closed —
the declarative form of bg-zammad-mcp's hand-written OBO resolver. The token is
resolved from the verified access-token claims first (cheapest, no I/O), then
from the OAuth-state storage keyed by the JWT ``jti`` / ``sub``. When no per-user
token can be found the resolver raises (no unauthenticated upstream call) —
unless a static fallback credential is configured, which it then applies
(logged). This single "per-user, else static, else fail-closed" policy replaces
mode-switching server code: in an auth mode that carries no per-user token, the
claim/storage lookup simply finds nothing and the static fallback takes over.

PER-CALL ONLY (security guardrail #3): ``default_headers`` is empty. The resolver
drives ``ctx.request`` / ``request_json``; an OpenAPI tool source uses the bare
httpx client (default headers), which cannot carry a per-user credential — OBO
needs a python / request-based tool surface.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..observability import get_logger
from ..profile.loader import ProfileError

logger = get_logger("bg-mcpcore.auth.obo")

# Claim names that may carry the upstream token directly on the issued JWT.
_DEFAULT_CLAIMS: tuple[str, ...] = ("upstream_access_token", "upstream_token")
# Storage-key prefixes FastMCP's OAuth proxy uses; "" = the bare jti/sub key.
_DEFAULT_KEY_PREFIXES: tuple[str, ...] = (
    "upstream_tokens/",
    "oauth_proxy/upstream_tokens/",
    "tokens/upstream/",
    "",
)


class MissingUpstreamToken(RuntimeError):
    """No per-user upstream token could be resolved for the current request."""


class PerUserTokenResolver:
    """Outbound ``AuthHeaderSource`` that forwards the caller's upstream token."""

    def __init__(
        self,
        *,
        header: str = "Authorization",
        scheme: str = "Bearer",
        claims: Sequence[str] = _DEFAULT_CLAIMS,
        key_prefixes: Sequence[str] = _DEFAULT_KEY_PREFIXES,
        static_fallback: str | None = None,
        static_fallback_template: str | None = None,
    ) -> None:
        self._header = header
        self._scheme = scheme
        self._claims = tuple(claims)
        self._key_prefixes = tuple(key_prefixes)
        self._static_fallback = static_fallback
        self._static_template = static_fallback_template

    def default_headers(self) -> dict[str, str]:
        # Per-call only — never bake a credential (the static fallback is applied
        # per request via auth_headers so a missing per-user token fails closed).
        return {}

    async def auth_headers(self, _ctx: Any) -> dict[str, str]:
        token = await self._resolve_per_user()
        if token:
            return {self._header: f"{self._scheme} {token}".strip()}
        if self._static_fallback is not None:
            logger.warning("auth.obo_missing_per_user_token_falling_back_to_static")
            return {self._header: self._format_static(self._static_fallback)}
        raise MissingUpstreamToken(
            "No per-user upstream token for this request and no static fallback "
            "configured (fail-closed)"
        )

    def _format_static(self, token: str) -> str:
        if self._static_template:
            return self._static_template.replace("{token}", token)
        return f"{self._scheme} {token}".strip()

    async def _resolve_per_user(self) -> str | None:
        from fastmcp.server.dependencies import get_access_token

        access_token = get_access_token()
        if access_token is None:
            return None
        claims = getattr(access_token, "claims", {}) or {}

        # Path 1: the token embedded directly in the JWT claims (no storage I/O).
        for name in self._claims:
            value = claims.get(name)
            if isinstance(value, str) and value:
                return value

        # Path 2/3: a storage round-trip keyed by jti, then sub.
        storage = _resolve_client_storage_from_context()
        if storage is None:
            return None
        for identifier in (claims.get("jti") or "", claims.get("sub") or ""):
            if not identifier:
                continue
            for prefix in self._key_prefixes:
                extracted = _extract_access_token(await _safe_get(storage, f"{prefix}{identifier}"))
                if extracted:
                    return extracted
        return None


def build_per_user_resolver(cfg: Any, env: Mapping[str, str]) -> PerUserTokenResolver:
    """Build the resolver from a profile ``auth.outbound`` (type per_user_token)."""
    extra = getattr(cfg, "model_extra", None) or {}
    header = cfg.header or "Authorization"
    scheme = extra.get("scheme", "Bearer")
    claims = extra.get("claims") or list(_DEFAULT_CLAIMS)
    key_prefixes = extra.get("storage_key_prefixes") or list(_DEFAULT_KEY_PREFIXES)
    if not isinstance(claims, list) or not all(isinstance(c, str) for c in claims):
        raise ProfileError("per_user_token 'claims' must be a list of strings")
    if not isinstance(key_prefixes, list) or not all(isinstance(p, str) for p in key_prefixes):
        raise ProfileError("per_user_token 'storage_key_prefixes' must be a list of strings")

    static_env = extra.get("static_fallback_env")
    static_token: str | None = None
    if static_env:
        static_token = env.get(static_env) or None
    return PerUserTokenResolver(
        header=header,
        scheme=scheme,
        claims=claims,
        key_prefixes=key_prefixes,
        static_fallback=static_token,
        static_fallback_template=extra.get("static_fallback_template"),
    )


# ── storage-from-context helpers (lifted from bg-zammad-mcp, generalised) ─────


def _resolve_client_storage_from_context() -> Any | None:
    """Best-effort: pull the OAuth-state store from FastMCP's bound context."""
    try:
        from fastmcp.server.dependencies import get_context

        context = get_context()
    except (ImportError, RuntimeError):
        return None
    if context is None:
        return None
    for attr_path in (
        ("request_context", "lifespan_context", "client_storage"),
        ("lifespan_context", "client_storage"),
        ("fastmcp", "auth", "client_storage"),
        ("auth", "client_storage"),
    ):
        node: Any = context
        for part in attr_path:
            node = _safe_attr(node, part)
            if node is None:
                break
        else:
            if node is not None:
                return node
    return None


def _safe_attr(node: Any, name: str) -> Any | None:
    if node is None:
        return None
    if isinstance(node, dict):
        return node.get(name)
    return getattr(node, name, None)


async def _safe_get(storage: Any, key: str) -> Any | None:
    try:
        return await storage.get(key)
    except Exception as exc:
        logger.debug("auth.obo_storage_lookup_failed", key=key, error=str(exc))
        return None


def _extract_access_token(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        for key in ("access_token", "upstream_access_token", "token", "value"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
    return None


__all__ = ["MissingUpstreamToken", "PerUserTokenResolver", "build_per_user_resolver"]
