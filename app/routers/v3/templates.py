"""Saved query templates router — Enhancement 3.2.

Endpoints:
  GET  /v3/templates                — list current user's templates
  POST /v3/templates                — create or upsert template (by name)
  DELETE /v3/templates/{id}         — delete template (owner only)
  POST /v3/templates/{id}/use       — bump last_used + use_count
  GET  /v3/user/defaults            — get per-user default envelope
  PUT  /v3/user/defaults            — set per-user default envelope
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_all, fetch_one, execute

log = logging.getLogger(__name__)

router = APIRouter(tags=["v3-templates"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class EnvelopeIn(BaseModel):
    speed: Optional[str] = "normal"
    capability: Optional[str] = "general"
    resource: Optional[str] = "medium"
    depth: Optional[str] = "search"
    hypothesis_count: Optional[str] = "competing"
    mode: Optional[str] = None


class TemplateIn(BaseModel):
    name: str
    query: str
    envelope: EnvelopeIn
    strategy_id: str


class TemplateOut(BaseModel):
    id: str
    user_id: str
    name: str
    query: str
    envelope: dict
    strategy_id: str
    last_used: Optional[str]
    use_count: int
    created_at: str


class UserDefaultsIn(BaseModel):
    envelope: EnvelopeIn


class UserDefaultsOut(BaseModel):
    envelope: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_template(row: dict) -> TemplateOut:
    envelope = row["envelope"]
    if isinstance(envelope, str):
        envelope = json.loads(envelope)
    return TemplateOut(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        name=row["name"],
        query=row["query"],
        envelope=envelope,
        strategy_id=row["strategy_id"],
        last_used=row["last_used"].isoformat() if row.get("last_used") else None,
        use_count=row["use_count"],
        created_at=row["created_at"].isoformat(),
    )


# ---------------------------------------------------------------------------
# Templates endpoints
# ---------------------------------------------------------------------------


@router.get("/v3/templates", response_model=list[TemplateOut])
def list_templates(user: dict = Depends(get_current_user)):
    """List the current user's templates ordered by last_used DESC NULLS LAST, created_at DESC."""
    uid = str(user["id"])
    rows = fetch_all(
        """SELECT id, user_id, name, query, envelope, strategy_id,
                  last_used, use_count, created_at
             FROM saved_templates
            WHERE user_id = %s
            ORDER BY last_used DESC NULLS LAST, created_at DESC""",
        (uid,),
    )
    return [_row_to_template(r) for r in rows]


@router.post("/v3/templates", response_model=TemplateOut, status_code=201)
def create_template(body: TemplateIn, user: dict = Depends(get_current_user)):
    """Create or UPSERT a saved template (unique per user_id + name)."""
    uid = str(user["id"])
    envelope_json = json.dumps(body.envelope.model_dump())
    row = fetch_one(
        """INSERT INTO saved_templates (user_id, name, query, envelope, strategy_id)
           VALUES (%s, %s, %s, %s::jsonb, %s)
           ON CONFLICT (user_id, name)
           DO UPDATE SET
               query       = EXCLUDED.query,
               envelope    = EXCLUDED.envelope,
               strategy_id = EXCLUDED.strategy_id
           RETURNING id, user_id, name, query, envelope, strategy_id,
                     last_used, use_count, created_at""",
        (uid, body.name, body.query, envelope_json, body.strategy_id),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create template")
    return _row_to_template(row)


@router.delete("/v3/templates/{template_id}", status_code=204)
def delete_template(template_id: str, user: dict = Depends(get_current_user)):
    """Hard-delete a template. Owner check enforced."""
    uid = str(user["id"])
    existing = fetch_one(
        "SELECT id, user_id FROM saved_templates WHERE id = %s",
        (template_id,),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")
    if str(existing["user_id"]) != uid:
        raise HTTPException(status_code=403, detail="Not your template")
    execute("DELETE FROM saved_templates WHERE id = %s", (template_id,))


@router.post("/v3/templates/{template_id}/use", response_model=TemplateOut)
def use_template(template_id: str, user: dict = Depends(get_current_user)):
    """Bump last_used to now() and increment use_count. Returns updated template."""
    uid = str(user["id"])
    row = fetch_one(
        """UPDATE saved_templates
              SET last_used = now(),
                  use_count = use_count + 1
            WHERE id = %s AND user_id = %s
        RETURNING id, user_id, name, query, envelope, strategy_id,
                  last_used, use_count, created_at""",
        (template_id, uid),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Template not found or not yours")
    return _row_to_template(row)


# ---------------------------------------------------------------------------
# Per-user default envelope endpoints
# ---------------------------------------------------------------------------


@router.get("/v3/user/defaults", response_model=UserDefaultsOut)
def get_user_defaults(user: dict = Depends(get_current_user)):
    """Return the current user's default envelope. Returns empty envelope if not set."""
    uid = str(user["id"])
    row = fetch_one(
        "SELECT envelope FROM user_defaults WHERE user_id = %s",
        (uid,),
    )
    if not row:
        return UserDefaultsOut(envelope={})
    envelope = row["envelope"]
    if isinstance(envelope, str):
        envelope = json.loads(envelope)
    return UserDefaultsOut(envelope=envelope)


@router.put("/v3/user/defaults", response_model=UserDefaultsOut)
def put_user_defaults(body: UserDefaultsIn, user: dict = Depends(get_current_user)):
    """Upsert the current user's default envelope."""
    uid = str(user["id"])
    envelope_json = json.dumps(body.envelope.model_dump())
    row = fetch_one(
        """INSERT INTO user_defaults (user_id, envelope)
           VALUES (%s, %s::jsonb)
           ON CONFLICT (user_id)
           DO UPDATE SET envelope = EXCLUDED.envelope, updated_at = now()
           RETURNING envelope""",
        (uid, envelope_json),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to save defaults")
    envelope = row["envelope"]
    if isinstance(envelope, str):
        envelope = json.loads(envelope)
    return UserDefaultsOut(envelope=envelope)
