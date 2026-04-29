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
    display_name = "Apify Actor"
    category = "source"
    # Fields that are stored as arrays but entered as comma-separated strings.
    _ARRAY_FIELDS = {"jobTitles", "locations", "segmentationCountries"}

    config_schema = {
        "type": "object",
        "properties": {
            "actor_id": {
                "type": "string",
                "title": "Actor ID",
                "default": "harvestapi/linkedin-profile-search",
            },
            "jobTitles": {
                "type": "array",
                "title": "Job Titles",
                "items": {"type": "string"},
            },
            "locations": {
                "type": "array",
                "title": "Locations",
                "items": {"type": "string"},
            },
            "maxItems": {
                "type": "integer",
                "title": "Max Items",
                "default": 20,
                "minimum": 1,
                "maximum": 1000,
            },
            "profileScraperMode": {
                "type": "string",
                "title": "Scraper Mode",
                "enum": ["Full", "Fast"],
                "default": "Fast",
            },
            "autoQuerySegmentation": {
                "type": "boolean",
                "title": "Auto Query Segmentation",
                "default": False,
            },
            "segmentationLevels": {
                "type": "integer",
                "title": "Segmentation Levels",
                "default": 1,
                "minimum": 1,
                "maximum": 5,
            },
            "segmentationCountries": {
                "type": "array",
                "title": "Segmentation Countries",
                "items": {"type": "string"},
            },
            "recentlyChangedJobs": {
                "type": "boolean",
                "title": "Recently Changed Jobs",
                "default": False,
            },
            "recentlyPosted": {
                "type": "boolean",
                "title": "Recently Posted",
                "default": False,
            },
            "startPage": {
                "type": "integer",
                "title": "Start Page",
                "default": 1,
                "minimum": 1,
            },
            "timeout": {
                "type": "integer",
                "title": "Timeout (seconds)",
                "default": 60,
                "minimum": 10,
                "maximum": 3600,
            },
        },
        "required": ["actor_id"],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        api_key = _resolve_api_key()
        actor_id = config.get("actor_id", "harvestapi/linkedin-profile-search")
        actor_input = {}
        for k, v in config.items():
            if k == "actor_id" or v is None:
                continue
            # Coerce legacy string values for array fields (e.g. "CEO, CTO" → ["CEO", "CTO"])
            if k in self._ARRAY_FIELDS and isinstance(v, str):
                v = [s.strip() for s in v.split(",") if s.strip()]
            actor_input[k] = v

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
        """Normalise a harvestapi/linkedin-profile-search response item."""
        return {
            "id": item.get("linkedinUrl") or item.get("profileUrl") or item.get("id") or "",
            "first_name": item.get("firstName") or item.get("first_name", ""),
            "last_name": item.get("lastName") or item.get("last_name", ""),
            "full_name": item.get("fullName") or item.get("name", ""),
            "headline": item.get("headline", ""),
            "about": item.get("about") or item.get("summary", ""),
            "location": item.get("location", ""),
            "linkedin_url": item.get("linkedinUrl") or item.get("profileUrl", ""),
            "company": item.get("currentCompanyName") or item.get("company", ""),
            "title": item.get("currentPositionTitle") or item.get("headline", ""),
            "source": "apify",
            "_raw": item,
        }
