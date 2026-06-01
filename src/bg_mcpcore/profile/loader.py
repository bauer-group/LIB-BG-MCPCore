"""Profile loading + ``${env:VAR}`` interpolation (fail-closed).

Non-secret interpolation (``base_url: "${env:SHLINK_URL}"``) is resolved here.
A referenced env var that is unset raises ``ProfileError`` (guardrail #5) — unless
a default is supplied with shell-style ``:-`` syntax: ``"${env:SHLINK_OPENAPI_URL:-
file:///app/openapi/shlink.json}"`` resolves to the default when the var is unset
or empty, while still honouring an explicit override (so a documented-but-optional
knob does not become a silent no-op). Defaults are literal and intended for
NON-SECRET config (URLs, paths); secrets are NOT pulled into the profile object —
the outbound-auth resolver reads ``value_from_env`` directly at build time (with no
default), so credentials never sit in the parsed profile and stay fail-closed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import Profile

# ${env:VAR} (fail-closed if unset) or ${env:VAR:-default} (shell-style default
# used when VAR is unset or empty). The default runs up to the closing brace, so
# it cannot itself contain '}'.
_ENV_RE = re.compile(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ProfileError(RuntimeError):
    """Raised when a profile cannot be read, interpolated, or validated."""


def _interpolate(value: Any, env: Mapping[str, str]) -> Any:
    if isinstance(value, str):

        def _repl(match: re.Match[str]) -> str:
            name = match.group(1)
            default = match.group(2)  # None when no ':-default' was given
            resolved = env.get(name)
            if resolved:
                return resolved
            # Unset or empty from here on.
            if default is not None:
                return default  # ${env:VAR:-default} → shell ':-' semantics
            if resolved is not None:
                return resolved  # set-but-empty, no default → preserve "" (legacy)
            raise ProfileError(
                f"Profile references ${{env:{name}}} but environment variable "
                f"{name} is not set"
            )

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

    if isinstance(data, dict):
        # `$schema` is a JSON-Schema editor/validation hint (it points profiles at
        # mcp-profile/v1.json for IDE autocompletion), not profile data — drop it
        # so the strict model does not reject an otherwise-valid profile. Strip it
        # BEFORE interpolation so a ${env:VAR} inside the (discarded) schema URL
        # never fails closed on an unset var. Copying avoids mutating a caller dict.
        data = {key: item for key, item in data.items() if key != "$schema"}

    if interpolate_env:
        data = _interpolate(data, env)

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
    except OSError as exc:
        # A directory, permission error, or malformed file:// path — honour the
        # documented contract that any read failure surfaces as ProfileError.
        raise ProfileError(f"Profile file could not be read: {path} ({exc})") from exc


__all__ = ["ProfileError", "load_profile"]
