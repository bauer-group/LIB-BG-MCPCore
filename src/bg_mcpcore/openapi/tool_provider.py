"""Profile-driven OpenAPI tool source ([openapi] extra).

A ConstructingToolProvider that builds the FastMCP instance from an OpenAPI spec
via ``FastMCP.from_openapi``. Everything Shlink hard-coded in ``tool_mapper.py``
(route maps, name overrides, description overrides, method-annotation policy,
path-prefix normalisation) is now read DECLARATIVELY from the profile's
``tools`` block — adding a vanilla OpenAPI backend becomes a config-only job.

The provider drives ``ctx.client.httpx_client`` (the UpstreamClient's raw client,
with the static outbound header already baked into its default headers — see the
dual-auth path in auth/resolvers.py), exactly as Shlink does today.
"""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING, Any

from ..observability import get_logger
from ..profile.loader import ProfileError
from ..profile.models import ToolsConfig

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..tools.protocol import ToolContext

logger = get_logger("bg-mcpcore.openapi.tools")

# HTTP method -> MCP safety hints. GET is safe-to-auto; everything else needs
# human approval (defense-in-depth: clients may ignore these hints).
_METHOD_ANNOTATIONS: dict[str, dict[str, bool]] = {
    "GET": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True},
    "POST": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    "PUT": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
    "PATCH": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
    "DELETE": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
}


class _OpenApiConfig:
    """Reads the openapi-specific fields off a ToolsConfig (extra='allow')."""

    def __init__(self, cfg: ToolsConfig) -> None:
        extra = cfg.model_extra or {}
        spec = extra.get("spec") or {}
        if not isinstance(spec, dict) or not spec.get("source"):
            raise ProfileError("tools.source 'openapi' requires spec.source")
        self.spec_source: str = spec["source"]
        self.spec_timeout: float = float(spec.get("timeout", 30))
        self.strip_path_prefix: str | None = (extra.get("normalize") or {}).get("strip_path_prefix")
        self.route_maps: list[dict[str, str]] = extra.get("route_maps") or []
        self.name_overrides: dict[str, str] = extra.get("name_overrides") or {}
        self.descriptions: dict[str, str] = extra.get("descriptions") or {}
        self.annotations: Any = extra.get("annotations", "by_http_method")


def _normalize_spec(spec: dict[str, Any], strip_prefix: str | None) -> dict[str, Any]:
    """Strip a path prefix (e.g. '/rest/v{version}') and drop the freed path param."""
    if not strip_prefix:
        return spec
    # Turn "/rest/v{version}" into a regex that also matches concrete versions.
    pattern = re.escape(strip_prefix)
    pattern = pattern.replace(r"\{version\}", r"(?:\d+|\{[^}]+\})")
    prefix_re = re.compile("^" + pattern)
    param_names = set(re.findall(r"\{([^}]+)\}", strip_prefix))

    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return spec
    new_paths: dict[str, Any] = {}
    for raw_path, path_item in paths.items():
        new_key = prefix_re.sub("", raw_path) or "/"
        if isinstance(path_item, dict):
            new_item: dict[str, Any] = {}
            for method, operation in path_item.items():
                if isinstance(operation, dict) and isinstance(operation.get("parameters"), list):
                    operation = {
                        **operation,
                        "parameters": [
                            p
                            for p in operation["parameters"]
                            if not (
                                isinstance(p, dict)
                                and p.get("in") == "path"
                                and p.get("name") in param_names
                            )
                        ],
                    }
                new_item[method] = operation
            new_paths[new_key] = new_item
        else:
            new_paths[new_key] = path_item
    return {**spec, "paths": new_paths}


def _strip_prefix_for_match(strip_prefix: str | None) -> re.Pattern[str]:
    if not strip_prefix:
        return re.compile(r"^$")  # matches nothing extra
    pattern = re.escape(strip_prefix).replace(r"\{version\}", r"(?:\d+|\{[^}]+\})")
    return re.compile("^" + pattern)


