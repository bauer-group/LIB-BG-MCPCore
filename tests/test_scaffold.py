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
        "tests/test_smoke.py",
    ):
        assert (dest / rel).is_file(), rel


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
