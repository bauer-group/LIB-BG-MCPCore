"""CLI factory: turn a profile into a Typer app (the server entrypoint).

A server's ``main.py`` is then 4 lines::

    from bg_mcpcore import load_profile, make_cli
    app = make_cli(load_profile("profiles/mautic.json"))
    if __name__ == "__main__":
        app()

(No ``from __future__ import annotations`` here: Typer introspects real
annotation objects at decoration time.)
"""

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import typer

from .app import build_app_from_profile
from .profile.models import Profile
from .server.runner import patch_dual_stack_socket, run_transport
from .settings.base import BaseMcpSettings
from .settings.factory import get_settings


def make_cli(
    profile: Profile,
    *,
    settings_cls: type[BaseMcpSettings] = BaseMcpSettings,
    version: str = "0.0.0",
    static_dir: str | Path | None = None,
    lifespan: Any | None = None,
    extra_sensitive_fragments: Sequence[str] = (),
    extra_middleware: Sequence[Any] = (),
) -> typer.Typer:
    """Build a Typer app exposing ``serve`` (default) for a profile-driven server.

    ``lifespan``, ``extra_sensitive_fragments`` and ``extra_middleware`` are passed
    straight through to :func:`build_app_from_profile`, so a server can wire a
    Tier-3 access-control gate (e.g. a role-allowlist middleware) without bypassing
    ``make_cli``.
    """
    patch_dual_stack_socket()
    cli = typer.Typer(
        name=profile.id,
        help=f"Remote MCP server: {profile.display_name}",
        no_args_is_help=False,
        add_completion=False,
    )

    @cli.callback(invoke_without_command=True)
    def _default(ctx: typer.Context) -> None:
        """Default to `serve` when called with no subcommand."""
        if ctx.invoked_subcommand is None:
            ctx.invoke(serve)

    @cli.command()
    def serve(
        host: str | None = typer.Option(None, "--host", help="Bind address (overrides MCP_HOST)"),
        port: int | None = typer.Option(None, "--port", help="Listen port (overrides MCP_PORT)"),
        transport: str | None = typer.Option(
            None, "--transport", help="MCP transport: streamable-http (default) or stdio"
        ),
    ) -> None:
        """Run the MCP server (default mode)."""
        settings = get_settings(settings_cls)
        if host is not None:
            settings.mcp_host = host
        if port:
            settings.mcp_port = port
        chosen = transport or settings.mcp_transport

        async def _run() -> None:
            mcp = await build_app_from_profile(
                profile,
                settings,
                version=version,
                static_dir=static_dir,
                lifespan=lifespan,
                extra_sensitive_fragments=extra_sensitive_fragments,
                extra_middleware=extra_middleware,
            )
            await run_transport(
                mcp, host=settings.mcp_host, port=settings.mcp_port, transport=chosen
            )

        asyncio.run(_run())

    return cli


def main() -> None:
    """Console-script entry. The `new <name>` scaffolder lands in Phase 7."""
    typer.echo("bg-mcpcore framework. The `bg-mcpcore new <name>` scaffolder lands in Phase 7.")
