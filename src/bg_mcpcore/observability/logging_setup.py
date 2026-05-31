"""Structured logging.

structlog is the single source of truth. Two output modes:
  - 'console' (dev): Rich-coloured human output, key=value tail
  - 'json'    (prod): one JSON object per line, aggregator-ready

Stdlib ``logging`` is also routed through structlog so third-party libraries
(httpx, fastmcp, uvicorn) emit in the same shape as our own log lines.

Lifted verbatim from the bg-zammad-mcp / bg-shlink-mcp servers (byte-identical
there) with one addition: ``setup_logging`` accepts ``extra_sensitive_fragments``
so each server can extend the PII/secret redaction list with its own backend
secret field names (security guardrail #5 — additive redaction).
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Iterable
from typing import Any

import structlog
from rich.console import Console
from structlog.stdlib import ProcessorFormatter
from structlog.typing import EventDict, Processor

# Shared console - Rich auto-detects terminal width; force_terminal keeps
# colours alive in Docker logs that lack a real TTY.
console = Console(force_terminal=True, soft_wrap=True)

_initialized = False


def setup_logging(
    log_format: str = "console",
    log_level: str = "INFO",
    *,
    extra_sensitive_fragments: Iterable[str] = (),
) -> None:
    """Wire structlog + stdlib logging. Idempotent.

    ``extra_sensitive_fragments`` are merged into the baseline redaction set so
    a server can mask its own secret field names (e.g. ``fints_pin``, ``pat``).
    """
    global _initialized
    if _initialized:
        return

    level = getattr(logging, log_level.upper(), logging.INFO)

    timestamper: Processor = structlog.processors.TimeStamper(
        fmt="iso", utc=True, key="timestamp"
    )

    fragments = _SENSITIVE_KEY_FRAGMENTS + tuple(extra_sensitive_fragments)
    sensitive_filter = _make_sensitive_filter(fragments)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
        sensitive_filter,
        timestamper,
    ]

    if log_format == "json":
        renderer: Processor = structlog.processors.JSONRenderer(sort_keys=True)
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True, pad_event=25)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ProcessorFormatter(
            processor=renderer,
            foreign_pre_chain=shared_processors,
        )
    )
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet down very chatty libraries even at INFO.
    logging.getLogger("httpx").setLevel(max(level, logging.WARNING))
    logging.getLogger("httpcore").setLevel(max(level, logging.WARNING))
    logging.getLogger("hpack").setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.format_exc_info,
            ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _initialized = True


def reset_logging() -> None:
    """Reset the idempotency latch — for tests that re-run setup_logging."""
    global _initialized
    _initialized = False


def get_logger(name: str = "bg-mcpcore") -> structlog.stdlib.BoundLogger:
    """Get a structured logger - call after setup_logging()."""
    return structlog.stdlib.get_logger(name)


# ── Processors ───────────────────────────────────────────────────────────────

# Substrings that, if present in a key, mark a value as sensitive and should
# never appear in logs verbatim. Add aggressively - false positives just print
# `***` instead of the value.
_SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "signing_key",
    "encryption_key",
    "x-api-key",
    "bearer",
)


def _make_sensitive_filter(fragments: tuple[str, ...]) -> Processor:
    """Build a structlog processor that masks values under sensitive-looking keys."""

    def _drop(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
        for key in list(event_dict.keys()):
            lowered = key.lower()
            if any(frag in lowered for frag in fragments):
                event_dict[key] = "***"
        return event_dict

    return _drop


# Default-fragment processor, exposed for direct use / unit tests.
_drop_sensitive_keys: Processor = _make_sensitive_filter(_SENSITIVE_KEY_FRAGMENTS)


# ── Helpers ─────────────────────────────────────────────────────────────────


def now_iso() -> str:
    """ISO-8601 UTC timestamp - used in places that need one outside structlog."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


__all__ = [
    "console",
    "get_logger",
    "now_iso",
    "reset_logging",
    "setup_logging",
]
