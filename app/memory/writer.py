"""Writer for indexing IS brain research findings into the research_memory Qdrant collection."""

from __future__ import annotations

import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

log = logging.getLogger(__name__)

COLLECTION = "research_memory"
NAMESPACE = uuid.NAMESPACE_URL

_EMBED_WORKERS = 10   # concurrent embedding threads
_UPSERT_BATCH = 50    # max points per Qdrant upsert call


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

    # Build (index, embed_input, payload) tuples up-front so we can embed in parallel.
    items: list[tuple[int, str, dict[str, Any]]] = []
    for i, finding in enumerate(valid):
        title = finding.get("title") or ""
        content = finding.get("content") or ""
        embed_input = (title + "\n" + content)[:2000]  # nomic-embed-text has token limits
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
        items.append((i, embed_input, payload))

    # Embed all texts in parallel — _embed_text is synchronous so use threads.
    vectors: dict[int, list[float]] = {}
    with ThreadPoolExecutor(max_workers=_EMBED_WORKERS) as pool:
        future_to_idx = {
            pool.submit(_embed_text, embed_input): idx
            for idx, embed_input, _ in items
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            vectors[idx] = future.result()

    # Assemble PointStructs in original order.
    points: list[PointStruct] = []
    for i, _embed_input, payload in items:
        point_id = str(uuid.uuid5(NAMESPACE, f"{run_id}:{i}"))
        points.append(PointStruct(id=point_id, vector=vectors[i], payload=payload))

    # Upsert in batches to avoid memory pressure on large finding sets.
    for batch_start in range(0, len(points), _UPSERT_BATCH):
        batch = points[batch_start : batch_start + _UPSERT_BATCH]
        client.upsert(collection_name=COLLECTION, points=batch)

    log.info("Indexed %d findings for run_id=%s", len(points), run_id)
    return len(points)
