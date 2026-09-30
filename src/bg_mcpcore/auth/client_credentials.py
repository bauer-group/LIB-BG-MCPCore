"""Outbound OAuth2 client-credentials resolver (``type: client_credentials``).

For an upstream REST API that issues its own service tokens rather than
accepting a static key. The server authenticates as *itself* — no user, no
browser — caches the token, and re-mints it shortly before it expires.

This is deliberately not FastMCP's ``ClientCredentialsOAuthProvider``: that one
authenticates a FastMCP *client* to a protected *MCP server* and discovers its
token endpoint from MCP OAuth metadata. Here the counterparty is an ordinary
REST API with a plain RFC 6749 §4.4 token endpoint, so the exchange is done
directly.

PER-CALL (security guardrail #3): a minted token expires, so it cannot be baked
into the client's default headers at construction — ``default_headers`` is empty
and the credential is applied per request. As with the on-behalf-of resolver,
that means the OpenAPI tool source (which drives the bare client) is not covered;
use a python / ``ctx.request`` tool surface with this resolver. A failed mint
raises rather than returning ``{}``, so a request never goes out unauthenticated.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from typing import Any

from ..observability import get_logger
from ..profile.loader import ProfileError

logger = get_logger("bg-mcpcore.auth.client_credentials")

# Re-mint this many seconds before the token actually expires, so a request is
# never issued with a credential that dies in flight at the upstream.
_REFRESH_MARGIN_SECONDS = 60.0
# Applied when the token endpoint omits expires_in — short, so a wrong guess
# costs an extra mint rather than a window of 401s.
_FALLBACK_LIFETIME_SECONDS = 300.0


class ClientCredentialsError(RuntimeError):
    """The upstream token endpoint did not issue a usable access token."""


class ClientCredentialsResolver:
    """Mints and caches an upstream token via the client-credentials grant."""

    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        scopes: Sequence[str] = (),
        audience: str | None = None,
        header: str = "Authorization",
        scheme: str = "Bearer",
        auth_style: str = "basic",
        timeout: float = 30.0,
    ) -> None:
        if not token_url:
            raise ProfileError("Outbound auth 'client_credentials' requires 'token_url'")
        if not client_id or not client_secret:
            raise ProfileError(
                "Outbound auth 'client_credentials' requires a client id and secret "
                "(set client_id_env / client_secret_env)"
            )
        if auth_style not in ("basic", "post"):
            raise ProfileError(
                f"Outbound auth 'client_credentials' auth_style must be 'basic' or 'post', "
                f"got {auth_style!r}"
            )
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = list(scopes)
        self._audience = audience
        self._header = header
        self._scheme = scheme
        self._auth_style = auth_style
        self._timeout = timeout

        self._token: str | None = None
        self._expires_at: float = 0.0
        # One in-flight mint per resolver: without this, a burst of concurrent
        # tool calls on a cold cache would each hit the token endpoint.
        self._lock = asyncio.Lock()

    def default_headers(self) -> dict[str, str]:
        # Per-call only: a minted token expires, so it must not be frozen into
        # the AsyncClient's default headers at construction.
        return {}

    async def auth_headers(self, _ctx: Any | None) -> dict[str, str]:
        token = await self._get_token()
        return {self._header: f"{self._scheme} {token}".strip()}

    async def _get_token(self) -> str:
        if self._token is not None and time.monotonic() < self._expires_at:
            return self._token
        async with self._lock:
            # Re-check: another coroutine may have minted while we waited.
            if self._token is not None and time.monotonic() < self._expires_at:
                return self._token
            token, lifetime = await self._mint()
            self._token = token
            self._expires_at = time.monotonic() + max(lifetime - _REFRESH_MARGIN_SECONDS, 1.0)
            return token

    async def _mint(self) -> tuple[str, float]:
        import httpx2

        data: dict[str, str] = {"grant_type": "client_credentials"}
        if self._scopes:
            data["scope"] = " ".join(self._scopes)
        if self._audience:
            data["audience"] = self._audience

        # httpx2 distinguishes "no auth" from "client default", so pass the
        # kwarg only in the basic-auth style rather than handing it None.
        post_kwargs: dict[str, Any] = {}
        if self._auth_style == "basic":
            post_kwargs["auth"] = (self._client_id, self._client_secret)
        else:
            data["client_id"] = self._client_id
            data["client_secret"] = self._client_secret

        try:
            async with httpx2.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._token_url, data=data, **post_kwargs)
        except httpx2.HTTPError as exc:
            raise ClientCredentialsError(
                f"token endpoint {self._token_url} unreachable: {exc}"
            ) from exc

        if response.status_code >= 400:
            # The body can echo the client_secret back on some IdPs; never log it.
            raise ClientCredentialsError(
                f"token endpoint {self._token_url} returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ClientCredentialsError("token endpoint returned a non-JSON body") from exc

        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise ClientCredentialsError("token endpoint response carried no access_token")

        raw_expiry = payload.get("expires_in")
        try:
            lifetime = float(raw_expiry) if raw_expiry is not None else _FALLBACK_LIFETIME_SECONDS
        except (TypeError, ValueError):
            lifetime = _FALLBACK_LIFETIME_SECONDS

        logger.info(
            "auth.client_credentials_minted",
            token_url=self._token_url,
            scopes=self._scopes,
            expires_in=lifetime,
        )
        return token, lifetime


def build_client_credentials_resolver(
    cfg: Any, env: Mapping[str, str]
) -> ClientCredentialsResolver:
    """Build the resolver from a profile ``auth.outbound`` (type client_credentials).

    Structure comes from the profile; the credential comes from the environment,
    per the profile contract — never inline a secret.
    """
    extra = getattr(cfg, "model_extra", None) or {}

    client_id_env = extra.get("client_id_env")
    client_secret_env = extra.get("client_secret_env")
    if not client_id_env or not client_secret_env:
        raise ProfileError(
            "Outbound auth 'client_credentials' requires 'client_id_env' and "
            "'client_secret_env' (names of the env vars holding the credential)"
        )
    client_id = env.get(str(client_id_env), "")
    client_secret = env.get(str(client_secret_env), "")
    if not client_id or not client_secret:
        raise ProfileError(
            f"Outbound auth 'client_credentials': {client_id_env} / {client_secret_env} "
            "are unset in the environment"
        )

    scopes = extra.get("scopes") or []
    if not isinstance(scopes, list) or not all(isinstance(x, str) for x in scopes):
        raise ProfileError("Outbound auth 'client_credentials' 'scopes' must be a list of strings")

    return ClientCredentialsResolver(
        token_url=str(extra.get("token_url", "")),
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes,
        audience=extra.get("audience"),
        header=cfg.header or "Authorization",
        scheme=extra.get("scheme", "Bearer"),
        auth_style=str(extra.get("auth_style", "basic")),
        timeout=float(extra.get("timeout", 30.0)),
    )


__all__ = [
    "ClientCredentialsError",
    "ClientCredentialsResolver",
    "build_client_credentials_resolver",
]
