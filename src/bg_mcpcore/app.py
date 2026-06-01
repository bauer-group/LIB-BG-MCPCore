"""The orchestrator: assemble a FastMCP server from a profile + settings.

Fixed spine, with hook seams for the parts that genuinely differ:
    setup_logging -> init_sentry -> inbound auth -> outbound client
    -> construct (constructing source) OR build bare FastMCP
    -> rate-limit middleware FIRST -> register tool sources
    -> healthz/logo/index routes -> banner

The construct-vs-register fork is resolved here: if a tool source is a
ConstructingToolProvider (OpenAPI), it builds the FastMCP instance; otherwise a
bare instance is built and the registering sources add to it.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .http.client import UpstreamClient
from .observability import get_logger, init_sentry, print_banner, setup_logging, warn_no_auth
from .plugins import (
    build_auth_middleware,
    build_auth_provider,
    build_outbound_resolver,
    build_tool_provider,
)
from .profile.loader import ProfileError
from .profile.models import Profile
from .server.middleware import build_rate_limit_middleware
from .server.routes import register_healthz_route, register_index_route, register_logo_route
from .settings.base import BaseMcpSettings
from .tools.protocol import ToolContext

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastmcp import FastMCP

logger = get_logger("bg-mcpcore.app")


async def build_app_from_profile(
    profile: Profile,
    settings: BaseMcpSettings,
    *,
    version: str = "0.0.0",
    static_dir: str | Path | None = None,
    lifespan: Any | None = None,
    extra_sensitive_fragments: Sequence[str] = (),
    extra_middleware: Sequence[Any] = (),
) -> FastMCP:
    """Build a fully wired FastMCP instance from a declarative profile."""
    from fastmcp import FastMCP
    from mcp.types import Icon

    setup_logging(
        log_format=settings.log_format,
        log_level=settings.log_level,
        extra_sensitive_fragments=extra_sensitive_fragments,
    )
    init_sentry(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or str(settings.environment),
        traces_sample_rate=settings.sentry_traces_sample_rate,
        release=version,
    )

    auth_provider = build_auth_provider(settings)

    client: UpstreamClient | None = None
    if profile.backend is not None:
        resolver = build_outbound_resolver(profile.auth.outbound)
        client = UpstreamClient(
            base_url=profile.backend.base_url,
            api_base_path=profile.backend.api_base_path,
            auth=resolver,
            timeout=float(profile.backend.http_timeout),
            verify_tls=profile.backend.verify_tls,
            user_agent=profile.backend.user_agent,
        )

    ctx = ToolContext(settings=settings, client=client, logger=get_logger(f"bg-mcpcore.{profile.id}"))

    providers = [build_tool_provider(tc) for tc in profile.tool_sources]
    constructing = [p for p in providers if hasattr(p, "construct")]
    registering = [p for p in providers if hasattr(p, "register")]
    if len(constructing) > 1:
        raise ProfileError("At most one constructing tool source (e.g. openapi) is allowed")

    base_url = str(settings.public_base_url).rstrip("/")
    icon_url = settings.mcp_icon_url or profile.icon_url or f"{base_url}/logo.svg"
    website_url = settings.mcp_website_url or profile.website_url

    @asynccontextmanager
    async def _client_lifespan(_app: FastMCP) -> Any:
        try:
            yield {"settings": settings, "client": client, "profile": profile}
        finally:
            if client is not None:
                await client.aclose()
            logger.info("app.shutdown_complete", profile=profile.id)

    effective_lifespan = lifespan or _client_lifespan

    mcp: FastMCP
    if constructing:
        mcp = await constructing[0].construct(
            name=settings.mcp_display_name,
            instructions=profile.instructions,
            auth=auth_provider,
            lifespan=effective_lifespan,
            icon_url=icon_url,
            website_url=website_url,
            ctx=ctx,
        )
    else:
        kwargs: dict[str, Any] = {
            "name": settings.mcp_display_name,
            "instructions": profile.instructions,
            "lifespan": effective_lifespan,
        }
        if auth_provider is not None:
            kwargs["auth"] = auth_provider
        if icon_url:
            kwargs["icons"] = [Icon(src=icon_url, mimeType="image/svg+xml")]
        if website_url:
            kwargs["website_url"] = website_url
        mcp = FastMCP(**kwargs)

    # Rate limiter goes on FIRST - cheapest rejection path under load.
    rate_limit_mw = build_rate_limit_middleware(settings)
    if rate_limit_mw is not None:
        mcp.add_middleware(rate_limit_mw)

    # Auth-mode middleware (e.g. Entra tenant allowlist), discovered config-driven
    # via the auth_middleware entry-point group, then any caller-supplied extras.
    for middleware in (*build_auth_middleware(settings), *extra_middleware):
        mcp.add_middleware(middleware)

    total = 0
    for provider in registering:
        total += await provider.register(mcp, ctx)

    if profile.routes.healthz:
        register_healthz_route(mcp)
    if static_dir is not None:
        static_path = Path(static_dir)
        if profile.routes.logo:
            register_logo_route(mcp, static_dir=static_path)
        if profile.routes.index:
            register_index_route(
                mcp,
                static_dir=static_path,
                template_vars={
                    "version": version,
                    "protocol": "MCP / Streamable HTTP",
                    "environment": str(settings.environment),
                    "auth_mode": str(settings.auth_mode),
                    "mcp_url": f"{base_url}/mcp",
                },
            )

    print_banner(
        title=settings.mcp_display_name,
        version=version,
        environment=str(settings.environment),
        auth_mode=str(settings.auth_mode),
        public_base_url=base_url,
    )
    if str(settings.auth_mode) == "none":
        warn_no_auth()

    logger.info(
        "app.built",
        profile=profile.id,
        tools_registered=total,
        constructing=bool(constructing),
    )
    return mcp


__all__ = ["build_app_from_profile"]
