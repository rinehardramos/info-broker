"""Exa neural/semantic web search node — finds conceptually similar content via AI-native search."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Exa uses neural embeddings to surface conceptually relevant pages — "
    "ideal for discovering industry reports, competitors, and thought leadership "
    "that keyword search would miss"
)
_EXA_SEARCH_URL = "https://api.exa.ai/search"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("EXA_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'exa_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class ExaSearchNode:
    node_type = "exa_search"
    display_name = "Exa Neural Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Exa API Key",
                "description": "Leave blank to use EXA_API_KEY env var or DB setting.",
            },
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Natural language query for neural search.",
            },
            "search_type": {
                "type": "string",
                "title": "Search Type",
                "enum": ["neural", "keyword"],
                "default": "neural",
                "description": (
                    "neural: semantic/embedding-based similarity search; "
                    "keyword: traditional keyword matching"
                ),
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        query = (config.get("query") or "").strip()
        if not query:
            return [{"error": "No query provided for Exa search", "source": "exa_search", "reason": _REASON}]

        api_key = _resolve_api_key(config.get("api_key"))
        if not api_key:
            log.warning("exa_search: no API key configured")
            return [{"error": "EXA_API_KEY not configured", "source": "exa_search", "reason": _REASON}]

        max_results = min(int(config.get("max_results", 10)), 100)

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, _search_exa, query, api_key, max_results)
        return results


def _search_exa(query: str, api_key: str, max_results: int) -> list[dict]:
    """POST to Exa search API and return normalised results."""
    payload = {
        "query": query,
        "numResults": max_results,
        "type": "neural",
        "useAutoprompt": True,
        "contents": {"text": True},
    }
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(_EXA_SEARCH_URL, json=payload, headers=headers)
            if response.status_code == 401:
                return [{"error": "Exa: unauthorized — check API key", "source": "exa_search", "reason": _REASON}]
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("exa_search: HTTP error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "exa_search", "reason": _REASON}]
    except Exception as exc:
        log.warning("exa_search: unexpected error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "exa_search", "reason": _REASON}]

    raw_results = data.get("results") or []
    return [_map_result(r) for r in raw_results]


def _map_result(r: dict) -> dict:
    """Normalise a single Exa result record."""
    contents = r.get("contents") or {}
    return {
        "title": r.get("title") or "",
        "url": r.get("url") or "",
        "text": r.get("text") or contents.get("text") or "",
        "score": r.get("score"),
        "published_date": r.get("publishedDate") or "",
        "source": "exa_search",
        "reason": _REASON,
    }
