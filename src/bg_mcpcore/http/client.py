"""Async upstream HTTP client with a dual outbound-auth path.

The dual path is mandatory (security guardrail #3): static credentials are folded
into the AsyncClient's default headers at construction (so FastMCP's bare
``httpx_client`` path used by the OpenAPI tool source is covered), while per-call
resolvers contribute headers per request via ``auth_headers(ctx)``. A per-call
resolver that cannot produce a credential raises, so a request never silently
inherits a static default it shouldn't.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..auth.resolvers import AuthHeaderSource, NoAuthResolver
from ..observability import get_logger
from .retry import (
    DEFAULT_BACKOFF_BASE,
    DEFAULT_BACKOFF_MAX,
    DEFAULT_MAX_RETRIES,
    IDEMPOTENT_METHODS,
    RETRYABLE_STATUSES,
    parse_retry_after,
    sleep_backoff,
)

logger = get_logger("bg-mcpcore.http")


class UpstreamClient:
    """Thin httpx wrapper: base URL, timeouts, outbound auth, retry/backoff."""

    def __init__(
        self,
        *,
        base_url: str,
        api_base_path: str = "",
        auth: AuthHeaderSource | None = None,
        timeout: float = 30.0,
        verify_tls: bool = True,
        user_agent: str = "bg-mcpcore",
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        backoff_max: float = DEFAULT_BACKOFF_MAX,
    ) -> None:
        self._auth: AuthHeaderSource = auth or NoAuthResolver()
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        # Normalise api_base_path to a leading-slash, no-trailing-slash suffix so a
        # value written without a leading slash ("rest/v1") does not fuse onto the
        # host ("https://hostrest/v1"). Empty stays empty.
        trimmed = api_base_path.strip("/")
        full_base = base_url.rstrip("/") + (f"/{trimmed}" if trimmed else "")
        headers = {"User-Agent": user_agent, **self._auth.default_headers()}
        self._client = httpx.AsyncClient(
            base_url=full_base,
            timeout=httpx.Timeout(timeout),
            verify=verify_tls,
            headers=headers,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=16),
        )

    @property
    def httpx_client(self) -> httpx.AsyncClient:
        """The raw client — handed to FastMCP.from_openapi by the OpenAPI source."""
        return self._client

    async def request(
        self,
        method: str,
        path: str,
        *,
        ctx: Any | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Issue a request, merging per-call auth headers and retrying transients."""
        merged = dict(headers or {})
        merged.update(await self._auth.auth_headers(ctx))
        # A non-idempotent method (POST/PATCH) must not be retried on a retryable
        # STATUS — the upstream may have already applied it before returning 5xx,
        # so re-issuing risks a duplicate side effect. Such methods are still
        # retried on a connect-phase TransportError, where the request provably
        # never reached the server.
        idempotent = method.upper() in IDEMPOTENT_METHODS
        attempt = 0
        while True:
            try:
                response = await self._client.request(
                    method, path, headers=merged or None, **kwargs
                )
            except httpx.TransportError as exc:
                connect_only = isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))
                if (idempotent or connect_only) and attempt < self._max_retries:
                    await sleep_backoff(attempt, base=self._backoff_base, max_delay=self._backoff_max)
                    attempt += 1
                    continue
                raise
            if (
                response.status_code in RETRYABLE_STATUSES
                and idempotent
                and attempt < self._max_retries
            ):
                await sleep_backoff(
                    attempt,
                    base=self._backoff_base,
                    max_delay=self._backoff_max,
                    retry_after=parse_retry_after(response),
                )
                attempt += 1
                continue
            return response

    async def health(self, path: str = "/", *, headers: dict[str, str] | None = None) -> int:
        """GET ``path`` and return the status code (for liveness probes)."""
        response = await self._client.get(path, headers=headers)
        return response.status_code

    async def __aenter__(self) -> UpstreamClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["UpstreamClient"]
