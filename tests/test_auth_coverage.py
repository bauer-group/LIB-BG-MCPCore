"""Coverage proof: the library's seams support BOTH server auth models.

This is the test that matters for "does bg-mcpcore really cover all cases?". The
two production servers diverge precisely on outbound auth + access control, and
both shapes must work unchanged through the library's seams:

* Shlink (Tier 1) — a static ``X-Api-Key`` baked into the client at construction.
* Zammad (Tier 3) — a per-user on-behalf-of bearer resolved PER CALL, which must
  fail closed (raise) when no user token is available, plus a role-gate
  middleware. All via the python escape hatch + the extra_middleware seam.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from bg_mcpcore import BaseMcpSettings, build_app_from_profile, load_profile
from bg_mcpcore.auth.resolvers import StaticHeaderResolver
from bg_mcpcore.http.client import UpstreamClient


class _Demo(BaseMcpSettings):
    mcp_display_name: str = "Demo"


# ── Shlink-shaped outbound: a static header, baked in at construction ─────────


def test_static_header_resolver_exposes_default_header() -> None:
    assert StaticHeaderResolver("X-Api-Key", "secret").default_headers() == {"X-Api-Key": "secret"}


@pytest.mark.asyncio
async def test_static_header_is_sent_on_every_request() -> None:
    client = UpstreamClient(base_url="https://api.test", auth=StaticHeaderResolver("X-Api-Key", "k"))
    with respx.mock:
        route = respx.get("https://api.test/ping").mock(return_value=httpx.Response(200))
        await client.request("GET", "/ping")
    await client.aclose()
    assert route.calls.last.request.headers["X-Api-Key"] == "k"


# ── Zammad-shaped outbound: per-user on-behalf-of, fail-closed ────────────────


class _OnBehalfOfResolver:
    """A per-user bearer per call; raises when no token (Zammad's OBO model)."""

    def __init__(self, token: str | None) -> None:
        self._token = token

    def default_headers(self) -> dict[str, str]:
        return {}  # nothing static — the credential is strictly per-user

    async def auth_headers(self, ctx: object) -> dict[str, str]:
        if not self._token:
            raise PermissionError("no upstream token resolved for this user")
        return {"Authorization": f"Bearer {self._token}"}


@pytest.mark.asyncio
async def test_obo_resolver_forwards_the_per_user_token() -> None:
    client = UpstreamClient(base_url="https://api.test", auth=_OnBehalfOfResolver("user-tok"))
    with respx.mock:
        route = respx.get("https://api.test/me").mock(return_value=httpx.Response(200))
        await client.request("GET", "/me")
    await client.aclose()
    assert route.calls.last.request.headers["Authorization"] == "Bearer user-tok"


@pytest.mark.asyncio
async def test_obo_resolver_fails_closed_with_no_token() -> None:
    # The request must raise BEFORE any network call — never inherit a default.
    client = UpstreamClient(base_url="https://api.test", auth=_OnBehalfOfResolver(None))
    with pytest.raises(PermissionError):
        await client.request("GET", "/me")
    await client.aclose()


# ── Zammad-shaped access control: a role-gate middleware via the seam ─────────


@pytest.mark.asyncio
async def test_role_gate_middleware_wires_via_extra_middleware() -> None:
    from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

    seen: list[str] = []

    class _RoleGate(Middleware):
        async def on_request(self, ctx: MiddlewareContext, call_next: CallNext):  # type: ignore[type-arg]
            seen.append("checked")
            return await call_next(ctx)

    profile = load_profile(
        {"id": "z", "display_name": "Z", "tools": {"source": "registry", "include": ["bg.ping"]}},
        env={},
    )
    mcp = await build_app_from_profile(
        profile,
        _Demo(environment="development", auth_mode="none"),
        version="1.0.0",
        extra_middleware=[_RoleGate()],
    )
    # The middleware was accepted and the Zammad-shaped server assembled cleanly.
    assert mcp is not None
