"""Multi-mount gateway — N profiles behind ONE MCP endpoint, namespaced by prefix.

The optional "central tool availability" mode: instead of one server per backend,
mount several profiles under name prefixes on a single FastMCP. A client sees the
union of every backend's tools (``alpha_ping``, ``beta_ping``, …) behind one URL
and one OAuth wall.

Run:
    export ENVIRONMENT=development AUTH_MODE=none PUBLIC_BASE_URL=http://localhost:8000
    python main.py        # serves alpha_*/beta_* at /mcp, health at /healthz
"""

from __future__ import annotations

import asyncio

from bg_mcpcore import (
    BaseMcpSettings,
    build_gateway,
    get_settings,
    load_profile,
    patch_dual_stack_socket,
    run_transport,
)


class Settings(BaseMcpSettings):
    mcp_display_name: str = "BG MCP Gateway"


def _registry_profile(pid: str):  # type: ignore[no-untyped-def]
    # Two backend-less demo profiles. In a real gateway these would be full
    # OpenAPI/python profiles for different upstreams (e.g. shlink + zammad).
    return load_profile(
        {
            "id": pid,
            "display_name": pid,
            "instructions": f"{pid} backend",
            "tools": {"source": "registry", "include": ["bg.ping"]},
        },
        env={},
    )


async def _main() -> None:
    settings = get_settings(Settings)
    gateway = await build_gateway(
        [
            ("alpha", _registry_profile("alpha")),
            ("beta", _registry_profile("beta")),
        ],
        settings,
        name="BG MCP Gateway",
        instructions="Two demo backends behind one endpoint.",
    )
    await run_transport(
        gateway,
        host=settings.mcp_host,
        port=settings.mcp_port,
        transport=settings.mcp_transport,
    )


if __name__ == "__main__":
    patch_dual_stack_socket()
    asyncio.run(_main())
