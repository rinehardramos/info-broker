"""Writer for indexing IS brain research findings into the research_memory Qdrant collection."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

log = logging.getLogger(__name__)

COLLECTION = "research_memory"
NAMESPACE = uuid.NAMESPACE_URL


def _get_qdrant_client() -> QdrantClient:
    """Return a QdrantClient configured from environment variables."""
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )


def _embed_text(text: str) -> list[float]:
    """Embed text using the shared llm_providers embedding function.

    Loads GEMINI_API_KEY from core_settings if not in env.
    """
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


async def index_research_findings(
    run_id: str,
    query: str,
    findings: list[dict[str, Any]],
) -> int:
    """Index valid research findings into the research_memory Qdrant collection.

    Skips any finding with error_flagged=True.
    Returns the count of findings successfully indexed.
    """
    valid = [f for f in findings if not f.get("error_flagged", False)]
    if not valid:
        return 0

    client = _get_qdrant_client()

    points: list[PointStruct] = []
    for i, finding in enumerate(valid):
        title = finding.get("title") or ""
        content = finding.get("content") or ""
        newline = "\n"
        embed_input = title + newline + content
        vector = _embed_text(embed_input)

        point_id = str(uuid.uuid5(NAMESPACE, f"{run_id}:{i}"))

        payload: dict[str, Any] = {
            "run_id": run_id,
            "query": query,
            "finding_index": i,
            "title": title,
            "content": content[:2000],
            "source_tool": finding.get("source") or finding.get("source_tool") or "",
            "confidence": finding.get("confidence", 0),
            "user_score": 0,
            "entity_refs": [],
            "observed_at": finding.get("observed_at"),
        }

        points.append(PointStruct(id=point_id, vector=vector, payload=payload))

    client.upsert(collection_name=COLLECTION, points=points)
    log.info("Indexed %d findings for run_id=%s", len(points), run_id)
    return len(points)
