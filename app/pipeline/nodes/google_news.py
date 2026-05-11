"""Google News source node — search news articles via the Google News RSS feed."""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import quote_plus

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Recent news articles surface press releases, funding events, leadership changes, and business risks"
_GN_RSS_URL = "https://news.google.com/rss/search"


class GoogleNewsNode:
    node_type = "google_news"
    display_name = "Google News"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Company name or topic to search for in Google News",
            },
            "language": {
                "type": "string",
                "title": "Language",
                "default": "en-PH",
                "description": "BCP-47 language/region code (e.g. 'en-PH', 'en-US', 'fil-PH')",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
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
        query = (config.get("query") or "").strip()
        language = (config.get("language") or "en-PH").strip()
        max_results = min(int(config.get("max_results", 20)), 100)

        # Supplement query from upstream inputs
        queries: list[str] = [query] if query else []
        for item in inputs:
            q = (
                item.get("query")
                or item.get("company")
                or item.get("name")
                or item.get("message")
                or ""
            ).strip()
            if q and q not in queries:
                queries.append(q)

        if not queries:
            log.warning("google_news: no query provided")
            return [{"error": "No query configured", "source": "google_news"}]

        loop = asyncio.get_running_loop()
        results: list[dict] = []

        for q in queries:
            batch = await loop.run_in_executor(
                None, _fetch_news, q, language, max_results
            )
            results.extend(batch)

        return results


def _fetch_news(query: str, language: str, max_results: int) -> list[dict]:
    """Fetch Google News RSS feed and parse results."""
    # language like "en-PH" → hl=en-PH&gl=PH&ceid=PH:en
    parts = language.split("-")
    lang = parts[0]
    country = parts[1] if len(parts) > 1 else "US"

    params = {
        "q": query,
        "hl": language,
        "gl": country,
        "ceid": f"{country}:{lang}",
    }

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(
                _GN_RSS_URL,
                params=params,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; info-broker/1.0)"
                    ),
                    "Accept": "application/rss+xml, text/xml, */*",
                },
            )
            response.raise_for_status()
            xml = response.text
    except httpx.HTTPStatusError as exc:
        log.warning("google_news: HTTP error for %r: %s", query, exc)
        return [{"query": query, "source": "google_news", "error": str(exc)}]
    except Exception as exc:
        log.warning("google_news: unexpected error for %r: %s", query, exc)
        return [{"query": query, "source": "google_news", "error": str(exc)}]

    items = _parse_rss(xml)
    return items[:max_results]


def _parse_rss(xml: str) -> list[dict]:
    """Parse RSS <item> blocks from Google News feed."""
    results: list[dict] = []

    item_blocks = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    for block in item_blocks:
        title = _extract_tag(block, "title")
        link = _extract_tag(block, "link")
        pub_date = _extract_tag(block, "pubDate")
        description = _extract_tag(block, "description")
        source_tag = re.search(r'<source[^>]*>(.*?)</source>', block, re.DOTALL)
        source_name = _strip_cdata(source_tag.group(1)) if source_tag else ""

        if not title and not link:
            continue

        results.append({
            "title": _strip_cdata(title),
            "url": _strip_cdata(link),
            "published_at": _strip_cdata(pub_date),
            "summary": _strip_tags(_strip_cdata(description)),
            "news_source": source_name,
            "source": "google_news",
            "reason": _REASON,
        })

    return results


def _extract_tag(xml: str, tag: str) -> str:
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else ""


def _strip_cdata(text: str) -> str:
    """Remove CDATA wrappers and decode HTML entities."""
    text = re.sub(r"<!\[CDATA\[(.*?)]]>", r"\1", text, flags=re.DOTALL)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return text.strip()


def _strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()
