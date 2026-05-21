from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.crypto import decrypt_value, encrypt_value
from app.modes.loader import get_default_mode_id, list_modes
from app.routers.v3.auth import get_current_user, require_admin
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import CoreSettingIn, CoreSettingsOut, DefaultModeIn, DefaultModeOut

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

    # Validate value (None means clear)
    if body.value is not None:
        valid = {m.id for m in list_modes()}
        if body.value not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown mode id; must be one of {sorted(valid)}",
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
