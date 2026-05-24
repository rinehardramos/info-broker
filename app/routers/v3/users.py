from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_one
from app.routers.v3.models import PreferencesIn, PreferencesOut, UserOut, UserProfileIn

router = APIRouter(prefix="/v3/users", tags=["v3-users"])


def _user_to_out(user: dict) -> UserOut:
    payload = dict(user)
    payload["password_set"] = bool(payload.get("password_hash"))
    return UserOut(**payload)


@router.get("/me", response_model=UserOut)
def get_me(user: dict = Depends(get_current_user)):
    return _user_to_out(user)


@router.patch("/me", response_model=UserOut)
def update_me(body: UserProfileIn, user: dict = Depends(get_current_user)):
    """Self-service personalization. Username, email, admin flags untouched."""
    allowed = {
        "display_name": body.display_name,
        "avatar_url":   body.avatar_url,
        "timezone":     body.timezone,
        "locale":       body.locale,
    }
    # Only include keys the client explicitly sent (None means leave unchanged)
    updates = {k: v for k, v in allowed.items() if v is not None}
    if not updates:
        return _user_to_out(user)
    # Trim free-text fields, enforce reasonable max length
    for k in ("display_name", "timezone", "locale"):
        if k in updates and isinstance(updates[k], str):
            updates[k] = updates[k].strip()[:128]
    if "avatar_url" in updates and isinstance(updates["avatar_url"], str):
        updates["avatar_url"] = updates["avatar_url"].strip()[:512]
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    row = fetch_one(
        f"UPDATE ui_users SET {set_clause} WHERE id = %s RETURNING *",  # noqa: S608 - set_clause keys from hardcoded allowlist; values parameterized
        tuple(list(updates.values()) + [str(user["id"])]),
    )
    return _user_to_out(dict(row))


@router.get("/me/preferences", response_model=PreferencesOut)
def get_preferences(user: dict = Depends(get_current_user)):
    prefs = fetch_one("SELECT * FROM ui_preferences WHERE user_id = %s", (str(user["id"]),))
    if not prefs:
        return PreferencesOut(theme="navy", column_layout={})
    return PreferencesOut(theme=prefs["theme"], column_layout=prefs["column_layout"])


@router.put("/me/preferences", response_model=PreferencesOut)
def update_preferences(body: PreferencesIn, user: dict = Depends(get_current_user)):
    uid = str(user["id"])
    prefs = fetch_one("SELECT * FROM ui_preferences WHERE user_id = %s", (uid,))
    theme = body.theme or (prefs["theme"] if prefs else "navy")
    layout = body.column_layout if body.column_layout is not None else (prefs["column_layout"] if prefs else {})
    execute(
        """
        INSERT INTO ui_preferences (user_id, theme, column_layout)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET theme = EXCLUDED.theme, column_layout = EXCLUDED.column_layout, updated_at = now()
        """,
        (uid, theme, json.dumps(layout)),
    )
    return PreferencesOut(theme=theme, column_layout=layout)
