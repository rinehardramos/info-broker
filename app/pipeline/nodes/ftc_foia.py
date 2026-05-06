"""FTC FOIA enrich node — Federal Trade Commission enforcement actions and FOIA records lookup."""

from __future__ import annotations

import logging

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "FTC enforcement actions and FOIA records reveal regulatory history, consumer complaints, and legal violations"
_FTC_BASE = "https://www.ftc.gov"
_FTC_SEARCH_URL = "https://www.ftc.gov/search"
_FTC_ACTIONS_URL = "https://www.ftc.gov/enforcement/cases-proceedings"


class FtcFoiaNode:
    node_type = "ftc_foia"
    display_name = "FTC / FOIA Lookup"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Company name or individual to search in FTC enforcement records",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 30,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        query = (config.get("query") or "").strip()
        max_results = min(int(config.get("max_results", 10)), 30)

        queries: list[str] = [query] if query else []
        for item in inputs:
            q = (
                item.get("query")
                or item.get("company")
                or item.get("name")
                or item.get("title")
                or ""
            ).strip()
            if q and q not in queries:
                queries.append(q)

        if not queries:
            log.warning("ftc_foia: no query provided")
            return [{"error": "No query provided", "source": "ftc_foia", "confidence": 0, "error_flagged": True}]

        results: list[dict] = []
        for q in queries:
            batch = await _search_ftc(q, max_results)
            results.extend(batch)

        return results


async def _search_ftc(query: str, max_results: int) -> list[dict]:
    """Search FTC enforcement actions via DDG site search."""
    from app.search_engine.plugins.ddg import DdgPlugin

    plugin = DdgPlugin()
    ddg_query = f'site:ftc.gov "{query}" enforcement OR complaint OR settlement OR action'

    try:
        hits = await plugin.search(ddg_query, max_results=max_results)
    except Exception as exc:
        log.warning("ftc_foia: DDG search failed for %r: %s", query, exc)
        return [{"query": query, "source": "ftc_foia", "error": str(exc), "confidence": 0, "error_flagged": True}]

    results: list[dict] = []
    for hit in hits:
        title = hit.title or ""
        url = hit.url or ""
        snippet = hit.snippet or ""

        if not title and not url:
            continue

        results.append({
            "source": "ftc_foia",
            "title": title,
            "content": snippet[:600],
            "url": url,
            "query": query,
            "confidence": 80,
            "reason": _REASON,
        })

    if not results:
        # Fallback: try broader search without site restriction
        try:
            broad_hits = await plugin.search(
                f"FTC enforcement action complaint {query}",
                max_results=max_results,
            )
            for hit in broad_hits:
                if "ftc.gov" in (hit.url or ""):
                    results.append({
                        "source": "ftc_foia",
                        "title": hit.title or "",
                        "content": (hit.snippet or "")[:600],
                        "url": hit.url or "",
                        "query": query,
                        "confidence": 70,
                        "reason": _REASON,
                    })
        except Exception as exc:
            log.debug("ftc_foia: fallback search failed: %s", exc)

    return results[:max_results]
