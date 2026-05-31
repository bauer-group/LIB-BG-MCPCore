"""Tests for the lifted operational routes (healthz / logo / index).

Light smoke tests: registration must be graceful when brand assets are missing
(logged + skipped, never raised) and must succeed when present.
"""

from __future__ import annotations

from fastmcp import FastMCP

from bg_mcpcore.server.routes import (
    register_healthz_route,
    register_index_route,
    register_logo_route,
)


def test_healthz_registers() -> None:
    mcp = FastMCP(name="test")
    register_healthz_route(mcp)  # must not raise


def test_logo_and_index_graceful_when_assets_missing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    mcp = FastMCP(name="test")
    # Empty dir -> missing logo.svg / index.html -> warn + skip, no exception.
    register_logo_route(mcp, static_dir=tmp_path)
    register_index_route(mcp, static_dir=tmp_path, template_vars={"version": "1.0"})


def test_logo_and_index_register_when_assets_present(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "logo.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "index.html").write_text("version=$version env=$environment", encoding="utf-8")
    mcp = FastMCP(name="test")
    register_logo_route(mcp, static_dir=tmp_path)
    register_index_route(
        mcp,
        static_dir=tmp_path,
        template_vars={"version": "1.2.3", "environment": "test"},
    )
