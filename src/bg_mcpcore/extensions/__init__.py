"""Config-driven extensions: operator-defined prompts + resources.

Lightweight (fastmcp + httpx only), so this lives in core. Export tasks (bespoke
bulk exporters) are server business logic, not part of this generic layer.
"""

from __future__ import annotations

from .config import ExtensionsConfig, ExtensionsConfigError, load_config
from .loader import load_extensions

__all__ = ["ExtensionsConfig", "ExtensionsConfigError", "load_config", "load_extensions"]
