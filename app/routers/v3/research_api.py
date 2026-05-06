"""Research trails and plugin-request endpoints for the MCP server."""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends

from app.deps import require_api_key
from app.routers.v3.db import execute, fetch_all

router = APIRouter(prefix="/v3", tags=["v3-research"])
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Research trails
# ---------------------------------------------------------------------------


@router.post("/research-trails")
def create_research_trail(body: dict, _key: str = Depends(require_api_key)) -> dict:
    """Persist a research trail produced by the IS brain."""
    user_id = body.get("user_id", "mcp-system")
    execute(
        """
        INSERT INTO research_trails
            (id, user_id, query, entity_type, findings, trail, tool_calls)
        VALUES (%s, %s, %s, %s, %s, %s, 0)
        """,
        (
            str(uuid.uuid4()),
            user_id,
            body.get("query", ""),
            body.get("entity_type", "unknown"),
            json.dumps(body.get("findings", [])),
            json.dumps(body.get("trail", {})),
        ),
    )
    return {"status": "ok"}


@router.get("/research-trails/{run_id}")
def get_research_trail_by_run(run_id: str, _key: str = Depends(require_api_key)) -> dict | None:
    """Get a research trail by its pipeline run ID."""
    from app.routers.v3.db import fetch_one
    row = fetch_one(
        "SELECT id, query, entity_type, findings, trail, tool_calls, created_at FROM research_trails WHERE run_id = %s",
        (run_id,),
    )
    return dict(row) if row else None


@router.get("/research-trails")
def list_research_trails(
    query: str = "",
    limit: int = 5,
    _key: str = Depends(require_api_key),
) -> list[dict]:
    """Return the most recent research trails for the authenticated user.

    When ``query`` is provided the results are filtered by a simple text match
    on the stored query field. Full semantic search requires Qdrant integration
    which can be added later.
    """
    if query:
        rows = fetch_all(
            """
            SELECT id, query, entity_type, findings, trail, tool_calls, created_at
            FROM research_trails
            WHERE query ILIKE %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (f"%{query}%", limit),
        )
    else:
        rows = fetch_all(
            """
            SELECT id, query, entity_type, findings, trail, tool_calls, created_at
            FROM research_trails
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Plugin requests (POST — the GET/PUT are in pipelines.py)
# ---------------------------------------------------------------------------


@router.post("/plugin-requests")
def create_plugin_request(body: dict, _key: str = Depends(require_api_key)) -> dict:
    """Submit a request for a new plugin/tool to be built into info-broker."""
    spec = {
        "name": body.get("name", ""),
        "description": body.get("description", ""),
        "reason": body.get("reason", ""),
    }
    # user_id is optional — MCP calls don't have a user context
    user_id = body.get("user_id")
    execute(
        """
        INSERT INTO plugin_requests (id, user_id, spec, status)
        VALUES (%s, %s, %s, 'pending')
        """,
        (str(uuid.uuid4()), user_id, json.dumps(spec)),
    )
    return {"status": "ok"}
