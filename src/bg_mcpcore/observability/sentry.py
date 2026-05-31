"""Optional Sentry error tracking.

Generalised from the two servers' identical ``_init_sentry_if_configured``: the
release string and environment are passed in explicitly rather than read off a
module-global ``__version__`` / a concrete Settings. ``sentry-sdk`` is imported
lazily so it stays an optional runtime concern controlled by SENTRY_DSN.
"""

from __future__ import annotations

from .logging_setup import get_logger

logger = get_logger("bg-mcpcore.sentry")


def init_sentry(
    *,
    dsn: str | None,
    environment: str,
    traces_sample_rate: float,
    release: str,
) -> bool:
    """Initialise Sentry when a DSN is configured. Returns True if initialised.

    No-op (returns False) when ``dsn`` is falsy or sentry-sdk is not installed.
    PII is never sent (send_default_pii=False).
    """
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("sentry.sdk_missing", hint="install sentry-sdk to enable error tracking")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        release=release,
        send_default_pii=False,
    )
    logger.info(
        "sentry.initialized",
        environment=environment,
        traces_sample_rate=traces_sample_rate,
    )
    return True


__all__ = ["init_sentry"]
