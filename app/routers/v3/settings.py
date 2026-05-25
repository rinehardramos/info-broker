from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.crypto import decrypt_value, encrypt_value
from app.modes.loader import get_default_mode_id
from app.routers.v3.auth import get_current_user, require_admin
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import CoreSettingIn, CoreSettingsOut, DefaultModeIn, DefaultModeOut
from app.routers.v3.preflight import valid_preflight_mode_ids

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v3/settings", tags=["v3-settings"])


@router.get("/core", response_model=CoreSettingsOut)
def get_core_settings(user: dict = Depends(get_current_user)):
    rows = fetch_all("SELECT key, value, is_secret FROM core_settings")
    return CoreSettingsOut(
        settings={r["key"]: (None if r["is_secret"] else decrypt_value(r["value"])) for r in rows}
    )


@router.put("/core", response_model=CoreSettingsOut)
def update_core_settings(body: list[CoreSettingIn], user: dict = Depends(require_admin)):
    for item in body:
        stored_value = encrypt_value(item.value) if item.is_secret else item.value
        execute(
            """
            INSERT INTO core_settings (key, value, is_secret)
            VALUES (%s, %s, %s)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, is_secret = EXCLUDED.is_secret, updated_at = now()
            """,
            (item.key, stored_value, item.is_secret),
        )
    rows = fetch_all("SELECT key, value, is_secret FROM core_settings")
    return CoreSettingsOut(
        settings={r["key"]: (None if r["is_secret"] else decrypt_value(r["value"])) for r in rows}
    )


@router.get("/plugins/{plugin_id}/enabled")
def get_plugin_enabled(plugin_id: str, user: dict = Depends(get_current_user)):
    key = f"plugin.{plugin_id}.enabled"
    row = fetch_one("SELECT value FROM core_settings WHERE key = %s", (key,))
    return {"plugin_id": plugin_id, "enabled": row["value"].lower() == "true" if row else True}


@router.put("/plugins/{plugin_id}/enabled", status_code=204)
def set_plugin_enabled(plugin_id: str, body: dict, user: dict = Depends(require_admin)):
    key = f"plugin.{plugin_id}.enabled"
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES (%s, %s, false) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
        (key, "true" if body.get("enabled", True) else "false"),
    )


@router.get("/default_mode", response_model=DefaultModeOut)
def get_default_mode(user: dict = Depends(get_current_user)) -> DefaultModeOut:
    org_id = str(user["org_id"]) if user.get("org_id") else None

    org_row = (
        fetch_one(
            "SELECT value FROM org_settings WHERE org_id = %s AND key = 'default_mode_id'",
            (org_id,),
        )
        if org_id
        else None
    )
    org_value = org_row["value"] if org_row and org_row.get("value") else None

    global_row = fetch_one(
        "SELECT value FROM core_settings WHERE key = 'default_mode_id'", ()
    )
    global_value = global_row["value"] if global_row and global_row.get("value") else None

    resolved = get_default_mode_id(org_id)
    if org_value and resolved == org_value:
        source: str = "org"
    elif global_value and resolved == global_value:
        source = "global"
    else:
        source = "fallback"

    return DefaultModeOut(
        resolved=resolved,
        source=source,  # type: ignore[arg-type]
        org_value=org_value,
        global_value=global_value,
    )


