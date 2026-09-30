"""Outbound OAuth2 client-credentials resolver: caching, refresh, fail-closed."""

from __future__ import annotations

import pytest

from bg_mcpcore.auth.client_credentials import (
    ClientCredentialsError,
    ClientCredentialsResolver,
    build_client_credentials_resolver,
)
from bg_mcpcore.profile.loader import ProfileError
from bg_mcpcore.profile.models import OutboundAuthConfig
from bg_mcpcore.testing import mock_upstream, upstream_response

TOKEN_URL = "https://idp.test/oauth/token"


def _resolver(**over: object) -> ClientCredentialsResolver:
    kwargs: dict[str, object] = {
        "token_url": TOKEN_URL,
        "client_id": "svc",
        "client_secret": "shh",
        "scopes": ["api.read"],
    }
    return ClientCredentialsResolver(**{**kwargs, **over})  # type: ignore[arg-type]


# ── the guardrail: per-call only, never baked in ─────────────────────────────


def test_default_headers_are_empty() -> None:
    """A minted token expires, so it must never be frozen into the client."""
    assert _resolver().default_headers() == {}


# ── minting ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mints_and_applies_a_bearer() -> None:
    with mock_upstream() as router:
        router.post(TOKEN_URL).mock(
            return_value=upstream_response(200, json={"access_token": "tok-1", "expires_in": 3600})
        )
        headers = await _resolver().auth_headers(None)
    assert headers == {"Authorization": "Bearer tok-1"}


@pytest.mark.asyncio
async def test_token_is_cached_across_calls() -> None:
    """A second call must not hit the token endpoint again."""
    resolver = _resolver()
    with mock_upstream() as router:
        route = router.post(TOKEN_URL).mock(
            return_value=upstream_response(200, json={"access_token": "tok-1", "expires_in": 3600})
        )
        await resolver.auth_headers(None)
        await resolver.auth_headers(None)
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_expiry_is_pulled_in_by_the_refresh_margin() -> None:
    """The cache must expire BEFORE the upstream token does, never after."""
    import time

    resolver = _resolver()
    with mock_upstream() as router:
        router.post(TOKEN_URL).mock(
            return_value=upstream_response(200, json={"access_token": "t", "expires_in": 3600})
        )
        await resolver.auth_headers(None)
    remaining = resolver._expires_at - time.monotonic()
    assert 3500 < remaining < 3600, remaining


@pytest.mark.asyncio
async def test_an_expired_token_is_reminted() -> None:
    resolver = _resolver()
    with mock_upstream() as router:
        route = router.post(TOKEN_URL).mock(
            side_effect=[
                upstream_response(200, json={"access_token": "tok-1", "expires_in": 3600}),
                upstream_response(200, json={"access_token": "tok-2", "expires_in": 3600}),
            ]
        )
        first = await resolver.auth_headers(None)
        resolver._expires_at = 0.0  # simulate the cached token ageing out
        second = await resolver.auth_headers(None)
    assert route.call_count == 2
    assert first["Authorization"] == "Bearer tok-1"
    assert second["Authorization"] == "Bearer tok-2"


@pytest.mark.asyncio
async def test_a_very_short_token_still_gets_a_positive_lifetime() -> None:
    """expires_in under the margin must not yield a zero/negative cache window."""
    import time

    resolver = _resolver()
    with mock_upstream() as router:
        router.post(TOKEN_URL).mock(
            return_value=upstream_response(200, json={"access_token": "t", "expires_in": 1})
        )
        await resolver.auth_headers(None)
    assert resolver._expires_at > time.monotonic()


@pytest.mark.asyncio
async def test_concurrent_cold_calls_mint_once() -> None:
    """A burst on a cold cache must not stampede the token endpoint."""
    import asyncio

    resolver = _resolver()
    with mock_upstream() as router:
        route = router.post(TOKEN_URL).mock(
            return_value=upstream_response(200, json={"access_token": "tok", "expires_in": 3600})
        )
        await asyncio.gather(*(resolver.auth_headers(None) for _ in range(8)))
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_scope_and_audience_are_sent() -> None:
    with mock_upstream() as router:
        route = router.post(TOKEN_URL).mock(
            return_value=upstream_response(200, json={"access_token": "t", "expires_in": 60})
        )
        await _resolver(scopes=["a", "b"], audience="https://api.test").auth_headers(None)
    body = route.calls.last.request.content.decode()
    assert "grant_type=client_credentials" in body
    assert "scope=a+b" in body
    assert "audience=https" in body


