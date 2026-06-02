"""Declarative export tool source: config validation, pagination, render, register."""

from __future__ import annotations

from typing import Any

import pytest

from bg_mcpcore.profile.loader import ProfileError
from bg_mcpcore.profile.models import ToolsConfig
from bg_mcpcore.tools.export import (
    ExportToolProvider,
    _cell,
    _dig,
    _ExportConfig,
    _fetch_all,
    _to_csv,
    create_export_tool_provider,
)

# ── fakes ─────────────────────────────────────────────────────────────────────


class _Resp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeCtx:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> _Resp:
        self.calls.append({"method": method, "path": path, **kwargs})
        page = int(kwargs["params"]["page"])
        return _Resp(self._pages[page - 1])


def _shlink_page(data: list[dict[str, Any]], current: int, total: int) -> dict[str, Any]:
    return {"shortUrls": {"data": data, "pagination": {"currentPage": current, "pagesCount": total}}}


def _shlink_cfg(**over: Any) -> _ExportConfig:
    base: dict[str, Any] = {
        "source": "export",
        "name": "export_short_urls",
        "endpoint": "/short-urls",
        "items_path": "shortUrls.data",
        "page_param": "page",
        "page_size_param": "itemsPerPage",
        "page_size": 200,
        "current_page_path": "shortUrls.pagination.currentPage",
        "total_pages_path": "shortUrls.pagination.pagesCount",
        "formats": ["csv", "json"],
        "tags": ["export", "bulk"],
        "task": {"mode": "required", "poll_interval_seconds": 2.0},
    }
    base.update(over)
    return _ExportConfig(ToolsConfig(**base))


# ── helpers ───────────────────────────────────────────────────────────────────


def test_dig_navigates_dotted_paths() -> None:
    body = {"a": {"b": {"c": 42}}}
    assert _dig(body, "a.b.c") == 42
    assert _dig(body, "a.b.missing") is None
    assert _dig(body, "a.x.c") is None


def test_cell_and_csv() -> None:
    assert _cell(["x", "y"]) == '["x", "y"]'
    out = _to_csv([{"a": 1, "tags": ["x"]}, {"a": 2, "b": 3}])
    assert out.splitlines()[0] == "a,b,tags"


# ── config validation ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("missing", ["name", "endpoint", "items_path"])
def test_config_requires_core_fields(missing: str) -> None:
    fields = {"source": "export", "name": "x", "endpoint": "/e", "items_path": "d"}
    del fields[missing]
    with pytest.raises(ProfileError):
        _ExportConfig(ToolsConfig(**fields))


# ── pagination ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_all_pages_through_everything() -> None:
    ctx = _FakeCtx(
        [
            _shlink_page([{"shortCode": "a"}, {"shortCode": "b"}], current=1, total=2),
            _shlink_page([{"shortCode": "c"}], current=2, total=2),
        ]
    )
    items = await _fetch_all(ctx, _shlink_cfg())  # type: ignore[arg-type]
    assert [i["shortCode"] for i in items] == ["a", "b", "c"]
    assert len(ctx.calls) == 2
    assert ctx.calls[0]["params"] == {"page": 1, "itemsPerPage": 200}


@pytest.mark.asyncio
async def test_fetch_all_stops_on_single_page() -> None:
    ctx = _FakeCtx([_shlink_page([{"shortCode": "a"}], current=1, total=1)])
    items = await _fetch_all(ctx, _shlink_cfg())  # type: ignore[arg-type]
    assert len(items) == 1 and len(ctx.calls) == 1


@pytest.mark.asyncio
async def test_fetch_all_stops_on_empty_without_page_counters() -> None:
    # No current/total paths: stop when a page returns no items.
    ctx = _FakeCtx([{"data": [{"id": 1}]}, {"data": []}])
    cfg = _ExportConfig(
        ToolsConfig(
            source="export",
            name="e",
            endpoint="/e",
            items_path="data",
            page_size_param="per_page",
        )
    )
    items = await _fetch_all(ctx, cfg)  # type: ignore[arg-type]
    assert items == [{"id": 1}]
    assert len(ctx.calls) == 2


# ── registration ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_creates_task_tool() -> None:
    pytest.importorskip("docket")  # task registration needs the [tasks] extra

    from fastmcp import FastMCP

    from bg_mcpcore import ToolContext

    provider = create_export_tool_provider(
        ToolsConfig(
            source="export",
            name="export_short_urls",
            title="Export Short URLs",
            endpoint="/short-urls",
            items_path="shortUrls.data",
        )
    )
    assert isinstance(provider, ExportToolProvider)
    mcp = FastMCP(name="t")
    count = await provider.register(mcp, ToolContext(settings=None))
    assert count == 1
    names = {getattr(t, "name", "") for t in await mcp.list_tools()}
    assert "export_short_urls" in names


def test_build_tool_provider_dispatches_export() -> None:
    from bg_mcpcore.plugins import build_tool_provider

    provider = build_tool_provider(
        ToolsConfig(source="export", name="e", endpoint="/e", items_path="d")
    )
    assert isinstance(provider, ExportToolProvider)
