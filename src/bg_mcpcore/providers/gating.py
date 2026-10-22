"""Which MCP methods an access gate enforces on (shared by the allowlist gates).

Both deny-gates — the Entra tenant allowlist (``providers/middleware.py``) and
the declarative role allowlist (``providers/access_control.py``) — run in
``Middleware.on_request`` and deny by raising a ``PermissionError`` subclass.

FastMCP 4 changed what reaches that hook, so the set of methods a gate sees is
no longer the set it saw in 3.x. Measured against FastMCP 4.0.0, ``on_request``
receives:

* modern (``2026-07-28``) connections — ``server/discover``, ``tools/list``,
  ``tools/call``, ``resources/read``, ``prompts/get`` …
* handshake-era connections — ``initialize``, ``tools/list``, ``tools/call`` …

Notifications are NOT included: they dispatch to ``on_notification``, and only
``on_message`` sees every message. So the practical change for these gates is
that ``server/discover`` (modern) and ``initialize`` (legacy) now pass through
them, where in 3.x neither did.

Both gates already pass through unauthenticated requests (``token is None``), so
this policy only decides what an *authenticated but disallowed* principal may
still do.
"""

from __future__ import annotations

# Methods that merely describe the server rather than act on it. `server/discover`
# is the modern protocol's capability probe; `initialize` is its handshake-era
# counterpart. `ping` is a liveness check.
DISCOVERY_METHODS = frozenset({"server/discover", "initialize", "ping"})

# Methods that enumerate the component surface without executing anything.
LISTING_METHODS = frozenset(
    {"tools/list", "resources/list", "resources/templates/list", "prompts/list"}
)


def should_gate(method: str | None) -> bool:
    """Whether a disallowed principal must be denied this method.

    Called only for a request that carries a token whose tenant/roles failed the
    allowlist. Returning True denies (raises); returning False lets the request
    through to the upstream handler.

    Policy: the connection is allowed to establish, and everything after it is
    denied. A disallowed client completes discovery and then gets a precise,
    attributable ``PermissionError`` on its first real operation, instead of a
    connection that dies at the handshake with an error MCP clients tend to
    surface poorly. The cost is narrow — the client learns the server exists,
    but not what it offers, since ``tools/list`` is still denied.
    """
    return method not in DISCOVERY_METHODS


__all__ = ["DISCOVERY_METHODS", "LISTING_METHODS", "should_gate"]
