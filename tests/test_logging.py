"""Tests for the lifted structured-logging redaction + helpers."""

from __future__ import annotations

from bg_mcpcore.observability.logging_setup import (
    _SENSITIVE_KEY_FRAGMENTS,
    _drop_sensitive_keys,
    _make_sensitive_filter,
    now_iso,
)


def test_drop_sensitive_keys_masks_known_fragments() -> None:
    event = {
        "api_key": "abc",
        "authorization": "Bearer x",
        "client_secret": "s",
        "x-api-key": "k",
        "user": "alice",
        "count": 3,
    }
    out = _drop_sensitive_keys(None, "", dict(event))
    assert out["api_key"] == "***"
    assert out["authorization"] == "***"
    assert out["client_secret"] == "***"
    assert out["x-api-key"] == "***"
    # Non-sensitive keys are untouched.
    assert out["user"] == "alice"
    assert out["count"] == 3


def test_extra_sensitive_fragments_extend_baseline() -> None:
    # A new connector logging a differently-named secret must be redactable.
    filt = _make_sensitive_filter((*_SENSITIVE_KEY_FRAGMENTS, "fints_pin", "pat"))
    out = filt(None, "", {"fints_pin": "1234", "pat": "ghp_x", "name": "ok"})
    assert out["fints_pin"] == "***"
    assert out["pat"] == "***"
    assert out["name"] == "ok"


def test_now_iso_shape() -> None:
    stamp = now_iso()
    assert stamp.endswith("Z")
    assert "T" in stamp
    assert len(stamp) == 20  # YYYY-MM-DDTHH:MM:SSZ
