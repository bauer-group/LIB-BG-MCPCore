"""Declarative profile models — the schema for a config-driven MCP server.

A profile describes STRUCTURE (backend, outbound-auth type, tool sources, route
toggles, identity). Runtime VALUES and SECRETS come from the environment via
``BaseMcpSettings`` (inbound auth mode, OIDC creds) and ``value_from_env`` (the
outbound credential) — never inline in the profile.

Sub-configs that carry source-specific extras (the OpenAPI spec block, route
maps, name overrides) use ``extra="allow"`` so a profile stays valid before the
[openapi] extra is installed; the top-level model is strict to catch typos.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BackendConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    api_base_path: str = ""
    http_timeout: int = Field(default=30, ge=1, le=300)
    verify_tls: bool = True
    user_agent: str = "bg-mcpcore"


class InboundAuthConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    # Advisory default; the authoritative inbound mode is AUTH_MODE (env), held
    # and validated by BaseMcpSettings.
    mode: str = "none"


class OutboundAuthConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = "none"  # none | static_header | bearer_env | python
    header: str | None = None
    value_from_env: str | None = None
    value: str | None = None
    resolver: str | None = None  # dotted "module:attr" for type=python


class AuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inbound: InboundAuthConfig = Field(default_factory=InboundAuthConfig)
    outbound: OutboundAuthConfig = Field(default_factory=OutboundAuthConfig)


class ToolsConfig(BaseModel):
    # populate_by_name lets the JSON key stay "register" while the attribute is
    # register_target (avoids shadowing a pydantic BaseModel attribute).
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    source: str  # openapi | python | registry (+ plugins)
    register_target: str | None = Field(default=None, alias="register")  # python: "module:attr"
    include: list[str] = Field(default_factory=list)  # registry: tool names


class RoutesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    healthz: bool = True
    logo: bool = True
    index: bool = True


class ExtensionsRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str  # file:// URL or bare path to the extensions catalogue JSON
    required: bool = False


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    instructions: str = ""
    icon_url: str | None = None
    website_url: str | None = None
    backend: BackendConfig | None = None
    auth: AuthConfig = Field(default_factory=AuthConfig)
    tools: ToolsConfig | list[ToolsConfig]
    routes: RoutesConfig = Field(default_factory=RoutesConfig)
    extensions: ExtensionsRef | None = None

    @property
    def tool_sources(self) -> list[ToolsConfig]:
        return self.tools if isinstance(self.tools, list) else [self.tools]


__all__ = [
    "AuthConfig",
    "BackendConfig",
    "ExtensionsRef",
    "InboundAuthConfig",
    "OutboundAuthConfig",
    "Profile",
    "RoutesConfig",
    "ToolsConfig",
]
