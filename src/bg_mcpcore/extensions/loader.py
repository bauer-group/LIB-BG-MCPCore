"""Load the extensions catalogue and register prompts + resources.

Called by the assembler after the tool surface is built, when a profile declares
an ``extensions`` source. Failure policy: an unreadable/invalid config raises
(fail fast); one bad entry within a valid config is logged + skipped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..observability import get_logger
from .config import ExtensionsConfigError, config_exists, load_config
from .prompts import register_prompts
from .resources import register_resources

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..http.client import UpstreamClient

logger = get_logger("bg-mcpcore.extensions")


def load_extensions(
    mcp: FastMCP,
    *,
    config_source: str,
    client: UpstreamClient | None,
    required: bool = False,
) -> dict[str, int]:
    """Read, validate, and register prompts + resources. Returns counters."""
    empty = {"prompts": 0, "resources": 0, "templates": 0}
    if not config_exists(config_source):
        if required:
            raise ExtensionsConfigError(
                f"extensions config required but not found at {config_source}"
            )
        logger.info("extensions.skipped_no_config", source=config_source)
        return empty

    config = load_config(config_source)
    if config.resources and client is None:
        raise ExtensionsConfigError(
            "extensions declare resources but the profile has no backend (no client)"
        )

    counts = {"prompts": register_prompts(mcp, config.prompts)}
    if client is not None:
        resources, templates = register_resources(mcp, config.resources, client)
        counts["resources"] = resources
        counts["templates"] = templates
    logger.info("extensions.loaded", source=config_source, **counts)
    return counts


__all__ = ["load_extensions"]
