"""Multi-signal retrieval functions for the memory subsystem.

Each signal is async, wraps all exceptions with try/except (logs warning,
returns []), and produces list[MemoryResult] with a distinct source label.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level helpers — defined at module scope so tests can patch them
# ---------------------------------------------------------------------------

def _get_qdrant_client():
    from qdrant_client import QdrantClient
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6335")),
    )


def _embed_text(text: str) -> list[float]:
    if not os.getenv("GEMINI_API_KEY"):
        try:
            from app.routers.v3.db import fetch_one
            row = fetch_one("SELECT value FROM core_settings WHERE key = 'gemini_api_key'", ())
            if row and row["value"]:
                os.environ["GEMINI_API_KEY"] = row["value"]
        except Exception:
            pass
    from llm_providers import embed_text
    return embed_text(text)


# ---------------------------------------------------------------------------
# Import helpers for DB and knowledge graph (importable at module level so
# tests can patch app.memory.signals.fetch_all / Neo4jClient)
# ---------------------------------------------------------------------------

from app.routers.v3.db import fetch_all  # noqa: E402
from app.knowledge.neo4j_client import Neo4jClient  # noqa: E402
from app.memory.models import MemoryResult  # noqa: E402

_RESEARCH_MEMORY_COLLECTION = "research_memory"


# ---------------------------------------------------------------------------
# 1. Semantic search — Qdrant dense vector
# ---------------------------------------------------------------------------

async def semantic_search(query: str, limit: int = 50) -> list[MemoryResult]:
    """Dense vector search against the 'research_memory' Qdrant collection."""
    try:
        vector = _embed_text(query)
        client = _get_qdrant_client()
        hits = client.search(
            collection_name=_RESEARCH_MEMORY_COLLECTION,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )
        results: list[MemoryResult] = []
        for hit in hits:
            payload: dict[str, Any] = hit.payload or {}
            results.append(
                MemoryResult(
                    ref=payload.get("ref", ""),
                    title=payload.get("title", ""),
                    content=payload.get("content", ""),
                    source="semantic",
                    score=hit.score,
                    run_id=payload.get("run_id"),
                    entity_refs=payload.get("entity_refs") or [],
                )
            )
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("semantic_search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# 2. BM25 search — PG ILIKE on research_trails
# ---------------------------------------------------------------------------

async def bm25_search(query: str, limit: int = 50) -> list[MemoryResult]:
    """Full-text ILIKE search on research_trails (query + findings text).

    Extracts up to 5 findings per trail row.
    """
    try:
        sql = """
            SELECT id, query, run_id, findings
            FROM research_trails
            WHERE query ILIKE %(pattern)s
               OR findings::text ILIKE %(pattern)s
            LIMIT %(limit)s
        """
        rows = fetch_all(sql, {"pattern": f"%{query}%", "limit": limit})
        results: list[MemoryResult] = []
        for row in rows:
            run_id = str(row.get("run_id")) if row.get("run_id") else None
            raw_findings = row.get("findings")
            if isinstance(raw_findings, str):
                try:
                    findings = json.loads(raw_findings)
                except json.JSONDecodeError:
                    findings = []
            elif isinstance(raw_findings, list):
                findings = raw_findings
            else:
                findings = []

            for finding in findings[:5]:
                title = finding.get("title", "")
                content = finding.get("content", "")
                ref = f"trail:{row['id']}:{title[:32]}"
                results.append(
                    MemoryResult(
                        ref=ref,
                        title=title,
                        content=content,
                        source="bm25",
                        score=1.0,
                        run_id=run_id,
                    )
                )
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("bm25_search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# 3. Entity search — Neo4j
# ---------------------------------------------------------------------------

async def entity_search(query: str, limit: int = 30) -> list[MemoryResult]:
    """Search Neo4j for entities matching the query string."""
    client = None
    try:
        client = Neo4jClient()
        rows = client.search_entities(query, limit=limit)
        results: list[MemoryResult] = []
        for row in rows:
            # search_entities returns records; handle both raw dicts and Neo4j record dicts
            node = row.get("n", row)
            if hasattr(node, "__getitem__"):
                ref = node.get("ref", "")
                name = node.get("name", "")
                entity_type = node.get("entity_type", "")
                confidence = node.get("confidence", 50)
                observation_count = node.get("observation_count", 0)
            else:
                ref = row.get("ref", "")
                name = row.get("name", "")
                entity_type = row.get("entity_type", "")
                confidence = row.get("confidence", 50)
                observation_count = row.get("observation_count", 0)

            results.append(
                MemoryResult(
                    ref=ref,
                    title=name,
                    content=f"{entity_type} | observations: {observation_count}",
                    source="entity",
                    score=confidence / 100.0,
                )
            )
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("entity_search failed: %s", exc)
        return []
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# 4. Temporal search — PG entity_observations
# ---------------------------------------------------------------------------

async def temporal_search(
    query: str,
    limit: int = 30,
    time_filter: tuple[str, str] | None = None,
) -> list[MemoryResult]:
    """Search entity_observations WHERE value ILIKE query, optionally filtered by observed_at range."""
    try:
        if time_filter:
            sql = """
                SELECT entity_ref, entity_type, attribute, value,
                       confidence, observed_at, source_run_id
                FROM entity_observations
                WHERE value ILIKE %(pattern)s
                  AND observed_at BETWEEN %(from_dt)s AND %(to_dt)s
                ORDER BY observed_at DESC
                LIMIT %(limit)s
            """
            params: dict[str, Any] = {
                "pattern": f"%{query}%",
                "from_dt": time_filter[0],
                "to_dt": time_filter[1],
                "limit": limit,
            }
        else:
            sql = """
                SELECT entity_ref, entity_type, attribute, value,
                       confidence, observed_at, source_run_id
                FROM entity_observations
                WHERE value ILIKE %(pattern)s
                ORDER BY observed_at DESC
                LIMIT %(limit)s
            """
            params = {"pattern": f"%{query}%", "limit": limit}

        rows = fetch_all(sql, params)
        results: list[MemoryResult] = []
        for row in rows:
            entity_ref = row.get("entity_ref", "")
            attribute = row.get("attribute", "")
            value = row.get("value", "")
            observed_at = row.get("observed_at")
            run_id = str(row.get("source_run_id")) if row.get("source_run_id") else None
            confidence = row.get("confidence", 50)

            results.append(
                MemoryResult(
                    ref=entity_ref,
                    title=f"{entity_ref} — {attribute}",
                    content=value,
                    source="temporal",
                    score=confidence / 100.0,
                    run_id=run_id,
                    observed_at=str(observed_at) if observed_at else None,
                )
            )
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("temporal_search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# 5. Feedback search — PG finding_feedback
# ---------------------------------------------------------------------------

async def feedback_search(query: str, limit: int = 50) -> list[MemoryResult]:
    """Search finding_feedback WHERE finding_title or reason ILIKE query, ORDER BY user_score DESC."""
    try:
        sql = """
            SELECT run_id, finding_index, finding_title, user_score, reason
            FROM finding_feedback
            WHERE finding_title ILIKE %(pattern)s
               OR reason ILIKE %(pattern)s
            ORDER BY user_score DESC
            LIMIT %(limit)s
        """
        rows = fetch_all(sql, {"pattern": f"%{query}%", "limit": limit})
        results: list[MemoryResult] = []
        for row in rows:
            run_id = str(row.get("run_id")) if row.get("run_id") else None
            finding_index = row.get("finding_index", 0)
            title = row.get("finding_title") or ""
            user_score = row.get("user_score") or 0
            reason = row.get("reason") or ""
            ref = f"feedback:{run_id}:{finding_index}"

            results.append(
                MemoryResult(
                    ref=ref,
                    title=title,
                    content=reason,
                    source="feedback",
                    score=float(user_score),
                    run_id=run_id,
                    user_score=user_score,
                )
            )
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("feedback_search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# 6. Skill search — Qdrant research_memory filtered by type="skill"
# ---------------------------------------------------------------------------

async def skill_search(query: str, limit: int = 5) -> list[MemoryResult]:
    """Search Qdrant for skills matching the query by embedding similarity."""
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = _get_qdrant_client()
        vector = _embed_text(query)
        hits = client.search(
            collection_name="research_memory",
            query_vector=vector,
            query_filter=Filter(must=[
                FieldCondition(key="type", match=MatchValue(value="skill")),
            ]),
            limit=limit,
            with_payload=True,
        )
        return [
            MemoryResult(
                ref=str(h.id),
                title=f"Skill: {h.payload.get('query', '')[:50]}",
                content=f"Tools: {' -> '.join(h.payload.get('tool_sequence', [])[:6])}",
                source="skill",
                score=h.score,
                run_id=h.payload.get("skill_id"),
                user_score=0,
            )
            for h in hits if h.payload
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("Skill signal failed: %s", exc)
        return []
