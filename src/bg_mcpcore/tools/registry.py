"""Central tool registry — the basis for "all tools centrally available".

Reusable tool building blocks are registered here under a dotted name and can be
mounted onto any server via a profile's ``tools.source: "registry"`` with an
``include`` list. Built-ins live in core; plugins contribute more via the
``bg_mcpcore.tools`` entry-point group (discovered lazily, once).

A tool factory takes the FastMCP instance + the ToolContext and registers one or
more tools onto it.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from ..observability import get_logger
from .protocol import ToolContext

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger("bg-mcpcore.tools.registry")

ToolFactory = Callable[["FastMCP", ToolContext], None]

_REGISTRY: dict[str, ToolFactory] = {}
_ENTRYPOINTS_LOADED = False
_ENTRYPOINT_GROUP = "bg_mcpcore.tools"


def register_tool(name: str, factory: ToolFactory) -> None:
    """Register a named, reusable tool factory."""
    _REGISTRY[name] = factory


def _load_entrypoints() -> None:
    global _ENTRYPOINTS_LOADED
    if _ENTRYPOINTS_LOADED:
        return
    for ep in entry_points(group=_ENTRYPOINT_GROUP):
        if ep.name not in _REGISTRY:
            try:
                _REGISTRY[ep.name] = ep.load()
            except Exception as exc:
                logger.warning("tools.registry_entrypoint_failed", name=ep.name, error=str(exc))
    _ENTRYPOINTS_LOADED = True


def get_tool(name: str) -> ToolFactory:
    """Look up a registered tool factory by name (loads plugins on first use)."""
    _load_entrypoints()
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"Unknown registry tool '{name}'. Available: {available}")
    return _REGISTRY[name]


def available_tools() -> list[str]:
    """All registered tool names (built-in + plugins)."""
    _load_entrypoints()
    return sorted(_REGISTRY)


# ── Built-in reusable tools ──────────────────────────────────────────────────


def _register_ping(mcp: FastMCP, _ctx: ToolContext) -> None:
    @mcp.tool
    async def ping() -> str:
        """Return 'pong'. A trivial liveness tool to confirm the MCP is reachable."""
        return "pong"


register_tool("bg.ping", _register_ping)


__all__ = ["ToolFactory", "available_tools", "get_tool", "register_tool"]
