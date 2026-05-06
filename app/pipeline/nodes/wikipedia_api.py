"""Wikipedia API enrich node — fetch page summaries from the Wikipedia REST API."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "run_web_crawl failed on Wikipedia pages; a Wikipedia-specific fetch is needed"


class WikipediaApiNode:
    node_type = "wikipedia_api"
    display_name = "Wikipedia API"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "title": "Language",
                "default": "en",
                "description": "Wikipedia language subdomain (e.g. 'en', 'tl', 'es')",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        language = config.get("language", "en") or "en"
        loop = asyncio.get_running_loop()
        results: list[dict] = []

        for item in inputs:
            title = (
                item.get("title")
                or item.get("query")
                or item.get("message")
                or ""
            ).strip()
            if not title:
                log.debug("wikipedia_api: skipping item with no title/query: %s", item)
                continue

            result = await loop.run_in_executor(
                None, _fetch_summary, language, title
            )
            results.append(result)

        return results


def _fetch_summary(language: str, title: str) -> dict:
    """Synchronous Wikipedia REST API call — run in executor."""
    encoded = quote(title.replace(" ", "_"), safe="")
    url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{encoded}"

    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "info-broker/1.0"})

            if response.status_code == 404:
                log.info("wikipedia_api: 404 for title %r (lang=%s)", title, language)
                return {
                    "title": title,
                    "extract": None,
                    "url": None,
                    "thumbnail": None,
                    "source": "wikipedia",
                    "reason": _REASON,
                    "error": f"Page not found: {title!r}",
                }

            response.raise_for_status()
            data = response.json()

    except httpx.HTTPStatusError as exc:
        log.warning("wikipedia_api: HTTP error for %r: %s", title, exc)
        return {
            "title": title,
            "extract": None,
            "url": None,
            "thumbnail": None,
            "source": "wikipedia",
            "reason": _REASON,
            "error": str(exc),
        }
    except Exception as exc:
        log.warning("wikipedia_api: unexpected error for %r: %s", title, exc)
        return {
            "title": title,
            "extract": None,
            "url": None,
            "thumbnail": None,
            "source": "wikipedia",
            "reason": _REASON,
            "error": str(exc),
        }

    thumbnail = None
    thumbnail_data = data.get("thumbnail") or data.get("originalimage")
    if thumbnail_data:
        thumbnail = thumbnail_data.get("source")

    return {
        "title": data.get("title") or title,
        "extract": data.get("extract") or data.get("description"),
        "url": data.get("content_urls", {}).get("desktop", {}).get("page")
               or data.get("canonicalurl"),
        "thumbnail": thumbnail,
        "source": "wikipedia",
        "reason": _REASON,
    }
