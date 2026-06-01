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


def _openapi_profile(spec_path, route_maps):  # type: ignore[no-untyped-def]
    return load_profile(
        {
            "id": "api",
            "display_name": "API",
            "backend": {"base_url": "http://localhost:9999"},
            "tools": {
                "source": "openapi",
                "spec": {"source": str(spec_path)},
                "route_maps": route_maps,
            },
        },
        env={},
    )


@pytest.mark.asyncio
async def test_route_map_missing_pattern_raises(spec_path) -> None:  # type: ignore[no-untyped-def]
    from bg_mcpcore.profile.loader import ProfileError

    profile = _openapi_profile(spec_path, [{"type": "exclude"}])
    with pytest.raises(ProfileError, match="route_maps entry requires a 'pattern'"):
        await build_app_from_profile(
            profile, _Demo(environment="development", auth_mode="none"), version="1.0.0"
        )


@pytest.mark.asyncio
async def test_route_map_unknown_type_raises(spec_path) -> None:  # type: ignore[no-untyped-def]
    from bg_mcpcore.profile.loader import ProfileError

    profile = _openapi_profile(spec_path, [{"pattern": "^/items$", "type": "bogus"}])
    with pytest.raises(ProfileError, match="Unknown route_map type"):
        await build_app_from_profile(
            profile, _Demo(environment="development", auth_mode="none"), version="1.0.0"
        )


def test_normalize_spec_strips_prefix_and_drops_version_param() -> None:
    from bg_mcpcore.openapi.tool_provider import _normalize_spec

    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/rest/v3/short-urls": {
                "get": {
                    "operationId": "list",
                    "parameters": [
                        {"in": "path", "name": "version"},
                        {"in": "query", "name": "q"},
                    ],
                }
            }
        },
    }
    out = _normalize_spec(spec, "/rest/v{version}")
    assert "/short-urls" in out["paths"]
    names = [p["name"] for p in out["paths"]["/short-urls"]["get"]["parameters"]]
    assert "version" not in names  # the freed path param is dropped
    assert "q" in names  # the query param survives


@pytest.mark.asyncio
async def test_sibling_external_refs_are_not_false_circular(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A component file referencing a sibling in the SAME file (defs#/A -> defs#/B)
    # is the standard modular-spec pattern and must not be flagged circular.
    from bg_mcpcore.openapi.loader import load_spec

    (tmp_path / "defs.json").write_text(
        json.dumps(
            {
                "A": {"type": "object", "properties": {"b": {"$ref": "defs.json#/B"}}},
                "B": {"type": "string"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "main.json").write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "info": {"title": "t", "version": "1"},
                "paths": {
                    "/x": {
                        "get": {
                            "operationId": "getx",
                            "responses": {
                                "200": {
                                    "description": "ok",
                                    "content": {
                                        "application/json": {"schema": {"$ref": "defs.json#/A"}}
                                    },
                                }
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    loaded = await load_spec(str(tmp_path / "main.json"))
    assert "/x" in loaded.spec["paths"]


@pytest.mark.asyncio
async def test_true_circular_external_ref_is_detected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # a.json#/X -> b.json#/Y -> a.json#/X is a genuine cycle and must be caught.
    from bg_mcpcore.openapi.loader import SpecLoadError, load_spec

    (tmp_path / "a.json").write_text(json.dumps({"X": {"$ref": "b.json#/Y"}}), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"Y": {"$ref": "a.json#/X"}}), encoding="utf-8")
    (tmp_path / "main.json").write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "info": {"title": "t", "version": "1"},
                "paths": {
                    "/x": {
                        "get": {
                            "operationId": "g",
                            "responses": {
                                "200": {
                                    "description": "ok",
                                    "content": {
                                        "application/json": {"schema": {"$ref": "a.json#/X"}}
                                    },
                                }
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SpecLoadError, match="Circular"):
        await load_spec(str(tmp_path / "main.json"))
