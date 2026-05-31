"""Outbound auth resolvers — how the MCP server authenticates to the upstream API.

This is the one load-bearing divergence between servers (security guardrail #3),
so the contract is deliberately split into two mutually-exclusive halves:

* ``default_headers()`` — STATIC credentials applied once at AsyncClient
  construction. Used by gateway-style servers (Shlink's ``X-Api-Key``). These
  also cover FastMCP's bare-httpx-client path used by the OpenAPI tool source.
* ``auth_headers(ctx)`` — PER-CALL dynamic credentials resolved from the request
  context (e.g. a per-user bearer for on-behalf-of). A resolver that resolves
  per-call MUST raise when no credential is available rather than returning ``{}``
  — otherwise the request would silently inherit any static default and defeat a
  fail-closed model. Static resolvers therefore return ``{}`` from
  ``auth_headers`` and per-call resolvers return ``{}`` from ``default_headers``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import SecretStr


@runtime_checkable
class AuthHeaderSource(Protocol):
    """Produces the outbound auth headers for upstream requests."""

    def default_headers(self) -> dict[str, str]:
        """Static headers applied at client construction (empty for per-call resolvers)."""
        ...

    async def auth_headers(self, ctx: Any | None) -> dict[str, str]:
        """Per-request headers (empty for static resolvers; may raise to fail closed)."""
        ...


class NoAuthResolver:
    """Upstream needs no outbound auth."""

    def default_headers(self) -> dict[str, str]:
        return {}

    async def auth_headers(self, ctx: Any | None) -> dict[str, str]:
        return {}


class StaticHeaderResolver:
    """A fixed header, e.g. ``X-Api-Key: <key>`` (Shlink). Applied at construction."""

    def __init__(self, header: str, value: str | SecretStr) -> None:
        self._header = header
        self._value = value.get_secret_value() if isinstance(value, SecretStr) else value

    def default_headers(self) -> dict[str, str]:
        return {self._header: self._value}

    async def auth_headers(self, ctx: Any | None) -> dict[str, str]:
        return {}


class BearerEnvResolver:
    """A static ``Authorization: Bearer <token>`` from configuration."""

    def __init__(self, token: str | SecretStr) -> None:
        self._token = token.get_secret_value() if isinstance(token, SecretStr) else token

    def default_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def auth_headers(self, ctx: Any | None) -> dict[str, str]:
        return {}


__all__ = ["AuthHeaderSource", "BearerEnvResolver", "NoAuthResolver", "StaticHeaderResolver"]
