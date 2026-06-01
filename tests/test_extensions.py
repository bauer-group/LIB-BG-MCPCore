"""Tests for the config-driven extensions layer (prompts + resources)."""

from __future__ import annotations

import json

import pytest
from fastmcp import FastMCP

from bg_mcpcore import BaseMcpSettings, build_app_from_profile, load_profile
from bg_mcpcore.extensions import load_config, load_extensions
from bg_mcpcore.extensions.config import ExtensionsConfigError
from bg_mcpcore.http.client import UpstreamClient


def _write(tmp_path, payload: dict) -> str:  # type: ignore[no-untyped-def]
    path = tmp_path / "extensions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


class _Demo(BaseMcpSettings):
    mcp_display_name: str = "Demo"


@pytest.mark.asyncio
async def test_load_prompts_and_resource_template(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = _write(
        tmp_path,
        {
            "prompts": [
                {
                    "name": "greet",
                    "template": "Hello ${who}",
                    "arguments": [{"name": "who", "required": True}],
                }
            ],
            "resources": [
                {"uri": "demo://item/{id}", "name": "item", "backend": {"path": "/items/{id}"}}
            ],
        },
    )
    mcp = FastMCP(name="t")
    client = UpstreamClient(base_url="http://localhost:9999")
    try:
        counts = load_extensions(mcp, config_source=source, client=client)
    finally:
        await client.aclose()
    assert counts["prompts"] == 1
    assert counts["templates"] == 1  # parameterised URI -> resource template


def test_resource_uri_requires_scheme(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = _write(tmp_path, {"resources": [{"uri": "no-scheme", "name": "x", "backend": {"path": "/x"}}]})
    with pytest.raises(ExtensionsConfigError):
        load_config(source)


def test_prompt_placeholder_mismatch_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = _write(tmp_path, {"prompts": [{"name": "p", "template": "Hi ${missing}", "arguments": []}]})
    with pytest.raises(ExtensionsConfigError):
        load_config(source)


@pytest.mark.asyncio
async def test_missing_optional_config_is_skipped(tmp_path) -> None:  # type: ignore[no-untyped-def]
    mcp = FastMCP(name="t")
    counts = load_extensions(mcp, config_source=str(tmp_path / "nope.json"), client=None)
    assert counts == {"prompts": 0, "resources": 0, "templates": 0}


@pytest.mark.asyncio
async def test_profile_with_extensions_builds(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = _write(
        tmp_path,
        {"prompts": [{"name": "greet", "template": "Hi ${who}", "arguments": [{"name": "who", "required": True}]}]},
    )
    profile = load_profile(
        {
            "id": "x",
            "display_name": "X",
            "tools": {"source": "registry", "include": ["bg.ping"]},
            "extensions": {"source": source},
        },
        env={},
    )
    mcp = await build_app_from_profile(
        profile, _Demo(environment="development", auth_mode="none"), version="1.0.0"
    )
    # Strengthened: the prompt must actually be registered, not merely "built".
    prompts = await mcp.list_prompts()
    assert "greet" in {getattr(p, "name", "") for p in prompts}


def test_prompt_dollar_escape_is_allowed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # `$$` is string.Template's literal-$ escape and must not be read as a
    # placeholder (regression: "cost is $$5" was rejected).
    source = _write(
        tmp_path,
        {
            "prompts": [
                {
                    "name": "price",
                    "template": "cost is $$5 for ${item}",
                    "arguments": [{"name": "item", "required": True}],
                }
            ]
        },
    )
    cfg = load_config(source)  # must not raise
    assert len(cfg.prompts) == 1
