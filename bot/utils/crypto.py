"""Application-level encryption for sensitive DB columns.

Uses Fernet (AES-128-CBC + HMAC) keyed from ``settings.encryption_key``.
The :class:`EncryptedString` SQLAlchemy type encrypts on write and decrypts
on read, so repositories/handlers keep working with plaintext values.

Backward compatible: if the key is unset, values pass through unchanged;
if a stored value is not a valid Fernet token (legacy plaintext written
before encryption was enabled), it is returned as-is. Such rows become
encrypted automatically the next time they are written.
"""

from __future__ import annotations

from functools import lru_cache

from loguru import logger
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from bot.config import settings

_warned = False


@lru_cache(maxsize=4)
def _fernet_for(key: str):
    from cryptography.fernet import Fernet

    return Fernet(key.encode())


def _get_fernet():
    global _warned
    key = settings.encryption_key.strip()
    if not key:
        if not _warned:
            logger.warning(
                "ENCRYPTION_KEY is not set — sensitive fields (VLESS links, "
                "emails) are stored in PLAINTEXT. Set it before production."
            )
            _warned = True
        return None
    return _fernet_for(key)


def encrypt(value: str) -> str:
    fernet = _get_fernet()
    if fernet is None:
        return value
    return fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    fernet = _get_fernet()
    if fernet is None:
        return value
    from cryptography.fernet import InvalidToken

    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        # Legacy plaintext value written before encryption was enabled.
        return value


class EncryptedString(TypeDecorator):
    """Transparently encrypts/decrypts a text column with Fernet.

    Storage stays TEXT (base64 ciphertext). Equality filtering on the
    column is NOT supported (ciphertext is non-deterministic).
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return encrypt(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return decrypt(value)
