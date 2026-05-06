"""Glassdoor Reviews enrich node — company reviews via DuckDuckGo search."""

from __future__ import annotations

import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Glassdoor reviews surface employee sentiment, culture signals, and management quality "
    "useful for vendor due diligence and talent acquisition intelligence"
)


class GlassdoorReviewsNode:
    node_type = "glassdoor_reviews"
    display_name = "Glassdoor Reviews"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "company": {
                "type": "string",
                "title": "Company Name",
                "description": "Company to search for on Glassdoor",
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
        company = (config.get("company") or "").strip()
        max_results = min(int(config.get("max_results", 10)), 30)

        companies: list[str] = [company] if company else []
        for item in inputs:
            c = (
                item.get("company")
                or item.get("name")
                or item.get("query")
                or item.get("title")
                or ""
            ).strip()
            if c and c not in companies:
                companies.append(c)

        if not companies:
            log.warning("glassdoor_reviews: no company provided")
            return [{"error": "No company provided", "source": "glassdoor_reviews", "confidence": 0, "error_flagged": True}]

        results: list[dict] = []
        for c in companies:
            batch = await _search_glassdoor(c, max_results)
            results.extend(batch)

        return results


async def _search_glassdoor(company: str, max_results: int) -> list[dict]:
    """Search Glassdoor for company reviews via DDG site search."""
    from app.search_engine.plugins.ddg import DdgPlugin

    plugin = DdgPlugin()
    gd_host = "glassdoor.com"
    ddg_query = f"site:{gd_host} {company} reviews"

    try:
        hits = await plugin.search(ddg_query, max_results=max_results)
    except Exception as exc:
        log.warning("glassdoor_reviews: DDG search failed for %r: %s", company, exc)
        return [{"company": company, "source": "glassdoor_reviews", "error": str(exc), "confidence": 0, "error_flagged": True}]

    results: list[dict] = []
    for hit in hits:
        title = hit.title or ""
        url = hit.url or ""
        snippet = hit.snippet or ""

        if not title and not url:
            continue

        # Extract rating hint from snippet if present
        import re
        rating_match = re.search(r"(\d\.\d)\s*(?:out of 5|stars?|/5)", snippet, re.IGNORECASE)
        rating = rating_match.group(1) if rating_match else ""

        content_parts = []
        if rating:
            content_parts.append(f"Rating: {rating}/5")
        if snippet:
            content_parts.append(snippet[:500])

        results.append({
            "source": "glassdoor_reviews",
            "title": title,
            "content": " | ".join(content_parts) if content_parts else snippet[:600],
            "url": url,
            "company": company,
            "rating": rating,
            "confidence": 65,
            "reason": _REASON,
        })

    return results[:max_results]
