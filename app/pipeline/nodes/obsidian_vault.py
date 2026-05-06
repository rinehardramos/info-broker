"""Obsidian Vault datastore node — semantic search over an Obsidian vault via Qdrant."""

from __future__ import annotations

import asyncio
import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)


class ObsidianVaultNode:
    node_type = "obsidian_vault"
    display_name = "Obsidian Vault"
    category = "datastore"
    config_schema = {
        "type": "object",
        "properties": {
            "collection": {
                "type": "string",
                "title": "Qdrant Collection",
                "default": "obsidian_vault",
                "description": "Name of the Qdrant collection storing vault embeddings",
            },
            "top_k": {
                "type": "integer",
                "title": "Top-K Results",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": [],
    }

    # -- PipelineNode interface (datastore nodes are never scheduled) ----------

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        return []

    # -- ToolCallable interface ------------------------------------------------

    def tool_schema(self) -> dict:
        return {
            "name": "search_obsidian",
            "description": (
                "Semantic search over an Obsidian vault. Returns note chunks "
                "ranked by relevance to the query."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant notes",
                    },
                },
                "required": ["query"],
            },
        }

    async def tool_invoke(
        self, params: dict, context: RunContext
    ) -> list[dict]:
        query = params.get("query", "")
        if not query:
            return []

        # Read config from _tool_node_config injected at resolve time
        config = getattr(self, "_active_config", {})
        collection = config.get("collection", "obsidian_vault")
        top_k = int(config.get("top_k", 10))

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, _qdrant_search, query, collection, top_k
        )
        return results


def _qdrant_search(query: str, collection: str, top_k: int) -> list[dict]:
    """Synchronous Qdrant semantic search against a named collection."""
    try:
        import os
        from qdrant_client import QdrantClient
        from llm_providers import embed_text

        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6335"))
        client = QdrantClient(host=host, port=port)

        vector = embed_text(query)
        hits = client.search(
            collection_name=collection,
            query_vector=vector,
            limit=top_k,
        )
        return [
            {
                "title": h.payload.get("title", h.payload.get("vault_path", "")),
                "content": h.payload.get("text", h.payload.get("content", "")),
                "score": round(h.score, 4),
                "source": "obsidian_vault",
                "metadata": {k: v for k, v in h.payload.items() if k not in ("text", "content")},
            }
            for h in hits
        ]
    except Exception as exc:
        log.warning("obsidian_vault search failed: %s", exc)
        return [{"error": str(exc), "source": "obsidian_vault"}]
