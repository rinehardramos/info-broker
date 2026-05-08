"""OpenAlex academic search node — free 250M+ scholarly works API."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "OpenAlex indexes 250M+ scholarly works — search papers, authors, and institutions "
    "with citation counts, DOIs, and journal metadata, all free with no API key required"
)
_OPENALEX_WORKS_URL = "https://api.openalex.org/works"
_MAILTO = "info-broker@example.com"


class OpenAlexSearchNode:
    node_type = "openalex_search"
    display_name = "OpenAlex Academic Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Keywords to search for in titles, abstracts, and full text.",
            },
            "search_type": {
                "type": "string",
                "title": "Search Type",
                "enum": ["works", "authors", "institutions"],
                "default": "works",
                "description": "Type of entity to search. Currently 'works' is fully supported.",
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
            log.warning("openalex_search: no query provided")
            return [
                {
                    "error": "No query provided for OpenAlex search",
                    "source": "openalex_search",
                    "reason": _REASON,
                }
            ]

        max_results = min(int(config.get("max_results", 10)), 100)

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, _search_works, query, max_results)
        return results


def _search_works(query: str, max_results: int) -> list[dict]:
    """Search OpenAlex works endpoint and return normalised paper records."""
    params = {
        "search": query,
        "per-page": min(max_results, 100),
        "mailto": _MAILTO,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(_OPENALEX_WORKS_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("openalex_search: HTTP error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "openalex_search", "reason": _REASON}]
    except Exception as exc:
        log.warning("openalex_search: unexpected error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "openalex_search", "reason": _REASON}]

    results = data.get("results") or []
    return [_map_work(item) for item in results[:max_results]]


def _map_work(item: dict) -> dict:
    """Normalise an OpenAlex work record into the standard output shape."""
    authorships = item.get("authorships") or []
    authors = [
        a["author"]["display_name"]
        for a in authorships
        if a.get("author") and a["author"].get("display_name")
    ]

    primary_location = item.get("primary_location") or {}
    source = primary_location.get("source") or {}
    journal = source.get("display_name") or ""

    openalex_id = item.get("id") or ""
    # Strip URL prefix if present: "https://openalex.org/W123" -> "W123"
    if "/" in openalex_id:
        openalex_id = openalex_id.rsplit("/", 1)[-1]

    return {
        "title": item.get("title") or "",
        "year": item.get("publication_year"),
        "doi": item.get("doi") or "",
        "citations": item.get("cited_by_count") or 0,
        "authors": authors,
        "journal": journal,
        "openalex_id": openalex_id,
        "source": "openalex_search",
        "reason": _REASON,
    }
