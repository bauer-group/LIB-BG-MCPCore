"""Spec-driven builders for FastMCP's first-class inbound IdP providers.

Rather than a bespoke module per provider, each FastMCP provider is described by
a small declarative ``_Spec`` (its class + which ``auth.inbound.config`` keys map
to constructor kwargs) and assembled by one generic ``_build``. Adding a provider
is a spec entry + a one-line entry point — no new module.

Config source: the profile's ``auth.inbound.config`` block (NOT settings — these
long-tail providers must not bloat BaseMcpSettings). Secrets are referenced by a
``<key>_env`` config key naming an env var, resolved at build time, so the secret
never lands in the parsed profile object. Cross-cutting bits (base_url,
client_storage, jwt_signing_key) come from settings.

Two provider families (per FastMCP's constructors):
* DCR / OAuthProxy style — take client_storage + jwt_signing_key (auth0, aws,
  clerk, discord, github, oci, workos).
* Token-verifier style — validate externally-issued tokens, no client_storage
  (descope, keycloak, propelauth, scalekit, supabase).
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..observability import get_logger
from ..profile.loader import ProfileError

logger = get_logger("bg-mcpcore.auth.providers")


@dataclass(frozen=True)
class _Field:
    key: str  # config key == provider constructor kwarg
    required: bool = True
    secret: bool = False  # resolved from os.environ via the `<key>_env` config key


@dataclass(frozen=True)
class _Spec:
    cls_path: str  # "module:ClassName"
    fields: tuple[_Field, ...]
    needs_storage: bool = False  # inject client_storage + jwt_signing_key
    extra_fields: tuple[str, ...] = field(default=("required_scopes",))  # passthrough if present


def _load(cls_path: str) -> Any:
    module_name, _, attr = cls_path.partition(":")
    return getattr(importlib.import_module(module_name), attr)


def _build(spec: _Spec, settings: Any, inbound: Any | None) -> Any:
    config: Mapping[str, Any] = (getattr(inbound, "config", None) or {}) if inbound is not None else {}

    kwargs: dict[str, Any] = {"base_url": str(settings.public_base_url)}
    for f in spec.fields:
        if f.secret:
            env_name = config.get(f"{f.key}_env")
            value = os.environ.get(env_name) if env_name else None
            missing_hint = f"'{f.key}_env' naming an env var"
        else:
            value = config.get(f.key)
            missing_hint = f"'{f.key}'"
        if value is None:
            if f.required:
                raise ProfileError(
                    f"auth.inbound.config for this provider requires {missing_hint}"
                )
            continue
        kwargs[f.key] = value

    for extra in spec.extra_fields:
        if extra in config:
            kwargs[extra] = config[extra]

    if spec.needs_storage:
        from ..auth.storage import build_client_storage

        kwargs["client_storage"] = build_client_storage(settings)
        kwargs["jwt_signing_key"] = settings.auth_jwt_signing_key.get_secret_value()

    provider_cls = _load(spec.cls_path)
    provider = provider_cls(**kwargs)
    logger.info("auth.provider_configured", provider=spec.cls_path.rsplit(":", 1)[-1])
    return provider


_BASE = "fastmcp.server.auth.providers"

# ── DCR / OAuthProxy-style providers (need client_storage + jwt_signing_key) ──
_AUTH0 = _Spec(
    f"{_BASE}.auth0:Auth0Provider",
    (_Field("config_url"), _Field("client_id"), _Field("client_secret", secret=True), _Field("audience")),
    needs_storage=True,
)
_AWS_COGNITO = _Spec(
    f"{_BASE}.aws:AWSCognitoProvider",
    (
        _Field("user_pool_id"),
        _Field("client_id"),
        _Field("client_secret", secret=True),
        _Field("aws_region", required=False),
    ),
    needs_storage=True,
)
_CLERK = _Spec(
    f"{_BASE}.clerk:ClerkProvider",
    (_Field("domain"), _Field("client_id"), _Field("client_secret", required=False, secret=True)),
    needs_storage=True,
)
_DISCORD = _Spec(
    f"{_BASE}.discord:DiscordProvider",
    (_Field("client_id"), _Field("client_secret", secret=True)),
    needs_storage=True,
)
_GITHUB = _Spec(
    f"{_BASE}.github:GitHubProvider",
    (_Field("client_id"), _Field("client_secret", secret=True)),
    needs_storage=True,
)
_OCI = _Spec(
    f"{_BASE}.oci:OCIProvider",
    (
        _Field("config_url"),
        _Field("client_id"),
        _Field("client_secret", secret=True),
        _Field("audience", required=False),
    ),
    needs_storage=True,
)
_WORKOS = _Spec(
    f"{_BASE}.workos:WorkOSProvider",
    (_Field("client_id"), _Field("client_secret", secret=True), _Field("authkit_domain")),
    needs_storage=True,
)

# ── Token-verifier-style providers (no client_storage) ────────────────────────
_KEYCLOAK = _Spec(
    f"{_BASE}.keycloak:KeycloakAuthProvider",
    (_Field("realm_url"), _Field("audience", required=False)),
)
# DescopeProvider requires EITHER config_url (new API) OR both project_id +
# descope_base_url (legacy API), so all three are optional here and the provider
# validates the combination (a clear error if none is supplied).
_DESCOPE = _Spec(
    f"{_BASE}.descope:DescopeProvider",
    (
        _Field("config_url", required=False),
        _Field("project_id", required=False),
        _Field("descope_base_url", required=False),
    ),
)
_PROPELAUTH = _Spec(
    f"{_BASE}.propelauth:PropelAuthProvider",
    (
        _Field("auth_url"),
        _Field("introspection_client_id"),
        _Field("introspection_client_secret", secret=True),
    ),
)
_SCALEKIT = _Spec(
    f"{_BASE}.scalekit:ScalekitProvider",
    (_Field("environment_url"), _Field("resource_id"), _Field("client_id", required=False)),
)
_SUPABASE = _Spec(f"{_BASE}.supabase:SupabaseProvider", (_Field("project_url"),))


def _make_builder(spec: _Spec, name: str) -> Any:
    def _builder(settings: Any, inbound: Any | None = None) -> Any:
        return _build(spec, settings, inbound)

    _builder.__name__ = f"build_{name}"
    return _builder


build_auth0 = _make_builder(_AUTH0, "auth0")
build_aws_cognito = _make_builder(_AWS_COGNITO, "aws_cognito")
build_clerk = _make_builder(_CLERK, "clerk")
build_descope = _make_builder(_DESCOPE, "descope")
build_discord = _make_builder(_DISCORD, "discord")
build_github = _make_builder(_GITHUB, "github")
build_keycloak = _make_builder(_KEYCLOAK, "keycloak")
build_oci = _make_builder(_OCI, "oci")
build_propelauth = _make_builder(_PROPELAUTH, "propelauth")
build_scalekit = _make_builder(_SCALEKIT, "scalekit")
build_supabase = _make_builder(_SUPABASE, "supabase")
build_workos = _make_builder(_WORKOS, "workos")


__all__ = [
    "build_auth0",
    "build_aws_cognito",
    "build_clerk",
    "build_descope",
    "build_discord",
    "build_github",
    "build_keycloak",
    "build_oci",
    "build_propelauth",
    "build_scalekit",
    "build_supabase",
    "build_workos",
]