def _build_names_map(
    spec: dict[str, Any], overrides: dict[str, str], strip_re: re.Pattern[str]
) -> dict[str, str]:
    """Translate 'METHOD /path' overrides into FastMCP's {operationId: name} map."""
    result: dict[str, str] = {}
    paths = spec.get("paths") or {}
    if not isinstance(paths, dict):
        return result
    # Normalise the override keys once: "POST /short-urls" -> (POST, /short-urls)
    parsed = {}
    for key, name in overrides.items():
        method, _, path = key.partition(" ")
        parsed[(method.upper(), path)] = name
    for raw_path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        normalized = strip_re.sub("", raw_path) or "/"
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            op_id = operation.get("operationId")
            if not isinstance(op_id, str) or not op_id:
                continue
            mapped = parsed.get((method.upper(), normalized))
            if mapped:
                result[op_id] = mapped
    return result


class OpenApiToolProvider:
    """Builds a FastMCP server from an OpenAPI spec, configured by a profile."""

    def __init__(self, cfg: _OpenApiConfig) -> None:
        self._cfg = cfg

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
    ) -> FastMCP:
        from fastmcp import FastMCP
        from fastmcp.server.providers.openapi import MCPType, RouteMap
        from mcp.types import Icon, ToolAnnotations

        from .loader import load_spec

        if ctx.client is None:
            raise ProfileError("tools.source 'openapi' requires a backend (profile.backend)")

        loaded = await load_spec(self._cfg.spec_source, timeout=self._cfg.spec_timeout)
        spec = _normalize_spec(loaded.spec, self._cfg.strip_path_prefix)
        strip_re = _strip_prefix_for_match(self._cfg.strip_path_prefix)

        type_map = {"resource": MCPType.RESOURCE, "exclude": MCPType.EXCLUDE, "tool": MCPType.TOOL}
        route_maps = []
        for rm in self._cfg.route_maps:
            pattern = rm.get("pattern")
            if not pattern:
                raise ProfileError("Each tools.route_maps entry requires a 'pattern'")
            rtype = rm.get("type", "tool")
            if rtype not in type_map:
                raise ProfileError(
                    f"Unknown route_map type {rtype!r}; expected one of {sorted(type_map)}"
                )
            route_maps.append(RouteMap(pattern=pattern, mcp_type=type_map[rtype]))

        annotations_enabled = self._cfg.annotations == "by_http_method"
        descriptions = self._cfg.descriptions

        def _component_fn(route: Any, component: Any) -> None:
            comp_name = getattr(component, "name", None)
            if isinstance(comp_name, str) and comp_name in descriptions:
                with contextlib.suppress(AttributeError, ValueError):
                    component.description = descriptions[comp_name]
            if annotations_enabled and "Tool" in type(component).__name__:
                method = (getattr(route, "method", None) or "").upper()
                hints = _METHOD_ANNOTATIONS.get(method)
                if hints is not None:
                    with contextlib.suppress(AttributeError, ValueError):
                        component.annotations = ToolAnnotations(**hints)  # type: ignore[arg-type]

        kwargs: dict[str, Any] = {
            "openapi_spec": spec,
            "client": ctx.client.httpx_client,
            "name": name,
            "instructions": instructions,
            "route_maps": route_maps,
            "mcp_names": _build_names_map(spec, self._cfg.name_overrides, strip_re),
            "mcp_component_fn": _component_fn,
        }
        if auth is not None:
            kwargs["auth"] = auth
        if lifespan is not None:
            kwargs["lifespan"] = lifespan
        if icon_url:
            kwargs["icons"] = [Icon(src=icon_url, mimeType="image/svg+xml")]
        if website_url:
            kwargs["website_url"] = website_url

        mcp: FastMCP = FastMCP.from_openapi(**kwargs)
        logger.info(
            "openapi.tools_generated",
            spec_title=loaded.title,
            spec_version=loaded.info_version,
            operations=loaded.operation_count,
        )
        return mcp


def create_openapi_tool_provider(cfg: ToolsConfig) -> OpenApiToolProvider:
    """Entry-point factory for tools.source == 'openapi'."""
    return OpenApiToolProvider(_OpenApiConfig(cfg))


__all__ = ["OpenApiToolProvider", "create_openapi_tool_provider"]
