"""Instagram Profile source node — scrape public business profiles via Apify actor."""

from __future__ import annotations

import asyncio
import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Instagram business profiles expose contact info, product focus, and audience size for PH SMEs"
_DEFAULT_ACTOR = "apify/instagram-scraper"


class InstagramProfileNode:
    node_type = "instagram_profile"
    display_name = "Instagram Profile"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "usernames": {
                "type": "array",
                "title": "Instagram Usernames or URLs",
                "items": {"type": "string"},
                "description": (
                    "List of Instagram usernames (e.g. 'companyname') "
                    "or full profile URLs."
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
            return [{"error": str(exc), "source": "instagram"}]

        usernames: list[str] = list(config.get("usernames") or [])
        max_results = min(int(config.get("max_results", 20)), 100)

        # Pull usernames from upstream inputs
        for item in inputs:
            handle = (
                item.get("instagram_url")
                or item.get("instagram")
                or item.get("username")
                or ""
            ).strip()
            if handle and handle not in usernames:
                usernames.append(handle)

        if not usernames:
            log.warning("instagram_profile: no usernames provided")
            return [{"error": "No usernames configured", "source": "instagram"}]

        # Normalise to URLs that the actor expects
        start_urls = []
        for u in usernames:
            if u.startswith("http"):
                start_urls.append({"url": u})
            else:
                handle = u.lstrip("@")
                start_urls.append({"url": f"https://www.instagram.com/{handle}/"})

        actor_input = {
            "directUrls": [entry["url"] for entry in start_urls],
            "resultsType": "details",
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
        log.info("InstagramProfileNode: starting actor %s", slug)

        try:
            run = client.actor(slug).call(run_input=actor_input)
        except Exception as exc:
            log.error("InstagramProfileNode: actor call failed: %s", exc)
            return [{"error": str(exc), "source": "instagram"}]

        if not run:
            return [{"error": "Apify actor returned no run result", "source": "instagram"}]

        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            return [{"error": "Apify run has no dataset", "source": "instagram"}]

        items = list(client.dataset(dataset_id).iterate_items())
        log.info("InstagramProfileNode: actor returned %d items", len(items))
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
    """Normalise an apify/instagram-scraper profile result."""
    return {
        "username": item.get("username") or item.get("ownerUsername") or "",
        "full_name": item.get("fullName") or item.get("full_name") or "",
        "bio": item.get("biography") or item.get("bio") or "",
        "followers": item.get("followersCount") or item.get("followers") or None,
        "following": item.get("followsCount") or item.get("following") or None,
        "posts_count": item.get("postsCount") or item.get("posts_count") or None,
        "is_business": item.get("isBusinessAccount") or item.get("is_business") or False,
        "business_category": item.get("businessCategoryName") or item.get("category") or "",
        "email": item.get("businessEmail") or item.get("email") or "",
        "phone": item.get("businessPhoneNumber") or item.get("phone") or "",
        "website": item.get("externalUrl") or item.get("website") or "",
        "url": item.get("url") or (
            f"https://www.instagram.com/{item['username']}/" if item.get("username") else ""
        ),
        "source": "instagram",
        "reason": _REASON,
    }
