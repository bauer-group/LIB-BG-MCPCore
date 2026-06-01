"""Tests for the profile loader + plugin registries."""

from __future__ import annotations

import pytest

from bg_mcpcore.plugins import (
    build_auth_provider,
    build_outbound_resolver,
    build_tool_provider,
)
from bg_mcpcore.profile.loader import ProfileError, load_profile
from bg_mcpcore.profile.models import OutboundAuthConfig


def _profile_dict(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "demo",
        "display_name": "Demo",
        "tools": {"source": "registry", "include": ["bg.ping"]},
    }
    base.update(over)
    return base


def test_env_interpolation_resolves_placeholders() -> None:
    profile = load_profile(
        _profile_dict(backend={"base_url": "${env:DEMO_URL}", "api_base_path": "/api"}),
        env={"DEMO_URL": "https://demo.example.com"},
    )
    assert profile.backend is not None
    assert profile.backend.base_url == "https://demo.example.com"


def test_missing_env_var_fails_closed() -> None:
    with pytest.raises(ProfileError, match="DEMO_URL is not set"):
        load_profile(_profile_dict(backend={"base_url": "${env:DEMO_URL}"}), env={})


def test_invalid_profile_raises() -> None:
    with pytest.raises(ProfileError, match="Invalid profile"):
        load_profile({"id": "x"})  # missing display_name + tools


def test_unknown_top_level_key_rejected() -> None:
    with pytest.raises(ProfileError):
        load_profile(_profile_dict(bogus_key=True), env={})


def test_schema_hint_key_is_ignored() -> None:
    # `$schema` points editors at mcp-profile/v1.json for autocompletion; the
    # loader must drop it rather than reject the profile (every example ships it).
    over = {"$schema": "https://schemas.bauer-group.com/mcp-profile/v1.json"}
    profile = load_profile(_profile_dict(**over), env={})  # type: ignore[arg-type]
    assert profile.id == "demo"


# ── inbound auth (closed set) ────────────────────────────────────────────────


class _S:
    auth_mode = "none"


class _Unknown:
    auth_mode = "totally-made-up"


def test_auth_provider_none_returns_none() -> None:
    assert build_auth_provider(_S()) is None


def test_unknown_auth_mode_raises() -> None:
    with pytest.raises(ProfileError, match="Unknown AUTH_MODE"):
        build_auth_provider(_Unknown())


# ── outbound resolvers ───────────────────────────────────────────────────────


def test_static_header_reads_secret_from_env() -> None:
    cfg = OutboundAuthConfig(type="static_header", header="X-Api-Key", value_from_env="DEMO_KEY")
    resolver = build_outbound_resolver(cfg, env={"DEMO_KEY": "s3cr3t"})
    assert resolver.default_headers() == {"X-Api-Key": "s3cr3t"}


def test_static_header_missing_secret_fails_closed() -> None:
    cfg = OutboundAuthConfig(type="static_header", header="X-Api-Key", value_from_env="DEMO_KEY")
    with pytest.raises(ProfileError, match="DEMO_KEY"):
        build_outbound_resolver(cfg, env={})


def test_bearer_env_resolver() -> None:
    cfg = OutboundAuthConfig(type="bearer_env", value_from_env="TOK")
    resolver = build_outbound_resolver(cfg, env={"TOK": "abc"})
    assert resolver.default_headers() == {"Authorization": "Bearer abc"}


def test_none_resolver_has_no_headers() -> None:
    resolver = build_outbound_resolver(OutboundAuthConfig(type="none"), env={})
    assert resolver.default_headers() == {}


def test_unknown_outbound_type_raises() -> None:
    with pytest.raises(ProfileError, match="Unknown outbound auth type"):
        build_outbound_resolver(OutboundAuthConfig(type="made-up"), env={})


# ── tool sources ─────────────────────────────────────────────────────────────


def test_registry_tool_source_builds() -> None:
    from bg_mcpcore.profile.models import ToolsConfig

    provider = build_tool_provider(ToolsConfig(source="registry", include=["bg.ping"]))
    assert hasattr(provider, "register")


def test_unknown_tool_source_raises() -> None:
    from bg_mcpcore.profile.models import ToolsConfig

    with pytest.raises(ProfileError, match=r"Unknown tools\.source"):
        build_tool_provider(ToolsConfig(source="made-up"))
