from __future__ import annotations

import asyncio
import logging
import os

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)


def _resolve_api_key() -> str:
    """Env vars take priority over DB so .env works out of the box."""
    key = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one("SELECT value FROM core_settings WHERE key = 'apify_api_key'", ())
        if row and row["value"]:
            return row["value"]
    except Exception:
        pass
    raise RuntimeError(
        "Apify API key not found. Set APIFY_API_TOKEN in .env or configure it in Settings."
    )


def _actor_slug(actor_id: str) -> str:
    """Normalise 'owner/name' → 'owner~name' for the Apify REST path."""
    return actor_id.replace("/", "~")


class ApifyActorNode:
    node_type = "apify_actor"
    display_name = "Apify LinkedIn Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "actor_id": {
                "type": "string",
                "title": "Actor ID",
                "default": "harvestapi~linkedin-profile-search",
            },
            "searchUrl": {
                "type": "string",
                "title": "LinkedIn Search URL",
            },
            "maxResults": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 10,
            },
            "timeout": {
                "type": "integer",
                "title": "Timeout (seconds)",
                "default": 60,
                "minimum": 10,
                "maximum": 3600,
            },
        },
        "required": ["actor_id", "searchUrl"],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        api_key = _resolve_api_key()
        actor_id = config.get("actor_id", "harvestapi~linkedin-profile-search")
        actor_input = {
            "searchUrl": config.get("searchUrl", ""),
            "maxResults": min(int(config.get("maxResults", 10)), 10),
        }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._run_sync, actor_id, api_key, actor_input
        )

    def _run_sync(self, actor_id: str, api_key: str, actor_input: dict) -> list[dict]:
        from apify_client import ApifyClient

        client = ApifyClient(api_key)
        slug = _actor_slug(actor_id)
        log.info("Starting Apify actor: %s input=%s", slug, actor_input)

        run = client.actor(slug).call(run_input=actor_input)
        if not run:
            raise RuntimeError(f"Apify actor {slug} returned no run result")

        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            raise RuntimeError(f"Apify run for {slug} has no dataset")

        items = list(client.dataset(dataset_id).iterate_items())
        log.info("Apify actor %s returned %d items", slug, len(items))
        return [self._map_item(item) for item in items]

    @staticmethod
    def _map_item(item: dict) -> dict:
        """Normalise a harvestapi~linkedin-profile-search response item."""
        current = (item.get("currentPosition") or [{}])[0] if item.get("currentPosition") else {}
        return {
            "id": item.get("profileUrl") or item.get("linkedinUrl") or "",
            "first_name": item.get("firstName") or item.get("first_name", ""),
            "last_name": item.get("lastName") or item.get("last_name", ""),
            "full_name": item.get("fullName") or item.get("name", ""),
            "headline": item.get("headline", ""),
            "about": item.get("summary") or item.get("about", ""),
            "location": item.get("location", ""),
            "linkedin_url": item.get("profileUrl") or item.get("linkedinUrl", ""),
            "company": current.get("companyName") or item.get("currentCompanyName") or item.get("company", ""),
            "title": current.get("title") or item.get("currentPositionTitle") or item.get("headline", ""),
            "source": "apify",
            "_raw": item,
        }
