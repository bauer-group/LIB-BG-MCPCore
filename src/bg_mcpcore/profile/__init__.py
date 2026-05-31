"""Declarative profile: models + loader."""

from __future__ import annotations

from .loader import ProfileError, load_profile
from .models import (
    AuthConfig,
    BackendConfig,
    InboundAuthConfig,
    OutboundAuthConfig,
    Profile,
    RoutesConfig,
    ToolsConfig,
)

__all__ = [
    "AuthConfig",
    "BackendConfig",
    "InboundAuthConfig",
    "OutboundAuthConfig",
    "Profile",
    "ProfileError",
    "RoutesConfig",
    "ToolsConfig",
    "load_profile",
]
