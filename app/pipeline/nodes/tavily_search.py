"""Tavily AI search node — AI-optimized search returning structured excerpts for LLM consumption."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Tavily AI search returns structured excerpts and summaries optimised for LLM consumption "
    "— ideal for gathering fresh web intelligence on a company, person, or topic"
)
_TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("TAVILY_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'tavily_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class TavilySearchNode:
    node_type = "tavily_search"
    display_name = "Tavily AI Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Tavily API Key",
                "description": "Leave blank to use TAVILY_API_KEY env var or DB setting.",
            },
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "The search query to send to Tavily.",
            },
            "search_depth": {
                "type": "string",
                "title": "Search Depth",
                "enum": ["basic", "advanced"],
                "default": "basic",
                "description": "basic is faster; advanced performs deeper crawling.",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        query = (config.get("query") or "").strip()
        if not query:
            log.warning("tavily_search: no query provided")
            return [{"error": "No query provided", "source": "tavily_search", "reason": _REASON}]

        api_key = _resolve_api_key(config.get("api_key"))
        if not api_key:
            log.warning("tavily_search: no API key configured")
            return [
                {
                    "error": "TAVILY_API_KEY not configured",
                    "source": "tavily_search",
                    "reason": _REASON,
                }
            ]

        max_results = min(int(config.get("max_results", 5)), 20)
        depth = config.get("search_depth", "basic")

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, _search_tavily, query, api_key, max_results, depth
        )
        return results


def _search_tavily(
    query: str,
    api_key: str,
    max_results: int = 5,
    depth: str = "basic",
) -> list[dict]:
    """POST to Tavily search API and return normalised result list."""
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": depth,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(_TAVILY_SEARCH_URL, json=payload)
            if response.status_code == 401:
                return [{"error": "Tavily: unauthorized — check API key", "source": "tavily_search", "reason": _REASON}]
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("tavily_search: HTTP error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "tavily_search", "reason": _REASON}]
    except Exception as exc:
        log.warning("tavily_search: unexpected error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "tavily_search", "reason": _REASON}]

    raw_results = data.get("results") or []
    return [_map_result(r) for r in raw_results]


def _map_result(r: dict) -> dict:
    """Normalise a single Tavily result record."""
    return {
        "title": r.get("title") or "",
        "url": r.get("url") or "",
        "content": r.get("content") or r.get("raw_content") or "",
        "relevance_score": r.get("score"),
        "source": "tavily_search",
        "reason": _REASON,
    }
