"""The 1.x -> 2.0 codemod: rewrites what it should, leaves alone what it must."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "migrate_v2", Path(__file__).resolve().parent.parent / "scripts" / "migrate_v2.py"
)
assert _SPEC and _SPEC.loader
migrate_v2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(migrate_v2)


TOOL_FILE = '''"""Tools."""

from __future__ import annotations

import httpx

from bg_mcpcore import ToolContext


async def get(ctx: ToolContext) -> dict:
    resp: httpx.Response = await ctx.request("GET", "/x")
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        return {}
    return resp.json()
'''


def test_rewrites_types_and_imports(tmp_path: Path) -> None:
    target = tmp_path / "my_tools.py"
    target.write_text(TOOL_FILE, encoding="utf-8")
    migrate_v2.main([str(tmp_path), "--write"])
    out = target.read_text(encoding="utf-8")

    assert "from bg_mcpcore.http import HTTPStatusError, Response" in out
    assert "resp: Response = " in out
    assert "except HTTPStatusError:" in out
    assert "import httpx" not in out


def test_leaves_own_outbound_httpx_alone(tmp_path: Path) -> None:
    """A tool's own httpx client is unaffected by the migration and stays valid."""
    source = 'import httpx\n\n\nasync def f():\n    async with httpx.AsyncClient() as c:\n        return await c.get("https://x")\n'
    target = tmp_path / "other.py"
    target.write_text(source, encoding="utf-8")
    migrate_v2.main([str(tmp_path), "--write"])
    assert target.read_text(encoding="utf-8") == source


def test_keeps_names_it_does_not_reexport(tmp_path: Path) -> None:
    """Only the documented re-exports move; anything else stays on httpx."""
    source = (
        "from httpx import HTTPStatusError, Limits\n\n"
        "from bg_mcpcore import ToolContext\n\n\n"
        "def f(ctx: ToolContext):\n    return HTTPStatusError, Limits\n"
    )
    target = tmp_path / "mixed.py"
    target.write_text(source, encoding="utf-8")
    migrate_v2.main([str(tmp_path), "--write"])
    out = target.read_text(encoding="utf-8")
    assert "from httpx import Limits" in out
    assert "from bg_mcpcore.http import HTTPStatusError" in out


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "my_tools.py"
    target.write_text(TOOL_FILE, encoding="utf-8")
    migrate_v2.main([str(tmp_path)])
    assert target.read_text(encoding="utf-8") == TOOL_FILE


@pytest.mark.parametrize("name", migrate_v2.REEXPORTED)
def test_every_rewritten_name_actually_exists(name: str) -> None:
    """The codemod must never rewrite to a name bg_mcpcore.http does not export."""
    from bg_mcpcore import http

    assert hasattr(http, name), name
    assert name in http.__all__
