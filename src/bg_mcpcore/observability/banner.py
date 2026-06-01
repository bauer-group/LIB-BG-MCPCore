"""Startup banner + loud auth warnings.

Generalised from the two servers' near-identical ``print_banner``: the title is
a parameter and any backend-specific lines (Zammad's ``zammad_url`` / detected
version, etc.) are passed as ``extra_lines`` instead of fixed keyword args.
"""

from __future__ import annotations

from collections.abc import Sequence

from .logging_setup import console


def print_banner(
    *,
    title: str,
    version: str,
    environment: str,
    auth_mode: str,
    public_base_url: str,
    extra_lines: Sequence[str] | None = None,
) -> None:
    """Pretty boot banner - safe to call before setup_logging finished.

    ``extra_lines`` are appended verbatim (Rich markup allowed), e.g.
    ``["  zammad_url  : [bold]https://...[/bold] [dim](Zammad 7.2)[/dim]"]``.
    """
    lines = [
        f"\n[bold cyan]{title}[/bold cyan] [dim]v{version}[/dim]",
        f"  environment : [bold]{environment}[/bold]",
        f"  auth_mode   : [bold]{auth_mode}[/bold]",
        f"  public_url  : [bold]{public_base_url}[/bold]",
    ]
    if extra_lines:
        lines.extend(extra_lines)
    console.print("\n".join(lines) + "\n")


def warn_no_auth() -> None:
    """Loud warning when AUTH_MODE=none - only allowed in development."""
    console.print(
        "\n[bold red on yellow]  WARNING: AUTH_MODE=none - the MCP endpoint is UNPROTECTED  [/bold red on yellow]"
        "\n[yellow]This is only permitted in ENVIRONMENT=development. Never deploy this way.[/yellow]\n"
    )


def warn_role_audit_only() -> None:
    """Loud warning when role-check audit-only is enabled."""
    console.print(
        "\n[bold black on yellow]  NOTICE: role-check audit-only mode - denials are logged but NOT enforced  [/bold black on yellow]"
        "\n[yellow]Use this during rollout only. Switch to enforcement once the allowlist is verified.[/yellow]\n"
    )


def warn_entra_open_tenants() -> None:
    """Loud warning when AUTH_MODE=entra-multi runs without a tenant allowlist."""
    console.print(
        "\n[bold black on yellow]  WARNING: AUTH_MODE=entra-multi with no ENTRA_ALLOWED_TENANTS  [/bold black on yellow]"
        "\n[yellow]Access tokens from ANY Microsoft Entra tenant are accepted. Set "
        "ENTRA_ALLOWED_TENANTS to restrict access to your own tenant(s).[/yellow]\n"
    )


__all__ = ["print_banner", "warn_entra_open_tenants", "warn_no_auth", "warn_role_audit_only"]
