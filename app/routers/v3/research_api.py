"""Research trails and plugin-request endpoints for the MCP server."""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends

from app.deps import require_api_key
from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one

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
# Finding feedback
# ---------------------------------------------------------------------------


@router.post("/research-trails/{run_id}/findings/{index}/feedback")
def submit_finding_feedback(
    run_id: str,
    index: int,
    body: dict,
    user: dict = Depends(get_current_user),
):
    """Submit thumbs up/down feedback for a specific finding."""
    uid = str(user["id"])
    execute(
        """INSERT INTO finding_feedback (id, user_id, run_id, finding_index, finding_title, user_score, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, run_id, finding_index)
        DO UPDATE SET user_score = EXCLUDED.user_score, reason = EXCLUDED.reason, created_at = now()""",
        (str(uuid.uuid4()), uid, run_id, index, body.get("title", ""), body.get("score", 0), body.get("reason", "")),
    )
    # If thumbs down, learn the error pattern
    if body.get("score") == -1:
        _learn_error_pattern(body.get("title", ""), body.get("reason", ""))
    return {"status": "ok"}


@router.get("/research-trails/{run_id}/feedback")
def get_run_feedback(run_id: str, user: dict = Depends(get_current_user)):
    """Get all feedback for a specific research run."""
    uid = str(user["id"])
    rows = fetch_all(
        "SELECT finding_index, user_score, reason FROM finding_feedback WHERE user_id = %s AND run_id = %s",
        (uid, run_id),
    )
    return {str(r["finding_index"]): {"score": r["user_score"], "reason": r["reason"]} for r in rows}


def _learn_error_pattern(title: str, reason: str):
    """Extract error keywords from user feedback and store for future auto-detection."""
    # Load existing patterns
    row = fetch_one("SELECT value FROM core_settings WHERE key = 'scoring.error_patterns'", ())
    patterns = json.loads(row["value"]) if row else []

    # Extract meaningful keywords from the title (skip common words)
    stop_words = {"the", "and", "for", "from", "with", "that", "this", "not", "was", "are", "but"}
    keywords = [w.lower() for w in (title or "").split() if len(w) > 3 and w.isalpha() and w.lower() not in stop_words]

    added = False
    for kw in keywords[:3]:
        if kw not in patterns:
            patterns.append(kw)
            added = True

    if added:
        execute(
            "INSERT INTO core_settings (key, value, is_secret) VALUES (%s, %s, false) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            ("scoring.error_patterns", json.dumps(patterns)),
        )


# ---------------------------------------------------------------------------
# Analyze findings (JWT-authenticated, called from frontend)
# ---------------------------------------------------------------------------


@router.post("/research-trails/analyze")
async def analyze_findings(body: dict, user: dict = Depends(get_current_user)):
    """Run the Intelligence Analyzer on a set of findings. JWT-authenticated."""
    from app.pipeline.nodes import NodeRegistry
    from app.pipeline.nodes.base import RunContext

    NodeRegistry.auto_discover()
    node = NodeRegistry.get("analyzer")

    items = body.get("items") or body.get("inputs") or body.get("findings") or []
    config = {
        "analysis_type": body.get("analysis_type", "comprehensive"),
        "min_confidence": body.get("min_confidence", 50),
        "context_prompt": body.get("context_prompt", ""),
        "query": body.get("query", ""),
        "model": body.get("model", ""),  # empty = use reasoning_model() from settings
    }
    ctx = RunContext(
        user_id=str(user["id"]),
        run_id="analyze-adhoc",
        node_id="analyzer",
    )
    result = await node.execute(config, items, ctx)
    # Write analysis results to knowledge graph
    if result:
        try:
            from app.knowledge.writer import kg_writer
            analysis = result[0] if isinstance(result, list) else result
            kg_result = await kg_writer.write_from_analyzer(
                analysis, source_run_id=None,
            )
            log.info("KG Writer: %s", kg_result)
        except Exception as exc:
            log.warning("KG write failed (non-fatal): %s", exc)
    return {"status": "success", "items": result, "count": len(result)}


# ---------------------------------------------------------------------------
# Plugin requests (POST — the GET/PUT are in pipelines.py)
# ---------------------------------------------------------------------------


@router.post("/plugin-requests")
def create_plugin_request(body: dict, _key: str = Depends(require_api_key)) -> dict:
    """Submit a request for a new plugin/tool to be built into info-broker.

    Deduplication: if the suggested name matches an existing node type,
    mark it as an enhancement request instead of a new plugin.
    """
    name = body.get("name", "")
    reason = body.get("reason", "")
    description = body.get("description", "")

    # Check if this duplicates an existing node
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()
    existing_types = {n.node_type for n in NodeRegistry.all()}

    # Normalize name for matching (strip hyphens, underscores)
    normalized = name.lower().replace("-", "_").replace(" ", "_")
    is_enhancement = reason.startswith("ENHANCE:") or normalized in existing_types

    # Also check for partial matches (e.g., "linkedin-search" vs "linkedin_profile")
    if not is_enhancement:
        for et in existing_types:
            if normalized in et or et in normalized:
                is_enhancement = True
                reason = f"ENHANCE ({et}): {reason}"
                break

    spec = {
        "name": name,
        "description": description,
        "reason": reason,
        "is_enhancement": is_enhancement,
    }
    status = "enhancement" if is_enhancement else "pending"

    user_id = body.get("user_id")
    execute(
        """
        INSERT INTO plugin_requests (id, user_id, spec, status)
        VALUES (%s, %s, %s, %s)
        """,
        (str(uuid.uuid4()), user_id, json.dumps(spec), status),
    )
    return {"status": "ok", "is_enhancement": is_enhancement}
