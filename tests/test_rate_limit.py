"""Tests for the lifted rate-limit client-ID resolver + middleware factory."""

from __future__ import annotations

from types import SimpleNamespace

from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware

from bg_mcpcore.server.middleware import build_rate_limit_middleware, resolve_client_id


def test_auth_subject_wins_over_ip() -> None:
    assert (
        resolve_client_id(
            auth_subject="user-1",
            xff_header="203.0.113.5",
            direct_remote_ip="9.9.9.9",
            trusted_proxy_hops=1,
        )
        == "sub:user-1"
    )


def test_single_proxy_hop_reads_rightmost_xff() -> None:
    # Traefik prepends; with 1 trusted hop the rightmost entry is what Traefik saw.
    assert (
        resolve_client_id(
            auth_subject=None,
            xff_header="203.0.113.5, 10.0.0.1",
            direct_remote_ip=None,
            trusted_proxy_hops=1,
        )
        == "ip:10.0.0.1"
    )


def test_two_hops_picks_position_minus_two() -> None:
    assert (
        resolve_client_id(
            auth_subject=None,
            xff_header="client, proxy1, proxy2",
            direct_remote_ip=None,
            trusted_proxy_hops=2,
        )
        == "ip:proxy1"
    )


def test_xff_clipped_when_fewer_hops_than_configured() -> None:
    assert (
        resolve_client_id(
            auth_subject=None,
            xff_header="only-one",
            direct_remote_ip=None,
            trusted_proxy_hops=3,
        )
        == "ip:only-one"
    )


def test_zero_hops_ignores_xff_and_uses_direct_ip() -> None:
    assert (
        resolve_client_id(
            auth_subject=None,
            xff_header="1.2.3.4",
            direct_remote_ip="9.9.9.9",
            trusted_proxy_hops=0,
        )
        == "ip:9.9.9.9"
    )


def test_anonymous_with_nothing_falls_back_to_sentinel() -> None:
    assert (
        resolve_client_id(
            auth_subject=None,
            xff_header=None,
            direct_remote_ip=None,
            trusted_proxy_hops=1,
        )
        == "ip:unknown"
    )


def _settings(**over: object) -> SimpleNamespace:
    base = {
        "rate_limiter_enabled": True,
        "rate_limiter_max_requests_per_second": 10.0,
        "rate_limiter_burst_capacity": None,
        "rate_limiter_global": False,
        "rate_limiter_trusted_proxy_hops": 1,
    }
    base.update(over)
    return SimpleNamespace(**base)


def test_middleware_is_none_when_disabled() -> None:
    assert build_rate_limit_middleware(_settings(rate_limiter_enabled=False)) is None


def test_middleware_built_when_enabled() -> None:
    mw = build_rate_limit_middleware(_settings())
    assert isinstance(mw, RateLimitingMiddleware)
