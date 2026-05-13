"""Headless JS Crawler node — JavaScript-rendering page crawler via Apify web-scraper actor."""

from __future__ import annotations

import asyncio
import logging
import os

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Many modern sites (SPAs, dynamic dashboards) require JavaScript rendering — "
    "httpx-based web_crawl returns empty pages"
)
_APIFY_ACTOR = "apify/web-scraper"


def _resolve_api_key() -> str | None:
    """Reuse the same key-resolution pattern as apify_actor.py."""
    key = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one("SELECT value FROM core_settings WHERE key = 'apify_api_key'", ())
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class HeadlessCrawlerNode:
    node_type = "headless_crawler"
    display_name = "Headless JS Crawler"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "urls": {
                "title": "URLs",
                "description": "One or more URLs to crawl. Accepts a list or a single URL string.",
                "oneOf": [
                    {"type": "array", "items": {"type": "string"}},
                    {"type": "string"},
                ],
            },
            "max_pages": {
                "type": "integer",
                "title": "Max Pages",
                "default": 5,
                "minimum": 1,
                "maximum": 50,
            },
            "wait_for": {
                "type": "string",
                "title": "Wait For (CSS selector)",
                "description": "Optional CSS selector to wait for before extracting content.",
            },
        },
        "required": [],
    }

    async def health_check(self) -> "HealthStatus":
        from app.pipeline.nodes.base import HealthStatus

        _SETUP = (
            "1. Sign up at apify.com\n"
            "2. Go to Account > Integrations\n"
            "3. Copy your API token\n"
            "4. Paste in Settings > API Keys > Apify"
        )
        key = _resolve_api_key()
        if not key:
            return HealthStatus(
                healthy=False,
                error="Apify API key not configured",
                requires_key="APIFY_API_TOKEN",
                setup_url="https://console.apify.com/account/integrations",
                setup_instructions=_SETUP,
            )
        # Lightweight ping — verify the key works
        try:
            import httpx
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    "https://api.apify.com/v2/users/me",
                    headers={"Authorization": f"Bearer {key}"},
                )
                if resp.status_code == 200:
                    return HealthStatus(healthy=True, error=None, requires_key=None, setup_url=None, setup_instructions=None)
                return HealthStatus(
                    healthy=False,
                    error=f"Apify returned HTTP {resp.status_code}",
                    requires_key="APIFY_API_TOKEN",
                    setup_url="https://console.apify.com/account/integrations",
                    setup_instructions=_SETUP,
                )
        except Exception as exc:
            return HealthStatus(
                healthy=False,
                error=str(exc),
                requires_key="APIFY_API_TOKEN",
                setup_url="https://console.apify.com/account/integrations",
                setup_instructions=_SETUP,
            )

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        api_key = _resolve_api_key()
        if not api_key:
            log.warning("headless_crawler: Apify API key not configured")
            return [{"error": "Apify API key not configured", "source": "headless_crawler"}]

        # Accept urls from config, or fall back to input items
        raw_urls = config.get("urls") or []
        if isinstance(raw_urls, str):
            raw_urls = [u.strip() for u in raw_urls.split(",") if u.strip()]

        # Also collect any URLs from pipeline inputs
        for item in inputs:
            url = item.get("url") or item.get("link") or ""
            if url and url not in raw_urls:
                raw_urls.append(url)

        if not raw_urls:
            return [{"error": "No URLs provided", "source": "headless_crawler"}]

        max_pages = int(config.get("max_pages", 5))
        wait_for = config.get("wait_for", "") or ""

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _run_actor, api_key, raw_urls, max_pages, wait_for
        )


def _run_actor(
    api_key: str,
    urls: list[str],
    max_pages: int,
    wait_for: str,
) -> list[dict]:
    """Run the Apify web-scraper actor synchronously and return normalised results."""
    try:
        from apify_client import ApifyClient
    except ImportError:
        log.error("headless_crawler: apify_client package not installed")
        return [{"error": "apify_client not installed", "source": "headless_crawler"}]

    start_urls = [{"url": u} for u in urls]

    # pageFunction extracts title + visible text from the rendered DOM
    page_function = """
async function pageFunction(context) {
    const { page, request } = context;
    const title = await page.title();
    const content = await page.evaluate(() => document.body ? document.body.innerText : '');
    return { url: request.url, title, content };
}
"""
    actor_input: dict = {
        "startUrls": start_urls,
        "pageFunction": page_function,
        "maxPagesPerCrawl": max_pages,
        "waitForSelector": wait_for or "",
    }

    actor_slug = _APIFY_ACTOR.replace("/", "~")
    log.info("headless_crawler: starting Apify actor %s for %d URL(s)", actor_slug, len(urls))

    try:
        client = ApifyClient(api_key)
        run = client.actor(actor_slug).call(run_input=actor_input, timeout_secs=300)
    except Exception as exc:
        log.warning("headless_crawler: Apify actor call failed: %s", exc)
        return [{"error": str(exc), "source": "headless_crawler"}]

    if not run:
        return [{"error": "Apify actor returned no run result", "source": "headless_crawler"}]

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        return [{"error": "Apify run has no dataset", "source": "headless_crawler"}]

    try:
        items = list(client.dataset(dataset_id).iterate_items())
    except Exception as exc:
        log.warning("headless_crawler: failed to read dataset: %s", exc)
        return [{"error": str(exc), "source": "headless_crawler"}]

    log.info("headless_crawler: actor returned %d item(s)", len(items))
    return [_map_item(item) for item in items]


def _map_item(item: dict) -> dict:
    return {
        "url": item.get("url", ""),
        "title": item.get("title", ""),
        "content": (item.get("content") or "")[:6000],
        "source": "headless_crawler",
    }
