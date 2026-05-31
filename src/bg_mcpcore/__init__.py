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

The public surface grows per implementation phase. Phase 1 exposes the lifted
infrastructure (logging, banner, sentry, rate limiting, operational routes,
transport runner, encrypted OAuth-state storage, generic OIDC). The profile
engine (load_profile / build_app_from_profile / make_cli) and BaseMcpSettings
arrive in Phases 2-3.

MIT License — Copyright (c) 2026 BAUER GROUP.
"""

from __future__ import annotations

from .app import build_app_from_profile
from .auth import (
    OIDCDiscoveryError,
    build_client_storage,
    build_generic_oidc_provider,
    discover_endpoints,
)
from .auth.resolvers import (
    AuthHeaderSource,
    BearerEnvResolver,
    NoAuthResolver,
    StaticHeaderResolver,
)
from .cli import make_cli
from .http import UpstreamClient
from .observability import (
    get_logger,
    init_sentry,
    now_iso,
    print_banner,
    setup_logging,
    warn_no_auth,
    warn_role_audit_only,
)
from .plugins import build_auth_provider, build_outbound_resolver, build_tool_provider
from .profile import Profile, ProfileError, load_profile
from .server import (
    build_rate_limit_middleware,
    patch_dual_stack_socket,
    register_healthz_route,
    register_index_route,
    register_logo_route,
    resolve_client_id,
    run_transport,
)
from .settings import (
    BaseMcpSettings,
    Environment,
    get_settings,
    has_value,
    split_csv,
    validate_fernet_key,
    validate_persistence,
)
from .tools import (
    ConstructingToolProvider,
    ToolContext,
    ToolProvider,
    available_tools,
    register_tool,
)

__version__ = "0.1.0"
__author__ = "BAUER GROUP"
__email__ = "info@bauer-group.com"

__all__ = [
    "AuthHeaderSource",
    "BaseMcpSettings",
    "BearerEnvResolver",
    "ConstructingToolProvider",
    "Environment",
    "NoAuthResolver",
    "OIDCDiscoveryError",
    "Profile",
    "ProfileError",
    "StaticHeaderResolver",
    "ToolContext",
    "ToolProvider",
    "UpstreamClient",
    "__version__",
    "available_tools",
    "build_app_from_profile",
    "build_auth_provider",
    "build_client_storage",
    "build_generic_oidc_provider",
    "build_outbound_resolver",
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
