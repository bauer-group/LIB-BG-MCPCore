"""Tool-provider protocols + the tool context.

Two protocols model the verified construct-vs-register fork:

* ``ToolProvider`` — mutates an existing FastMCP instance and returns a count
  (Zammad-style hand-written tools, the central registry).
* ``ConstructingToolProvider`` — BUILDS the FastMCP instance from a spec
  (Shlink-style ``FastMCP.from_openapi``). At most one per server; the assembler
  delegates construction to it instead of building a bare instance.

``ToolContext`` is handed to the ``python`` escape hatch — the server's OWN
trusted code — so it carries ``settings`` + an authenticated ``client``. The
OpenAPI/registry sources do NOT receive settings (least privilege, guardrail #4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from ..http.client import UpstreamClient
from ..observability import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP


@dataclass
class ToolContext:
    """Dependencies passed to a python tool-source register callable.

    ``client`` is None for backend-less servers (e.g. a registry-only server);
    calling ``request`` on such a context raises.
    """

    settings: Any
    client: UpstreamClient | None = None
    logger: Any = field(default_factory=lambda: get_logger("bg-mcpcore.tools"))

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Authenticated upstream call routed through the outbound resolver."""
        if self.client is None:
            raise RuntimeError("This server has no upstream backend configured")
        return await self.client.request(method, path, ctx=self, **kwargs)


@runtime_checkable
class ToolProvider(Protocol):
    """Registers tools onto an existing FastMCP instance; returns the count."""

    async def register(self, mcp: FastMCP, ctx: ToolContext) -> int: ...


@runtime_checkable
class ConstructingToolProvider(Protocol):
    """Builds the FastMCP instance itself (e.g. from an OpenAPI spec)."""

    async def construct(
        self,
        *,
        name: str,
        instructions: str,
        auth: Any | None,
        lifespan: Any | None,
        icon_url: str | None,
        website_url: str | None,
        ctx: ToolContext,
    ) -> FastMCP: ...


__all__ = ["ConstructingToolProvider", "ToolContext", "ToolProvider"]
