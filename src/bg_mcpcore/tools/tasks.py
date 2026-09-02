"""Registration of the MCP background-tasks extension ([tasks] extra).

In FastMCP 3 ``task=True`` was a built-in server feature. In FastMCP 4 background
tasks left the core spec and came back as the ``io.modelcontextprotocol/tasks``
extension (SEP-2663), shipped in the separate ``fastmcp-tasks`` package. The
declaration and the engine are now separate things: ``task=`` on a tool is only
an intent, and a server carrying one refuses to *start* unless the extension is
registered — deliberately loud, since the alternative is a tool that silently
never runs as a task.

Two FastMCP rules shape this module:

* ``add_extension`` raises ``ValueError`` on a duplicate identifier, and a
  profile may declare several export tools, so registration must be idempotent.
* A mounted child's extensions do not propagate to the root, but the root's
  ``get_tasks()`` aggregates the child's task tools. A gateway must therefore
  carry the extension itself — see :func:`ensure_tasks_extension` in
  ``gateway.build_gateway``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..observability import get_logger
from ..profile.loader import ProfileError

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger("bg-mcpcore.tools.tasks")


def has_tasks_extension(mcp: FastMCP) -> bool:
    """Whether the tasks extension is already registered on ``mcp``.

    Reads FastMCP's private extension registry — there is no public accessor —
    so a regression test pins this to the shipped FastMCP.
    """
    from fastmcp.utilities.tasks import TASKS_EXTENSION_ID

    return TASKS_EXTENSION_ID in getattr(mcp, "_extensions", {})


def ensure_tasks_extension(mcp: FastMCP) -> bool:
    """Register the tasks extension on ``mcp`` unless it already carries one.

    Returns True if this call registered it. Raises :class:`ProfileError` naming
    the extra when ``fastmcp-tasks`` is not installed, rather than letting an
    ImportError surface from deep inside tool registration.
    """
    if has_tasks_extension(mcp):
        return False
    try:
        from fastmcp_tasks import TasksExtension
    except ImportError as exc:  # pragma: no cover - exercised via the [tasks] extra
        raise ProfileError(
            "Background tasks require the 'tasks' extra: "
            "install bg-mcpcore[tasks] (which pulls fastmcp[tasks])"
        ) from exc

    mcp.add_extension(TasksExtension())
    logger.info("tasks.extension_registered")
    return True


__all__ = ["ensure_tasks_extension", "has_tasks_extension"]
