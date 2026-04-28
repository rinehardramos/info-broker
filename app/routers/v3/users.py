from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_one
from app.routers.v3.models import PreferencesIn, PreferencesOut, UserOut

router = APIRouter(prefix="/v3/users", tags=["v3-users"])


@router.get("/me", response_model=UserOut)
def get_me(user: dict = Depends(get_current_user)):
    return UserOut(**user)


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
