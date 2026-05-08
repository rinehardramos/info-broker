"""Curation API — contradictions, stale flags, and curation stats."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one

router = APIRouter(prefix="/v3/knowledge", tags=["v3-curation"])
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ResolveBody(BaseModel):
    winner: str


# ---------------------------------------------------------------------------
# Contradictions
# ---------------------------------------------------------------------------


@router.get("/contradictions")
def list_contradictions(
    status: str | None = None,
    entity_ref: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _user: dict = Depends(get_current_user),
) -> list[dict]:
    """List knowledge-graph contradictions with optional filters."""
    where_clauses = []
    params: list = []

    if status is not None:
        where_clauses.append("status = %s")
        params.append(status)
    if entity_ref is not None:
        where_clauses.append("entity_ref = %s")
        params.append(entity_ref)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params += [limit, offset]

    rows = fetch_all(
        f"""
        SELECT id, entity_ref, attribute,
               value_a, value_b,
               confidence_a, confidence_b,
               observed_at_a, observed_at_b,
               source_run_a, source_run_b,
               observation_id_a, observation_id_b,
               winner, status, resolved_by, resolved_at,
               created_at
        FROM kg_contradictions
        {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        params,
    )
    return [dict(r) for r in rows]


@router.post("/contradictions/{contradiction_id}/resolve")
def resolve_contradiction(
    contradiction_id: int,
    body: ResolveBody,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Manually resolve a contradiction by selecting the winning value."""
    row = fetch_one(
        "SELECT id FROM kg_contradictions WHERE id = %s",
        (contradiction_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Contradiction not found")

    execute(
        """
        UPDATE kg_contradictions
           SET status = 'user_resolved',
               winner = %s,
               resolved_by = 'user',
               resolved_at = now()
         WHERE id = %s
        """,
        (body.winner, contradiction_id),
    )
    return {"id": contradiction_id, "status": "user_resolved", "winner": body.winner}


@router.post("/contradictions/{contradiction_id}/dismiss")
def dismiss_contradiction(
    contradiction_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Dismiss a contradiction (mark as not worth resolving)."""
    row = fetch_one(
        "SELECT id FROM kg_contradictions WHERE id = %s",
        (contradiction_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Contradiction not found")

    execute(
        """
        UPDATE kg_contradictions
           SET status = 'dismissed',
               resolved_by = 'user',
               resolved_at = now()
         WHERE id = %s
        """,
        (contradiction_id,),
    )
    return {"id": contradiction_id, "status": "dismissed"}


# ---------------------------------------------------------------------------
# Stale flags
# ---------------------------------------------------------------------------


@router.get("/stale")
def list_stale_flags(
    status: str | None = None,
    attribute: str | None = None,
    entity_ref: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _user: dict = Depends(get_current_user),
) -> list[dict]:
    """List stale observation flags with optional filters."""
    where_clauses = []
    params: list = []

    if status is not None:
        where_clauses.append("status = %s")
        params.append(status)
    if attribute is not None:
        where_clauses.append("attribute = %s")
        params.append(attribute)
    if entity_ref is not None:
        where_clauses.append("entity_ref = %s")
        params.append(entity_ref)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params += [limit, offset]

    rows = fetch_all(
        f"""
        SELECT id, entity_ref, attribute,
               current_value, observation_id,
               observed_at, ttl_days, status,
               created_at
        FROM kg_stale_flags
        {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        params,
    )
    return [dict(r) for r in rows]


@router.post("/stale/{flag_id}/dismiss")
def dismiss_stale_flag(
    flag_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Dismiss a stale flag (acknowledge staleness without action)."""
    row = fetch_one(
        "SELECT id FROM kg_stale_flags WHERE id = %s",
        (flag_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Stale flag not found")

    execute(
        "UPDATE kg_stale_flags SET status = 'dismissed' WHERE id = %s",
        (flag_id,),
    )
    return {"id": flag_id, "status": "dismissed"}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/curation/stats")
def get_curation_stats(_user: dict = Depends(get_current_user)) -> dict:
    """Return summary counts for the curation dashboard."""
    c_total = fetch_one("SELECT COUNT(*) AS n FROM kg_contradictions")
    c_unresolved = fetch_one(
        "SELECT COUNT(*) AS n FROM kg_contradictions WHERE status = 'needs_review'"
    )
    s_total = fetch_one("SELECT COUNT(*) AS n FROM kg_stale_flags")
    s_active = fetch_one(
        "SELECT COUNT(*) AS n FROM kg_stale_flags WHERE status = 'stale'"
    )

    return {
        "contradictions_total": c_total["n"] if c_total else 0,
        "contradictions_unresolved": c_unresolved["n"] if c_unresolved else 0,
        "stale_total": s_total["n"] if s_total else 0,
        "stale_active": s_active["n"] if s_active else 0,
    }
