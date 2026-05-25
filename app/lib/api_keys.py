"""Scoped API-key resolution helper.

Resolution order (first match wins):
    1. User-scoped vault row (``api_key_vault`` WHERE scope='user' AND owner_id=user_id)
    2. Org-scoped vault row  (``api_key_vault`` WHERE scope='org'  AND owner_id=org_id)
    3. Global vault row      (``api_key_vault`` WHERE scope='global' AND owner_id IS NULL)
    4. ``core_settings`` row (legacy; may be Fernet-encrypted with app.crypto prefix)
    5. Environment variable  (key_name.upper() — e.g. hunter_io_api_key → HUNTER_IO_API_KEY)

Security guarantees
-------------------
- Resolved values are NEVER logged. Only key_name, scope, and source are logged.
- Callers receive the decrypted string value or None.
- DB errors are swallowed (non-fatal) so a misconfigured DB doesn't break the
  resolution chain — the function falls through to the env fallback.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def _vault_fetch(key_name: str, scope: str, owner_id: str) -> dict | None:
    """Fetch a scoped vault row by (key_name, scope, owner_id). Non-fatal."""
    try:
        from app.routers.v3.db import fetch_one
        return fetch_one(
            """
            SELECT value_encrypted
              FROM api_key_vault
             WHERE key_name = %s AND scope = %s AND owner_id = %s::uuid
            """,
            (key_name, scope, owner_id),
        )
    except Exception:
        log.debug(
            "api_keys: vault fetch failed key_name=%r scope=%r",
            key_name, scope, exc_info=True,
        )
        return None


def _vault_fetch_global(key_name: str) -> dict | None:
    """Fetch the global vault row (owner_id IS NULL). Non-fatal."""
    try:
        from app.routers.v3.db import fetch_one
        return fetch_one(
            """
            SELECT value_encrypted
              FROM api_key_vault
             WHERE key_name = %s AND scope = 'global' AND owner_id IS NULL
            """,
            (key_name,),
        )
    except Exception:
        log.debug(
            "api_keys: global vault fetch failed key_name=%r",
            key_name, exc_info=True,
        )
        return None


def resolve_api_key(
    key_name: str,
    *,
    user_id: str | None,
    org_id: str | None,
) -> str | None:
    """Return the best-scoped API key for *key_name*, or None if not configured.

    NEVER logs the resolved value — only key_name, scope, and source.
    """
    from app.lib.secret_box import decrypt

    # 1. User-scoped vault
    if user_id and user_id not in ("mcp-system", ""):
        row = _vault_fetch(key_name, "user", user_id)
        if row and row.get("value_encrypted"):
            log.info(
                "api_keys: resolved key_name=%r scope=user source=vault",
                key_name,
            )
            return decrypt(row["value_encrypted"])

    # 2. Org-scoped vault
    if org_id:
        row = _vault_fetch(key_name, "org", org_id)
        if row and row.get("value_encrypted"):
            log.info(
                "api_keys: resolved key_name=%r scope=org source=vault",
                key_name,
            )
            return decrypt(row["value_encrypted"])

    # 3. Global vault row
    row = _vault_fetch_global(key_name)
    if row and row.get("value_encrypted"):
        log.info(
            "api_keys: resolved key_name=%r scope=global source=vault",
            key_name,
        )
        return decrypt(row["value_encrypted"])

    # 4. core_settings (legacy — may carry a Fernet-encrypted value with enc: prefix)
    try:
        from app.routers.v3.db import fetch_one
        cs_row = fetch_one(
            "SELECT value FROM core_settings WHERE key = %s",
            (key_name,),
        )
        if cs_row and cs_row.get("value"):
            log.info(
                "api_keys: resolved key_name=%r source=core_settings",
                key_name,
            )
            raw = cs_row["value"]
            if raw.startswith("enc:"):
                from app.crypto import decrypt_value
                raw = decrypt_value(raw)
            return raw
    except Exception:
        log.debug(
            "api_keys: core_settings lookup failed key_name=%r",
            key_name, exc_info=True,
        )

    # 5. Environment variable
    env_value = os.getenv(key_name.upper())
    if env_value:
        log.info(
            "api_keys: resolved key_name=%r source=env",
            key_name,
        )
        return env_value

    return None
