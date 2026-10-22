"""pytest11 plugin ([testkit] extra): reusable fixtures for server test suites.

Exposed as a pytest entry point, so installing bg-mcpcore[testkit] makes these
fixtures available without a conftest import. Imports are intentionally light
(stdlib + pytest + bg_mcpcore core) so loading the plugin never breaks an
unrelated project's test collection.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import respx


@pytest.fixture
def reset_bg_mcpcore() -> Iterator[None]:
    """Reset bg-mcpcore global latches (settings cache + logging) around a test."""
    from bg_mcpcore.observability.logging_setup import reset_logging
    from bg_mcpcore.settings import reset_settings_cache

    reset_settings_cache()
    reset_logging()
    yield
    reset_settings_cache()
    reset_logging()


@pytest.fixture
def isolate_env(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Return a helper that deletes env vars matching any of the given prefixes."""

    def _clear(*prefixes: str) -> None:
        for key in list(os.environ):
            if any(key.startswith(prefix) for prefix in prefixes):
                monkeypatch.delenv(key, raising=False)

    return _clear


@pytest.fixture
def valid_base_env() -> dict[str, str]:
    """A minimal env that satisfies BaseMcpSettings' fail-closed invariants (dev/none)."""
    return {
        "ENVIRONMENT": "development",
        "AUTH_MODE": "none",
        "MCP_DISPLAY_NAME": "Test MCP",
    }


@pytest.fixture
def mock_upstream() -> Iterator[respx.Router]:
    """respx router that intercepts bg-mcpcore's httpx2 upstream calls.

    Pair it with :func:`bg_mcpcore.testing.upstream_response` to build the
    mocked responses — see that module for why the two differ.
    """
    from bg_mcpcore.testing.http import mock_upstream as _mock_upstream

    with _mock_upstream() as router:
        yield router
