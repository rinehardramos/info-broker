"""TMDB search node — movie, TV, and person metadata via The Movie Database API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "TMDB provides rich movie, TV series, and person metadata including cast, crew, "
    "ratings, and episode data — useful for entertainment industry research and talent profiling"
)
_TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/{search_type}"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("TMDB_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'tmdb_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


def _map_result(item: dict) -> dict:
    """Normalise a single TMDB search result regardless of media_type."""
    media_type = item.get("media_type", "movie")

    if media_type == "tv":
        title = item.get("name") or item.get("original_name") or ""
        date = item.get("first_air_date") or ""
        overview = item.get("overview") or ""
        rating = item.get("vote_average")
    elif media_type == "person":
        title = item.get("name") or ""
        date = ""
        overview = item.get("known_for_department") or ""
        rating = None
    else:  # movie (and fallback)
        title = item.get("title") or item.get("original_title") or ""
        date = item.get("release_date") or ""
        overview = item.get("overview") or ""
        rating = item.get("vote_average")

    return {
        "tmdb_id": item.get("id"),
        "media_type": media_type,
        "title": title,
        "overview": overview,
        "date": date,
        "rating": rating,
        "source": "tmdb_search",
        "reason": _REASON,
    }


def _search_multi(query: str, api_key: str, max_results: int) -> list[dict]:
    """Search TMDB /search/multi and return normalised records."""
    url = _TMDB_SEARCH_URL.format(search_type="multi")
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"query": query, "page": 1}

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, params=params, headers=headers)
            if response.status_code == 401:
                return [{"error": "TMDB: unauthorized — check API key", "source": "tmdb_search", "reason": _REASON}]
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("tmdb_search: HTTP error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "tmdb_search", "reason": _REASON}]
    except Exception as exc:
        log.warning("tmdb_search: unexpected error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "tmdb_search", "reason": _REASON}]

    results = data.get("results") or []
    return [_map_result(item) for item in results[:max_results]]


class TmdbSearchNode:
    node_type = "tmdb_search"
    display_name = "TMDB Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "TMDB API Key (Bearer Token)",
                "description": "Leave blank to use TMDB_API_KEY env var or DB setting.",
            },
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Title, name, or keyword to search for.",
            },
            "search_type": {
                "type": "string",
                "title": "Search Type",
                "enum": ["multi", "movie", "tv", "person"],
                "default": "multi",
                "description": (
                    "multi: search across movies, TV shows, and people; "
                    "movie: movies only; tv: TV shows only; person: people only"
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
            log.warning("tmdb_search: no query provided")
            return [{"error": "No query provided", "source": "tmdb_search", "reason": _REASON}]

        api_key = _resolve_api_key(config.get("api_key"))
        if not api_key:
            log.warning("tmdb_search: no API key configured")
            return [{"error": "TMDB_API_KEY not configured", "source": "tmdb_search", "reason": _REASON}]

        max_results = min(int(config.get("max_results", 10)), 100)

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, _search_multi, query, api_key, max_results
        )
        return results
