"""Web Crawl datastore node — fetch and parse web pages."""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from urllib.parse import urljoin, urlparse

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User-Agent pool
# ---------------------------------------------------------------------------

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]


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
            "delay_seconds": {
                "type": "number",
                "title": "Delay Between Requests (s)",
                "default": 1.0,
                "minimum": 0.0,
                "description": "Seconds to wait between page fetches to avoid rate-limiting",
            },
            "respect_robots": {
                "type": "boolean",
                "title": "Respect robots.txt",
                "default": True,
                "description": "When enabled, obey Disallow rules in each domain's robots.txt",
            },
            "extract_mode": {
                "type": "string",
                "title": "Extract Mode",
                "enum": ["text", "html", "markdown"],
                "default": "text",
                "description": "Content format: plain text (default), raw HTML, or basic Markdown",
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
        delay_seconds = float(config.get("delay_seconds", 1.0))
        respect_robots = bool(config.get("respect_robots", True))
        extract_mode = config.get("extract_mode", "text")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            _crawl,
            url,
            allowed_domains,
            max_pages,
            scrape_depth,
            delay_seconds,
            respect_robots,
            extract_mode,
        )


# ---------------------------------------------------------------------------
# Internal synchronous crawl implementation
# ---------------------------------------------------------------------------

def _crawl(
    start_url: str,
    allowed_domains: list[str],
    max_pages: int,
    scrape_depth: int,
    delay_seconds: float = 1.0,
    respect_robots: bool = True,
    extract_mode: str = "text",
) -> list[dict]:
    """Synchronous BFS web crawl starting from start_url."""
    from app.lib.ddg_fallback import scrape_url

    visited: set[str] = set()
    results: list[dict] = []
    # BFS queue: (url, depth)
    queue: list[tuple[str, int]] = [(start_url, 0)]
    # robots.txt cache: domain -> set of disallowed path prefixes
    robots_cache: dict[str, set[str]] = {}
    last_fetch_time: float = 0.0

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

        # robots.txt check
        if respect_robots and not _is_allowed_by_robots(url, robots_cache):
            log.debug("web_crawl: robots.txt disallows %s", url)
            continue

        # Rate limiting: enforce delay between requests
        now = time.monotonic()
        elapsed = now - last_fetch_time
        if elapsed < delay_seconds:
            time.sleep(delay_seconds - elapsed)

        ua = random.choice(_USER_AGENTS)
        raw = _fetch_with_retry(url, ua, timeout=8)
        last_fetch_time = time.monotonic()

        if raw is None:
            continue

        content = _extract_content(raw, extract_mode)
        if not content:
            continue

        results.append({
            "title": _extract_title(raw if extract_mode == "text" else content, url),
            "url": url,
            "content": content[:6000],
            "source": "web_crawl",
        })

        # Follow links if within depth budget
        if depth < scrape_depth:
            links = _extract_links(url, raw)
            for link in links:
                if _normalize_url(link) not in visited:
                    queue.append((link, depth + 1))

    return results


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------

def _fetch_with_retry(url: str, user_agent: str, timeout: int = 8) -> str | None:
    """Fetch a URL with up to 3 attempts and exponential backoff.

    Returns the raw text content on success, None if all attempts fail.
    The caller controls User-Agent rotation by passing ``user_agent``.
    """
    from app.lib.ddg_fallback import scrape_url

    for attempt in range(3):
        try:
            text = scrape_url(url, timeout=timeout)
            if text:
                return text
        except Exception as exc:
            log.debug(
                "web_crawl: attempt %d failed for %s: %s", attempt + 1, url, exc
            )
        if attempt < 2:
            time.sleep(2 ** attempt)

    log.debug("web_crawl: all retries exhausted for %s", url)
    return None


# ---------------------------------------------------------------------------
# robots.txt support
# ---------------------------------------------------------------------------

def _is_allowed_by_robots(url: str, cache: dict[str, set[str]]) -> bool:
    """Return True if the URL is not disallowed by the domain's robots.txt."""
    parsed = urlparse(url)
    domain = parsed.netloc
    path = parsed.path or "/"

    if domain not in cache:
        cache[domain] = _fetch_robots_disallow(
            f"{parsed.scheme}://{domain}/robots.txt"
        )

    disallowed = cache[domain]
    for prefix in disallowed:
        if prefix and path.startswith(prefix):
            return False
    return True


def _fetch_robots_disallow(robots_url: str) -> set[str]:
    """Fetch robots.txt and return the set of Disallow path prefixes for *."""
    disallowed: set[str] = set()
    try:
        import httpx
        with httpx.Client(timeout=5.0, follow_redirects=True) as client:
            resp = client.get(
                robots_url,
                headers={"User-Agent": random.choice(_USER_AGENTS)},
            )
            if resp.status_code != 200:
                return disallowed
            text = resp.text
    except Exception as exc:
        log.debug("web_crawl: could not fetch robots.txt %s: %s", robots_url, exc)
        return disallowed

    # Parse: collect Disallow lines under "User-agent: *" sections
    applies = False
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            applies = agent == "*"
        elif applies and line.lower().startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path:
                disallowed.add(path)

    return disallowed


# ---------------------------------------------------------------------------
# Content extraction modes
# ---------------------------------------------------------------------------

def _extract_content(raw_text: str, extract_mode: str) -> str:
    """Convert raw scraped text into the requested format.

    ``raw_text`` is whatever ``scrape_url`` returned (already cleaned text).
    For "html" and "markdown" modes we have no raw HTML available through the
    current scraping interface, so we produce best-effort output from the text.
    """
    if extract_mode == "html":
        # Wrap the plain text in minimal HTML
        escaped = raw_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"<html><body><pre>{escaped}</pre></body></html>"

    if extract_mode == "markdown":
        return _text_to_markdown(raw_text)

    # Default: "text"
    return raw_text


def _text_to_markdown(text: str) -> str:
    """Convert plain scraped text to basic Markdown.

    Heuristics applied:
    - Short all-caps lines become ATX headings.
    - Lines that look like bullet points (start with -, *, •) are preserved.
    - URLs become Markdown links.
    - Everything else is left as paragraph text.
    """
    lines = text.split("\n")
    md_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            md_lines.append("")
            continue

        # All-caps short line → heading
        if stripped.isupper() and len(stripped) < 80 and len(stripped) > 3:
            md_lines.append(f"## {stripped.title()}")
            continue

        # Already bullet-like
        if stripped.startswith(("-", "*", "•")):
            md_lines.append(stripped)
            continue

        # Convert bare URLs to Markdown links
        converted = re.sub(
            r'(https?://[^\s<>"\')\]]+)',
            lambda m: f"[{m.group(1)}]({m.group(1)})",
            stripped,
        )
        md_lines.append(converted)

    return "\n".join(md_lines)


# ---------------------------------------------------------------------------
# Shared helpers (unchanged)
# ---------------------------------------------------------------------------

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
