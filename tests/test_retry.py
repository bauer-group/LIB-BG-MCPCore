"""Tests for the upstream HTTP retry loop + Retry-After parsing + base-path join.

These exercise the live data path behind every hand-written tool call, which the
rest of the suite did not cover. Backoff is forced to 0 for determinism.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from bg_mcpcore.http.client import UpstreamClient
from bg_mcpcore.http.retry import parse_retry_after


def _client(**over: object) -> UpstreamClient:
    kwargs: dict[str, object] = {
        "base_url": "https://api.test",
        "max_retries": 3,
        "backoff_base": 0.0,
        "backoff_max": 0.0,
    }
    kwargs.update(over)
    return UpstreamClient(**kwargs)  # type: ignore[arg-type]


# ── parse_retry_after ────────────────────────────────────────────────────────


def test_retry_after_delta_seconds() -> None:
    assert parse_retry_after(httpx.Response(503, headers={"retry-after": "120"})) == 120.0


def test_retry_after_negative_is_ignored() -> None:
    assert parse_retry_after(httpx.Response(503, headers={"retry-after": "-5"})) is None


def test_retry_after_garbage_is_ignored() -> None:
    assert parse_retry_after(httpx.Response(503, headers={"retry-after": "soon"})) is None


def test_retry_after_absent_is_none() -> None:
    assert parse_retry_after(httpx.Response(503)) is None


def test_retry_after_http_date_future_is_positive() -> None:
    resp = httpx.Response(503, headers={"retry-after": "Wed, 21 Oct 2099 07:28:00 GMT"})
    delay = parse_retry_after(resp)
    assert delay is not None and delay > 0


def test_retry_after_http_date_past_is_zero() -> None:
    resp = httpx.Response(503, headers={"retry-after": "Wed, 21 Oct 2000 07:28:00 GMT"})
    assert parse_retry_after(resp) == 0.0


# ── retry loop ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_retries_on_503_then_succeeds() -> None:
    client = _client()
    with respx.mock:
        route = respx.get("https://api.test/x").mock(
            side_effect=[httpx.Response(503), httpx.Response(200)]
        )
        resp = await client.request("GET", "/x")
    await client.aclose()
    assert resp.status_code == 200
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_get_retries_on_transport_error_then_succeeds() -> None:
    client = _client()
    with respx.mock:
        route = respx.get("https://api.test/x").mock(
            side_effect=[httpx.ConnectError("down"), httpx.Response(200)]
        )
        resp = await client.request("GET", "/x")
    await client.aclose()
    assert resp.status_code == 200
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_4xx_is_not_retried() -> None:
    client = _client()
    with respx.mock:
        route = respx.get("https://api.test/x").mock(return_value=httpx.Response(404))
        resp = await client.request("GET", "/x")
    await client.aclose()
    assert resp.status_code == 404
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_retries_exhaust_and_return_last_response() -> None:
    client = _client(max_retries=2)
    with respx.mock:
        route = respx.get("https://api.test/x").mock(return_value=httpx.Response(503))
        resp = await client.request("GET", "/x")
    await client.aclose()
    assert resp.status_code == 503
    assert route.call_count == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_post_is_not_retried_on_retryable_status() -> None:
    # A non-idempotent POST must NOT be retried on 503 — the upstream may already
    # have applied it. The first 503 is returned as-is.
    client = _client()
    with respx.mock:
        route = respx.post("https://api.test/x").mock(
            side_effect=[httpx.Response(503), httpx.Response(201)]
        )
        resp = await client.request("POST", "/x")
    await client.aclose()
    assert resp.status_code == 503
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_post_is_retried_on_connect_error() -> None:
    # A connect-phase error proves the request never reached the server, so even a
    # POST is safe to retry.
    client = _client()
    with respx.mock:
        route = respx.post("https://api.test/x").mock(
            side_effect=[httpx.ConnectError("down"), httpx.Response(201)]
        )
        resp = await client.request("POST", "/x")
    await client.aclose()
    assert resp.status_code == 201
    assert route.call_count == 2


# ── base-path normalisation ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_base_path_without_leading_slash_is_normalised() -> None:
    # "rest/v1" (no leading slash) must not fuse onto the host.
    client = _client(api_base_path="rest/v1")
    with respx.mock:
        route = respx.get("https://api.test/rest/v1/widgets").mock(return_value=httpx.Response(200))
        await client.request("GET", "/widgets")
    await client.aclose()
    assert route.called


@pytest.mark.asyncio
async def test_api_base_path_with_leading_slash_still_works() -> None:
    client = _client(api_base_path="/rest/v1")
    with respx.mock:
        route = respx.get("https://api.test/rest/v1/widgets").mock(return_value=httpx.Response(200))
        await client.request("GET", "/widgets")
    await client.aclose()
    assert route.called
