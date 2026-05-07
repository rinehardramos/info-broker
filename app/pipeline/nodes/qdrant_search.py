from __future__ import annotations

import asyncio

from app.pipeline.nodes.base import RunContext

_VALID_COLLECTIONS = ("search_results", "linkedin_profiles")


class QdrantSearchNode:
    node_type = "qdrant_search"
    display_name = "Qdrant Search"
    category = "enrich"
    config_schema = {
        "type": "object",
        "properties": {
            "collection": {
                "type": "string",
                "title": "Collection",
                "enum": list(_VALID_COLLECTIONS),
                "default": "search_results",
            },
            "limit": {"type": "integer", "title": "Top-K Results", "default": 20, "minimum": 1, "maximum": 100},
        },
        "required": [],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        from llm_providers import embed_text
        import os

        collection = config.get("collection", "search_results")
        if collection not in _VALID_COLLECTIONS:
            collection = "search_results"
        limit = int(config.get("limit", 20))

        loop = asyncio.get_running_loop()

        def _search(text: str) -> list[dict]:
            try:
                vector = embed_text(text)
                client = QdrantClient(
                    host=os.getenv("QDRANT_HOST", "localhost"),
                    port=int(os.getenv("QDRANT_PORT", "6335")),
                )
                hits = client.query_points(
                    collection_name=collection,
                    query=vector,
                    limit=limit,
                    with_payload=True,
                ).points
                return [h.payload for h in hits if h.payload]
            except Exception:
                return []

        output = []
        for item in inputs:
            query_text = " ".join(filter(None, [
                item.get("title", ""),
                item.get("snippet", ""),
                item.get("headline", ""),
            ]))
            if not query_text.strip():
                output.append(item)
                continue
            matches = await loop.run_in_executor(None, _search, query_text)
            output.append({**item, "qdrant_matches": matches})

        # If no inputs, return empty — qdrant_search is an enrich node
        return output
