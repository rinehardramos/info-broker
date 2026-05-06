"""Symmetric encryption for secrets stored in Postgres."""
from __future__ import annotations

import base64
import logging
import os

log = logging.getLogger(__name__)


def _get_key() -> bytes | None:
    """Get encryption key from env (set by OpenBao loader or .env)."""
    raw = os.getenv("SETTINGS_ENCRYPTION_KEY")
    if not raw:
        return None
    # Fernet requires 32 bytes, URL-safe base64 encoded (44 chars with padding)
    # Accept either a pre-formatted Fernet key (44 chars) or a raw string
    try:
        if len(raw) == 44:
            # Already a Fernet-formatted key — validate it's valid base64
            base64.urlsafe_b64decode(raw)
            return raw.encode()
        else:
            # Treat as raw secret — pad/truncate to 32 bytes then base64-encode
            return base64.urlsafe_b64encode(raw.encode()[:32].ljust(32, b"\0"))
    except Exception:
        log.warning("Invalid SETTINGS_ENCRYPTION_KEY format")
        return None


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string. Returns 'enc:...' prefixed ciphertext, or plaintext if no key."""
    key = _get_key()
    if not key:
        return plaintext
    from cryptography.fernet import Fernet

    f = Fernet(key)
    return "enc:" + f.encrypt(plaintext.encode()).decode()


def decrypt_value(stored: str) -> str:
    """Decrypt a string. If not prefixed with 'enc:', returns as-is (legacy unencrypted)."""
    if not stored.startswith("enc:"):
        return stored  # legacy unencrypted value
    key = _get_key()
    if not key:
        log.warning("Encrypted value found but no SETTINGS_ENCRYPTION_KEY set")
        return stored  # can't decrypt, return as-is
    from cryptography.fernet import Fernet

    f = Fernet(key)
    return f.decrypt(stored[4:].encode()).decode()
