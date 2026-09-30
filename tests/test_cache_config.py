"""The profile `cache` block → FastMCP 4 response-freshness hints.

A caching client may reuse a result instead of making another round trip. The
security-relevant half is `scope`: `"public"` permits a SHARED cache (a proxy,
a fleet-wide store) to hold the entry, so a per-user result published as public
could be served to a different user. The default is therefore `"private"`, and
these tests pin that default.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bg_mcpcore.profile.models import CacheConfig, Profile


def _profile(**cache: object) -> Profile:
    return Profile.model_validate(
        {
            "id": "t",
            "display_name": "T",
            "tools": {"source": "registry", "include": ["bg.ping"]},
            **({"cache": cache} if cache else {}),
        }
    )


def test_cache_defaults_to_private_scope() -> None:
    """A result derived from the caller's identity must never land in a shared cache."""
    assert CacheConfig(ttl=300).scope == "private"


def test_cache_is_absent_unless_declared() -> None:
    assert _profile().cache is None


def test_cache_block_is_parsed() -> None:
    profile = _profile(ttl=300, scope="public")
    assert profile.cache is not None
    assert (profile.cache.ttl, profile.cache.scope) == (300, "public")


@pytest.mark.parametrize("ttl", [0, -1, 86_401])
def test_ttl_is_bounded(ttl: int) -> None:
    """A zero/negative TTL is meaningless and an unbounded one is a stale-data bug."""
    with pytest.raises(ValidationError):
        _profile(ttl=ttl)


def test_unknown_scope_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _profile(ttl=60, scope="shared")


def test_unknown_cache_field_is_rejected() -> None:
    """extra="forbid" catches a typo instead of silently ignoring it."""
    with pytest.raises(ValidationError):
        _profile(ttl=60, scopes="public")


@pytest.mark.asyncio
async def test_cache_reaches_the_built_server() -> None:
    from bg_mcpcore import BaseMcpSettings, build_app_from_profile

    settings = BaseMcpSettings(
        environment="development",  # type: ignore[arg-type]
        auth_mode="none",  # type: ignore[arg-type]
        mcp_display_name="T",
        public_base_url="http://localhost:8000",
    )
    mcp = await build_app_from_profile(_profile(ttl=120, scope="public"), settings)
    hints = mcp._mcp_server.cache_hints
    assert hints, "profile cache block did not reach the server"
    # Applied to the cacheable results, in milliseconds; tool calls are excluded.
    assert "tools/list" in hints and "resources/read" in hints
    assert "tools/call" not in hints
    assert all(h.ttl_ms == 120_000 and h.scope == "public" for h in hints.values())


@pytest.mark.asyncio
async def test_no_cache_block_leaves_the_server_untouched() -> None:
    from bg_mcpcore import BaseMcpSettings, build_app_from_profile

    settings = BaseMcpSettings(
        environment="development",  # type: ignore[arg-type]
        auth_mode="none",  # type: ignore[arg-type]
        mcp_display_name="T",
        public_base_url="http://localhost:8000",
    )
    mcp = await build_app_from_profile(_profile(), settings)
    assert mcp._mcp_server.cache_hints == {}
