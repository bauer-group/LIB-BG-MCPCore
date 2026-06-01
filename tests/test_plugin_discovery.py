"""A third-party tool source (the examples/example_plugin) is discovered + loaded
through the bg_mcpcore.tool_sources entry-point group — no core edit.

The test wraps the *real* example-plugin factory in a fake EntryPoint and
monkeypatches the discovery call, so it exercises both the example code and the
plugin seam without depending on the package being pip-installed first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the example plugin importable without an install step.
_PLUGIN_SRC = Path(__file__).resolve().parent.parent / "examples" / "example_plugin" / "src"
if str(_PLUGIN_SRC) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_SRC))


class _FakeEntryPoint:
    """Mimics an importlib.metadata.EntryPoint for the example plugin."""

    name = "echo"

    def load(self):  # type: ignore[no-untyped-def]
        from bg_mcpcore_echo import create_echo_source

        return create_echo_source


def _patch_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    import bg_mcpcore.plugins as plugins

    def _fake_entry_points(*, group: str | None = None, **_: object):  # type: ignore[no-untyped-def]
        return [_FakeEntryPoint()] if group == "bg_mcpcore.tool_sources" else []

    monkeypatch.setattr(plugins, "entry_points", _fake_entry_points)


def test_third_party_source_is_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    from bg_mcpcore.plugins import build_tool_provider
    from bg_mcpcore.profile.models import ToolsConfig

    _patch_discovery(monkeypatch)
    provider = build_tool_provider(ToolsConfig(source="echo"))
    assert hasattr(provider, "register")


def test_unknown_source_lists_the_discovered_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    from bg_mcpcore.plugins import build_tool_provider
    from bg_mcpcore.profile.loader import ProfileError
    from bg_mcpcore.profile.models import ToolsConfig

    _patch_discovery(monkeypatch)
    # An unknown source error must enumerate the discovered plugin (so operators
    # see that `echo` is available) alongside the built-ins.
    with pytest.raises(ProfileError, match="echo"):
        build_tool_provider(ToolsConfig(source="does-not-exist"))


@pytest.mark.asyncio
async def test_third_party_source_registers_its_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastmcp import FastMCP

    from bg_mcpcore import ToolContext
    from bg_mcpcore.plugins import build_tool_provider
    from bg_mcpcore.profile.models import ToolsConfig

    _patch_discovery(monkeypatch)
    provider = build_tool_provider(ToolsConfig(source="echo"))

    mcp: FastMCP = FastMCP(name="t")
    count = await provider.register(mcp, ToolContext(settings=None))
    assert count == 1
    names = {getattr(t, "name", "") for t in await mcp.list_tools()}
    assert "echo" in names
