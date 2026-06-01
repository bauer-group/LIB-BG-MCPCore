"""Schema for an operator-defined extensions catalogue (prompts + resources).

Two config-driven MCP primitives that layer on top of the tool surface:

* **prompts** — reusable multi-step prompt templates (`${name}` placeholders).
* **resources** — read-only (GET) upstream calls surfaced as MCP resources /
  resource templates.

Ported + generalised from bg-shlink-mcp: the resource URI scheme is no longer
hardcoded to ``shlink://`` (any ``scheme://`` is accepted; servers conventionally
use their profile id). Export tasks (bespoke bulk exporters) are intentionally
NOT here — they are server business logic, registered per server.

JSON over YAML (stdlib parser, `$schema`-friendly); ``extra="forbid"`` so a typo
fails loudly at boot.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

PYTHON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}


class _StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PromptArgumentConfig(_StrictBase):
    name: str = Field(..., description="Argument name and `${name}` placeholder.")
    type: Literal["string", "integer", "number", "boolean"] = "string"
    description: str = ""
    required: bool = False
    default: str | int | float | bool | None = None

    @field_validator("name")
    @classmethod
    def _valid_identifier(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(f"prompt argument name {v!r} is not a valid identifier")
        return v

    @model_validator(mode="after")
    def _check_default_type(self) -> PromptArgumentConfig:
        if self.default is None:
            return self
        expected = PYTHON_TYPE_MAP[self.type]
        if expected is int and isinstance(self.default, bool):
            raise ValueError(f"argument {self.name!r}: default does not match type 'integer'")
        if not isinstance(self.default, expected):
            raise ValueError(f"argument {self.name!r}: default does not match type {self.type!r}")
        return self


class PromptConfig(_StrictBase):
    name: str = Field(..., description="Prompt name shown to the AI client.")
    title: str | None = None
    description: str = ""
    arguments: list[PromptArgumentConfig] = Field(default_factory=list)
    template: str = Field(..., description="Body with `${name}` placeholders.")
    tags: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(f"prompt name {v!r} is not a valid identifier")
        return v

    @model_validator(mode="after")
    def _placeholders_match_arguments(self) -> PromptConfig:
        # string.Template uses `$$` as a literal-`$` escape; drop those first so a
        # template like "cost is $$5 for ${item}" is not read as a `$5`/`item` pair
        # and "$$word" (renders to a literal "$word") is not flagged as a placeholder.
        scan = self.template.replace("$$", "")
        placeholders = set(re.findall(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}", scan))
        placeholders |= set(re.findall(r"\$([a-zA-Z_][a-zA-Z0-9_]*)", scan))
        declared = {a.name for a in self.arguments}
        if placeholders - declared:
            raise ValueError(
                f"prompt {self.name!r}: template references undeclared placeholders "
                f"{sorted(placeholders - declared)}"
            )
        if declared - placeholders:
            raise ValueError(
                f"prompt {self.name!r}: arguments {sorted(declared - placeholders)} are "
                f"declared but never used"
            )
        return self


class BackendCall(_StrictBase):
    method: Literal["GET"] = "GET"
    path: str = Field(..., description="Upstream path (relative to backend.api_base_path).")

    @field_validator("path")
    @classmethod
    def _starts_with_slash(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError(f"backend path {v!r} must start with '/'")
        return v


class ResourceConfig(_StrictBase):
    uri: str = Field(..., description="`<scheme>://...` URI; `{name}` segments make it a template.")
    name: str
    title: str | None = None
    description: str = ""
    mime_type: str = "application/json"
    backend: BackendCall
    tags: list[str] = Field(default_factory=list)

    @field_validator("uri")
    @classmethod
    def _has_scheme(cls, v: str) -> str:
        if not _SCHEME_RE.match(v):
            raise ValueError(f"resource uri {v!r} must use a `<scheme>://` form")
        return v

    @model_validator(mode="after")
    def _placeholders_match(self) -> ResourceConfig:
        uri_params = set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", self.uri))
        path_params = set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", self.backend.path))
        if uri_params != path_params:
            raise ValueError(
                f"resource {self.uri!r}: URI placeholders {sorted(uri_params)} do not match "
                f"backend-path placeholders {sorted(path_params)}"
            )
        return self


class ExtensionsConfig(_StrictBase):
    prompts: list[PromptConfig] = Field(default_factory=list)
    resources: list[ResourceConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_names(self) -> ExtensionsConfig:
        for label, items in [
            ("prompt", [p.name for p in self.prompts]),
            ("resource", [r.uri for r in self.resources]),
        ]:
            if len(items) != len(set(items)):
                dupes = sorted({x for x in items if items.count(x) > 1})
                raise ValueError(f"duplicate {label} identifiers: {dupes}")
        return self


class ExtensionsConfigError(RuntimeError):
    """Raised when the extensions catalogue is unreadable or invalid."""


def load_config(source: str) -> ExtensionsConfig:
    """Read + validate the extensions catalogue from a `file://` or bare path.

    Remote sources are deliberately unsupported — the catalogue is server-side
    trust (baked into the image or a mounted volume), not pulled from the network.
    """
    raw = _read_source(source)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtensionsConfigError(f"extensions config at {source} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExtensionsConfigError(f"extensions config at {source} must be a JSON object")
    payload.pop("$schema", None)
    try:
        return ExtensionsConfig.model_validate(payload)
    except Exception as exc:
        raise ExtensionsConfigError(f"extensions config at {source} failed validation: {exc}") from exc


def config_exists(source: str) -> bool:
    """Cheap existence check handling `file://` and bare paths."""
    parsed = urlparse(source)
    if parsed.scheme == "file":
        return Path(_file_url_to_path(source)).exists()
    if not parsed.scheme or (len(parsed.scheme) == 1 and parsed.scheme.isalpha()):
        return Path(source).exists()
    return False


def _read_source(source: str) -> str:
    parsed = urlparse(source)
    if parsed.scheme == "file":
        return Path(_file_url_to_path(source)).read_text(encoding="utf-8")
    if not parsed.scheme or (len(parsed.scheme) == 1 and parsed.scheme.isalpha()):
        return Path(source).read_text(encoding="utf-8")
    raise ExtensionsConfigError(
        f"extensions config source {source!r} uses unsupported scheme {parsed.scheme!r} "
        "(only file:// and bare paths are accepted)"
    )


def _file_url_to_path(url: str) -> str:
    from_uri = getattr(Path, "from_uri", None)
    if from_uri is not None:
        try:
            return str(from_uri(url))
        except (ValueError, OSError):
            pass
    parsed = urlparse(url)
    raw_path = parsed.path
    if parsed.netloc and not re.match(r"^[a-zA-Z]:$", parsed.netloc) and parsed.netloc != "localhost":
        return r"\\" + parsed.netloc + url2pathname(raw_path)
    if parsed.netloc:
        raw_path = "/" + parsed.netloc + raw_path
    return url2pathname(unquote(raw_path))


def python_annotation_for(arg: PromptArgumentConfig) -> Any:
    return PYTHON_TYPE_MAP[arg.type]


__all__ = [
    "BackendCall",
    "ExtensionsConfig",
    "ExtensionsConfigError",
    "PromptArgumentConfig",
    "PromptConfig",
    "ResourceConfig",
    "config_exists",
    "load_config",
    "python_annotation_for",
]
