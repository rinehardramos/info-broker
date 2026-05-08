"""Knowledge graph REST API endpoints."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_api_key
from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_all, fetch_one

router = APIRouter(prefix="/v3/knowledge", tags=["v3-knowledge"])
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entity types / relationship types
# ---------------------------------------------------------------------------


@router.get("/entity-types")
def list_entity_types(user: dict = Depends(get_current_user)) -> list:
    return fetch_all("SELECT * FROM entity_types ORDER BY name")


@router.get("/relationship-types")
def list_relationship_types(user: dict = Depends(get_current_user)) -> list:
    return fetch_all("SELECT * FROM relationship_types ORDER BY name")


# ---------------------------------------------------------------------------
# Entity search
# ---------------------------------------------------------------------------


@router.get("/entities")
def search_entities(
    q: str = "",
    entity_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(get_current_user),
) -> list:
    # Try Neo4j first
    try:
        from app.knowledge.neo4j_client import Neo4jClient

        client = Neo4jClient()
        try:
            results = client.search_entities(query=q, entity_type=entity_type, limit=limit)
            # Flatten neo4j Node objects to plain dicts
            out = []
            for record in results:
                node = record.get("n")
                if node is not None:
                    out.append(dict(node))
                else:
                    out.append(record)
            return out
        finally:
            client.close()
    except Exception as exc:
        _log.warning("Neo4j search unavailable, falling back to PG: %s", exc)

    # PG fallback
    if q:
        if entity_type:
            rows = fetch_all(
                """
                SELECT entity_ref, entity_type,
                       MAX(value) FILTER (WHERE attribute = 'name') AS name,
                       MAX(confidence) AS confidence,
                       COUNT(*) AS observation_count
                FROM entity_observations
                WHERE entity_type = %s AND value ILIKE %s
                GROUP BY entity_ref, entity_type
                LIMIT %s
                """,
                (entity_type, f"%{q}%", limit),
            )
        else:
            rows = fetch_all(
                """
                SELECT entity_ref, entity_type,
                       MAX(value) FILTER (WHERE attribute = 'name') AS name,
                       MAX(confidence) AS confidence,
                       COUNT(*) AS observation_count
                FROM entity_observations
                WHERE value ILIKE %s
                GROUP BY entity_ref, entity_type
                LIMIT %s
                """,
                (f"%{q}%", limit),
            )
    else:
        if entity_type:
            rows = fetch_all(
                """
                SELECT entity_ref, entity_type,
                       MAX(value) FILTER (WHERE attribute = 'name') AS name,
                       MAX(confidence) AS confidence,
                       COUNT(*) AS observation_count
                FROM entity_observations
                WHERE entity_type = %s
                GROUP BY entity_ref, entity_type
                LIMIT %s
                """,
                (entity_type, limit),
            )
        else:
            rows = fetch_all(
                """
                SELECT entity_ref, entity_type,
                       MAX(value) FILTER (WHERE attribute = 'name') AS name,
                       MAX(confidence) AS confidence,
                       COUNT(*) AS observation_count
                FROM entity_observations
                GROUP BY entity_ref, entity_type
                LIMIT %s
                """,
                (limit,),
            )
    return rows


# ---------------------------------------------------------------------------
# Entity detail
# ---------------------------------------------------------------------------


@router.get("/entities/{ref:path}/observations")
def get_entity_observations(
    ref: str,
    user: dict = Depends(get_current_user),
) -> list:
    return fetch_all(
        """
        SELECT * FROM entity_observations
        WHERE entity_ref = %s
        ORDER BY observed_at DESC
        """,
        (ref,),
    )


@router.get("/entities/{ref:path}/graph")
def get_entity_graph(
    ref: str,
    hops: int = Query(2, ge=1, le=5),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        from app.knowledge.neo4j_client import Neo4jClient

        client = Neo4jClient()
        try:
            subgraph = client.get_subgraph(ref=ref, hops=hops)
            return {"ref": ref, "hops": hops, "subgraph": subgraph}
        finally:
            client.close()
    except Exception as exc:
        _log.warning("Neo4j subgraph unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Graph database unavailable")


@router.get("/entities/{ref:path}")
def get_entity_detail(
    ref: str,
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        from app.knowledge.neo4j_client import Neo4jClient

        client = Neo4jClient()
        try:
            entity = client.get_entity(ref=ref)
            if entity is None:
                raise HTTPException(status_code=404, detail="Entity not found")
            relationships = client.get_entity_relationships(ref=ref)
            return {"entity": entity, "relationships": relationships}
        finally:
            client.close()
    except HTTPException:
        raise
    except Exception as exc:
        _log.warning("Neo4j entity detail unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Graph database unavailable")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/stats")
def get_stats(user: dict = Depends(get_current_user)) -> dict:
    entity_count_row = fetch_one(
        "SELECT COUNT(DISTINCT entity_ref) AS cnt FROM entity_observations"
    )
    rel_count_row = fetch_one("SELECT COUNT(*) AS cnt FROM relationship_observations")
    entities_by_type = fetch_all(
        """
        SELECT entity_type, COUNT(DISTINCT entity_ref) AS cnt
        FROM entity_observations
        GROUP BY entity_type
        ORDER BY cnt DESC
        """
    )
    materializer_state = fetch_one("SELECT * FROM graph_materializer_state WHERE id = 1")

    return {
        "entity_count": entity_count_row["cnt"] if entity_count_row else 0,
        "relationship_count": rel_count_row["cnt"] if rel_count_row else 0,
        "entities_by_type": entities_by_type,
        "materializer_state": materializer_state,
    }


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


@router.get("/timeline")
def get_timeline(
    start: Optional[str] = None,
    end: Optional[str] = None,
    entity_ref: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    user: dict = Depends(get_current_user),
) -> list:
    conditions = []
    params: list = []

    if start:
        conditions.append("observed_at >= %s")
        params.append(start)
    if end:
        conditions.append("observed_at <= %s")
        params.append(end)
    if entity_ref:
        conditions.append("entity_ref = %s")
        params.append(entity_ref)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    return fetch_all(
        f"""
        SELECT * FROM entity_observations
        {where}
        ORDER BY observed_at DESC
        LIMIT %s
        """,
        tuple(params),
    )


# ---------------------------------------------------------------------------
# Memory search
# ---------------------------------------------------------------------------


@router.post("/memory/search")
async def search_memory_endpoint(body: dict, _key: str = Depends(require_api_key)):
    """Multi-signal fused memory search."""
    from app.memory.retriever import fused_retrieve
    query = body.get("query", "")
    limit = body.get("limit", 20)
    results = await fused_retrieve(query, limit=limit)
    return [
        {
            "ref": r.ref, "title": r.title, "content": r.content[:500],
            "source": r.source, "source_tool": r.source_tool, "score": r.score,
            "run_id": r.run_id, "entity_refs": r.entity_refs,
            "observed_at": r.observed_at, "user_score": r.user_score,
            "signals": r.signals,
        }
        for r in results
    ]
