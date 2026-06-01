"""Reusable test stubs ([testkit] extra).

Lightweight fakes so server tests can exercise storage-dependent and
context-dependent code without real Redis/disk or a live FastMCP context.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class InMemoryKeyValue:
    """A toy AsyncKeyValue (get/put/delete) for testing client storage wiring."""

    def __init__(self) -> None:
        self._data: dict[tuple[str | None, str], dict[str, Any]] = {}

    async def get(self, key: str, *, collection: str | None = None) -> dict[str, Any] | None:
        return self._data.get((collection, key))

    async def put(
        self,
        key: str,
        value: Mapping[str, Any],
        *,
        collection: str | None = None,
        ttl: float | None = None,
    ) -> None:
        self._data[(collection, key)] = dict(value)

    async def delete(self, key: str, *, collection: str | None = None) -> bool:
        return self._data.pop((collection, key), None) is not None


__all__ = ["InMemoryKeyValue"]
