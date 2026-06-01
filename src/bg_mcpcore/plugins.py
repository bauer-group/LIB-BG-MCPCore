"""Plugin registries — entry-point discovery + core built-ins.

Three pluggable seams, each a Python entry-point group so new capabilities are
pip-installable without touching core:

* ``bg_mcpcore.auth_providers``  - inbound IdP modes  (built-in: none, oidc)
* ``bg_mcpcore.auth_resolvers``  - outbound auth      (built-in: none,
  static_header, bearer_env, python)
* ``bg_mcpcore.tool_sources``    - tool generation    (built-in: python, registry)

``build_auth_provider`` enforces a CLOSED set (security guardrail #1): an unknown
AUTH_MODE raises rather than silently booting unauthenticated.
"""

from __future__ import annotations

import importlib
import inspect
import os
from collections.abc import Callable, Mapping
from importlib.metadata import EntryPoint, entry_points
from typing import TYPE_CHECKING, Any

from .auth.generic_oidc import build_generic_oidc_provider
from .auth.resolvers import (
    AuthHeaderSource,
    BearerEnvResolver,
    NoAuthResolver,
    StaticHeaderResolver,
)
from .observability import get_logger
from .profile.loader import ProfileError
from .profile.models import OutboundAuthConfig, ToolsConfig
from .tools.protocol import ToolContext

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger("bg-mcpcore.plugins")


def _import_attr(dotted: str) -> Any:
    """Import 'module.path:attr' (or 'module.path.attr') -> the attribute."""
    if ":" in dotted:
        module_name, _, attr = dotted.partition(":")
    else:
        module_name, _, attr = dotted.rpartition(".")
    if not module_name or not attr:
        raise ProfileError(f"Invalid dotted path '{dotted}' (expected 'module.path:attr')")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ProfileError(f"Cannot import '{module_name}' for '{dotted}': {exc}") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ProfileError(f"'{module_name}' has no attribute '{attr}'") from exc


def _discover(group: str) -> dict[str, EntryPoint]:
    return {ep.name: ep for ep in entry_points(group=group)}


# ── Inbound auth providers ───────────────────────────────────────────────────

# Builders take (settings, inbound): cross-cutting/secret values come from
# settings; provider-specific params come from the profile's auth.inbound.config
# (used by the spec-driven providers; the built-ins read settings and ignore it).
def _no_auth(_settings: Any, _inbound: Any) -> None:
    return None


_BUILTIN_AUTH_PROVIDERS: dict[str, Callable[[Any, Any], Any]] = {
    "none": _no_auth,
    "oidc": build_generic_oidc_provider,
}


def build_auth_provider(settings: Any, inbound: Any | None = None) -> Any:
    """Build the inbound auth provider for ``settings.auth_mode`` (None for 'none').

    ``inbound`` is the profile's ``auth.inbound`` (carrying provider config for the
    spec-driven IdPs). Raises ProfileError on an unknown mode - the closed set.
    """
    mode = str(settings.auth_mode)
    if mode in _BUILTIN_AUTH_PROVIDERS:
        return _BUILTIN_AUTH_PROVIDERS[mode](settings, inbound)
    eps = _discover("bg_mcpcore.auth_providers")
    if mode in eps:
        return eps[mode].load()(settings, inbound)
    known = sorted(set(_BUILTIN_AUTH_PROVIDERS) | set(eps))
    raise ProfileError(f"Unknown AUTH_MODE '{mode}'. Known modes: {', '.join(known)}")


def build_auth_middleware(settings: Any) -> list[Any]:
    """Optional post-auth middleware for the active mode (e.g. Entra tenant gate).

    Discovered via the bg_mcpcore.auth_middleware entry-point group; a factory
    returns a middleware or None. Config-driven, so the core assembler adds it
    without per-server wiring. Unknown modes simply contribute nothing.
    """
    mode = str(settings.auth_mode)
    eps = _discover("bg_mcpcore.auth_middleware")
    out: list[Any] = []
    if mode in eps:
        middleware = eps[mode].load()(settings)
        if middleware is not None:
            out.append(middleware)
    return out


# ── Outbound auth resolvers ──────────────────────────────────────────────────


def _read_secret(cfg: OutboundAuthConfig, env: Mapping[str, str]) -> str:
    if cfg.value_from_env:
        value = env.get(cfg.value_from_env)
        if value is None:
            raise ProfileError(
                f"Outbound auth needs env var {cfg.value_from_env}, but it is not set"
            )
        return value
    if cfg.value is not None:
        return cfg.value
    raise ProfileError(f"Outbound auth type '{cfg.type}' requires value_from_env or value")


def build_outbound_resolver(
    cfg: OutboundAuthConfig, *, env: Mapping[str, str] | None = None
) -> AuthHeaderSource:
    """Build the outbound auth resolver declared by a profile's auth.outbound."""
    if env is None:
        env = os.environ
    kind = cfg.type
    if kind == "none":
        return NoAuthResolver()
    if kind == "static_header":
        if not cfg.header:
            raise ProfileError("Outbound auth 'static_header' requires 'header'")
        return StaticHeaderResolver(cfg.header, _read_secret(cfg, env))
    if kind == "bearer_env":
        return BearerEnvResolver(_read_secret(cfg, env))
    if kind == "python":
        if not cfg.resolver:
            raise ProfileError("Outbound auth 'python' requires 'resolver' (dotted module:attr)")
        resolver = _import_attr(cfg.resolver)(cfg)
        return resolver  # type: ignore[no-any-return]
    eps = _discover("bg_mcpcore.auth_resolvers")
    if kind in eps:
        return eps[kind].load()(cfg)  # type: ignore[no-any-return]
    known = ["none", "static_header", "bearer_env", "python", *sorted(eps)]
    raise ProfileError(f"Unknown outbound auth type '{kind}'. Known: {', '.join(known)}")


# ── Tool sources ─────────────────────────────────────────────────────────────


class _PythonToolProvider:
    """Escape hatch: register the server's own hand-written tools via a dotted path."""

    def __init__(self, dotted: str | None) -> None:
        if not dotted:
            raise ProfileError("tools.source 'python' requires 'register' (dotted module:attr)")
        self._dotted = dotted

    async def register(self, mcp: FastMCP, ctx: ToolContext) -> int:
        fn = _import_attr(self._dotted)
        result = fn(mcp, ctx)
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, int) else 0


class _RegistryToolProvider:
    """Mount named, reusable tools from the central registry onto the server."""

    def __init__(self, include: list[str]) -> None:
        self._include = include

    async def register(self, mcp: FastMCP, ctx: ToolContext) -> int:
        from .tools.registry import get_tool

        for name in self._include:
            get_tool(name)(mcp, ctx)
        return len(self._include)


def build_tool_provider(cfg: ToolsConfig) -> Any:
    """Build a tool provider (ToolProvider or ConstructingToolProvider) for a source."""
    source = cfg.source
    if source == "python":
        return _PythonToolProvider(cfg.register_target)
    if source == "registry":
        return _RegistryToolProvider(cfg.include)
    eps = _discover("bg_mcpcore.tool_sources")
    if source in eps:
        return eps[source].load()(cfg)
    known = ["python", "registry", *sorted(eps)]
    raise ProfileError(f"Unknown tools.source '{source}'. Known: {', '.join(known)}")


__all__ = [
    "build_auth_middleware",
    "build_auth_provider",
    "build_outbound_resolver",
    "build_tool_provider",
]
