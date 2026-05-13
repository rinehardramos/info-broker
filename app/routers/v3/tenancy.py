from __future__ import annotations

from fastapi import HTTPException

from app.routers.v3.db import fetch_one


def user_org_id(user: dict) -> str:
    """Return the authenticated user's organization id."""
    return str(user.get("org_id") or "")


def require_system_user(user_id: str, org_id: str) -> dict:
    """Validate a system/API-key request against both user_id and org_id."""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id is required")
    user = fetch_one(
        "SELECT id, org_id FROM ui_users WHERE id = %s AND org_id = %s AND is_active = true",
        (user_id, org_id),
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found in organization")
    return user


def require_user_run(run_id: str, user_id: str, org_id: str) -> dict:
    run = fetch_one(
        "SELECT * FROM pipeline_runs WHERE id = %s AND user_id = %s AND org_id = %s",
        (run_id, user_id, org_id),
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def require_user_source(source_id: str, user_id: str, org_id: str) -> dict:
    source = fetch_one(
        "SELECT * FROM research_sources WHERE id = %s AND user_id = %s AND org_id = %s",
        (source_id, user_id, org_id),
    )
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source
