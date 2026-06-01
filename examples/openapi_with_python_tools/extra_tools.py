"""Tier-2 escape hatch: a few hand-written tools ALONGSIDE the OpenAPI surface.

The `openapi` tool source ([openapi] extra) generates one tool per operation
(`list_pets`, `create_pet`). This module adds composite tools the raw spec can't
express. They call the SAME backend through ``ctx.request`` — so they inherit the
profile's outbound auth, base path, timeout, and retries — and they are mounted
in the same profile via a second `python` tool source. That is the whole of
Tier 2: mostly config, a little code.

``register_extras`` may be sync or async and returns the number of tools added.
"""

from __future__ import annotations

from typing import Any


def register_extras(mcp: Any, ctx: Any) -> int:
    @mcp.tool
    async def pet_count() -> int:
        """Count the pets in the store — a composite the raw /pets endpoint lacks."""
        resp = await ctx.request("GET", "/pets")
        return len(resp.json())

    @mcp.tool
    async def find_pet_by_name(name: str) -> list[dict[str, Any]]:
        """Find pets whose name matches `name` (client-side filter over /pets)."""
        resp = await ctx.request("GET", "/pets")
        return [pet for pet in resp.json() if pet.get("name") == name]

    return 2  # number of tools registered
