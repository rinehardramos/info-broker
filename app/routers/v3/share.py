"""Share-link endpoints for public read-only run views (Story 3.9).

Endpoints
---------
POST /v3/runs/{run_id}/share          — auth required; issues a share token
DELETE /v3/runs/{run_id}/share/{token} — auth required; revokes a token
GET /share/{token}                    — NO auth; returns public-safe run data
"""
from __future__ import annotations

import math
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_one

router = APIRouter(tags=["share"])

_MAX_TTL_DAYS = 30
_DEFAULT_TTL_DAYS = 7


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CreateShareIn(BaseModel):
    ttl_days: int = _DEFAULT_TTL_DAYS


class ShareOut(BaseModel):
    token: str
    share_url: str
    expires_at: str


# ---------------------------------------------------------------------------
# Helper: build share URL from request object (works in dev + prod)
# ---------------------------------------------------------------------------

def _share_url(request: Request, token: str) -> str:
    frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
    if frontend_url:
        return f"{frontend_url}/share/{token}"
    # Derive from the incoming request's base URL (covers all environments)
    base = str(request.base_url).rstrip("/")
    return f"{base}/share/{token}"


# ---------------------------------------------------------------------------
# POST /v3/runs/{run_id}/share
# ---------------------------------------------------------------------------

@router.post("/v3/runs/{run_id}/share", response_model=ShareOut, status_code=201)
def create_share_link(
    run_id: str,
    body: CreateShareIn,
    request: Request,
    user: dict = Depends(get_current_user),
):
    if body.ttl_days < 1 or body.ttl_days > _MAX_TTL_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"ttl_days must be between 1 and {_MAX_TTL_DAYS}",
        )

    # Ownership check
    run = fetch_one(
        "SELECT id, user_id FROM pipeline_runs WHERE id = %s",
        (run_id,),
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if str(run["user_id"]) != str(user["id"]):
        raise HTTPException(status_code=403, detail="Not your run")

    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(days=body.ttl_days)

    execute(
        """INSERT INTO run_share_links (token, run_id, created_by, expires_at)
           VALUES (%s, %s, %s, %s)""",
        (token, run_id, str(user["id"]), expires_at),
    )

    return ShareOut(
        token=token,
        share_url=_share_url(request, token),
        expires_at=expires_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# DELETE /v3/runs/{run_id}/share/{token}
# ---------------------------------------------------------------------------

@router.delete("/v3/runs/{run_id}/share/{token}", status_code=204)
def revoke_share_link(
    run_id: str,
    token: str,
    user: dict = Depends(get_current_user),
):
    link = fetch_one(
        "SELECT token, run_id, created_by FROM run_share_links WHERE token = %s",
        (token,),
    )
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    if str(link["run_id"]) != run_id:
        raise HTTPException(status_code=404, detail="Share link not found")
    if str(link["created_by"]) != str(user["id"]):
        raise HTTPException(status_code=403, detail="Not your share link")

    execute(
        "UPDATE run_share_links SET revoked_at = now() WHERE token = %s AND revoked_at IS NULL",
        (token,),
    )


# ---------------------------------------------------------------------------
# GET /share/{token}  — NO auth dependency (public)
# ---------------------------------------------------------------------------

@router.get("/share/{token}")
def get_shared_run(token: str):
    link = fetch_one(
        """SELECT token, run_id, expires_at, revoked_at, created_at
           FROM run_share_links
           WHERE token = %s""",
        (token,),
    )

    # Unified 404 for invalid / expired / revoked (no info-leak differentiation)
    if not link:
        raise HTTPException(status_code=404, detail="Not found")

    now = datetime.now(timezone.utc)
    expires_at = link["expires_at"]
    if hasattr(expires_at, "tzinfo") and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if link["revoked_at"] is not None or expires_at <= now:
        raise HTTPException(status_code=404, detail="Not found")

    run_id = str(link["run_id"])

    # Pull run row for basic metadata
    run = fetch_one(
        "SELECT id, query, status, started_at, finished_at FROM pipeline_runs WHERE id = %s",
        (run_id,),
    )
    if not run:
        raise HTTPException(status_code=404, detail="Not found")

    # Pull research_trail for ranked_candidates + phases
    trail_row = fetch_one(
        "SELECT trail, findings FROM research_trails WHERE run_id = %s ORDER BY created_at DESC LIMIT 1",
        (run_id,),
    )

    ranked_candidates: list = []
    phases: list = []

    if trail_row:
        import json as _json
        trail_data = trail_row.get("trail") or {}
        if isinstance(trail_data, str):
            trail_data = _json.loads(trail_data)

        raw_candidates = trail_data.get("ranked_candidates", [])
        for c in raw_candidates:
            if isinstance(c, dict):
                ranked_candidates.append({
                    "name": c.get("name", ""),
                    "confidence": c.get("confidence", 0.0),
                    "signal_scores": c.get("signal_scores", {}),
                    "evidence": c.get("evidence", []),
                    "slot_idx": c.get("slot_idx", 0),
                })

        # Build phases list from branches — group by phase_id
        branches = trail_data.get("branches", [])
        phase_map: dict[str, list] = {}
        for b in branches:
            pid = b.get("phase_id", "unknown")
            phase_map.setdefault(pid, []).append({
                "candidate_name": b.get("candidate_name", ""),
                "source_class": b.get("source_class", ""),
                "confidence": b.get("confidence", 0.0),
                "evidence_summary": b.get("evidence_summary", ""),
            })
        for pid, findings in phase_map.items():
            phases.append({"phase_id": pid, "aggregated_findings": findings})

    expires_in_hours = max(0, math.ceil((expires_at - now).total_seconds() / 3600))

    return {
        "run_id": run_id,
        "query": run.get("query", ""),
        "started_at": run["started_at"].isoformat() if run.get("started_at") else None,
        "completed_at": run["finished_at"].isoformat() if run.get("finished_at") else None,
        "status": run.get("status", ""),
        "ranked_candidates": ranked_candidates,
        "phases": phases,
        "shared_at": link["created_at"].isoformat() if link.get("created_at") else None,
        "expires_at": expires_at.isoformat(),
        "expires_in_hours": expires_in_hours,
    }
