"""Process runtime: dual-stack socket patch + transport dispatch.

Lifted from the servers' ``main.py``. ``patch_dual_stack_socket`` must run
before asyncio creates any server socket (call it at process start, e.g. in
``make_cli``). ``run_transport`` is the transport-dispatch body of the old
``_serve_async``.
"""

from __future__ import annotations

import socket as _socket
from typing import TYPE_CHECKING

from ..observability import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger("bg-mcpcore.runner")

_orig_socket = _socket.socket
_patched = False


class _DualStackSocket(_orig_socket):
    # asyncio hardcodes IPV6_V6ONLY=1 on v6 server sockets; coerce back to 0 so
    # a "::" bind accepts both IPv6 and v4-mapped IPv4 in one listener.
    def setsockopt(self, level: int, optname: int, value: int | bytes) -> None:  # type: ignore[override]
        if level == _socket.IPPROTO_IPV6 and optname == _socket.IPV6_V6ONLY and value:
            value = 0
        super().setsockopt(level, optname, value)


def patch_dual_stack_socket() -> None:
    """Monkey-patch socket.socket so a ``::`` bind serves IPv6 + IPv4. Idempotent."""
    global _patched
    if _patched:
        return
    _socket.socket = _DualStackSocket  # type: ignore[misc]
    _patched = True


async def run_transport(mcp: FastMCP, *, host: str, port: int, transport: str) -> None:
    """Hand off to FastMCP's transport runner.

    An empty ``host`` means "any stack, any interface" -> bind "::" so the
    dual-stack patch produces a combined v6+v4 listener.
    """
    bind_host = host or "::"
    logger.info("server.starting", transport=transport, host=bind_host, port=port)

    if transport == "stdio":
        await mcp.run_stdio_async()
    elif transport == "streamable-http":
        await mcp.run_http_async(host=bind_host, port=port, transport="streamable-http")
    else:
        raise ValueError(f"Unsupported transport: {transport!r}")


__all__ = ["patch_dual_stack_socket", "run_transport"]
