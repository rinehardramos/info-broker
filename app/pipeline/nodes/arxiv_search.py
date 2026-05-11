"""arXiv search node — free preprint search via the arXiv Atom API."""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "arXiv indexes 2M+ preprints in CS, math, physics, and biology — "
    "the authoritative source for AI/ML research papers before peer review"
)
_ARXIV_API_URL = "https://export.arxiv.org/api/query"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

_VALID_SORT_BY = {"relevance", "lastUpdatedDate", "submittedDate"}
_VALID_CATEGORIES = {
    "cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE", "cs.IR",
    "stat.ML", "math.ST", "econ.GN", "q-bio", "physics",
}


class ArxivSearchNode:
    node_type = "arxiv_search"
    display_name = "arXiv Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Keywords or arXiv search expression (e.g. 'memory augmented LLM').",
            },
            "category": {
                "type": "string",
                "title": "Category Filter",
                "description": "Optional arXiv category (e.g. cs.AI, cs.LG, stat.ML). Leave blank for all.",
                "default": "",
            },
            "sort_by": {
                "type": "string",
                "title": "Sort By",
                "enum": ["relevance", "lastUpdatedDate", "submittedDate"],
                "default": "relevance",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        query = (config.get("query") or "").strip()
        if not query:
            for item in inputs:
                q = item.get("query") or item.get("topic") or item.get("name") or ""
                if q:
                    query = str(q).strip()
                    break

        if not query:
            log.warning("arxiv_search: no query provided")
            return [{"error": "No query provided", "source": "arxiv_search", "reason": _REASON}]

        category = (config.get("category") or "").strip()
        sort_by = config.get("sort_by", "relevance")
        if sort_by not in _VALID_SORT_BY:
            sort_by = "relevance"
        max_results = min(int(config.get("max_results", 10)), 50)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _search_arxiv, query, category, sort_by, max_results
        )


def _build_search_query(query: str, category: str) -> str:
    if category:
        return f"({query}) AND cat:{category}"
    return query


def _search_arxiv(
    query: str, category: str, sort_by: str, max_results: int
) -> list[dict]:
    search_query = _build_search_query(query, category)
    params = {
        "search_query": f"all:{search_query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": "descending",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(_ARXIV_API_URL, params=params)
            response.raise_for_status()
            xml_text = response.text
    except httpx.HTTPStatusError as exc:
        log.warning("arxiv_search: HTTP error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "arxiv_search", "reason": _REASON}]
    except Exception as exc:
        log.warning("arxiv_search: unexpected error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "arxiv_search", "reason": _REASON}]

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("arxiv_search: XML parse error: %s", exc)
        return [{"error": f"XML parse error: {exc}", "source": "arxiv_search", "reason": _REASON}]

    entries = root.findall("atom:entry", _NS)
    return [_map_entry(e) for e in entries]


def _map_entry(entry: ET.Element) -> dict:
    arxiv_id_raw = (entry.findtext("atom:id", default="", namespaces=_NS) or "").strip()
    # Strip URL prefix: "http://arxiv.org/abs/2301.01234v2" -> "2301.01234v2"
    arxiv_id = arxiv_id_raw.rsplit("/", 1)[-1] if "/" in arxiv_id_raw else arxiv_id_raw

    authors = [
        (a.findtext("atom:name", default="", namespaces=_NS) or "").strip()
        for a in entry.findall("atom:author", _NS)
    ]

    categories = [
        c.get("term", "")
        for c in entry.findall("atom:category", _NS)
    ]

    # Prefer the PDF link
    pdf_url = ""
    abs_url = ""
    for link in entry.findall("atom:link", _NS):
        rel = link.get("rel", "")
        href = link.get("href", "")
        title = link.get("title", "")
        if title == "pdf":
            pdf_url = href
        elif rel == "alternate":
            abs_url = href

    return {
        "arxiv_id": arxiv_id,
        "title": (entry.findtext("atom:title", default="", namespaces=_NS) or "").strip(),
        "authors": authors,
        "abstract": (entry.findtext("atom:summary", default="", namespaces=_NS) or "").strip(),
        "published": (entry.findtext("atom:published", default="", namespaces=_NS) or "").strip(),
        "updated": (entry.findtext("atom:updated", default="", namespaces=_NS) or "").strip(),
        "categories": categories,
        "url": abs_url or arxiv_id_raw,
        "pdf_url": pdf_url,
        "source": "arxiv_search",
        "reason": _REASON,
    }
