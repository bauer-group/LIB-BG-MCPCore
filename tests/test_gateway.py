"""Multi-mount gateway: N profiles behind one endpoint, namespaced by prefix."""

from __future__ import annotations

import pytest

from bg_mcpcore import BaseMcpSettings, build_gateway, load_profile


class _Demo(BaseMcpSettings):
    mcp_display_name: str = "Gateway"


def _dev_settings() -> _Demo:
    return _Demo(environment="development", auth_mode="none")


def _registry_profile(pid: str):  # type: ignore[no-untyped-def]
    return load_profile(
        {
            "id": pid,
            "display_name": pid,
            "instructions": "backend-less demo",
            "tools": {"source": "registry", "include": ["bg.ping"]},
        },
        env={},
    )


@pytest.mark.asyncio
async def test_gateway_mounts_profiles_under_prefixes() -> None:
    mounts = [("alpha", _registry_profile("a")), ("beta", _registry_profile("b"))]
    gateway = await build_gateway(mounts, _dev_settings(), name="Test Gateway")

    names = sorted(getattr(t, "name", "") for t in await gateway.list_tools())
    # Each backend's `ping` tool is namespaced by its mount prefix, so the two
    # never collide behind the single endpoint.
    assert len(names) == 2
    assert any(n.startswith("alpha") and "ping" in n for n in names), names
    assert any(n.startswith("beta") and "ping" in n for n in names), names


@pytest.mark.asyncio
async def test_gateway_rejects_duplicate_prefix() -> None:
    profile = _registry_profile("x")
    with pytest.raises(ValueError, match="Duplicate gateway prefix"):
        await build_gateway([("dup", profile), ("dup", profile)], _dev_settings())


@pytest.mark.asyncio
async def test_gateway_requires_at_least_one_mount() -> None:
    with pytest.raises(ValueError, match="at least one"):
        await build_gateway([], _dev_settings())
