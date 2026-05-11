"""Twitter/X Search source node — search tweets and profiles via Apify actor."""

from __future__ import annotations

import asyncio
import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "X/Twitter reveals executive social presence, opinions, and professional network"
_DEFAULT_ACTOR = "quacker/twitter-scraper"


class TwitterSearchNode:
    node_type = "twitter_search"
    display_name = "Twitter/X Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Twitter search term, hashtag, or @username",
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
            return [{"error": str(exc), "source": "twitter"}]

        query = (config.get("query") or "").strip()
        max_results = min(int(config.get("max_results", 20)), 100)

        # Supplement query from upstream inputs
        if not query:
            for item in inputs:
                q = (
                    item.get("query")
                    or item.get("name")
                    or item.get("company")
                    or item.get("message")
                    or ""
                ).strip()
                if q:
                    query = q
                    break

        if not query:
            log.warning("twitter_search: no query provided")
            return [{"error": "No query configured", "source": "twitter"}]

        actor_input = {
            "searchTerms": [query],
            "maxTweets": max_results,
            "addUserInfo": True,
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
        log.info("TwitterSearchNode: starting actor %s", slug)

        try:
            run = client.actor(slug).call(run_input=actor_input)
        except Exception as exc:
            log.error("TwitterSearchNode: actor call failed: %s", exc)
            return [{"error": str(exc), "source": "twitter"}]

        if not run:
            return [{"error": "Apify actor returned no run result", "source": "twitter"}]

        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            return [{"error": "Apify run has no dataset", "source": "twitter"}]

        items = list(client.dataset(dataset_id).iterate_items())
        log.info("TwitterSearchNode: actor returned %d items", len(items))
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
    """Normalise a quacker/twitter-scraper result item."""
    author = item.get("author") or item.get("user") or {}
    return {
        "username": author.get("userName") or author.get("screen_name") or item.get("username") or "",
        "full_name": author.get("name") or item.get("full_name") or "",
        "bio": author.get("description") or item.get("bio") or "",
        "followers": author.get("followers") or author.get("followersCount") or None,
        "tweet_text": item.get("text") or item.get("full_text") or item.get("tweetText") or "",
        "url": item.get("url") or item.get("tweetUrl") or "",
        "source": "twitter",
        "reason": _REASON,
    }
