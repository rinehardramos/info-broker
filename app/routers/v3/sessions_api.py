"""Agent session CRUD endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import AgentSessionOut

router = APIRouter(prefix="/v3/agent/sessions", tags=["v3-sessions"])


@router.post("", response_model=AgentSessionOut, status_code=201)
def create_session(body: dict, user: dict = Depends(get_current_user)):
    """Create a new investigation session."""
    genesis_query = (body.get("genesis_query") or "").strip()
    if not genesis_query:
        raise HTTPException(status_code=422, detail="genesis_query required")
    session_id = str(uuid.uuid4())
    uid = str(user["id"])
    row = fetch_one(
        """INSERT INTO agent_sessions (id, user_id, genesis_query)
           VALUES (%s, %s, %s) RETURNING *""",
        (session_id, uid, genesis_query),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return _row_to_out(row)


@router.get("", response_model=list[AgentSessionOut])
def list_sessions(user: dict = Depends(get_current_user)):
    """List all sessions for the current user, newest first."""
    uid = str(user["id"])
    rows = fetch_all(
        "SELECT * FROM agent_sessions WHERE user_id = %s ORDER BY created_at DESC LIMIT 50",
        (uid,),
    )
    return [_row_to_out(r) for r in rows]


@router.get("/{session_id}", response_model=AgentSessionOut)
def get_session(session_id: str, user: dict = Depends(get_current_user)):
    """Get a single session with full conversation thread."""
    uid = str(user["id"])
    row = fetch_one(
        "SELECT * FROM agent_sessions WHERE id = %s AND user_id = %s",
        (session_id, uid),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return _row_to_out(row)


@router.post("/{session_id}/archive")
def archive_session(session_id: str, user: dict = Depends(get_current_user)):
    """Archive a session (triggered by chat clear)."""
    uid = str(user["id"])
    row = fetch_one(
        "SELECT id FROM agent_sessions WHERE id = %s AND user_id = %s",
        (session_id, uid),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    execute(
        "UPDATE agent_sessions SET status = 'archived', archived_at = now() WHERE id = %s",
        (session_id,),
    )
    return {"status": "archived", "session_id": session_id}


def _row_to_out(row: dict) -> AgentSessionOut:
    return AgentSessionOut(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        genesis_query=row["genesis_query"],
        status=row["status"],
        created_at=row["created_at"],
        archived_at=row.get("archived_at"),
        run_count=row.get("run_count", 0),
        turn_count=row.get("turn_count", 0),
        accumulated_summary=row.get("accumulated_summary") or "",
        conversation_thread=row.get("conversation_thread") or [],
        key_findings=row.get("key_findings") or [],
        entity_type=row.get("entity_type") or "unknown",
    )
