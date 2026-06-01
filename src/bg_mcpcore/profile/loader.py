"""Profile loading + ``${env:VAR}`` interpolation (fail-closed).

Non-secret interpolation (``base_url: "${env:SHLINK_URL}"``) is resolved here.
Secrets are NOT pulled into the profile object — the outbound-auth resolver reads
``value_from_env`` directly at build time, so credentials never sit in the parsed
profile. A referenced env var that is unset raises ``ProfileError`` (guardrail #5).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import Profile

_ENV_RE = re.compile(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}")


class ProfileError(RuntimeError):
    """Raised when a profile cannot be read, interpolated, or validated."""


def _interpolate(value: Any, env: Mapping[str, str]) -> Any:
    if isinstance(value, str):

        def _repl(match: re.Match[str]) -> str:
            name = match.group(1)
            resolved = env.get(name)
            if resolved is None:
                raise ProfileError(
                    f"Profile references ${{env:{name}}} but environment variable "
                    f"{name} is not set"
                )
            return resolved

        return _ENV_RE.sub(_repl, value)
    if isinstance(value, dict):
        return {key: _interpolate(item, env) for key, item in value.items()}
    if isinstance(value, list):
        return [_interpolate(item, env) for item in value]
    return value


def load_profile(
    source: str | Path | dict[str, Any],
    *,
    interpolate_env: bool = True,
    env: Mapping[str, str] | None = None,
) -> Profile:
    """Load + validate a profile from a JSON file path, ``file://`` URL, or dict.

    ``env`` defaults to ``os.environ`` (injectable for tests).
    """
    if env is None:
        import os

        env = os.environ

    if isinstance(source, dict):
        data: Any = source
    else:
        text = _read_source(source)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProfileError(f"Profile is not valid JSON: {exc}") from exc

    if interpolate_env:
        data = _interpolate(data, env)

    if isinstance(data, dict):
        # `$schema` is a JSON-Schema editor/validation hint (it points profiles at
        # mcp-profile/v1.json for IDE autocompletion), not profile data — drop it
        # so the strict model does not reject an otherwise-valid profile. Copying
        # avoids mutating a dict passed in by the caller.
        data = {key: item for key, item in data.items() if key != "$schema"}

    try:
        return Profile.model_validate(data)
    except ValidationError as exc:
        raise ProfileError(f"Invalid profile: {exc}") from exc


def _read_source(source: str | Path) -> str:
    raw = str(source)
    if raw.startswith("file://"):
        raw = raw[len("file://") :]
        # file:///abs -> /abs ; on Windows file:///C:/x -> C:/x
        if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
            raw = raw[1:]
    path = Path(raw)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ProfileError(f"Profile file not found: {path}") from exc


__all__ = ["ProfileError", "load_profile"]
