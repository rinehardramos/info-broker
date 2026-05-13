from __future__ import annotations

from fastapi import Depends, HTTPException

from app.routers.v3.db import fetch_one


def user_org_id(user: dict) -> str:
    """Return the authenticated user's organization id as a string."""
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


def _user_role(user: dict) -> str:
    """Resolve effective role: explicit role column falls back to is_admin flag."""
    if user.get("is_admin"):
        return "admin"
    return user.get("role") or "analyst"


def require_analyst(user: dict) -> dict:
    """Dependency: passes for admin and analyst; blocks viewers."""
    if _user_role(user) not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Analyst or admin role required")
    return user


def require_viewer(user: dict) -> dict:
    """Dependency: passes for any authenticated user (admin / analyst / viewer)."""
    return user


def _make_analyst_dep():
    from app.routers.v3.auth import get_current_user

    def _dep(user: dict = Depends(get_current_user)) -> dict:
        return require_analyst(user)

    return _dep


require_analyst_user = _make_analyst_dep()


def require_user_run(run_id: str, user_id: str, org_id: str) -> dict:
    """Fetch a pipeline_run scoped to user and org, raising 404 if not found."""
    run = fetch_one(
        "SELECT * FROM pipeline_runs WHERE id = %s AND user_id = %s AND org_id = %s",
        (run_id, user_id, org_id),
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def require_user_source(source_id: str, user_id: str, org_id: str) -> dict:
    """Fetch a research_source scoped to user and org, raising 404 if not found."""
    source = fetch_one(
        "SELECT * FROM research_sources WHERE id = %s AND user_id = %s AND org_id = %s",
        (source_id, user_id, org_id),
    )
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


def org_scope_clause(user: dict) -> tuple[str, list]:
    """Return (sql_fragment, params) for org scoping.

    Superadmin (is_admin=True) sees all orgs — returns empty fragment.
    All other users are scoped to their own org_id.

    Usage:
        clause, params = org_scope_clause(user)
        cursor.execute(
            f"SELECT * FROM pipelines WHERE id = %s {clause}",
            [pipeline_id, *params],
        )
    """
    if user.get("is_admin"):
        return ("", [])
    return ("AND org_id = %s", [user_org_id(user)])
