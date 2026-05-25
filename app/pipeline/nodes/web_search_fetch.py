"""Web Search & Fetch node — DDG search with optional page content fetching."""

from __future__ import annotations

import asyncio
import logging
import re

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)


class WebSearchFetchNode:
    node_type = "web_search_fetch"
    display_name = "Web Search & Fetch"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
            "fetch_content": {
                "type": "boolean",
                "title": "Fetch Page Content",
                "default": False,
                "description": "Fetch and extract text from each result URL",
            },
            "search_engine": {
                "type": "string",
                "title": "Search Engine",
                "enum": ["ddg"],
                "default": "ddg",
            },
        },
        "required": [],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        from app.search_engine.plugins.ddg import DdgPlugin

        max_results = int(config.get("max_results", 10))
        fetch_content = bool(config.get("fetch_content", False))
        # search_engine is currently always "ddg"; reserved for future extension
        _ = config.get("search_engine", "ddg")

        plugin = DdgPlugin()
        all_results: list[dict] = []

        for item in inputs:
            query = (
                item.get("query")
                or item.get("message")
                or item.get("title")
                or ""
            )
            if not query:
                continue

            try:
                results = await plugin.search(query, max_results=max_results)
            except Exception as exc:
                log.warning("WebSearchFetchNode: search failed for %r: %s", query, exc)
                continue

            for r in results:
                entry: dict = {
                    "title": r.title or "",
                    "url": r.url or "",
                    "snippet": r.snippet or "",
                    "query": query,
                    "source": "web_search",
                }

                if fetch_content and r.url:
                    try:
                        loop = asyncio.get_running_loop()
                        content = await loop.run_in_executor(
                            None, _fetch_page_text, r.url
                        )
                        entry["content"] = content
                    except Exception as exc:
                        log.debug(
                            "WebSearchFetchNode: failed to fetch %s: %s", r.url, exc
                        )
                        entry["content"] = ""

                all_results.append(entry)

        return all_results


def _fetch_page_text(url: str, timeout: int = 10) -> str:
    """Fetch URL and return stripped plain text.

    Delegates to ``scrape_url``, which fetches through ``security.safe_fetch_url``
    (SSRF-guarded, redirects disabled) with browser TLS/HTTP2 impersonation via
    curl_cffi — far more robust against bot-blocking than the old raw-httpx fetch.
    """
    from app.lib.ddg_fallback import scrape_url

    text = scrape_url(url, timeout=timeout)
    return text[:8000]


def _html_to_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace to extract readable text."""
    # Remove script and style blocks entirely
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    text = (
        text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&nbsp;", " ")
    )
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()
