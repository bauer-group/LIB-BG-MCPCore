"""OpenAPI spec loader ([openapi] extra).

Fetches an OpenAPI 3 spec once at startup, caches it in memory, and optionally
refreshes on a fixed interval. A refresh failure NEVER tears down the cached
spec. Supports https:// (httpx) and file:// (local) sources, and resolves
external ``$ref`` pointers so unbundled modular specs work at runtime.

Ported from bg-shlink-mcp (neutralised logger + user agent). No heavy deps:
JSON is stdlib; YAML support is lazy via the optional pyyaml in [openapi].
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import url2pathname

import httpx

from ..observability import get_logger

logger = get_logger("bg-mcpcore.openapi")


@dataclass
class LoadedSpec:
    spec: dict[str, Any]
    source: str
    info_version: str | None
    title: str | None
    operation_count: int


class SpecLoadError(RuntimeError):
    """Raised when the spec cannot be loaded for the first time."""


async def load_spec(source: str, *, timeout: float = 30.0) -> LoadedSpec:
    """Fetch, parse, and dereference an OpenAPI spec. Raises SpecLoadError."""
    spec = await _fetch_and_parse(source, timeout=timeout)
    if not isinstance(spec, dict):
        raise SpecLoadError(f"OpenAPI spec at {source} is not a JSON object")
    if "paths" not in spec:
        raise SpecLoadError(f"OpenAPI spec at {source} is missing the `paths` section")

    try:
        spec = await _resolve_external_refs(spec, source, timeout=timeout)
    except SpecLoadError:
        raise
    except Exception as exc:
        raise SpecLoadError(f"Failed to resolve external $refs from {source}: {exc}") from exc

    operation_count = _count_operations(spec)
    if operation_count == 0:
        raise SpecLoadError(
            f"OpenAPI spec at {source} has 0 operations - `paths` is empty or contains "
            f"only unresolved $refs. Did the build-time bundling step run?"
        )

    info = spec.get("info", {}) if isinstance(spec.get("info"), dict) else {}
    return LoadedSpec(
        spec=spec,
        source=source,
        info_version=info.get("version"),
        title=info.get("title"),
        operation_count=operation_count,
    )


async def _fetch_and_parse(uri: str, *, timeout: float) -> Any:
    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()
    if scheme in ("http", "https"):
        raw = await _fetch_remote(uri, timeout=timeout)
    elif scheme == "file":
        raw = _read_local(_file_url_to_path(uri))
    elif os.path.exists(uri):
        # Bare filesystem path - including Windows "C:\..." where urlparse
        # mistakes the drive letter for a scheme.
        raw = _read_local(uri)
    else:
        raise SpecLoadError(f"Unsupported spec source scheme: {uri!r}")
    try:
        return _parse(raw)
    except ValueError as exc:
        raise SpecLoadError(f"Failed to parse OpenAPI spec from {uri}: {exc}") from exc


def _resolve_ref_uri(base: str, ref: str) -> str:
    parsed = urlparse(base)
    if parsed.scheme in ("http", "https"):
        return urljoin(base, ref)
    if parsed.scheme == "file":
        base_path = Path(_file_url_to_path(base))
        return (base_path.parent / ref).resolve().as_uri()
    base_path = Path(base)
    return str((base_path.parent / ref).resolve())


async def _resolve_external_refs(
    node: Any,
    current_uri: str,
    *,
    timeout: float,
    seen: tuple[str, ...] = (),
) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref and not ref.startswith("#"):
            ref_path, _, fragment = ref.partition("#")
            target_uri = _resolve_ref_uri(current_uri, ref_path)
            if target_uri in seen:
                chain = " -> ".join((*seen, target_uri))
                raise SpecLoadError(f"Circular external $ref chain: {chain}")
            sub = await _fetch_and_parse(target_uri, timeout=timeout)
            if fragment:
                for part in fragment.lstrip("/").split("/"):
                    if not isinstance(sub, dict):
                        raise SpecLoadError(
                            f"Fragment {fragment!r} cannot traverse non-object while "
                            f"resolving {ref!r} from {current_uri}"
                        )
                    if part not in sub:
                        raise SpecLoadError(
                            f"Fragment part {part!r} not found in {target_uri}"
                        )
                    sub = sub[part]
            return await _resolve_external_refs(
                sub, target_uri, timeout=timeout, seen=(*seen, target_uri)
            )
        return {
            key: await _resolve_external_refs(value, current_uri, timeout=timeout, seen=seen)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [
            await _resolve_external_refs(item, current_uri, timeout=timeout, seen=seen)
            for item in node
        ]
    return node


async def _fetch_remote(url: str, *, timeout: float) -> str:
    headers = {
        "Accept": "application/json, application/yaml, text/yaml",
        "User-Agent": "bg-mcpcore",
    }
    async with httpx.AsyncClient(
        timeout=timeout, headers=headers, follow_redirects=True
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


def _read_local(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _file_url_to_path(url: str) -> str:
    """Convert a file:// URL to a local path, cross-platform."""
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


