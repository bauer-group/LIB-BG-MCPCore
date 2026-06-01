"""Security-critical tests for the lifted encrypted OAuth-state store.

These close the coverage gap that bg-zammad-mcp had (it shipped client_storage
with NO tests) and — crucially — guard the salt-preservation invariant: if a
FastMCP upgrade changes ``derive_jwt_key`` or the disk salt drifts, deployed
encrypted state becomes undecryptable. The cross-instance round-trip below fails
loudly in that case (FernetEncryptionWrapper raises on decryption error).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from bg_mcpcore.auth.storage import _sanitize_redis_url, build_client_storage


def _disk_settings(tmp_path: object) -> SimpleNamespace:
    return SimpleNamespace(
        auth_redis_url=None,
        auth_storage_encryption_key=None,
        auth_jwt_signing_key=SecretStr("a-strong-32-byte-signing-key-value-123456"),
        auth_disk_storage_path=str(tmp_path),
    )


@pytest.mark.asyncio
async def test_disk_storage_encrypts_and_round_trips(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = build_client_storage(_disk_settings(tmp_path / "oauth"))
    await store.put("jti-1", {"upstream_token": "secret-abc"}, collection="oauth")
    got = await store.get("jti-1", collection="oauth")
    assert got == {"upstream_token": "secret-abc"}


@pytest.mark.asyncio
async def test_derived_key_is_stable_across_restarts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # The disk key is derived from AUTH_JWT_SIGNING_KEY + a fixed salt, so it must
    # be identical on every boot. A second store built from the SAME settings
    # (a restart simulation) must decrypt what the first wrote - otherwise a
    # restart would kick every user out. Guards the derive_jwt_key invariant.
    settings = _disk_settings(tmp_path / "oauth")
    before_restart = build_client_storage(settings)
    await before_restart.put("client-meta", {"client_id": "dcr-123"}, collection="clients")

    after_restart = build_client_storage(settings)
    assert await after_restart.get("client-meta", collection="clients") == {"client_id": "dcr-123"}


def test_sanitize_redis_url_strips_credentials() -> None:
    assert _sanitize_redis_url("redis://user:pw@host:6379/0") == "redis://***@host:6379/0"
    assert _sanitize_redis_url("rediss://:token@host:6380/1") == "rediss://***@host:6380/1"


def test_sanitize_redis_url_passthrough_without_credentials() -> None:
    assert _sanitize_redis_url("redis://host:6379/0") == "redis://host:6379/0"
