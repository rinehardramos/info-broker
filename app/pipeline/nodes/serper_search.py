"""Serper Google SERP search node — web, news, and image results via the Serper API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Serper provides low-latency Google SERP results (web, news, images) — "
    "ideal for surface-level research, brand monitoring, and lead discovery"
)
_SERPER_BASE_URL = "https://google.serper.dev"

_SEARCH_TYPE_PATHS = {
    "search": "/search",
    "news": "/news",
    "images": "/images",
}


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("SERPER_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'serper_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class SerperSearchNode:
    node_type = "serper_search"
    display_name = "Serper Google Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Serper API Key",
                "description": "Leave blank to use SERPER_API_KEY env var or DB setting.",
            },
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "The search query to send to Google via Serper.",
            },
            "search_type": {
                "type": "string",
                "title": "Search Type",
                "enum": ["search", "news", "images"],
                "default": "search",
                "description": "search: web results; news: news articles; images: image results.",
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
            # Try to pull a query from upstream inputs
            for item in inputs:
                q = item.get("query") or item.get("company") or item.get("name") or ""
                if q:
                    query = q.strip()
                    break

        if not query:
            log.warning("serper_search: no query provided")
            return [{"error": "No query provided", "source": "serper_search", "reason": _REASON}]

        api_key = _resolve_api_key(config.get("api_key"))
        if not api_key:
            log.warning("serper_search: no API key configured")
            return [
                {
                    "error": "SERPER_API_KEY not configured",
                    "source": "serper_search",
                    "reason": _REASON,
                }
            ]

        search_type = config.get("search_type", "search")
        if search_type not in _SEARCH_TYPE_PATHS:
            search_type = "search"
        max_results = min(int(config.get("max_results", 10)), 100)

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, _search_serper, query, api_key, max_results, search_type
        )
        return results


def _search_serper(
    query: str,
    api_key: str,
    max_results: int,
    search_type: str = "search",
) -> list[dict]:
    """POST to Serper and return normalised result dicts."""
    path = _SEARCH_TYPE_PATHS.get(search_type, "/search")
    url = f"{_SERPER_BASE_URL}{path}"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    payload = {"q": query, "num": max_results}

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code == 401:
                return [{"error": "Serper: unauthorized — check API key", "source": "serper_search", "reason": _REASON}]
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("serper_search: HTTP error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "serper_search", "reason": _REASON}]
    except Exception as exc:
        log.warning("serper_search: unexpected error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "serper_search", "reason": _REASON}]

    organic = data.get("organic") or data.get("news") or data.get("images") or []
    return [_map_result(item, idx) for idx, item in enumerate(organic[:max_results], start=1)]


def _map_result(item: dict, position: int) -> dict:
    """Normalise a single Serper result record."""
    return {
        "title": item.get("title") or "",
        "url": item.get("link") or item.get("imageUrl") or "",
        "snippet": item.get("snippet") or item.get("description") or "",
        "position": item.get("position") or position,
        "source": "serper_search",
        "reason": _REASON,
    }
