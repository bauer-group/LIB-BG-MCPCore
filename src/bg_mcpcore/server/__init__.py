"""Server runtime: rate-limit middleware, operational routes, transport runner.

The ``build_app`` orchestrator + ``make_cli`` (which compose these) land in
Phase 3 with the profile engine.
"""

from __future__ import annotations

from .middleware import build_rate_limit_middleware, resolve_client_id
from .routes import register_healthz_route, register_index_route, register_logo_route
from .runner import patch_dual_stack_socket, run_transport

__all__ = [
    "build_rate_limit_middleware",
    "patch_dual_stack_socket",
    "register_healthz_route",
    "register_index_route",
    "register_logo_route",
    "resolve_client_id",
    "run_transport",
]
