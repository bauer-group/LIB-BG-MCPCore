"""Tests for settings helpers + the fail-closed persistence invariants.

Covers the exported pure helpers (split_csv / has_value / validate_fernet_key)
and the whitespace-signing-key gap in validate_persistence.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from bg_mcpcore.settings.helpers import (
    has_value,
    split_csv,
    validate_fernet_key,
    validate_persistence,
)

# ── split_csv ────────────────────────────────────────────────────────────────


def test_split_csv_parses_and_trims() -> None:
    assert split_csv("a, b ,c") == ["a", "b", "c"]


def test_split_csv_empty_and_none() -> None:
    assert split_csv("") == []
    assert split_csv(None) == []


def test_split_csv_list_tolerates_non_str_items() -> None:
    # Regression: the transform used item.strip() and crashed on a non-str item.
    assert split_csv([1, 2, ""]) == ["1", "2"]
    assert split_csv(["x ", "", " y"]) == ["x", "y"]


# ── has_value ────────────────────────────────────────────────────────────────


def test_has_value_str_and_secret_consistency() -> None:
    assert has_value(None) is False
    assert has_value("   ") is False
    assert has_value(SecretStr("   ")) is False  # regression: secret was not stripped
    assert has_value("x") is True
    assert has_value(SecretStr("x")) is True


# ── validate_fernet_key ──────────────────────────────────────────────────────


def test_validate_fernet_key_accepts_real_key() -> None:
    validate_fernet_key(Fernet.generate_key().decode())  # must not raise


def test_validate_fernet_key_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="Fernet key"):
        validate_fernet_key("deadbeef" * 4)


# ── validate_persistence (fail-closed invariants) ────────────────────────────


def _persistence(**over: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "auth_mode": "oidc",
        "environment": "development",
        "auth_jwt_signing_key": SecretStr("a-strong-32-byte-signing-key-value-123456"),
        "auth_redis_url": None,
        "auth_storage_encryption_key": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


def test_whitespace_signing_key_rejected_for_active_mode() -> None:
    # Regression: a whitespace-only key was truthy and passed the invariant.
    with pytest.raises(ValueError, match="AUTH_JWT_SIGNING_KEY"):
        validate_persistence(_persistence(auth_jwt_signing_key=SecretStr("   ")))


def test_lowercase_change_me_placeholder_rejected() -> None:
    with pytest.raises(ValueError, match="AUTH_JWT_SIGNING_KEY"):
        validate_persistence(_persistence(auth_jwt_signing_key=SecretStr("change_me_please")))


def test_none_in_production_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden in production"):
        validate_persistence(_persistence(auth_mode="none", environment="production"))


def test_valid_active_mode_passes() -> None:
    validate_persistence(_persistence())  # must not raise


def test_redis_without_storage_key_rejected() -> None:
    with pytest.raises(ValueError, match="AUTH_STORAGE_ENCRYPTION_KEY"):
        validate_persistence(_persistence(auth_redis_url="redis://localhost:6379/0"))
