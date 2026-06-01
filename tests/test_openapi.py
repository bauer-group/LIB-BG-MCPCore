"""Tests for the [openapi] tool source: spec loader + profile-driven generation."""

from __future__ import annotations

import json

import pytest

from bg_mcpcore import BaseMcpSettings, build_app_from_profile, load_profile

_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Demo API", "version": "1.0"},
    "paths": {
        "/items": {
            "get": {
                "operationId": "listItems",
                "summary": "List items.",
                "responses": {"200": {"description": "ok"}},
            }
        }
    },
}


class _Demo(BaseMcpSettings):
    mcp_display_name: str = "Demo API"


@pytest.fixture
def spec_path(tmp_path):  # type: ignore[no-untyped-def]
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(_SPEC), encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_openapi_source_generates_tools_with_name_override(spec_path) -> None:  # type: ignore[no-untyped-def]
    profile = load_profile(
        {
            "id": "api",
            "display_name": "API",
            "backend": {"base_url": "http://localhost:9999"},
            "tools": {
                "source": "openapi",
                "spec": {"source": str(spec_path)},
                "name_overrides": {"GET /items": "list_items"},
            },
        },
        env={},
    )
    settings = _Demo(environment="development", auth_mode="none")
    mcp = await build_app_from_profile(profile, settings, version="1.0.0")

    names = {getattr(t, "name", "") for t in await mcp.list_tools()}
    assert "list_items" in names  # operationId 'listItems' renamed via the profile


@pytest.mark.asyncio
async def test_load_spec_rejects_empty_paths(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from bg_mcpcore.openapi.loader import SpecLoadError, load_spec

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"openapi": "3.0.0", "paths": {}}), encoding="utf-8")
    with pytest.raises(SpecLoadError, match="0 operations"):
        await load_spec(str(bad))
