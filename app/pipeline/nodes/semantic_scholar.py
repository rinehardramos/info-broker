"""Semantic Scholar search node — academic paper search via the Semantic Scholar Graph API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Semantic Scholar provides free access to academic papers, citation graphs, and author "
    "profiles — useful for research-backed prospecting and identifying domain experts"
)
_S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_DEFAULT_FIELDS = "title,year,citationCount,abstract,authors,externalIds"


class SemanticScholarNode:
    node_type = "semantic_scholar"
    display_name = "Semantic Scholar"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Academic paper search query.",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
            },
            "fields": {
                "type": "string",
                "title": "Fields",
                "default": _DEFAULT_FIELDS,
                "description": "Comma-separated list of fields to return.",
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
                q = item.get("query") or item.get("topic") or item.get("name") or ""
                if q:
                    query = str(q).strip()
                    break

        if not query:
            log.warning("semantic_scholar: no query provided")
            return [{"error": "No query provided", "source": "semantic_scholar", "reason": _REASON}]

        max_results = min(int(config.get("max_results", 10)), 100)

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, _search_papers, query, max_results)
        return results


def _search_papers(query: str, max_results: int) -> list[dict]:
    """Call the Semantic Scholar paper search endpoint and return normalised results."""
    params: dict = {
        "query": query,
        "limit": max_results,
        "fields": _DEFAULT_FIELDS,
    }
    headers: dict = {}
    api_key = os.getenv("S2_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(_S2_SEARCH_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("semantic_scholar: HTTP error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "semantic_scholar", "reason": _REASON}]
    except Exception as exc:
        log.warning("semantic_scholar: unexpected error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "semantic_scholar", "reason": _REASON}]

    papers = data.get("data") or []
    return [_map_paper(p) for p in papers]


def _map_paper(paper: dict) -> dict:
    """Normalise a Semantic Scholar paper record."""
    authors = [a.get("name", "") for a in (paper.get("authors") or []) if a.get("name")]
    external_ids = paper.get("externalIds") or {}
    doi = external_ids.get("DOI") or ""
    return {
        "paper_id": paper.get("paperId") or "",
        "title": paper.get("title") or "",
        "year": paper.get("year"),
        "citations": paper.get("citationCount") or 0,
        "abstract": paper.get("abstract") or "",
        "authors": authors,
        "doi": doi,
        "source": "semantic_scholar",
        "reason": _REASON,
    }
