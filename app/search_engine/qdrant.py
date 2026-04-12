from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from llm_providers import embed_text

log = logging.getLogger(__name__)

COLLECTION = "search_results"
VECTOR_DIM = 768


def _client() -> QdrantClient:
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6335")),
    )


def ensure_collection() -> None:
    client = _client()
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        log.info("Created Qdrant collection %r", COLLECTION)


def build_embedding_text(*, title: str, snippet: str, full_text: str | None) -> str:
    parts = [title, snippet]
    if full_text:
        parts.append(full_text[:4000])
    return "\n".join(parts)


def upsert_result(
    *,
    result_id: uuid.UUID,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    plugin: str,
    title: str,
    url: str | None,
    snippet: str,
    full_text: str | None,
) -> None:
    text = build_embedding_text(title=title, snippet=snippet, full_text=full_text)
    vector = embed_text(text)
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(result_id)))
    client = _client()
    client.upsert(
        collection_name=COLLECTION,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "result_id": str(result_id),
                    "job_id": str(job_id),
                    "user_id": str(user_id),
                    "plugin": plugin,
                    "title": title,
                    "url": url,
                    "snippet": snippet[:500] if snippet else "",
                    "full_text": full_text,
                },
            )
        ],
    )


def get_result_payload(result_id: uuid.UUID) -> dict[str, Any] | None:
    client = _client()
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(result_id)))
    try:
        points = client.retrieve(
            collection_name=COLLECTION, ids=[point_id], with_payload=True
        )
        if points:
            return points[0].payload
    except Exception as exc:
        log.warning("Qdrant retrieve failed for %s: %s", result_id, exc)
    return None


def get_results_payloads(result_ids: list[uuid.UUID]) -> dict[str, dict]:
    if not result_ids:
        return {}
    client = _client()
    point_ids = [
        str(uuid.uuid5(uuid.NAMESPACE_DNS, str(rid))) for rid in result_ids
    ]
    try:
        points = client.retrieve(
            collection_name=COLLECTION, ids=point_ids, with_payload=True
        )
        return {p.payload["result_id"]: p.payload for p in points if p.payload}
    except Exception as exc:
        log.warning("Qdrant batch retrieve failed: %s", exc)
        return {}
