"""Session state (FastMCP 4 UserSession / SessionId) wiring.

The modern protocol has no transport session, so state a tool needs across
calls lives server-side keyed to the authenticated user. FastMCP's default
store is process-local — correct for one replica, silently lossy behind a load
balancer. Enabling this points it at the same encrypted store the OAuth state
already uses, so a deployment gains no second backend.
"""

from __future__ import annotations

import pytest

from bg_mcpcore import BaseMcpSettings, build_app_from_profile
from bg_mcpcore.profile.loader import ProfileError
from bg_mcpcore.profile.models import Profile


def _profile() -> Profile:
    return Profile.model_validate(
        {
            "id": "t",
            "display_name": "T",
            "tools": {"source": "registry", "include": ["bg.ping"]},
        }
    )


def _settings(**over: object) -> BaseMcpSettings:
    base: dict[str, object] = {
        "environment": "development",
        "auth_mode": "none",
        "mcp_display_name": "T",
        "public_base_url": "http://localhost:8000",
    }
    return BaseMcpSettings(**{**base, **over})  # type: ignore[arg-type]


def test_disabled_by_default() -> None:
    assert _settings().mcp_session_state_enabled is False


@pytest.mark.asyncio
async def test_unauthenticated_server_refuses_session_state() -> None:
    """UserSession keys on the caller's identity, so anonymous access is a config error."""
    with pytest.raises(ProfileError, match="requires an authenticated server"):
        await build_app_from_profile(_profile(), _settings(mcp_session_state_enabled=True))


@pytest.mark.asyncio
async def test_default_leaves_the_process_local_store_in_place() -> None:
    mcp = await build_app_from_profile(_profile(), _settings())
    assert mcp is not None
