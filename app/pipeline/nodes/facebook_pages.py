"""Facebook Pages source node — scrape company pages via Apify actor."""

from __future__ import annotations

import asyncio
import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Facebook dominates PH social media — company pages reveal executives, contact info, and business focus"
_DEFAULT_ACTOR = "apify/facebook-pages-scraper"


class FacebookPagesNode:
    node_type = "facebook_pages"
    display_name = "Facebook Pages"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "page_urls": {
                "type": "array",
                "title": "Page URLs or Search Query",
                "items": {"type": "string"},
                "description": (
                    "List of Facebook page URLs (e.g. https://www.facebook.com/CompanyName) "
                    "or a single search query string."
                ),
                "default": [],
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
        from app.pipeline.nodes.apify_actor import _resolve_api_key

        try:
            api_key = _resolve_api_key()
        except RuntimeError as exc:
            return [{"error": str(exc), "source": "facebook"}]

        page_urls: list[str] = list(config.get("page_urls") or [])
        max_results = min(int(config.get("max_results", 20)), 100)

        # Merge page URLs or queries from upstream inputs
        for item in inputs:
            url = (
                item.get("facebook_url")
                or item.get("url")
                or item.get("query")
                or ""
            ).strip()
            if url and url not in page_urls:
                page_urls.append(url)

        if not page_urls:
            log.warning("facebook_pages: no page_urls provided and no upstream input")
            return [{"error": "No page_urls configured", "source": "facebook"}]

        actor_input = {
            "startUrls": [{"url": u} if u.startswith("http") else {"searchQuery": u} for u in page_urls],
            "maxPostsPerPage": max_results,
            "resultsLimit": max_results,
        }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._run_sync, api_key, actor_input
        )

    def _run_sync(self, api_key: str, actor_input: dict) -> list[dict]:
        from apify_client import ApifyClient
        from app.pipeline.nodes.apify_actor import _actor_slug

        client = ApifyClient(api_key)
        slug = _actor_slug(_DEFAULT_ACTOR)
        log.info("FacebookPagesNode: starting actor %s", slug)

        try:
            run = client.actor(slug).call(run_input=actor_input)
        except Exception as exc:
            log.error("FacebookPagesNode: actor call failed: %s", exc)
            return [{"error": str(exc), "source": "facebook"}]

        if not run:
            return [{"error": "Apify actor returned no run result", "source": "facebook"}]

        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            return [{"error": "Apify run has no dataset", "source": "facebook"}]

        items = list(client.dataset(dataset_id).iterate_items())
        log.info("FacebookPagesNode: actor returned %d items", len(items))
        return [_map_item(item) for item in items]

    async def health_check(self) -> "HealthStatus":
        from app.pipeline.nodes.base import HealthStatus
        from app.pipeline.nodes.apify_actor import _resolve_api_key
        try:
            _resolve_api_key()
        except RuntimeError:
            return HealthStatus(
                healthy=False,
                error="Apify API key not configured",
                requires_key="APIFY_API_TOKEN",
                setup_url="/settings",
                setup_instructions="Add your Apify API token in Settings → Integrations.",
            )
        return HealthStatus(
            healthy=True,
            error=None,
            requires_key="APIFY_API_TOKEN",
            setup_url="/settings",
            setup_instructions=None,
        )


def _map_item(item: dict) -> dict:
    """Normalise an apify/facebook-pages-scraper result item."""
    return {
        "name": item.get("name") or item.get("title") or "",
        "url": item.get("url") or item.get("pageUrl") or "",
        "category": item.get("category") or item.get("categories") or "",
        "followers": item.get("followers") or item.get("followersCount") or None,
        "about": item.get("about") or item.get("description") or "",
        "email": item.get("email") or "",
        "phone": item.get("phone") or item.get("phoneNumber") or "",
        "website": item.get("website") or item.get("websiteUrl") or "",
        "source": "facebook",
        "reason": _REASON,
    }
