from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import MonitorIn, MonitorOut

router = APIRouter(prefix="/v3/monitors", tags=["v3-monitors"])


@router.get("", response_model=list[MonitorOut])
def list_monitors(user: dict = Depends(get_current_user)):
    rows = fetch_all(
        "SELECT * FROM feed_monitors WHERE user_id = %s ORDER BY created_at DESC",
        (str(user["id"]),),
    )
    return [MonitorOut(**r) for r in rows]


@router.post("", response_model=MonitorOut, status_code=201)
def create_monitor(body: MonitorIn, user: dict = Depends(get_current_user)):
    row = fetch_one(
        """
        INSERT INTO feed_monitors (user_id, name, type, target, poll_interval_minutes)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
        """,
        (str(user["id"]), body.name, body.type, body.target, body.poll_interval_minutes),
    )
    return MonitorOut(**row)


@router.delete("/{monitor_id}", status_code=204)
def delete_monitor(monitor_id: str, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT id FROM feed_monitors WHERE id = %s AND user_id = %s",
        (monitor_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Monitor not found")
    execute("DELETE FROM feed_monitors WHERE id = %s", (monitor_id,))
