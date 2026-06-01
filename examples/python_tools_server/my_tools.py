"""Hand-written tools mounted via the `tools.source: python` escape hatch.

The register callable receives the FastMCP instance and a ToolContext (which
carries `settings`, an authenticated `client`, and a logger). This is the
Tier-3 pattern used by servers with no usable OpenAPI spec (e.g. Zammad): the
tool surface is hand-written and upstream calls go through `ctx.request`, which
applies the profile's outbound resolver (here the per-user OBO resolver in
`my_auth.py`).
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

    @mcp.tool
    async def whoami() -> dict[str, Any]:
        """Fetch the current user from the upstream API.

        The call goes out with THIS user's own token via the on-behalf-of
        resolver; it raises fail-closed when no token is available.
        """
        resp = await ctx.request("GET", "/users/me")
        return resp.json()

    return 3  # number of tools registered
