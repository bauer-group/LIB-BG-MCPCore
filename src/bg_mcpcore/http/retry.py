"""Retry/backoff leaf helpers shared by the upstream HTTP client.

Extracted as plain functions/constants (not a base class) per the design review:
the two servers' retry loops are identical, but their auth-injection points are
not, so only the loop primitives are shared.
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

# Transient statuses worth retrying. 4xx (except 429) are caller errors and are
# never retried.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

# Methods safe to retry on a retryable STATUS: re-issuing them cannot cause a
# duplicate side effect. POST/PATCH are excluded — the upstream may have already
# applied the first request before returning 5xx (see UpstreamClient.request).
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE", "TRACE"})

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 0.25
DEFAULT_BACKOFF_MAX = 4.0


def parse_retry_after(response: httpx.Response) -> float | None:
    """Read a Retry-After header if present and sane (delta-seconds OR HTTP-date).

    RFC 9110 allows both ``Retry-After: 120`` and ``Retry-After: Wed, 21 Oct 2026
    07:28:00 GMT``; Cloudflare/nginx commonly emit the date form on 429/503.
    """
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        seconds = float(raw)
        return seconds if seconds >= 0 else None
    except ValueError:
        pass
    # HTTP-date form: parse and return the delay until that instant.
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delay = (when - datetime.now(UTC)).total_seconds()
    return max(0.0, delay)


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
