"""Retry/backoff leaf helpers shared by the upstream HTTP client.

Extracted as plain functions/constants (not a base class) per the design review:
the two servers' retry loops are identical, but their auth-injection points are
not, so only the loop primitives are shared.
"""

from __future__ import annotations

import asyncio
import random

import httpx

# Transient statuses worth retrying. 4xx (except 429) are caller errors and are
# never retried.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 0.25
DEFAULT_BACKOFF_MAX = 4.0


def parse_retry_after(response: httpx.Response) -> float | None:
    """Read a Retry-After header (delta-seconds form) if present and sane."""
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


async def sleep_backoff(
    attempt: int,
    *,
    base: float = DEFAULT_BACKOFF_BASE,
    max_delay: float = DEFAULT_BACKOFF_MAX,
    retry_after: float | None = None,
) -> None:
    """Sleep before the next attempt: honour Retry-After, else exp-backoff + jitter."""
    if retry_after is not None:
        delay = min(retry_after, max_delay)
    else:
        ceiling = min(max_delay, base * (2**attempt))
        # Full jitter: a uniform draw in [0, ceiling] de-correlates retriers.
        delay = random.uniform(0, ceiling)
    await asyncio.sleep(delay)


__all__ = [
    "DEFAULT_BACKOFF_BASE",
    "DEFAULT_BACKOFF_MAX",
    "DEFAULT_MAX_RETRIES",
    "RETRYABLE_STATUSES",
    "parse_retry_after",
    "sleep_backoff",
]
