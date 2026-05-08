"""Multi-engine meta-search node — parallel dispatch, dedup, and consensus ranking."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Multi-engine search maximises coverage by querying several providers in parallel "
    "and surfaces the most credible results via cross-engine consensus scoring"
)

_SERPER_HOST = "google.serper.dev"
_BRAVE_HOST = "api.search.brave.com"
_EXA_HOST = "api.exa.ai"


# ---------------------------------------------------------------------------
# DDG backend
# ---------------------------------------------------------------------------

def _ddg_search_impl(query: str, max_results: int) -> list[dict]:
    """Thin wrapper around DDGS so tests can mock it cleanly."""
    from duckduckgo_search import DDGS
    raw = DDGS().text(query, max_results=max_results) or []
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in raw
    ]


def _search_ddg(query: str, max_results: int) -> list[dict]:
    """Return DDG results tagged with engine='ddg'. Returns [] on failure."""
    try:
        raw = _ddg_search_impl(query, max_results)
        return [
            {
                "title": r["title"],
                "url": r["url"],
                "snippet": r["snippet"],
                "engine": "ddg",
            }
            for r in raw
        ]
    except Exception as exc:
        log.warning("multi_search: ddg error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Serper backend
# ---------------------------------------------------------------------------

def _search_serper(query: str, api_key: str, max_results: int) -> list[dict]:
    """Return Serper (Google) results tagged with engine='serper'. Returns [] on failure."""
    endpoint = f"https://{_SERPER_HOST}/search"
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                endpoint,
                json={"q": query, "num": max_results},
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "engine": "serper",
            }
            for item in (data.get("organic") or [])
        ]
    except Exception as exc:
        log.warning("multi_search: serper error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Brave backend
# ---------------------------------------------------------------------------

def _search_brave(query: str, api_key: str, max_results: int) -> list[dict]:
    """Return Brave Search results tagged with engine='brave'. Returns [] on failure."""
    endpoint = f"https://{_BRAVE_HOST}/res/v1/web/search"
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                endpoint,
                params={"q": query, "count": max_results},
                headers={"Accept": "application/json", "Accept-Encoding": "gzip", "X-Subscription-Token": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        web = data.get("web") or {}
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
                "engine": "brave",
            }
            for item in (web.get("results") or [])
        ]
    except Exception as exc:
        log.warning("multi_search: brave error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Exa backend
# ---------------------------------------------------------------------------

def _search_exa(query: str, api_key: str, max_results: int) -> list[dict]:
    """Return Exa results tagged with engine='exa'. Returns [] on failure."""
    endpoint = f"https://{_EXA_HOST}/search"
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                endpoint,
                json={"query": query, "numResults": max_results},
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("text", "") or item.get("highlights", [""])[0],
                "engine": "exa",
            }
            for item in (data.get("results") or [])
        ]
    except Exception as exc:
        log.warning("multi_search: exa error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Dedup + ranking helpers
# ---------------------------------------------------------------------------

_UTM_PATTERN = re.compile(r"utm_[^&]+&?", re.IGNORECASE)


def _normalize_url(url: str) -> str:
    """Strip trailing slash and utm_* tracking params for dedup keying."""
    try:
        parsed = urlparse(url)
        # Remove utm_* query params
        qs = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in qs.items() if not k.lower().startswith("utm_")}
        # Rebuild query string with sorted keys for stable comparison
        clean_query = urlencode(sorted(filtered.items()))
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            parsed.params,
            clean_query,
            "",  # drop fragment
        ))
        return normalized
    except Exception:
        return url.rstrip("/")


def _dedup_results(results: list[dict]) -> list[dict]:
    """
    Group results by normalized URL.
    For each group: merge engines list, keep best title/snippet (longest non-empty),
    and set consensus_score = number of distinct engines that found it.
    """
    seen: dict[str, dict] = {}  # normalized_url -> merged record
    order: list[str] = []       # preserve first-seen insertion order

    for r in results:
        key = _normalize_url(r.get("url", ""))
        if key not in seen:
            seen[key] = {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", ""),
                "engines": [r["engine"]],
                "consensus_score": 1,
            }
            order.append(key)
        else:
            entry = seen[key]
            engine = r["engine"]
            if engine not in entry["engines"]:
                entry["engines"].append(engine)
                entry["consensus_score"] += 1
            # Prefer longer title / snippet
            if len(r.get("title", "")) > len(entry["title"]):
                entry["title"] = r["title"]
            if len(r.get("snippet", "")) > len(entry["snippet"]):
                entry["snippet"] = r["snippet"]

    return [seen[k] for k in order]


def _rank_by_consensus(results: list[dict]) -> list[dict]:
    """Sort descending by consensus_score, preserving relative order for ties."""
    return sorted(results, key=lambda r: r["consensus_score"], reverse=True)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def _get_api_key(engine: str) -> str | None:
    return os.getenv(f"{engine.upper()}_API_KEY")


class MultiSearchNode:
    node_type = "multi_search"
    display_name = "Multi-Engine Web Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "The query to dispatch to all selected search engines.",
            },
            "engines": {
                "type": "array",
                "title": "Engines",
                "description": "Which search engines to use. ddg is free; others require API keys.",
                "items": {"type": "string", "enum": ["ddg", "serper", "brave", "exa"]},
                "default": ["ddg", "serper", "brave"],
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "description": "Maximum number of deduplicated results to return.",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        # 1. Resolve query — config first, then first upstream input
        query: str = (
            config.get("query")
            or next(
                (
                    i.get("query") or i.get("message") or i.get("title")
                    for i in inputs
                    if i
                ),
                None,
            )
            or ""
        ).strip()

        if not query:
            return [{
                "error": "multi_search requires a 'query' in config or upstream input",
                "source": "multi_search",
            }]

        engines: list[str] = config.get("engines") or ["ddg", "serper", "brave"]
        max_results: int = int(config.get("max_results", 20))

        # 2. Build executor tasks — skip engines that lack API keys (except ddg)
        loop = asyncio.get_running_loop()
        tasks: list[asyncio.Future] = []

        for engine in engines:
            if engine == "ddg":
                tasks.append(loop.run_in_executor(None, _search_ddg, query, max_results))
            elif engine == "serper":
                key = _get_api_key("serper")
                if key:
                    tasks.append(loop.run_in_executor(None, _search_serper, query, key, max_results))
                else:
                    log.debug("multi_search: skipping serper — SERPER_API_KEY not set")
            elif engine == "brave":
                key = _get_api_key("brave")
                if key:
                    tasks.append(loop.run_in_executor(None, _search_brave, query, key, max_results))
                else:
                    log.debug("multi_search: skipping brave — BRAVE_API_KEY not set")
            elif engine == "exa":
                key = _get_api_key("exa")
                if key:
                    tasks.append(loop.run_in_executor(None, _search_exa, query, key, max_results))
                else:
                    log.debug("multi_search: skipping exa — EXA_API_KEY not set")

        if not tasks:
            return [{
                "error": "no search engines available — add 'ddg' or set API keys",
                "source": "multi_search",
            }]

        # 3. Parallel dispatch
        batches = await asyncio.gather(*tasks, return_exceptions=True)

        raw: list[dict] = []
        for batch in batches:
            if isinstance(batch, Exception):
                log.warning("multi_search: engine task raised: %s", batch)
                continue
            raw.extend(batch)  # type: ignore[arg-type]

        # 4. Dedup + consensus rank
        deduped = _dedup_results(raw)
        ranked = _rank_by_consensus(deduped)
        top = ranked[:max_results]

        # 5. Stamp standard output fields
        return [
            {
                "title": r["title"],
                "url": r["url"],
                "snippet": r["snippet"],
                "engines": r["engines"],
                "consensus_score": r["consensus_score"],
                "source": "multi_search",
                "reason": _REASON,
            }
            for r in top
        ]
