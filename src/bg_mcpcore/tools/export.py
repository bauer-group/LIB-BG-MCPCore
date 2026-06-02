"""Declarative bulk-export tool source (``tools.source: "export"``).

Pages a list endpoint and renders the full inventory as CSV or JSON, registered
as an MCP task — the declarative form of bg-shlink-mcp's hand-written export. All
the pagination shape (the items path, the page params, where the page counters
live) is config, so a backend with the common "page + items + pagesCount"
convention needs no Python.

The provider is a *registering* tool source: it drives ``ctx.request`` (the
authenticated upstream client), so it works with a settings-less context — no
secrets needed. Requires the ``[tasks]`` extra (FastMCP TaskConfig).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from ..observability import get_logger
from ..profile.loader import ProfileError

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..profile.models import ToolsConfig
    from .protocol import ToolContext

logger = get_logger("bg-mcpcore.tools.export")

_DEFAULT_FORMATS = ("csv", "json")
_MAX_PAGES_DEFAULT = 10_000  # safety backstop against a non-converging paginator


class _ExportConfig:
    """Reads the export-specific fields off a ToolsConfig (extra='allow')."""

    def __init__(self, cfg: ToolsConfig) -> None:
        extra = cfg.model_extra or {}
        self.name: str = extra.get("name", "")
        if not self.name:
            raise ProfileError("tools.source 'export' requires a 'name'")
        self.endpoint: str = extra.get("endpoint", "")
        if not self.endpoint:
            raise ProfileError("tools.source 'export' requires an 'endpoint'")
        self.items_path: str = extra.get("items_path", "")
        if not self.items_path:
            raise ProfileError("tools.source 'export' requires 'items_path' (dotted)")
        self.title: str | None = extra.get("title")
        self.description: str | None = extra.get("description")
        self.method: str = extra.get("method", "GET")
        self.tags: list[str] = list(extra.get("tags") or [])
        self.page_param: str = extra.get("page_param", "page")
        self.page_size_param: str = extra.get("page_size_param", "per_page")
        self.page_size: int = int(extra.get("page_size", 100))
        self.current_page_path: str | None = extra.get("current_page_path")
        self.total_pages_path: str | None = extra.get("total_pages_path")
        self.max_pages: int = int(extra.get("max_pages", _MAX_PAGES_DEFAULT))
        self.formats: tuple[str, ...] = tuple(extra.get("formats") or _DEFAULT_FORMATS)
        if not self.formats:
            raise ProfileError("tools.source 'export' 'formats' must be non-empty")
        task = extra.get("task") or {}
        self.task_mode: str = task.get("mode", "required")
        if self.task_mode not in ("forbidden", "optional", "required"):
            raise ProfileError(
                f"export task.mode must be one of forbidden/optional/required, got {self.task_mode!r}"
            )
        self.poll_interval_seconds: float = float(task.get("poll_interval_seconds", 2.0))


def _dig(body: Any, dotted: str) -> Any:
    """Navigate a dotted path through nested dicts; None if any step misses."""
    node = body
    for part in dotted.split("."):
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    return node


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _to_csv(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    columns = sorted({k for item in items for k in item})
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow({c: _cell(item.get(c)) for c in columns})
    return buffer.getvalue()


def _to_json(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False, indent=2)


async def _fetch_all(ctx: ToolContext, cfg: _ExportConfig) -> list[dict[str, Any]]:
    """Page ``cfg.endpoint`` and return the flattened items at ``cfg.items_path``."""
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        response = await ctx.request(
            cfg.method,
            cfg.endpoint,
            params={cfg.page_param: page, cfg.page_size_param: cfg.page_size},
        )
        response.raise_for_status()
        body = response.json()
        data = _dig(body, cfg.items_path) or []
        if isinstance(data, list):
            items.extend(data)
        if not data:
            break
        if cfg.current_page_path and cfg.total_pages_path:
            current = int(_dig(body, cfg.current_page_path) or page)
            total = int(_dig(body, cfg.total_pages_path) or current)
            if current >= total:
                break
        page += 1
        if page > cfg.max_pages:
            logger.warning("export.max_pages_reached", name=cfg.name, max_pages=cfg.max_pages)
            break
    return items


class ExportToolProvider:
    """Registers one bulk-export task tool, configured by a profile."""

    def __init__(self, cfg: ToolsConfig) -> None:
        self._cfg = _ExportConfig(cfg)

    async def register(self, mcp: FastMCP, ctx: ToolContext) -> int:
        from fastmcp.utilities.tasks import TaskConfig

        cfg = self._cfg
        task_config = TaskConfig(
            mode=cfg.task_mode,  # type: ignore[arg-type]  # validated to the Literal set in _ExportConfig
            poll_interval=timedelta(seconds=cfg.poll_interval_seconds),
        )
        default_format = cfg.formats[0]

        async def _export(format: str = default_format) -> dict[str, Any]:
            if format not in cfg.formats:
                raise ValueError(f"unknown format {format!r}; allowed: {list(cfg.formats)}")
            items = await _fetch_all(ctx, cfg)
            if format == "csv":
                body, mime = _to_csv(items), "text/csv"
            else:
                body, mime = _to_json(items), "application/json"
            logger.info("export.completed", name=cfg.name, format=format, item_count=len(items))
            return {"format": format, "mime_type": mime, "item_count": len(items), "content": body}

        _export.__name__ = cfg.name
        mcp.tool(
            name=cfg.name,
            title=cfg.title,
            description=cfg.description or None,
            tags=set(cfg.tags) if cfg.tags else None,
            task=task_config,
        )(_export)
        logger.info("export.registered", name=cfg.name, formats=list(cfg.formats))
        return 1


def create_export_tool_provider(cfg: ToolsConfig) -> ExportToolProvider:
    """Factory for ``tools.source == 'export'``."""
    return ExportToolProvider(cfg)


__all__ = ["ExportToolProvider", "create_export_tool_provider"]
