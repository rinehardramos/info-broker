"""Web Crawl datastore node — fetch and parse web pages."""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urljoin, urlparse

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)


class WebCrawlNode:
    node_type = "web_crawl"
    display_name = "Web Crawl"
    category = "datastore"
    config_schema = {
        "type": "object",
        "properties": {
            "allowed_domains": {
                "type": "array",
                "title": "Allowed Domains",
                "items": {"type": "string"},
                "description": "Only crawl URLs on these domains (empty = allow all)",
            },
            "max_pages": {
                "type": "integer",
                "title": "Max Pages",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
            },
            "scrape_depth": {
                "type": "integer",
                "title": "Scrape Depth",
                "default": 1,
                "minimum": 0,
                "maximum": 3,
                "description": "How many link-follows deep to crawl (0 = just the given URL)",
            },
        },
        "required": [],
    }

    # -- PipelineNode interface ------------------------------------------------

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        return []

    # -- ToolCallable interface ------------------------------------------------

    def tool_schema(self) -> dict:
        return {
            "name": "web_crawl",
            "description": (
                "Fetch and extract text content from a web page URL. "
                "Can follow links up to the configured scrape depth."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to crawl and extract content from",
                    },
                },
                "required": ["url"],
            },
        }

    async def tool_invoke(
        self, params: dict, context: RunContext
    ) -> list[dict]:
        url = params.get("url", "")
        if not url:
            return []

        config = getattr(self, "_active_config", {})
        allowed_domains = config.get("allowed_domains", [])
        max_pages = int(config.get("max_pages", 10))
        scrape_depth = int(config.get("scrape_depth", 1))

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _crawl, url, allowed_domains, max_pages, scrape_depth
        )


def _crawl(
    start_url: str,
    allowed_domains: list[str],
    max_pages: int,
    scrape_depth: int,
) -> list[dict]:
    """Synchronous BFS web crawl starting from start_url."""
    from app.lib.ddg_fallback import scrape_url

    visited: set[str] = set()
    results: list[dict] = []
    # BFS queue: (url, depth)
    queue: list[tuple[str, int]] = [(start_url, 0)]

    while queue and len(results) < max_pages:
        url, depth = queue.pop(0)
        normalized = _normalize_url(url)
        if normalized in visited:
            continue
        visited.add(normalized)

        # Domain check
        if allowed_domains:
            domain = urlparse(url).hostname or ""
            if not any(domain.endswith(d) for d in allowed_domains):
                continue

        try:
            text = scrape_url(url, timeout=8)
        except Exception as exc:
            log.debug("web_crawl: failed to scrape %s: %s", url, exc)
            continue

        if not text:
            continue

        results.append({
            "title": _extract_title(text, url),
            "url": url,
            "content": text[:6000],
            "source": "web_crawl",
        })

        # Follow links if within depth budget
        if depth < scrape_depth:
            links = _extract_links(url, text)
            for link in links:
                if _normalize_url(link) not in visited:
                    queue.append((link, depth + 1))

    return results


def _normalize_url(url: str) -> str:
    """Strip fragment and trailing slash for dedup."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def _extract_title(text: str, url: str) -> str:
    """Best-effort title extraction from scraped text."""
    first_line = text.strip().split("\n")[0][:120]
    return first_line if first_line else urlparse(url).path


def _extract_links(base_url: str, text: str) -> list[str]:
    """Extract HTTP(S) links from text (heuristic — works on scraped markdown/text)."""
    urls: list[str] = []
    for match in re.finditer(r'https?://[^\s<>"\')\]]+', text):
        absolute = urljoin(base_url, match.group(0))
        if absolute.startswith("http"):
            urls.append(absolute)
    return urls[:50]  # cap to avoid runaway
