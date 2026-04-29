"""AES-256-GCM encrypted token vault backed by the social_tokens table.

Environment
-----------
SOCIAL_TOKEN_ENCRYPTION_KEY
    64-char hex string (32 raw bytes).  The service fails closed if this var
    is absent or malformed — raw tokens are never written to disk or logged.

API
---
store(platform, owner_ref, raw_token) -> str (UUID)
fetch(token_uuid) -> str
delete(token_uuid) -> None
"""
from __future__ import annotations

import logging
import os
import uuid as _uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)

_KEY_ENV = "SOCIAL_TOKEN_ENCRYPTION_KEY"


def _key() -> bytes:
    raw = os.getenv(_KEY_ENV, "")
    if len(raw) != 64:
        raise RuntimeError(
            f"{_KEY_ENV} must be a 64-char hex string (32 bytes); "
            f"got length {len(raw)}"
        )
    try:
        return bytes.fromhex(raw)
    except ValueError as exc:
        raise RuntimeError(f"{_KEY_ENV} is not valid hex: {exc}") from exc


def store(platform: str, owner_ref: str, raw_token: str) -> str:
    """Encrypt *raw_token* and persist it.  Returns the token UUID."""
    from app.routers.v3.db import execute, fetch_one

    key_bytes = _key()
    aesgcm = AESGCM(key_bytes)
    nonce = os.urandom(12)  # 96-bit nonce standard for GCM
    ciphertext = aesgcm.encrypt(nonce, raw_token.encode(), None)

    token_id = str(_uuid.uuid4())
    execute(
        """
        INSERT INTO social_tokens (id, platform, owner_ref, ciphertext, nonce)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (token_id, platform, owner_ref, ciphertext, nonce),
    )
    log.info("token_vault.store platform=%s owner=%s id=%s", platform, owner_ref, token_id)
    return token_id


def fetch(token_uuid: str) -> str:
    """Decrypt and return the raw token for *token_uuid*.

    Raises ``KeyError`` if the UUID is not found.
    """
    from app.routers.v3.db import fetch_one

    row = fetch_one(
        "SELECT ciphertext, nonce FROM social_tokens WHERE id = %s",
        (token_uuid,),
    )
    if not row:
        raise KeyError(f"token {token_uuid!r} not found")

    key_bytes = _key()
    aesgcm = AESGCM(key_bytes)
    plaintext = aesgcm.decrypt(bytes(row["nonce"]), bytes(row["ciphertext"]), None)
    return plaintext.decode()


def delete(token_uuid: str) -> None:
    """Remove a stored token.  No-op if UUID does not exist."""
    from app.routers.v3.db import execute

    execute("DELETE FROM social_tokens WHERE id = %s", (token_uuid,))
    log.info("token_vault.delete id=%s", token_uuid)
