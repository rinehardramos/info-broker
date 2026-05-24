"""Fernet-based symmetric encryption for the API-key vault.

Keys are encrypted before being written to ``api_key_vault`` and decrypted only
at the server-side node-execute path. Decrypted values NEVER leave the process
via logs, WS payloads, or HTTP responses.

Environment variable
--------------------
``VAULT_ENCRYPTION_KEY`` — 32-byte URL-safe base64-encoded key (44 chars).
Generate with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

A dev fallback is derived from a fixed secret when the env var is absent. The
fallback logs a LOUD warning at every startup so it can't be silently used in
production.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os

log = logging.getLogger(__name__)

_warned_dev_key: bool = False


def _get_fernet_key() -> bytes:
    """Return the Fernet key bytes, warning loudly if falling back to dev key."""
    global _warned_dev_key
    raw = os.getenv("VAULT_ENCRYPTION_KEY", "")
    if raw:
        return raw.encode("ascii")

    # Dev fallback: deterministic but NOT secret — any production deploy MUST
    # set VAULT_ENCRYPTION_KEY or encrypted values are trivially reversible.
    if not _warned_dev_key:
        log.warning(
            "VAULT_ENCRYPTION_KEY is not set — using insecure dev fallback. "
            "Set VAULT_ENCRYPTION_KEY to a real Fernet key before going to production."
        )
        _warned_dev_key = True

    digest = hashlib.sha256(b"info-broker-dev-vault-key-do-not-use-in-prod").digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* and return a URL-safe base64 Fernet token."""
    from cryptography.fernet import Fernet

    fernet = Fernet(_get_fernet_key())
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a Fernet *token* and return the plaintext.

    Raises :exc:`ValueError` on invalid token or key mismatch — callers should
    treat this as a configuration error, not a user-visible failure.
    """
    from cryptography.fernet import Fernet, InvalidToken

    fernet = Fernet(_get_fernet_key())
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            "vault decrypt failed — token is invalid or key mismatch"
        ) from exc