@router.put("/default_mode", response_model=DefaultModeOut)
def put_default_mode(
    body: DefaultModeIn,
    user: dict = Depends(get_current_user),
) -> DefaultModeOut:
    # Authz
    if body.scope == "global":
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Global default requires admin")
    else:  # "org"
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Org default requires org admin role")
        if not user.get("org_id"):
            raise HTTPException(status_code=400, detail="User has no org")

    # Validate value (None means clear). Validate against the preflight mode
    # catalog — these are the ids the picker actually renders.
    if body.value is not None:
        valid = valid_preflight_mode_ids()
        if body.value not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown mode id; must be one of {sorted(valid)}",
            )

        # Don't let admins pin a default that they've hidden — would brick
        # non-admin users. Check visibility at the same scope they're setting.
        from app.routers.v3.visibility import is_id_visible
        scope_org_id = str(user["org_id"]) if body.scope == "org" else None
        if not is_id_visible("mode", body.value, scope_org_id):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Cannot set '{body.value}' as default — it is currently "
                    f"hidden via mode_visibility. Unhide it first or pick a "
                    f"visible mode."
                ),
            )

    if body.scope == "global":
        if body.value is None:
            execute("DELETE FROM core_settings WHERE key = 'default_mode_id'", ())
        else:
            execute(
                """INSERT INTO core_settings (key, value, is_secret)
                   VALUES ('default_mode_id', %s, false)
                   ON CONFLICT (key) DO UPDATE
                   SET value = EXCLUDED.value, updated_at = now()""",
                (body.value,),
            )
    else:
        org_id = str(user["org_id"])
        if body.value is None:
            execute(
                "DELETE FROM org_settings WHERE org_id = %s AND key = 'default_mode_id'",
                (org_id,),
            )
        else:
            execute(
                """INSERT INTO org_settings (org_id, key, value)
                   VALUES (%s, 'default_mode_id', %s)
                   ON CONFLICT (org_id, key) DO UPDATE
                   SET value = EXCLUDED.value, updated_at = now()""",
                (org_id, body.value),
            )

    return get_default_mode(user=user)


# ---------------------------------------------------------------------------
# API-key vault endpoints
# ---------------------------------------------------------------------------


class ApiKeyIn(BaseModel):
    key_name: str
    value: str
    scope: str  # 'user' | 'org' | 'global'


class ApiKeyEntry(BaseModel):
    key_name: str
    scope: str
    owner_id: str | None


@router.post("/api-keys", status_code=204)
def upsert_api_key(body: ApiKeyIn, user: dict = Depends(get_current_user)) -> None:
    """Store or update an API key in the encrypted vault.

    Authorization:
    - scope='user'   → the calling user's own entry (no elevation needed)
    - scope='org'    → requires org-admin role
    - scope='global' → requires is_admin

    The value is Fernet-encrypted before storage and is NEVER returned in any
    response — GET /v3/settings/api-keys returns presence only.
    """
    from app.lib.secret_box import encrypt

    scope = body.scope
    if scope not in ("user", "org", "global"):
        raise HTTPException(status_code=400, detail="scope must be 'user', 'org', or 'global'")

    if scope == "global":
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Global scope requires admin")
        owner_id = None
    elif scope == "org":
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Org scope requires org-admin role")
        if not user.get("org_id"):
            raise HTTPException(status_code=400, detail="User has no org")
        owner_id = str(user["org_id"])
    else:  # user
        owner_id = str(user["id"])

    encrypted = encrypt(body.value)

    if owner_id is None:
        execute(
            """
            INSERT INTO api_key_vault (key_name, scope, owner_id, value_encrypted, updated_at)
            VALUES (%s, %s, NULL, %s, now())
            ON CONFLICT (key_name, scope, owner_id) DO UPDATE
            SET value_encrypted = EXCLUDED.value_encrypted, updated_at = now()
            """,
            (body.key_name, scope, encrypted),
        )
    else:
        execute(
            """
            INSERT INTO api_key_vault (key_name, scope, owner_id, value_encrypted, updated_at)
            VALUES (%s, %s, %s::uuid, %s, now())
            ON CONFLICT (key_name, scope, owner_id) DO UPDATE
            SET value_encrypted = EXCLUDED.value_encrypted, updated_at = now()
            """,
            (body.key_name, scope, owner_id, encrypted),
        )

    # For global scope also mirror into core_settings so legacy resolvers still work
    if scope == "global":
        from app.crypto import encrypt_value as _enc
        execute(
            """
            INSERT INTO core_settings (key, value, is_secret)
            VALUES (%s, %s, true)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, is_secret = true, updated_at = now()
            """,
            (body.key_name, _enc(body.value)),
        )

    # Log only the key name and scope — never the value.
    log.info(
        "api_keys: upserted key_name=%r scope=%r owner_id=%r by user=%r",
        body.key_name, scope, owner_id, str(user.get("id")),
    )


