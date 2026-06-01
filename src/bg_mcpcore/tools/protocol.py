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

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from ..http.client import UpstreamClient
from ..observability import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP


class UpstreamError(RuntimeError):
    """Raised by ``ToolContext.request_json`` on a non-2xx upstream response.

    Carries the HTTP status and the parsed error body so a tool (or a caller's
    ``error_factory``) can branch on them. This is the framework default; a
    server with its own typed exception hierarchy passes ``error_factory`` to
    ``request_json`` to keep raising its own classes instead.
    """

    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.body = body or {}
        detail = self.body.get("detail") or self.body.get("error") or self.body.get("message")
        super().__init__(f"upstream returned HTTP {status_code}" + (f": {detail}" if detail else ""))


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
        """Authenticated upstream call routed through the outbound resolver.

        Returns the raw ``httpx.Response`` — call ``.json()`` / ``.raise_for_status()``
        yourself, or use :meth:`request_json` for the common decode-or-raise path.
        """
        if self.client is None:
            raise RuntimeError("This server has no upstream backend configured")
        return await self.client.request(method, path, ctx=self, **kwargs)

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        error_factory: Callable[[int, dict[str, Any]], Exception] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Authenticated upstream call that decodes on 2xx and raises on non-2xx.

        On a 2xx response: returns the parsed JSON body (or the raw text when the
        response is not JSON). On a non-2xx response: parses the error body (a
        dict, else ``{}``) and raises ``error_factory(status, body)`` when given,
        otherwise :class:`UpstreamError`. This is the decode-and-typed-error
        contract hand-written tool surfaces expect — no per-server shim needed.
        """
        response = await self.request(method, path, **kwargs)
        content_type = response.headers.get("content-type", "")
        if 200 <= response.status_code < 300:
            if "json" in content_type:
                try:
                    return response.json()
                except ValueError:
                    return response.text
            return response.text
        body: dict[str, Any] = {}
        if "json" in content_type:
            try:
                parsed = response.json()
                if isinstance(parsed, dict):
                    body = parsed
            except ValueError:
                pass
        if error_factory is not None:
            raise error_factory(response.status_code, body)
        raise UpstreamError(response.status_code, body)


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


__all__ = ["ConstructingToolProvider", "ToolContext", "ToolProvider", "UpstreamError"]
