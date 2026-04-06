"""Semantic search over ingested LinkedIn profiles via Qdrant."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_api_key
from app.schemas import SearchHit, SearchRequest, SearchResponse

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest, _: str = Depends(require_api_key)):
    from qdrant_client import QdrantClient

    from security import validate_search_query

    query = validate_search_query(req.query)
    if not query:
        raise HTTPException(status_code=400, detail="invalid query")

    try:
        from research_agent import get_embedding
        vector = get_embedding(query)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"embedding failure: {e}") from e

    client = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )
    try:
        hits = client.search(
            collection_name="linkedin_profiles",
            query_vector=vector,
            limit=req.limit,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"qdrant failure: {e}") from e

    out = []
    for h in hits:
        payload = h.payload or {}
        out.append(
            SearchHit(
                id=str(payload.get("apify_id") or h.id),
                first_name=payload.get("first_name"),
                last_name=payload.get("last_name"),
                headline=payload.get("headline"),
                score=float(h.score) if h.score is not None else None,
            )
        )
    return SearchResponse(query=query, hits=out)
