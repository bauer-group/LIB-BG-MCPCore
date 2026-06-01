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


def test_make_cli_forwards_passthrough_to_build(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Regression: make_cli must actually FORWARD lifespan / extra_middleware /
    # extra_sensitive_fragments to build_app_from_profile (the Tier-3 seam), not
    # just accept them. Stub the build + transport so `serve` runs without a server.
    import bg_mcpcore.cli as climod
    from bg_mcpcore import make_cli
    from bg_mcpcore.settings import reset_settings_cache

    for key, value in {"ENVIRONMENT": "development", "AUTH_MODE": "none", "MCP_DISPLAY_NAME": "T"}.items():
        monkeypatch.setenv(key, value)
    reset_settings_cache()

    captured: dict[str, object] = {}

    async def _fake_build(profile, settings, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return object()

    async def _fake_run(mcp, **kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(climod, "build_app_from_profile", _fake_build)
    monkeypatch.setattr(climod, "run_transport", _fake_run)

    sentinel = object()
    profile = load_profile(
        {"id": "demo", "display_name": "Demo", "tools": {"source": "registry", "include": ["bg.ping"]}},
        env={},
    )
    cli = make_cli(
        profile,
        version="9.9.9",
        extra_middleware=[sentinel],
        extra_sensitive_fragments=["x-secret"],
    )

    from typer.testing import CliRunner

    result = CliRunner().invoke(cli, [])  # no subcommand -> serve
    reset_settings_cache()
    assert result.exit_code == 0, result.output
    assert captured["extra_middleware"] == [sentinel]
    assert captured["extra_sensitive_fragments"] == ["x-secret"]
    assert captured["version"] == "9.9.9"


@pytest.mark.asyncio
async def test_least_privilege_registry_source_gets_no_settings() -> None:
    # Guardrail #4 enforced: a registry (non-python) source receives a
    # settings-less ToolContext.
    from bg_mcpcore.tools.registry import register_tool

    seen: dict[str, object] = {}
    register_tool("test.capture_ctx", lambda _mcp, ctx: seen.__setitem__("settings", ctx.settings))
    profile = load_profile(
        {"id": "d", "display_name": "D", "tools": {"source": "registry", "include": ["test.capture_ctx"]}},
        env={},
    )
    await build_app_from_profile(profile, _dev_settings(), version="1.0.0")
    assert seen["settings"] is None


@pytest.mark.asyncio
async def test_unknown_registry_tool_raises_profileerror() -> None:
    from bg_mcpcore.profile.loader import ProfileError

    profile = load_profile(
        {"id": "d", "display_name": "D", "tools": {"source": "registry", "include": ["does.not.exist"]}},
        env={},
    )
    with pytest.raises(ProfileError, match="Unknown registry tool"):
        await build_app_from_profile(profile, _dev_settings(), version="1.0.0")


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
