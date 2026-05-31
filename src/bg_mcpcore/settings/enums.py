"""Shared settings enums."""

from __future__ import annotations

from enum import StrEnum


class Environment(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"


__all__ = ["Environment"]
