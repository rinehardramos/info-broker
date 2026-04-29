from __future__ import annotations

from fastapi import APIRouter, Depends

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import CoreSettingIn, CoreSettingsOut

router = APIRouter(prefix="/v3/settings", tags=["v3-settings"])


@router.get("/core", response_model=CoreSettingsOut)
def get_core_settings(user: dict = Depends(get_current_user)):
    rows = fetch_all("SELECT key, value, is_secret FROM core_settings")
    return CoreSettingsOut(
        settings={r["key"]: (None if r["is_secret"] else r["value"]) for r in rows}
    )


@router.put("/core", response_model=CoreSettingsOut)
def update_core_settings(body: list[CoreSettingIn], user: dict = Depends(get_current_user)):
    for item in body:
        execute(
            """
            INSERT INTO core_settings (key, value, is_secret)
            VALUES (%s, %s, %s)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, is_secret = EXCLUDED.is_secret, updated_at = now()
            """,
            (item.key, item.value, item.is_secret),
        )
    rows = fetch_all("SELECT key, value, is_secret FROM core_settings")
    return CoreSettingsOut(
        settings={r["key"]: (None if r["is_secret"] else r["value"]) for r in rows}
    )


@router.get("/plugins/{plugin_id}/enabled")
def get_plugin_enabled(plugin_id: str, user: dict = Depends(get_current_user)):
    key = f"plugin.{plugin_id}.enabled"
    row = fetch_one("SELECT value FROM core_settings WHERE key = %s", (key,))
    return {"plugin_id": plugin_id, "enabled": row["value"].lower() == "true" if row else True}


@router.put("/plugins/{plugin_id}/enabled", status_code=204)
def set_plugin_enabled(plugin_id: str, body: dict, user: dict = Depends(get_current_user)):
    key = f"plugin.{plugin_id}.enabled"
    execute(
        "INSERT INTO core_settings (key, value, is_secret) VALUES (%s, %s, false) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
        (key, "true" if body.get("enabled", True) else "false"),
    )
