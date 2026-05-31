"""End-to-end: a declarative profile assembles into a working FastMCP server."""

from __future__ import annotations

import pytest

from bg_mcpcore import BaseMcpSettings, build_app_from_profile, load_profile


class _Demo(BaseMcpSettings):
    mcp_display_name: str = "Demo MCP"


def _dev_settings(**over: object) -> _Demo:
    base: dict[str, object] = {"environment": "development", "auth_mode": "none"}
    base.update(over)
    return _Demo(**base)


@pytest.mark.asyncio
async def test_registry_profile_assembles_and_registers_tools() -> None:
    profile = load_profile(
        {
            "id": "demo",
            "display_name": "Demo",
            "instructions": "A backend-less demo server.",
            "tools": {"source": "registry", "include": ["bg.ping"]},
        },
        env={},
    )
    mcp = await build_app_from_profile(profile, _dev_settings(), version="1.0.0")

    tools = await mcp.list_tools()
    names = {getattr(t, "name", "") for t in tools}
    assert "ping" in names


@pytest.mark.asyncio
async def test_python_tool_source_escape_hatch() -> None:
    # The 'python' source imports a dotted register callable - here a built-in
    # registry factory (signature (mcp, ctx)) used as the escape-hatch target.
    profile = load_profile(
        {
            "id": "demo-py",
            "display_name": "Demo Py",
            "tools": {"source": "python", "register": "bg_mcpcore.tools.registry:_register_ping"},
        },
        env={},
    )
    mcp = await build_app_from_profile(profile, _dev_settings(), version="1.0.0")
    tools = await mcp.list_tools()
    assert "ping" in {getattr(t, "name", "") for t in tools}
