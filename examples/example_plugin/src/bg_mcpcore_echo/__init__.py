"""Example bg-mcpcore plugin — a custom ``echo`` tool source via an entry point.

This proves extensibility **without editing bg-mcpcore**: `pip install` this
package and any profile can use ``{"source": "echo"}`` to get an ``echo`` tool.
The entry point in ``pyproject.toml`` registers :func:`create_echo_source` under
the ``bg_mcpcore.tool_sources`` group, which bg-mcpcore's ``build_tool_provider``
discovers lazily — no core change, no per-server wiring.

A tool source is any object with ``async def register(mcp, ctx) -> int`` (this
one) or ``async def construct(...) -> FastMCP`` (the OpenAPI source). The factory
receives the profile's ``tools`` config so a real plugin can read its own knobs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from bg_mcpcore import ToolContext


class EchoToolProvider:
    """Registers a single ``echo`` tool onto the server."""

    def __init__(self, cfg: Any) -> None:
        # `cfg` is the profile's ToolsConfig (extra='allow'); a real plugin would
        # read its own fields off cfg.model_extra. The demo ignores it.
        self._cfg = cfg

    async def register(self, mcp: FastMCP, ctx: ToolContext) -> int:
        @mcp.tool(name="echo", description="Echo the given text back unchanged.")
        async def echo(text: str) -> str:
            return text

        return 1


def create_echo_source(cfg: Any) -> EchoToolProvider:
    """Entry-point factory for ``tools.source == 'echo'``."""
    return EchoToolProvider(cfg)


__all__ = ["EchoToolProvider", "create_echo_source"]
