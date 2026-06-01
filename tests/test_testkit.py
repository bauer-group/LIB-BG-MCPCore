"""Tests for the [testkit] pytest11 fixtures — they ship to consumer suites, so
untested helpers would be a trap. The fixtures are provided by the auto-loaded
bg_mcpcore_testkit plugin (entry point), not a local conftest.
"""

from __future__ import annotations

import os


def test_isolate_env_removes_prefixed(isolate_env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ZZTEST_A", "1")
    monkeypatch.setenv("ZZTEST_B", "2")
    isolate_env("ZZTEST_")
    assert not any(key.startswith("ZZTEST_") for key in os.environ)


def test_reset_bg_mcpcore_runs_clean(reset_bg_mcpcore) -> None:  # type: ignore[no-untyped-def]
    # Requesting the fixture exercises its setup + teardown (settings-cache +
    # logging reset). It yields None; reaching here proves the reset hooks import
    # and run without error.
    assert reset_bg_mcpcore is None


def test_valid_base_env_satisfies_invariants(isolate_env, valid_base_env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from bg_mcpcore.settings.base import BaseMcpSettings

    isolate_env("AUTH_", "OIDC_", "MCP_", "ENVIRONMENT", "PUBLIC_", "SENTRY_", "RATE_", "LOG_")
    for key, value in valid_base_env.items():
        monkeypatch.setenv(key, value)
    settings = BaseMcpSettings()  # must construct cleanly with the dev/none base env
    assert str(settings.auth_mode) == "none"
    assert str(settings.environment) == "development"
