"""OAuth client-storage factory.

FastMCP's OAuth providers (OIDCProxy, OAuthProxy, AzureProvider, GoogleProvider)
persist five classes of state: DCR client metadata, authorization codes + PKCE
challenges, refresh-token-hash -> upstream-token-id mappings, FastMCP-issued JWT
JTI -> upstream-token mappings, and in-flight OAuth transactions.

Without an explicit ``client_storage`` FastMCP falls back to a DiskStore under
``platformdirs.user_data_dir()``, which inside a container is ephemeral - every
restart wipes everything, forcing re-registration + re-auth. This factory always
supplies a durable, encrypted-at-rest backend.

Two operator-selectable backends:

* AUTH_REDIS_URL set  -> RedisStore wrapped in FernetEncryptionWrapper using the
  operator-provided AUTH_STORAGE_ENCRYPTION_KEY. Recommended for production
  (survives restarts + replacement, supports horizontal scaling).
* AUTH_REDIS_URL unset -> DiskStore at AUTH_DISK_STORAGE_PATH wrapped in
  FernetEncryptionWrapper using a key DERIVED from AUTH_JWT_SIGNING_KEY via HKDF.

Lifted from the servers (byte-identical there bar the logger name). Two additions
for fleet safety (security guardrail #2):

* ``storage_salt`` is parameterised. It DEFAULTS to the legacy constant so all
  already-deployed encrypted state stays decryptable. Pass a per-service salt
  (e.g. ``f"bg-mcp-storage::{service_id}"``) ONLY as a deliberate, signed-off
  crypto cutover with a migration for existing data.
* In Redis mode we warn when AUTH_STORAGE_ENCRYPTION_KEY == AUTH_JWT_SIGNING_KEY,
  because reusing the signing key for at-rest encryption widens blast radius.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .._config_protocols import StorageSettings
from ..observability import get_logger

if TYPE_CHECKING:
    from key_value.aio.protocols import AsyncKeyValue

logger = get_logger("bg-mcpcore.auth.storage")

# The salt FastMCP uses for its own default DiskStore. Preserved as the default
# so existing encrypted state remains decryptable after the lift. DO NOT change
# the default without a crypto-cutover migration (see module docstring).
LEGACY_DISK_SALT = "fastmcp-storage-encryption-key"


def build_client_storage(
    settings: StorageSettings,
    *,
    storage_salt: str = LEGACY_DISK_SALT,
) -> AsyncKeyValue:
    """Construct the configured encrypted OAuth state store.

    Always returns a concrete AsyncKeyValue - never None. Called from each
    provider builder before the provider is instantiated.
    """
    from cryptography.fernet import Fernet
    from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

    if settings.auth_redis_url:
        # Redis-backed mode: operator-controlled key, audit-friendly because the
        # key is a discrete secret in their secret manager / Coolify UI.
        from key_value.aio.stores.redis import RedisStore

        assert settings.auth_storage_encryption_key is not None  # validator-enforced
        storage_secret = settings.auth_storage_encryption_key.get_secret_value()
        if storage_secret == settings.auth_jwt_signing_key.get_secret_value():
            logger.warning(
                "auth.storage_key_reuse",
                hint=(
                    "AUTH_STORAGE_ENCRYPTION_KEY equals AUTH_JWT_SIGNING_KEY; use a "
                    "dedicated storage key so a leaked signing key does not also "
                    "compromise stored OAuth state."
                ),
            )
        key_bytes = storage_secret.encode("ascii")
        redis_store = RedisStore(url=settings.auth_redis_url)

        logger.info(
            "auth.storage_configured",
            backend="redis",
            url=_sanitize_redis_url(settings.auth_redis_url),
        )
        return FernetEncryptionWrapper(key_value=redis_store, fernet=Fernet(key_bytes))

    # Disk-backed fallback. Encryption key is derived from AUTH_JWT_SIGNING_KEY
    # (mandatory for any auth mode) via HKDF + Fernet-format encoding.
    from fastmcp.server.auth.jwt_issuer import derive_jwt_key
    from key_value.aio.stores.disk import DiskStore

    disk_path = Path(settings.auth_disk_storage_path)
    disk_path.mkdir(parents=True, exist_ok=True)

    derived_key = derive_jwt_key(
        high_entropy_material=settings.auth_jwt_signing_key.get_secret_value(),
        salt=storage_salt,
    )

    logger.info(
        "auth.storage_configured",
        backend="disk",
        path=str(disk_path),
        warning_if_not_mounted=(
            "Mount this path as a Docker volume in production; otherwise OAuth "
            "state is wiped on every container restart."
        ),
    )
    return FernetEncryptionWrapper(
        key_value=DiskStore(directory=disk_path),
        fernet=Fernet(key=derived_key),
    )


def _sanitize_redis_url(url: str) -> str:
    """Strip credentials from a Redis URL before logging.

    redis://user:pass@host:6379/0 -> redis://***@host:6379/0
    """
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1) if "://" in url else ("redis", url)
    _credentials, host_part = rest.split("@", 1)
    return f"{scheme}://***@{host_part}"


__all__ = ["LEGACY_DISK_SALT", "build_client_storage"]
