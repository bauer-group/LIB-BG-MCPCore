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

The public API is intentionally small. Higher-level symbols (load_profile,
build_app_from_profile, make_cli, BaseMcpSettings, the ToolProvider/
AuthHeaderSource protocols) are added as their modules land per implementation
phase and re-exported here.

MIT License — Copyright (c) 2026 BAUER GROUP.
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "BAUER GROUP"
__email__ = "info@bauer-group.com"

__all__ = ["__version__"]
