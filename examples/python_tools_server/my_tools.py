"""Hand-written tools mounted via the `tools.source: python` escape hatch.

The register callable receives the FastMCP instance and a ToolContext (which
carries `settings`, an authenticated `client`, and a logger). This is the
Tier-3 pattern used by servers with no usable OpenAPI spec (e.g. Zammad).
"""

from __future__ import annotations

from typing import Any


def register(mcp: Any, ctx: Any) -> int:
    @mcp.tool
    async def greet(name: str) -> str:
        """Greet someone by name (a trivial hand-written tool)."""
        return f"Hello, {name}!"

    @mcp.tool
    async def echo_setting() -> str:
        """Show the configured display name (reads from ctx.settings)."""
        return ctx.settings.mcp_display_name

    return 2  # number of tools registered
