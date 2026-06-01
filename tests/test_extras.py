"""Tests for the central tool library + the [testkit] fixtures/stubs."""

from __future__ import annotations

import pytest

from bg_mcpcore import BaseMcpSettings, build_app_from_profile, load_profile
from bg_mcpcore.testing import InMemoryKeyValue
from bg_mcpcore.tools import available_tools


class _Demo(BaseMcpSettings):
    mcp_display_name: str = "Demo"


def test_available_tools_includes_builtins() -> None:
    tools = available_tools()
    assert "bg.ping" in tools
    assert "bg.health" in tools


@pytest.mark.asyncio
async def test_health_tool_mounts_via_registry() -> None:
    profile = load_profile(
        {
            "id": "h",
            "display_name": "H",
            "backend": {"base_url": "http://localhost:9999"},
            "tools": {"source": "registry", "include": ["bg.health"]},
        },
        env={},
    )
    mcp = await build_app_from_profile(
        profile, _Demo(environment="development", auth_mode="none"), version="1.0.0"
    )
    names = {getattr(t, "name", "") for t in await mcp.list_tools()}
    assert "upstream_health" in names


@pytest.mark.asyncio
async def test_in_memory_keyvalue_stub_roundtrips() -> None:
    kv = InMemoryKeyValue()
    await kv.put("k", {"v": "1"}, collection="c")
    assert await kv.get("k", collection="c") == {"v": "1"}
    assert await kv.delete("k", collection="c") is True
    assert await kv.get("k", collection="c") is None


def test_testkit_fixtures_are_available(valid_base_env) -> None:  # type: ignore[no-untyped-def]
    # valid_base_env comes from the bg_mcpcore[testkit] pytest11 plugin.
    assert valid_base_env["AUTH_MODE"] == "none"
    assert valid_base_env["ENVIRONMENT"] == "development"
