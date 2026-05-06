"""IBPAP enrich node — IT & Business Process Association of the Philippines member directory."""

from __future__ import annotations

import logging

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "IBPAP is the primary Philippine IT-BPM industry association — membership confirms legitimate outsourcing operations"
_IBPAP_BASE = "https://ibpap.org"
_IBPAP_MEMBERS_URL = "https://ibpap.org/member-companies"


class IbpapNode:
    node_type = "ibpap"
    display_name = "IBPAP Member Directory"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Company Name",
                "description": "Company name to search in the IBPAP member directory",
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
            log.warning("ibpap: no query provided")
            return [{"error": "No query provided", "source": "ibpap", "confidence": 0, "error_flagged": True}]

        results: list[dict] = []
        for q in queries:
            batch = await _search_ibpap(q, max_results)
            results.extend(batch)

        return results


async def _search_ibpap(query: str, max_results: int) -> list[dict]:
    """Search IBPAP member directory via site scrape and DDG fallback."""
    # Try direct scrape of IBPAP members page
    results = await _scrape_ibpap_members(query, max_results)
    if results and not results[0].get("error_flagged"):
        return results

    # Fallback: DDG search scoped to ibpap.org
    from app.search_engine.plugins.ddg import DdgPlugin

    plugin = DdgPlugin()
    ddg_query = f'site:ibpap.org "{query}"'

    try:
        hits = await plugin.search(ddg_query, max_results=max_results)
    except Exception as exc:
        log.warning("ibpap: DDG search failed for %r: %s", query, exc)
        return [{"query": query, "source": "ibpap", "error": str(exc), "confidence": 0, "error_flagged": True}]

    ddg_results: list[dict] = []
    for hit in hits:
        title = hit.title or ""
        url = hit.url or ""
        snippet = hit.snippet or ""

        if not title and not url:
            continue

        ddg_results.append({
            "source": "ibpap",
            "title": title,
            "content": snippet[:600],
            "url": url,
            "query": query,
            "confidence": 70,
            "reason": _REASON,
        })

    return ddg_results[:max_results]


async def _scrape_ibpap_members(query: str, max_results: int) -> list[dict]:
    """Attempt direct scrape of IBPAP member companies page."""
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                _IBPAP_MEMBERS_URL,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,*/*",
                },
            )
            if response.status_code != 200:
                log.debug("ibpap: members page returned HTTP %d", response.status_code)
                return [{"query": query, "source": "ibpap", "error": f"HTTP {response.status_code}", "confidence": 0, "error_flagged": True}]
            html = response.text
    except Exception as exc:
        log.debug("ibpap: failed to reach members page: %s", exc)
        return [{"query": query, "source": "ibpap", "error": str(exc), "confidence": 0, "error_flagged": True}]

    return _parse_member_html(html, query, max_results)


def _parse_member_html(html: str, query: str, max_results: int) -> list[dict]:
    """Parse IBPAP member directory HTML for matching companies."""
    import re

    results: list[dict] = []
    query_lower = query.lower()

    # Look for company names in common HTML patterns
    # IBPAP typically lists members in cards or list items
    # Try to find any text that contains the query
    patterns = [
        r'<(?:h[1-6]|strong|b|td)[^>]*>([^<]*' + re.escape(query) + r'[^<]*)</(?:h[1-6]|strong|b|td)>',
        r'class="[^"]*(?:company|member|name)[^"]*"[^>]*>([^<]*' + re.escape(query) + r'[^<]*)<',
    ]

    found: set[str] = set()
    for pattern in patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        for match in matches:
            company_name = match.strip()
            if company_name and company_name not in found:
                found.add(company_name)
                results.append({
                    "source": "ibpap",
                    "title": company_name,
                    "content": f"IBPAP member company: {company_name}",
                    "url": _IBPAP_MEMBERS_URL,
                    "query": query,
                    "confidence": 85,
                    "reason": _REASON,
                })

    if not results and query_lower in html.lower():
        # Query appears but we couldn't extract structured data
        results.append({
            "source": "ibpap",
            "title": f"{query} found in IBPAP directory",
            "content": f"'{query}' appears in IBPAP member directory. Visit the page for details.",
            "url": _IBPAP_MEMBERS_URL,
            "query": query,
            "confidence": 65,
            "reason": _REASON,
        })

    return results[:max_results]
