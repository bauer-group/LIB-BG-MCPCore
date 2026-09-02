"""Tier-2 escape hatch: a few hand-written tools ALONGSIDE the OpenAPI surface.

The `openapi` tool source ([openapi] extra) generates one tool per operation
(`list_pets`, `create_pet`). This module adds composite tools the raw spec can't
express. They call the SAME backend through ``ctx.request`` — so they inherit the
profile's outbound auth, base path, timeout, and retries — and they are mounted
in the same profile via a second `python` tool source. That is the whole of
Tier 2: mostly config, a little code.

``register_extras`` may be sync or async and returns the number of tools added.

Note the imports below. HTTP types come from ``bg_mcpcore.http``, never from an
HTTP library directly. bg-mcpcore 2.0 moved from httpx to httpx2 (following
FastMCP 4), and a tool written this way needed no change. A tool that had
written ``except httpx.HTTPStatusError`` would still import and still type-check
after that move — and would silently never match again.
"""

from __future__ import annotations

from typing import Any

from bg_mcpcore.http import HTTPStatusError, Response, TimeoutException


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

    @mcp.tool
    async def pet_status(pet_id: int) -> dict[str, Any]:
        """Look up one pet, turning upstream failures into answers an agent can use.

        Demonstrates the error-handling shape: annotate with ``Response`` and
        catch the ``bg_mcpcore.http`` exceptions. ``ctx.request_json`` covers the
        common decode-or-raise path; drop to ``ctx.request`` like this when you
        want to branch on the status yourself.
        """
        try:
            resp: Response = await ctx.request("GET", f"/pets/{pet_id}")
            resp.raise_for_status()
        except HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"found": False, "pet_id": pet_id}
            raise
        except TimeoutException:
            # Retries are already exhausted by UpstreamClient at this point.
            return {"found": False, "pet_id": pet_id, "error": "upstream timed out"}
        return {"found": True, "pet": resp.json()}

    return 3  # number of tools registered
