"""OAuth client-storage factory.

FastMCP's OAuth providers (OIDCProxy, OAuthProxy, AzureProvider, GoogleProvider)
persist five classes of state: DCR client metadata, authorization codes + PKCE
challenges, refresh-token-hash -> upstream-token-id mappings, FastMCP-issued JWT
JTI -> upstream-token mappings, and in-flight OAuth transactions.

Without an explicit ``client_storage`` FastMCP falls back to a DiskStore under
``platformdirs.user_data_dir()``, which inside a container is ephemeral - every
restart wipes everything and kicks all users out. This factory always supplies a
durable, encrypted-at-rest backend.

Two operator-selectable backends, both encrypted at rest:

* AUTH_REDIS_URL set  -> RedisStore wrapped in FernetEncryptionWrapper with the
  operator-provided AUTH_STORAGE_ENCRYPTION_KEY. Recommended for production:
  survives restart + container replacement, supports horizontal scaling.
* AUTH_REDIS_URL unset -> DiskStore at AUTH_DISK_STORAGE_PATH wrapped in
  FernetEncryptionWrapper with a key DERIVED from AUTH_JWT_SIGNING_KEY via HKDF.

The one invariant that matters: the encryption key must be STABLE across
container restarts, otherwise every restart invalidates all stored state and
forces every user to re-authenticate. Stability is guaranteed because the key is
derived from AUTH_JWT_SIGNING_KEY (a fixed env var, mandatory for any auth mode)
plus a fixed salt - the same inputs every boot yield the same key. The operator's
remaining duty is to MOUNT the disk path as a volume (or use Redis); otherwise
the encrypted files themselves vanish on restart regardless of the key.

There is intentionally NO backward-compatibility with any prior salt: the
encrypted store is server-side OAuth state, and a one-time re-authentication on
cutover is acceptable. We do not couple to FastMCP's historical DiskStore salt.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .._config_protocols import StorageSettings
from ..observability import get_logger

if TYPE_CHECKING:
    from key_value.aio.protocols import AsyncKeyValue

logger = get_logger("bg-mcpcore.auth.storage")

# Fixed salt for the disk-mode HKDF derivation. Its only requirement is to be
# constant, so the derived key is identical on every boot (restart-stable). It is
# bg-mcpcore's own value and deliberately NOT FastMCP's historical default - we
# do not aim to decrypt state written by a different stack.
_STORAGE_KEY_SALT = "bg-mcpcore-oauth-storage"


def build_client_storage(settings: StorageSettings) -> AsyncKeyValue:
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

    # Disk-backed fallback. The key is derived from AUTH_JWT_SIGNING_KEY (a fixed
    # env var) + a fixed salt, so it is identical on every restart. Mount the path
    # as a volume or the encrypted files are wiped on restart regardless.
    from fastmcp.server.auth.jwt_issuer import derive_jwt_key
    from key_value.aio.stores.disk import DiskStore

    disk_path = Path(settings.auth_disk_storage_path)
    disk_path.mkdir(parents=True, exist_ok=True)

    derived_key = derive_jwt_key(
        high_entropy_material=settings.auth_jwt_signing_key.get_secret_value(),
        salt=_STORAGE_KEY_SALT,
    )

    logger.info(
        "auth.storage_configured",
        backend="disk",
        path=str(disk_path),
        warning_if_not_mounted=(
            "Mount this path as a Docker volume; otherwise OAuth state is wiped on "
            "every container restart and all users must re-authenticate."
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


__all__ = ["build_client_storage"]
