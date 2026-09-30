"""Outbound HTTP: the upstream client, retry primitives, and the HTTP types.

The response and exception types a tool needs are re-exported here so a server's
own code never imports an HTTP library directly. That indirection is the point:
FastMCP 4 moved its entire stack from ``httpx`` to ``httpx2`` and bg-mcpcore
followed in 2.0.0, which — without this seam — would have been a sweep through
every downstream repo. Re-exported, the next such move is one line in this file.

Import the names from here rather than from ``httpx2``::

    from bg_mcpcore.http import HTTPStatusError, Response

    async def my_tool(ctx: ToolContext) -> dict:
        try:
            response: Response = await ctx.request("GET", "/widgets")
            response.raise_for_status()
        except HTTPStatusError as exc:
            ...
"""

from __future__ import annotations

from httpx2 import (
    ConnectError,
    ConnectTimeout,
    HTTPError,
    HTTPStatusError,
    Request,
    RequestError,
    Response,
    TimeoutException,
    TransportError,
)

from .client import UpstreamClient
from .retry import RETRYABLE_STATUSES, parse_retry_after, sleep_backoff

__all__ = [
    "RETRYABLE_STATUSES",
    "ConnectError",
    "ConnectTimeout",
    "HTTPError",
    "HTTPStatusError",
    "Request",
    "RequestError",
    "Response",
    "TimeoutException",
    "TransportError",
    "UpstreamClient",
    "parse_retry_after",
    "sleep_backoff",
]
