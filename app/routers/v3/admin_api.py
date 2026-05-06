"""Admin API — MCP observability endpoints (sessions, dashboard, tool stats)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_all, fetch_one

router = APIRouter(prefix="/v3/admin", tags=["v3-admin"])
log = logging.getLogger(__name__)


@router.get("/sessions")
def list_sessions(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    if status:
        rows = fetch_all(
            """SELECT id, caller_identity, session_type, status, tool_call_count,
                  context, started_at, finished_at
            FROM mcp_sessions WHERE status = %s
            ORDER BY started_at DESC LIMIT %s""",
            (status, limit),
        )
    else:
        rows = fetch_all(
            """SELECT id, caller_identity, session_type, status, tool_call_count,
                  context, started_at, finished_at
            FROM mcp_sessions
            ORDER BY started_at DESC LIMIT %s""",
            (limit,),
        )
    return [dict(r) for r in rows]


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: dict = Depends(get_current_user)):
    session = fetch_one(
        """SELECT id, caller_identity, session_type, status, tool_call_count,
              context, started_at, finished_at
        FROM mcp_sessions WHERE id = %s""",
        (session_id,),
    )
    if not session:
        return {"error": "Session not found"}
    calls = fetch_all(
        """SELECT id, tool_name, node_type, call_id, parent_call_id, status,
              input_params, result_preview, result_count, error_message,
              duration_ms, created_at
        FROM mcp_tool_calls WHERE session_id = %s
        ORDER BY created_at""",
        (session_id,),
    )
    return {"session": dict(session), "calls": [dict(c) for c in calls]}


@router.get("/dashboard")
def get_dashboard(user: dict = Depends(get_current_user)):
    active = fetch_one("SELECT COUNT(*) AS cnt FROM mcp_sessions WHERE status = 'active'")
    total_calls = fetch_one("SELECT COUNT(*) AS cnt FROM mcp_tool_calls")
    error_rate = fetch_one(
        """SELECT
            COUNT(*) FILTER (WHERE status = 'failed') AS errors,
            COUNT(*) AS total
        FROM mcp_tool_calls
        WHERE created_at > now() - interval '1 hour'"""
    )
    avg_duration = fetch_one(
        """SELECT AVG(duration_ms) AS avg_ms
        FROM mcp_tool_calls
        WHERE status = 'succeeded' AND created_at > now() - interval '1 hour'"""
    )
    top_tools = fetch_all(
        """SELECT tool_name, COUNT(*) AS call_count, AVG(duration_ms) AS avg_ms
        FROM mcp_tool_calls
        WHERE created_at > now() - interval '24 hours'
        GROUP BY tool_name ORDER BY call_count DESC LIMIT 10"""
    )
    return {
        "active_sessions": active["cnt"] if active else 0,
        "total_tool_calls": total_calls["cnt"] if total_calls else 0,
        "error_rate_last_hour": {
            "errors": error_rate["errors"] if error_rate else 0,
            "total": error_rate["total"] if error_rate else 0,
        },
        "avg_duration_ms": round(avg_duration["avg_ms"] or 0, 1) if avg_duration else 0,
        "top_tools_24h": [dict(r) for r in top_tools],
    }


@router.get("/tools/stats")
def get_tool_stats(user: dict = Depends(get_current_user)):
    rows = fetch_all(
        """SELECT tool_name,
            COUNT(*) AS total_calls,
            COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed,
            AVG(duration_ms) FILTER (WHERE status = 'succeeded') AS avg_duration_ms,
            MAX(created_at) AS last_used
        FROM mcp_tool_calls
        GROUP BY tool_name ORDER BY total_calls DESC"""
    )
    return [dict(r) for r in rows]
