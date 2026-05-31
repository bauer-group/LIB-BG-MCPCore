"""Tests for BaseMcpSettings: composition, fail-closed invariants, the hook,
and structural compatibility with the Phase-1 infra protocols."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bg_mcpcore.auth.storage import build_client_storage
from bg_mcpcore.settings import BaseMcpSettings, get_settings, reset_settings_cache


class _Demo(BaseMcpSettings):
    """Minimal concrete settings: only adds the required display name."""

    mcp_display_name: str = "Demo MCP"


def _valid(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "environment": "development",
        "auth_mode": "oidc",
        "auth_jwt_signing_key": "a-strong-signing-key-0123456789abcdef",
    }
    base.update(over)
    return base


def test_valid_dev_none_mode_ok() -> None:
    s = _Demo(environment="development", auth_mode="none")
    assert s.is_development is True
    assert s.auth_mode == "none"


def test_none_mode_forbidden_in_production() -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE=none is forbidden in production"):
        _Demo(environment="production", auth_mode="none")


def test_active_mode_requires_jwt_signing_key() -> None:
    with pytest.raises(ValidationError, match="AUTH_JWT_SIGNING_KEY is required"):
        _Demo(environment="development", auth_mode="oidc")  # jwt key empty by default


def test_change_me_jwt_key_rejected() -> None:
    with pytest.raises(ValidationError, match="CHANGE_ME"):
        _Demo(**_valid(auth_jwt_signing_key="CHANGE_ME_please"))


def test_redis_requires_storage_encryption_key() -> None:
    with pytest.raises(ValidationError, match="AUTH_STORAGE_ENCRYPTION_KEY is required"):
        _Demo(**_valid(auth_redis_url="redis://localhost:6379/0"))


def test_valid_active_config_constructs() -> None:
    s = _Demo(**_valid())
    assert s.auth_mode == "oidc"
    assert s.mcp_website_url == "https://go.bauer-group.com/mcp-server"


def test_provider_auth_hook_runs_after_core_invariants() -> None:
    class _Strict(BaseMcpSettings):
        mcp_display_name: str = "Strict"

        def validate_provider_auth(self) -> None:
            if not self.oidc_client_id:
                raise ValueError("OIDC_CLIENT_ID required for this server")

    # Core invariants pass (dev + jwt set) but the subclass hook rejects.
    with pytest.raises(ValidationError, match="OIDC_CLIENT_ID required"):
        _Strict(**_valid())
    # ...and succeeds once the per-mode requirement is met.
    ok = _Strict(**_valid(oidc_client_id="abc"))
    assert ok.oidc_client_id == "abc"


def test_display_name_is_required_on_the_base() -> None:
    # The shared base does not default the display name (no two servers share one).
    assert "mcp_display_name" in BaseMcpSettings.model_fields
    assert BaseMcpSettings.model_fields["mcp_display_name"].is_required()


def test_get_settings_caches_per_class() -> None:
    reset_settings_cache()

    class _Cached(BaseMcpSettings):
        mcp_display_name: str = "Cached"
        environment: str = "development"  # type: ignore[assignment]

    a = get_settings(_Cached)
    b = get_settings(_Cached)
    assert a is b
    c = get_settings(_Cached, force_reload=True)
    assert c is not a


@pytest.mark.asyncio
async def test_base_settings_satisfies_storage_protocol(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Proves BaseMcpSettings structurally satisfies StorageSettings: the Phase-1
    # factory accepts it and the disk store round-trips.
    s = _Demo(**_valid(auth_disk_storage_path=str(tmp_path / "oauth")))
    store = build_client_storage(s)
    await store.put("k", {"v": "1"}, collection="c")
    assert await store.get("k", collection="c") == {"v": "1"}
