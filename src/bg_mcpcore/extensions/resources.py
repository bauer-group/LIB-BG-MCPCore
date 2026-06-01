"""Register operator-defined resources / resource templates from the catalogue.

Each entry becomes a FunctionResource (static URI) or ResourceTemplate
(parameterised URI). Ported from bg-shlink-mcp with one hardening change: the
GET goes through the ``UpstreamClient`` (so the outbound auth resolver applies),
not a raw httpx client.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from ..observability import get_logger
from .config import ResourceConfig

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..http.client import UpstreamClient

logger = get_logger("bg-mcpcore.extensions.resources")

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def register_resources(
    mcp: FastMCP,
    resources: list[ResourceConfig],
    client: UpstreamClient,
) -> tuple[int, int]:
    """Register every resource entry. Returns (resource_count, template_count)."""
    resource_count = 0
    template_count = 0
    for cfg in resources:
        try:
            fn = _build_resource_function(cfg, client)
            mcp.resource(
                cfg.uri,
                name=cfg.name,
                title=cfg.title,
                description=cfg.description or None,
                mime_type=cfg.mime_type,
                tags=set(cfg.tags) if cfg.tags else None,
            )(fn)
            if _PLACEHOLDER_RE.findall(cfg.uri):
                template_count += 1
                logger.info("extensions.template_registered", uri=cfg.uri)
            else:
                resource_count += 1
                logger.info("extensions.resource_registered", uri=cfg.uri)
        except Exception as exc:
            logger.error("extensions.resource_registration_failed", uri=cfg.uri, error=str(exc))
    return resource_count, template_count


def _build_resource_function(
    cfg: ResourceConfig, client: UpstreamClient
) -> Callable[..., Awaitable[Any]]:
    placeholders = _PLACEHOLDER_RE.findall(cfg.backend.path)
    method = cfg.backend.method
    backend_path = cfg.backend.path

    async def _runner(**kwargs: str) -> Any:
        # Percent-encode placeholder values (httpx does not re-encode interpolated
        # path strings) so a value like "abc/visits" cannot escape the segment.
        path = backend_path
        for name, value in kwargs.items():
            path = path.replace(f"{{{name}}}", quote(str(value), safe=""))
        response = await client.request(method, path)
        response.raise_for_status()
        ctype = response.headers.get("content-type", "").lower()
        if "json" in ctype or cfg.mime_type == "application/json":
            return response.json()
        return response.text

    _runner.__name__ = f"resource_{cfg.name.lower().replace(' ', '_')}"
    _runner.__doc__ = cfg.description or None
    parameters = [
        inspect.Parameter(name=p, kind=inspect.Parameter.KEYWORD_ONLY, annotation=str)
        for p in placeholders
    ]
    _runner.__signature__ = inspect.Signature(parameters=parameters, return_annotation=Any)  # type: ignore[attr-defined]
    _runner.__annotations__ = {p: str for p in placeholders} | {"return": Any}
    return _runner


__all__ = ["register_resources"]
