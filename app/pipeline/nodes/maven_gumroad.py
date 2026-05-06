from __future__ import annotations
import logging
import re
from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)
_REASON = "Maven and Gumroad surface creator economy products and courses"


class MavenGumroadNode:
    node_type = "maven_gumroad"
    display_name = "Maven/Gumroad Scraper"
    category = "enrich"
    config_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "title": "Search Query"},
            "platform": {"type": "string", "enum": ["maven", "gumroad", "both"], "default": "both"},
            "max_results": {"type": "integer", "default": 10, "minimum": 1, "maximum": 30},
        },
        "required": [],
    }

    async def execute(self, config, inputs, context):
        query = (config.get("query") or "").strip()
        platform = (config.get("platform") or "both").strip().lower()
        max_results = min(int(config.get("max_results", 10)), 30)
        queries = [query] if query else []
        for item in inputs:
            q = (item.get("query") or item.get("name") or item.get("company") or item.get("title") or "").strip()
            if q and q not in queries:
                queries.append(q)
        if not queries:
            return [{"error": "No query", "source": "maven_gumroad", "confidence": 0, "error_flagged": True}]
        results = []
        for q in queries:
            if platform in ("maven", "both"):
                results.extend(await _search_platform(q, "maven", max_results))
            if platform in ("gumroad", "both"):
                results.extend(await _search_platform(q, "gumroad", max_results))
        return results


async def _search_platform(query, platform, max_results):
    """Search Maven or Gumroad for courses/products via DDG."""
    from app.search_engine.plugins.ddg import DdgPlugin
    hosts = {"maven": "maven.com", "gumroad": "gumroad.com"}
    host = hosts[platform]
    plugin = DdgPlugin()
    ddg_query = f"site:{host} {query}"
    try:
        hits = await plugin.search(ddg_query, max_results=max_results)
    except Exception as exc:
        log.warning("maven_gumroad: %s search failed for %r: %s", platform, query, exc)
        return [{"query": query, "source": "maven_gumroad", "error": str(exc), "confidence": 0, "error_flagged": True}]
    results = []
    for hit in hits:
        title = hit.title or ""
        url = hit.url or ""
        snippet = hit.snippet or ""
        if not title and not url:
            continue
        extra = {}
        if platform == "maven":
            m = re.search(r"by\s+([A-Z][^|\n]{2,40})", title, re.IGNORECASE)
            extra["instructor"] = m.group(1).strip() if m else ""
        else:
            pm = re.search(r"\$[\d,]+(?:\.\d{2})?", snippet)
            extra["price"] = pm.group(0) if pm else ""
            cm = re.search(r"gumroad\.com/([^/]+)/", url)
            extra["creator"] = cm.group(1) if cm else ""
        results.append({
            "source": "maven_gumroad", "platform": platform,
            "title": title, "content": snippet[:600], "url": url,
            "query": query, "confidence": 70, "reason": _REASON, **extra,
        })
    return results[:max_results]
