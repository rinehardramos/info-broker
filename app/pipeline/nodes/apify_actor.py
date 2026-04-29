from __future__ import annotations

import asyncio
import logging
import os
import time

import requests

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_POLL_INTERVAL = 10
_MAX_POLL_TIME = 600


class ApifyActorNode:
    node_type = "apify_actor"
    display_name = "Apify Actor"
    category = "source"
    config_schema = {
        "type": "object",
        "properties": {
            "actor_id": {"type": "string", "title": "Actor ID"},
            "currentJobTitles": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Job Titles",
            },
            "locations": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Locations",
            },
            "maxItems": {"type": "integer", "title": "Max Items", "default": 100},
            "scraperMode": {"type": "string", "title": "Scraper Mode", "default": "fast"},
            "autoQuerySegmentation": {"type": "boolean", "title": "Auto Query Segmentation", "default": False},
            "autoQuerySegmentationLevels": {"type": "integer", "title": "Segmentation Levels", "default": 1},
            "autoQuerySegmentationTargetCountries": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Segmentation Countries",
            },
            "recentlyChangedJobs": {"type": "boolean", "title": "Recently Changed Jobs", "default": False},
            "recentlyPostedOnLinkedin": {"type": "boolean", "title": "Recently Posted", "default": False},
        },
        "required": ["actor_id"],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        from app.routers.v3.db import fetch_one

        api_key_row = fetch_one("SELECT value FROM core_settings WHERE key = 'apify_api_key'", ())
        api_key = api_key_row["value"] if api_key_row else None
        if not api_key:
            raise RuntimeError("Apify API key not configured in core_settings")

        actor_id = config.get("actor_id", "")
        if not actor_id:
            raise RuntimeError("actor_id is required in node config")

        actor_input = {k: v for k, v in config.items() if k != "actor_id"}

        base_url = os.getenv("APIFY_BASE_URL", "https://api.apify.com/v2")
        loop = asyncio.get_running_loop()
        profiles = await loop.run_in_executor(
            None, self._run_sync, base_url, actor_id, api_key, actor_input
        )
        return profiles

    def _run_sync(self, base_url: str, actor_id: str, api_key: str, actor_input: dict) -> list[dict]:
        # Start actor run
        resp = requests.post(
            f"{base_url}/acts/{actor_id}/runs",
            params={"token": api_key},
            json=actor_input,
            timeout=30,
        )
        resp.raise_for_status()
        apify_run_id = resp.json()["data"]["id"]

        # Poll until terminal
        dataset_id = None
        deadline = time.time() + _MAX_POLL_TIME
        while time.time() < deadline:
            time.sleep(_POLL_INTERVAL)
            try:
                r = requests.get(
                    f"{base_url}/actor-runs/{apify_run_id}",
                    params={"token": api_key},
                    timeout=30,
                )
                r.raise_for_status()
                run_data = r.json()["data"]
                status = run_data.get("status")
                if status == "SUCCEEDED":
                    dataset_id = run_data.get("defaultDatasetId")
                    break
                if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    raise RuntimeError(f"Apify actor run ended with status {status}")
            except RuntimeError:
                raise
            except Exception as exc:
                log.warning("Apify poll error: %s", exc)

        if not dataset_id:
            raise RuntimeError(f"Apify actor run timed out after {_MAX_POLL_TIME}s")

        # Fetch dataset items
        r = requests.get(
            f"{base_url}/datasets/{dataset_id}/items",
            params={"token": api_key},
            timeout=120,
        )
        r.raise_for_status()
        raw = r.json()
        if not isinstance(raw, list):
            return []

        return [
            {
                "id": item.get("linkedinUrl") or item.get("id") or "",
                "first_name": item.get("firstName", ""),
                "last_name": item.get("lastName", ""),
                "headline": item.get("headline", ""),
                "about": item.get("about", ""),
                "source": "apify",
            }
            for item in raw
        ]
