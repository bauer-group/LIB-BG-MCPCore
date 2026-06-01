"""Tests for the process runtime: transport dispatch + dual-stack patch."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from bg_mcpcore.server.runner import patch_dual_stack_socket, run_transport


@pytest.mark.asyncio
async def test_run_transport_rejects_unknown_transport() -> None:
    # An unknown transport must fail clearly before binding a socket.
    with pytest.raises(ValueError, match="Unsupported transport"):
        await run_transport(FastMCP(name="t"), host="", port=8000, transport="carrier-pigeon")


def test_patch_dual_stack_socket_is_idempotent() -> None:
    # Safe to call repeatedly (make_cli calls it on every construction).
    patch_dual_stack_socket()
    patch_dual_stack_socket()  # must not raise or re-wrap
