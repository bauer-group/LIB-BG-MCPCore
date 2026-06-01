"""Settings helpers + the shared fail-closed persistence validator.

``validate_persistence`` encodes the NON-NEGOTIABLE auth invariants that must
hold for every server regardless of its specific auth modes (security guardrail
#1). It is enforced in ``BaseMcpSettings`` BEFORE the subclass's per-mode
``validate_provider_auth`` hook, so a server cannot accidentally relax it.
"""

from __future__ import annotations

from pydantic import SecretStr

from .._config_protocols import PersistenceSettings


def split_csv(raw: str | list[str] | None) -> list[str]:
    """Parse a comma-separated env value into a list. Tolerates whitespace."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def has_value(value: object) -> bool:
    """True if a config value is present (handles SecretStr + str + None)."""
    if value is None:
        return False
    if isinstance(value, SecretStr):
        return bool(value.get_secret_value().strip())
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def validate_fernet_key(raw: str) -> None:
    """Ensure a value parses as a Fernet key (32 url-safe base64 bytes).

    Operators sometimes paste a hex string or a raw 32-byte blob - both are
    rejected here so boot fails loudly instead of surfacing as an InvalidToken
    deep inside FastMCP on the first login.
    """
    from cryptography.fernet import Fernet

    try:
        Fernet(raw.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "Storage encryption key is not a valid Fernet key. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        ) from exc


def validate_persistence(settings: PersistenceSettings) -> None:
    """Enforce the universal fail-closed auth invariants. Raises ValueError.

    1. AUTH_MODE=none is forbidden in production.
    2. AUTH_JWT_SIGNING_KEY is required (and not a CHANGE_ME placeholder) for any
       active (non-none) auth mode.
    3. A Redis-backed client store requires a valid AUTH_STORAGE_ENCRYPTION_KEY
       (no plaintext OAuth state at rest).
    """
    is_none = settings.auth_mode == "none"

    if is_none:
        if settings.environment == "production":
            raise ValueError(
                "AUTH_MODE=none is forbidden in production "
                "(set ENVIRONMENT=development if this is intentional)"
            )
    else:
        # Strip before the check: a whitespace-only key is as unusable as an empty
        # one and must not satisfy the invariant. Casefold the placeholder test so
        # a lowercase "change_me..." is rejected too.
        signing = settings.auth_jwt_signing_key.get_secret_value().strip()
        if not signing or signing.upper().startswith("CHANGE_ME"):
            raise ValueError(
                "AUTH_JWT_SIGNING_KEY is required and must not be a CHANGE_ME placeholder"
            )

    if settings.auth_redis_url and not is_none:
        key = settings.auth_storage_encryption_key
        if not key or not key.get_secret_value():
            raise ValueError("AUTH_STORAGE_ENCRYPTION_KEY is required when AUTH_REDIS_URL is set")
        validate_fernet_key(key.get_secret_value())


__all__ = ["has_value", "split_csv", "validate_fernet_key", "validate_persistence"]
