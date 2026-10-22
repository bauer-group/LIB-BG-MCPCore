"""Upstream-HTTP mocking helpers ([testkit] extra).

bg-mcpcore issues its upstream calls with ``httpx2`` (FastMCP 4's HTTP stack).
``respx`` is still the mocking library of record, but it predates httpx2 and has
two quirks that would otherwise be copy-pasted into every server's test suite:

* it must be told to patch the httpx2 transports (``using="httpcore2"``), and
* it models a *mocked response* with an ``httpx`` (v1) ``Response`` object even
  when the client under test is httpx2 — an internal ``isinstance`` check in
  respx's router enforces this. The client still receives a real
  ``httpx2.Response``; only the mock-side object differs.

Both quirks live here so a test reads as if neither existed.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

    import respx


def upstream_response(status_code: int = 200, **kwargs: Any) -> Any:
    """Build a mocked response for a :func:`mock_upstream` route.

    Takes the same arguments as an ``httpx.Response`` (``json=``, ``text=``,
    ``headers=`` ...). Use it for a route's ``return_value``; for a route's
    ``side_effect`` *exception*, raise the real thing from ``bg_mcpcore.http``
    (e.g. ``ConnectError``), which passes through to the caller unchanged.
    """
    import httpx  # respx's own response model — see the module docstring.

    return httpx.Response(status_code, **kwargs)


@contextmanager
def mock_upstream() -> Iterator[respx.Router]:
    """Intercept bg-mcpcore's httpx2 upstream traffic, yielding a respx router.

        with mock_upstream() as router:
            router.get("https://api.test/widgets").mock(
                return_value=upstream_response(200, json={"items": []})
            )
    """
    import respx

    with respx.mock(using="httpcore2") as router:
        yield router


__all__ = ["mock_upstream", "upstream_response"]
