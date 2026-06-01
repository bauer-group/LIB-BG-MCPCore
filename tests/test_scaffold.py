"""The `bg-mcpcore new <name>` scaffolder generates a valid Tier-1 server."""

from __future__ import annotations

import pytest

from bg_mcpcore import __version__
from bg_mcpcore.scaffold import ScaffoldError, scaffold


def test_scaffold_emits_expected_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    dest = scaffold("mautic", tmp_path)
    assert dest == tmp_path / "mautic"
    for rel in (
        "pyproject.toml",
        "README.md",
        ".env.example",
        "src/main.py",
        "src/config.py",
        "src/profiles/mautic.json",
        "src/static/index.html",
        "src/static/logo.svg",
        "tests/test_smoke.py",
    ):
        assert (dest / rel).is_file(), rel


def test_scaffolded_landing_page_renders(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The generated / page is the full reference design: name baked in, runtime
    placeholders filled by the index route, CSS braces preserved, icon served."""
    from fastmcp import FastMCP
    from starlette.testclient import TestClient

    from bg_mcpcore.server.routes import register_index_route, register_logo_route

    dest = scaffold("mautic", tmp_path)
    static = dest / "src" / "static"

    # The baked file keeps the runtime placeholders for the index route to fill.
    raw = (static / "index.html").read_text(encoding="utf-8")
    assert "BAUER GROUP Mautic" in raw  # display name baked at scaffold time
    assert "$version" in raw and "$mcp_url" in raw  # runtime placeholders preserved

    mcp = FastMCP(name="test")
    register_index_route(
        mcp,
        static_dir=static,
        template_vars={
            "version": "9.9.9",
            "protocol": "MCP / Streamable HTTP",
            "environment": "development",
            "auth_mode": "none",
            "mcp_url": "http://localhost:8000/mcp",
        },
    )
    register_logo_route(mcp, static_dir=static)
    with TestClient(mcp.http_app()) as client:
        page = client.get("/")
        logo = client.get("/logo.svg")

    assert page.status_code == 200
    assert "BAUER GROUP Mautic" in page.text  # name in the rendered page
    assert "9.9.9" in page.text  # version substituted at runtime
    assert "http://localhost:8000/mcp" in page.text  # mcp_url substituted
    assert "$version" not in page.text  # placeholder consumed
    assert "box-sizing" in page.text  # full CSS design preserved (not a stub)
    assert logo.status_code == 200
    assert "svg" in logo.text and logo.headers["content-type"].startswith("image/svg")


def test_scaffolded_profile_is_valid(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from bg_mcpcore import load_profile

    dest = scaffold("my-api", tmp_path)
    profile = load_profile(
        str(dest / "src" / "profiles" / "my-api.json"),
        env={"MY_API_URL": "https://api.example.com"},
    )
    assert profile.id == "my-api"
    assert profile.backend is not None
    assert profile.backend.base_url == "https://api.example.com"
    # The single tool source is the OpenAPI one.
    assert profile.tool_sources[0].source == "openapi"


def test_scaffold_pins_current_version(tmp_path) -> None:  # type: ignore[no-untyped-def]
    dest = scaffold("widget", tmp_path)
    pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
    assert f"@v{__version__}" in pyproject
    assert 'name = "bg-widget-mcp"' in pyproject


def test_scaffold_rejects_invalid_name(tmp_path) -> None:  # type: ignore[no-untyped-def]
    for bad in ("1api", "my_api", "has space", "-leading", "trailing-"):
        with pytest.raises(ScaffoldError, match="Invalid name"):
            scaffold(bad, tmp_path)


def test_scaffold_normalises_case(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A mixed-case name is lowercased to the slug convention rather than rejected.
    dest = scaffold("Mautic", tmp_path)
    assert dest == tmp_path / "mautic"


def test_scaffold_refuses_nonempty_destination(tmp_path) -> None:  # type: ignore[no-untyped-def]
    scaffold("dup", tmp_path)
    with pytest.raises(ScaffoldError, match="not empty"):
        scaffold("dup", tmp_path)
    # force overwrites.
    assert scaffold("dup", tmp_path, force=True) == tmp_path / "dup"
