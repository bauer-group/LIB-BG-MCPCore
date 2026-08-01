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

    Credential safety
    -----------------
    ``send_default_pii=False`` governs request bodies, headers and user
    identifiers — it does **not** cover stack-frame locals, which sentry-sdk
    attaches by default (``include_local_variables=True``). That default would
    ship secrets to a third party on any unhandled exception unwinding through
    a frame that holds one: the bearer token in an inbound token verifier, a
    static API credential in the outbound resolver, or the merged
    ``Authorization`` header in the HTTP client. Frame locals also bypass the
    structlog redaction pipeline entirely, since Sentry builds its event from
    the traceback rather than from a log record. Both are therefore off.
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
        # See the credential-safety note above — this is not implied by
        # send_default_pii and must be set explicitly.
        include_local_variables=False,
    )
    logger.info(
        "sentry.initialized",
        environment=environment,
        traces_sample_rate=traces_sample_rate,
    )
    return True


__all__ = ["init_sentry"]
