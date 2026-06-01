"""Tier-3 escape hatch: a per-user, on-behalf-of outbound resolver — FAIL-CLOSED.

This is the load-bearing divergence a backend like Zammad needs: each MCP user's
OWN upstream token is forwarded per call, never a shared service credential. The
``AuthHeaderSource`` contract splits into two mutually-exclusive halves:

* ``default_headers()`` returns ``{}`` — nothing static is ever sent.
* ``auth_headers(ctx)`` resolves the per-user token PER CALL and **raises** when
  none is available, so a request can never silently inherit a default
  credential. That fail-closed behaviour is the whole point — returning ``{}``
  here would let the call fall through unauthenticated.

In a real server the token comes from the validated inbound OAuth session. Here
it is read from an env var (``UPSTREAM_USER_TOKEN``) purely so the example is
runnable — the fail-closed shape is identical.
"""

from __future__ import annotations

import os
from typing import Any


class OnBehalfOfResolver:
    def default_headers(self) -> dict[str, str]:
        return {}  # never send a static/shared credential

    async def auth_headers(self, ctx: Any | None) -> dict[str, str]:
        token = os.environ.get("UPSTREAM_USER_TOKEN")  # stand-in for the per-user session token
        if not token:
            raise PermissionError("no upstream token for this user (fail-closed)")
        return {"Authorization": f"Bearer {token}"}


def make_resolver(cfg: Any) -> OnBehalfOfResolver:
    """Factory referenced by ``auth.outbound.resolver`` (receives the OutboundAuthConfig)."""
    return OnBehalfOfResolver()