@router.get("/api-keys", response_model=list[ApiKeyEntry])
def list_api_keys(user: dict = Depends(get_current_user)) -> list[ApiKeyEntry]:
    """List configured API key names and their scopes.

    Returns presence info only — encrypted values are NEVER included in the response.
    Each caller sees:
    - Their own user-scoped entries
    - Org-scoped entries for their org (if they have one)
    - All global entries (visible to everyone; admin-only write)
    """
    user_id = str(user["id"])
    org_id = str(user["org_id"]) if user.get("org_id") else None

    rows = fetch_all(
        """
        SELECT key_name, scope, owner_id::text AS owner_id
          FROM api_key_vault
         WHERE
            key_name NOT LIKE 'sitecred:%%'
            AND (
                (scope = 'global' AND owner_id IS NULL)
                OR (scope = 'user'   AND owner_id = %s::uuid)
                OR (scope = 'org'    AND owner_id = %s::uuid AND %s IS NOT NULL)
            )
         ORDER BY scope, key_name
        """,
        (user_id, org_id or user_id, org_id),
    )
    return [ApiKeyEntry(**r) for r in rows]


# ---------------------------------------------------------------------------
# Site-credential vault (Phase: authenticated sessions, #item-4)
# Stores the user's OWN login for a site (username+password) encrypted in the
# same vault, so the stealth browser can log in and access gated data. The
# password is NEVER returned by any endpoint and NEVER reaches the brain — it is
# resolved server-side at node-execute via resolve_site_credential().
# ---------------------------------------------------------------------------

_SITECRED_PREFIX = "sitecred:"


class SiteCredentialIn(BaseModel):
    site: str            # e.g. "fsbo.com"
    username: str
    password: str
    scope: str = "user"  # 'user' (own login) | 'org' (shared team account)


class SiteCredentialEntry(BaseModel):
    site: str
    scope: str
    username: str        # shown (not secret); password is NEVER returned


@router.post("/site-credentials", status_code=204)
def upsert_site_credential(body: SiteCredentialIn, user: dict = Depends(get_current_user)) -> None:
    """Store the user's OWN login for a site (encrypted). Password is never
    returned and never reaches the brain. The user is responsible for ensuring
    they are authorized to automate access to the site per its ToS."""
    import json

    from app.lib.secret_box import encrypt

    scope = body.scope
    if scope not in ("user", "org"):
        raise HTTPException(status_code=400, detail="scope must be 'user' or 'org'")
    if scope == "org":
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Org scope requires org-admin role")
        if not user.get("org_id"):
            raise HTTPException(status_code=400, detail="User has no org")
        owner_id = str(user["org_id"])
    else:
        owner_id = str(user["id"])

    site = body.site.strip().lower()
    if not site:
        raise HTTPException(status_code=400, detail="site is required")
    key_name = _SITECRED_PREFIX + site
    encrypted = encrypt(json.dumps({"username": body.username, "password": body.password}))

    execute(
        """
        INSERT INTO api_key_vault (key_name, scope, owner_id, value_encrypted, updated_at)
        VALUES (%s, %s, %s::uuid, %s, now())
        ON CONFLICT (key_name, scope, owner_id) DO UPDATE
        SET value_encrypted = EXCLUDED.value_encrypted, updated_at = now()
        """,
        (key_name, scope, owner_id, encrypted),
    )
    # Log site + scope only — NEVER the username or password.
    log.info(
        "site_credentials: upserted site=%r scope=%r owner_id=%r by user=%r",
        site, scope, owner_id, str(user.get("id")),
    )


@router.get("/site-credentials", response_model=list[SiteCredentialEntry])
def list_site_credentials(user: dict = Depends(get_current_user)) -> list[SiteCredentialEntry]:
    """List configured site logins (site + scope + username). Password is NEVER
    returned. Each caller sees their own user-scoped + their org-scoped entries."""
    import json

    from app.lib.secret_box import decrypt

    user_id = str(user["id"])
    org_id = str(user["org_id"]) if user.get("org_id") else None
    rows = fetch_all(
        """
        SELECT key_name, scope, value_encrypted
          FROM api_key_vault
         WHERE key_name LIKE 'sitecred:%%'
           AND ((scope = 'user' AND owner_id = %s::uuid)
                OR (scope = 'org' AND owner_id = %s::uuid AND %s IS NOT NULL))
         ORDER BY scope, key_name
        """,
        (user_id, org_id or user_id, org_id),
    )
    out: list[SiteCredentialEntry] = []
    for r in rows:
        site = r["key_name"][len(_SITECRED_PREFIX):]
        username = ""
        try:
            username = json.loads(decrypt(r["value_encrypted"])).get("username", "")
        except Exception:
            pass
        out.append(SiteCredentialEntry(site=site, scope=r["scope"], username=username))
    return out
