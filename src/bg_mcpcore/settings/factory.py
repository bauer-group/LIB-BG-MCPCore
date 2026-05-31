"""Per-class lazy-singleton settings factory.

Generalises each server's module-global ``get_settings()`` into a single helper
keyed by the concrete settings class, so multiple settings types (e.g. in a
multi-mount gateway) each get their own cached instance.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings

_cache: dict[type[BaseSettings], BaseSettings] = {}


def get_settings[T: BaseSettings](cls: type[T], *, force_reload: bool = False) -> T:
    """Return a cached instance of ``cls`` - parses env only once per class."""
    if force_reload or cls not in _cache:
        _cache[cls] = cls()
    instance = _cache[cls]
    assert isinstance(instance, cls)  # narrow for the type checker
    return instance


def reset_settings_cache() -> None:
    """Clear the settings cache - for tests."""
    _cache.clear()


__all__ = ["get_settings", "reset_settings_cache"]