def _parse(raw: str) -> dict[str, Any]:
    raw_stripped = raw.lstrip()
    if raw_stripped.startswith("{"):
        return json.loads(raw)  # type: ignore[no-any-return]
    try:
        return json.loads(raw)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass
    try:
        import yaml
    except ImportError as exc:
        raise ValueError(
            "spec appears to be YAML but pyyaml is not installed; install "
            "bg-mcpcore[openapi] (pyyaml) or use a JSON spec"
        ) from exc
    return yaml.safe_load(raw)  # type: ignore[no-any-return]


def _count_operations(spec: dict[str, Any]) -> int:
    paths = spec.get("paths", {}) or {}
    if not isinstance(paths, dict):
        return 0
    verbs = {"get", "post", "put", "patch", "delete", "head", "options"}
    return sum(
        1
        for path_item in paths.values()
        if isinstance(path_item, dict)
        for method in path_item
        if method.lower() in verbs
    )


class SpecCache:
    """Holds the active spec; offers a refresh task that never invalidates on failure."""

    def __init__(self, source: str, *, timeout: float = 30.0) -> None:
        self._source = source
        self._timeout = timeout
        self._lock = asyncio.Lock()
        self._current: LoadedSpec | None = None

    @property
    def current(self) -> LoadedSpec:
        if self._current is None:
            raise RuntimeError("SpecCache.current accessed before initial load")
        return self._current

    async def initial_load(self) -> LoadedSpec:
        async with self._lock:
            self._current = await load_spec(self._source, timeout=self._timeout)
            logger.info(
                "openapi.loaded",
                source=self._source,
                spec_title=self._current.title,
                spec_version=self._current.info_version,
                operations=self._current.operation_count,
            )
            return self._current

    async def refresh_once(self) -> bool:
        try:
            new_spec = await load_spec(self._source, timeout=self._timeout)
        except Exception as exc:
            logger.warning("openapi.refresh_failed", source=self._source, error=str(exc))
            return False
        async with self._lock:
            previous = self._current
            self._current = new_spec
        logger.info(
            "openapi.refreshed",
            source=self._source,
            spec_version=new_spec.info_version,
            previous_version=previous.info_version if previous else None,
        )
        return True

    async def run_refresh_loop(self, interval_seconds: int) -> None:
        if interval_seconds <= 0:
            return
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self.refresh_once()
            except asyncio.CancelledError:
                logger.info("openapi.refresh_loop_cancelled")
                raise
            except Exception as exc:
                logger.exception("openapi.refresh_loop_unexpected_error", error=str(exc))
                await asyncio.sleep(min(interval_seconds, 60))


__all__ = ["LoadedSpec", "SpecCache", "SpecLoadError", "load_spec"]
