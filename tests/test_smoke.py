"""Skeleton smoke tests.

These prove the mandatory core imports cleanly with NO optional extra installed
and that the version is exposed for hatch's dynamic-version build. Real behaviour
tests arrive with each implementation phase.
"""

from __future__ import annotations

import importlib


def test_version_is_exposed() -> None:
    import bg_mcpcore

    assert isinstance(bg_mcpcore.__version__, str)
    assert bg_mcpcore.__version__.count(".") >= 2  # at least MAJOR.MINOR.PATCH


def test_core_imports_without_extras() -> None:
    # The mandatory core must import without [openapi]/[redis]/[tasks] present.
    module = importlib.import_module("bg_mcpcore")
    assert module is not None
