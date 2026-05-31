"""Operational HTTP routes mounted alongside the MCP endpoint.

* ``/healthz``  - 200 OK as soon as the server is up (container/k8s probes).
* ``/logo.svg`` - brand icon for the OAuth consent screen, same-origin (no CORS).
* ``/``         - human-readable status + quickstart page.

The route LOGIC is shared; the brand assets (``logo.svg``, ``index.html``) stay
per-server, so ``static_dir`` and the index ``template_vars`` are passed in.
Files are read once at registration and cached in the closure - immutable at
runtime, no per-request disk hit.
"""

from __future__ import annotations

import string
from pathlib import Path
from typing import TYPE_CHECKING

from ..observability import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger("bg-mcpcore.routes")


def register_healthz_route(mcp: FastMCP) -> None:
    """Expose /healthz returning 200 OK. Distinct from the upstream's own
    health endpoint (which sits behind the OAuth wall)."""
    from starlette.responses import JSONResponse

    @mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def _healthz(_request) -> JSONResponse:  # type: ignore[no-untyped-def]
        return JSONResponse({"status": "ok"}, status_code=200)


def register_logo_route(mcp: FastMCP, *, static_dir: Path) -> None:
    """Serve /logo.svg from ``static_dir`` so the OAuth consent screen can fetch
    the brand icon from the same origin as the MCP server."""
    from starlette.responses import Response

    logo_path = Path(static_dir) / "logo.svg"
    try:
        svg_bytes = logo_path.read_bytes()
    except FileNotFoundError:
        logger.warning("logo.template_missing", path=str(logo_path))
        return

    @mcp.custom_route("/logo.svg", methods=["GET"], include_in_schema=False)
    async def _logo(_request) -> Response:  # type: ignore[no-untyped-def]
        return Response(
            svg_bytes,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )


def register_index_route(
    mcp: FastMCP,
    *,
    static_dir: Path,
    template_vars: dict[str, str],
) -> None:
    """Serve a human-readable status page at / from ``static_dir/index.html``.

    Rendered once with ``string.Template(...).safe_substitute(**template_vars)``
    (so CSS braces don't collide with str.format placeholders) and cached.
    """
    from starlette.responses import HTMLResponse

    template_path = Path(static_dir) / "index.html"
    try:
        raw = template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("index.template_missing", path=str(template_path))
        return

    rendered = string.Template(raw).safe_substitute(**template_vars)

    @mcp.custom_route("/", methods=["GET"], include_in_schema=False)
    async def _index(_request) -> HTMLResponse:  # type: ignore[no-untyped-def]
        return HTMLResponse(rendered, headers={"Cache-Control": "public, max-age=60"})


__all__ = [
    "register_healthz_route",
    "register_index_route",
    "register_logo_route",
]
