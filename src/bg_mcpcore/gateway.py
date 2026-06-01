"""Multi-mount gateway — expose N profiles behind one MCP endpoint.

Each profile becomes a sub-server (built by :func:`build_app_from_profile`)
mounted under a name prefix on a single parent FastMCP, so a client sees the
union of every backend's tools as ``<prefix>_<tool>`` behind one URL and one
OAuth wall. This is the optional "central tool availability" mode from the
design vision — opt-in, since most servers bridge a single backend.

Caveats:

* All sub-servers share the one ``BaseMcpSettings`` instance (bg-mcpcore has no
  ``env_prefix``), so per-backend secrets that would collide on the same env var
  name need a bespoke settings type. The common case — a few read-mostly
  backends behind one gateway — works as-is.
* Inbound auth belongs on the PARENT (pass ``auth=`` through to the gateway's
  HTTP layer when you serve it); the sub-servers are composed for their tool /
  resource / prompt surface, not their own auth wall. Build the sub-profiles
  with ``AUTH_MODE`` matching the gateway, or ``none`` behind a trusted proxy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .app import build_app_from_profile
from .observability import get_logger
from .settings.base import BaseMcpSettings

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastmcp import FastMCP

    from .profile.models import Profile

logger = get_logger("bg-mcpcore.gateway")


async def build_gateway(
    mounts: Sequence[tuple[str, Profile]],
    settings: BaseMcpSettings,
    *,
    name: str = "BG MCP Gateway",
    instructions: str = "",
    version: str = "0.0.0",
) -> FastMCP:
    """Mount each ``(prefix, profile)`` under its prefix on one parent FastMCP.

    Returns the parent server. Tool/resource/prompt names from each sub-server
    are namespaced by its prefix (e.g. ``shlink_list_short_urls``), so two
    backends never collide.
    """
    from fastmcp import FastMCP

    if not mounts:
        raise ValueError("build_gateway requires at least one (prefix, profile) mount")

    seen: set[str] = set()
    parent: FastMCP = FastMCP(name=name, instructions=instructions)
    for prefix, profile in mounts:
        if not prefix:
            raise ValueError(f"Mount for profile {profile.id!r} needs a non-empty prefix")
        if prefix in seen:
            raise ValueError(f"Duplicate gateway prefix {prefix!r}")
        seen.add(prefix)
        sub = await build_app_from_profile(profile, settings, version=version)
        # `namespace` is FastMCP 3.x's prefix mechanism (the old `prefix=` kwarg
        # is deprecated); tools surface as ``<namespace>_<tool>``.
        parent.mount(sub, namespace=prefix)
        logger.info("gateway.mounted", prefix=prefix, profile=profile.id)

    logger.info("gateway.built", mounts=len(mounts), prefixes=sorted(seen))
    return parent


__all__ = ["build_gateway"]
