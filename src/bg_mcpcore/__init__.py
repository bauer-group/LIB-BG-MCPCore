"""BAUER GROUP MCP Core — config-driven, pluggable REST-API MCP servers on FastMCP.

A shared framework for building secure, OAuth-gated MCP servers that bridge REST
APIs. Standard servers are described by a declarative JSON profile (config for
the 80 % both ZAMMAD and Shlink agree on); complex behaviour drops down to Python
escape hatches (the divergent 20 % — Zammad's per-user OBO, hand-written tools).

Design pillars:
    * Modular  — new auth modes / tool sources / resolvers are pip-installable
      plugins registered via Python entry points, never core edits.
    * Configurable — every standard behaviour is an overridable profile default.
    * Stable — the mandatory core depends only on fastmcp/pydantic/httpx/
      structlog/cryptography; volatile concerns live in optional extras.
    * Secure — fail-closed auth invariants are enforced in core and cannot be
      switched off by a profile.

The public API is re-exported here but resolved LAZILY (PEP 562 ``__getattr__``):
``import bg_mcpcore`` does not eagerly pull in fastmcp + every extra just to read
``__version__`` or load the [testkit] pytest plugin. ``from bg_mcpcore import X``
imports only X's submodule on first access.

MIT License — Copyright (c) 2026 BAUER GROUP.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

__version__ = "1.5.0"
__author__ = "BAUER GROUP"
__email__ = "info@bauer-group.com"

# Public name -> the submodule that exports it. Lazily resolved on first access.
_LAZY: dict[str, str] = {
    "build_app_from_profile": "app",
    "build_gateway": "gateway",
    "make_cli": "cli",
    "UpstreamClient": "http",
    "Profile": "profile",
    "ProfileError": "profile",
    "load_profile": "profile",
    "OIDCDiscoveryError": "auth",
    "build_client_storage": "auth",
    "build_generic_oidc_provider": "auth",
    "discover_endpoints": "auth",
    "AuthHeaderSource": "auth",
    "BearerEnvResolver": "auth",
    "NoAuthResolver": "auth",
    "StaticHeaderResolver": "auth",
    "MissingUpstreamToken": "auth",
    "PerUserTokenResolver": "auth",
    "build_per_user_resolver": "auth",
    "get_logger": "observability",
    "init_sentry": "observability",
    "now_iso": "observability",
    "print_banner": "observability",
    "setup_logging": "observability",
    "warn_no_auth": "observability",
    "warn_role_audit_only": "observability",
    "build_auth_provider": "plugins",
    "build_outbound_resolver": "plugins",
    "build_tool_provider": "plugins",
    "build_rate_limit_middleware": "server",
    "patch_dual_stack_socket": "server",
    "register_healthz_route": "server",
    "register_index_route": "server",
    "register_logo_route": "server",
    "resolve_client_id": "server",
    "run_transport": "server",
    "BaseMcpSettings": "settings",
    "Environment": "settings",
    "get_settings": "settings",
    "has_value": "settings",
    "split_csv": "settings",
    "validate_fernet_key": "settings",
    "validate_persistence": "settings",
    "ConstructingToolProvider": "tools",
    "ToolContext": "tools",
    "ToolProvider": "tools",
    "UpstreamError": "tools",
    "available_tools": "tools",
    "register_tool": "tools",
}


def __getattr__(name: str) -> object:
    submodule = _LAZY.get(name)
    if submodule is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(f"{__name__}.{submodule}"), name)
    globals()[name] = value  # cache: __getattr__ runs at most once per name
    return value


def __dir__() -> list[str]:
    return sorted(__all__)


if TYPE_CHECKING:  # precise types for consumers + IDEs; not executed at runtime
    from .app import build_app_from_profile as build_app_from_profile
    from .auth import (
        AuthHeaderSource as AuthHeaderSource,
    )
    from .auth import (
        BearerEnvResolver as BearerEnvResolver,
    )
    from .auth import (
        MissingUpstreamToken as MissingUpstreamToken,
    )
    from .auth import (
        NoAuthResolver as NoAuthResolver,
    )
    from .auth import (
        OIDCDiscoveryError as OIDCDiscoveryError,
    )
    from .auth import (
        PerUserTokenResolver as PerUserTokenResolver,
    )
    from .auth import (
        StaticHeaderResolver as StaticHeaderResolver,
    )
    from .auth import (
        build_client_storage as build_client_storage,
    )
    from .auth import (
        build_generic_oidc_provider as build_generic_oidc_provider,
    )
    from .auth import (
        build_per_user_resolver as build_per_user_resolver,
    )
    from .auth import (
        discover_endpoints as discover_endpoints,
    )
    from .cli import make_cli as make_cli
    from .gateway import build_gateway as build_gateway
    from .http import UpstreamClient as UpstreamClient
    from .observability import (
        get_logger as get_logger,
    )
    from .observability import (
        init_sentry as init_sentry,
    )
    from .observability import (
        now_iso as now_iso,
    )
    from .observability import (
        print_banner as print_banner,
    )
    from .observability import (
        setup_logging as setup_logging,
    )
    from .observability import (
        warn_no_auth as warn_no_auth,
    )
    from .observability import (
        warn_role_audit_only as warn_role_audit_only,
    )
    from .plugins import (
        build_auth_provider as build_auth_provider,
    )
    from .plugins import (
        build_outbound_resolver as build_outbound_resolver,
    )
    from .plugins import (
        build_tool_provider as build_tool_provider,
    )
    from .profile import (
        Profile as Profile,
    )
    from .profile import (
        ProfileError as ProfileError,
    )
    from .profile import (
        load_profile as load_profile,
    )
    from .server import (
        build_rate_limit_middleware as build_rate_limit_middleware,
    )
    from .server import (
        patch_dual_stack_socket as patch_dual_stack_socket,
    )
    from .server import (
        register_healthz_route as register_healthz_route,
    )
    from .server import (
        register_index_route as register_index_route,
    )
    from .server import (
        register_logo_route as register_logo_route,
    )
    from .server import (
        resolve_client_id as resolve_client_id,
    )
    from .server import (
        run_transport as run_transport,
    )
    from .settings import (
        BaseMcpSettings as BaseMcpSettings,
    )
    from .settings import (
        Environment as Environment,
    )
    from .settings import (
        get_settings as get_settings,
    )
    from .settings import (
        has_value as has_value,
    )
    from .settings import (
        split_csv as split_csv,
    )
    from .settings import (
        validate_fernet_key as validate_fernet_key,
    )
    from .settings import (
        validate_persistence as validate_persistence,
    )
    from .tools import (
        ConstructingToolProvider as ConstructingToolProvider,
    )
    from .tools import (
        ToolContext as ToolContext,
    )
    from .tools import (
        ToolProvider as ToolProvider,
    )
    from .tools import (
        UpstreamError as UpstreamError,
    )
    from .tools import (
        available_tools as available_tools,
    )
    from .tools import (
        register_tool as register_tool,
    )

__all__ = [
    "AuthHeaderSource",
    "BaseMcpSettings",
    "BearerEnvResolver",
    "ConstructingToolProvider",
    "Environment",
    "MissingUpstreamToken",
    "NoAuthResolver",
    "OIDCDiscoveryError",
    "PerUserTokenResolver",
    "Profile",
    "ProfileError",
    "StaticHeaderResolver",
    "ToolContext",
    "ToolProvider",
    "UpstreamClient",
    "UpstreamError",
    "__version__",
    "available_tools",
    "build_app_from_profile",
    "build_auth_provider",
    "build_client_storage",
    "build_gateway",
    "build_generic_oidc_provider",
    "build_outbound_resolver",
    "build_per_user_resolver",
    "build_rate_limit_middleware",
    "build_tool_provider",
    "discover_endpoints",
    "get_logger",
    "get_settings",
    "has_value",
    "init_sentry",
    "load_profile",
    "make_cli",
    "now_iso",
    "patch_dual_stack_socket",
    "print_banner",
    "register_healthz_route",
    "register_index_route",
    "register_logo_route",
    "register_tool",
    "resolve_client_id",
    "run_transport",
    "setup_logging",
    "split_csv",
    "validate_fernet_key",
    "validate_persistence",
    "warn_no_auth",
    "warn_role_audit_only",
]