@pytest.mark.asyncio
async def test_post_style_sends_credentials_in_the_body() -> None:
    with mock_upstream() as router:
        route = router.post(TOKEN_URL).mock(
            return_value=upstream_response(200, json={"access_token": "t", "expires_in": 60})
        )
        await _resolver(auth_style="post").auth_headers(None)
    assert "client_secret=shh" in route.calls.last.request.content.decode()


# ── fail closed ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {"status_code": 401, "json": {"error": "invalid_client"}},
        {"status_code": 200, "json": {"not_a_token": "x"}},
        {"status_code": 200, "text": "not json"},
    ],
)
async def test_a_bad_token_response_raises(response: dict[str, object]) -> None:
    """Never return {} — that would let the request go out unauthenticated."""
    with mock_upstream() as router:
        router.post(TOKEN_URL).mock(return_value=upstream_response(**response))  # type: ignore[arg-type]
        with pytest.raises(ClientCredentialsError):
            await _resolver().auth_headers(None)


@pytest.mark.asyncio
async def test_unreachable_token_endpoint_raises() -> None:
    from bg_mcpcore.http import ConnectError

    with mock_upstream() as router:
        router.post(TOKEN_URL).mock(side_effect=ConnectError("down"))
        with pytest.raises(ClientCredentialsError, match="unreachable"):
            await _resolver().auth_headers(None)


@pytest.mark.asyncio
async def test_secret_is_not_in_the_error_message() -> None:
    with mock_upstream() as router:
        router.post(TOKEN_URL).mock(
            return_value=upstream_response(400, json={"error": "bad", "client_secret": "shh"})
        )
        with pytest.raises(ClientCredentialsError) as excinfo:
            await _resolver().auth_headers(None)
    assert "shh" not in str(excinfo.value)


# ── profile wiring ───────────────────────────────────────────────────────────


def test_builder_reads_credentials_from_the_environment() -> None:
    cfg = OutboundAuthConfig.model_validate(
        {
            "type": "client_credentials",
            "token_url": TOKEN_URL,
            "client_id_env": "SVC_ID",
            "client_secret_env": "SVC_SECRET",
            "scopes": ["api.read"],
        }
    )
    resolver = build_client_credentials_resolver(cfg, {"SVC_ID": "svc", "SVC_SECRET": "shh"})
    assert isinstance(resolver, ClientCredentialsResolver)


def test_builder_fails_when_the_env_vars_are_unset() -> None:
    cfg = OutboundAuthConfig.model_validate(
        {
            "type": "client_credentials",
            "token_url": TOKEN_URL,
            "client_id_env": "SVC_ID",
            "client_secret_env": "SVC_SECRET",
        }
    )
    with pytest.raises(ProfileError, match="unset in the environment"):
        build_client_credentials_resolver(cfg, {})


def test_builder_requires_a_token_url() -> None:
    cfg = OutboundAuthConfig.model_validate(
        {"type": "client_credentials", "client_id_env": "A", "client_secret_env": "B"}
    )
    with pytest.raises(ProfileError, match="token_url"):
        build_client_credentials_resolver(cfg, {"A": "x", "B": "y"})


def test_dispatch_from_plugins() -> None:
    from bg_mcpcore.plugins import build_outbound_resolver

    cfg = OutboundAuthConfig.model_validate(
        {
            "type": "client_credentials",
            "token_url": TOKEN_URL,
            "client_id_env": "SVC_ID",
            "client_secret_env": "SVC_SECRET",
        }
    )
    resolver = build_outbound_resolver(cfg, env={"SVC_ID": "svc", "SVC_SECRET": "shh"})
    assert isinstance(resolver, ClientCredentialsResolver)
