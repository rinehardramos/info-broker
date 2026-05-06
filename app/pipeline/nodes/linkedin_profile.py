"""LinkedIn Profile Search node — dedicated LinkedIn profile search via Apify."""

from __future__ import annotations

import asyncio
import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_DEFAULT_ACTOR = "harvestapi~linkedin-profile-search"


class LinkedInProfileNode:
    node_type = "linkedin_profile"
    display_name = "LinkedIn Profile Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "search_url": {
                "type": "string",
                "title": "LinkedIn Search URL",
                "description": (
                    "Full LinkedIn people-search URL. "
                    "If omitted, one is built from location + title_filter."
                ),
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
            "location": {
                "type": "string",
                "title": "Location",
                "default": "Philippines",
            },
            "title_filter": {
                "type": "string",
                "title": "Job Title Filter",
                "description": "e.g. 'CEO', 'CTO', 'Owner'",
            },
        },
        "required": [],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        from app.pipeline.nodes.apify_actor import _resolve_api_key

        try:
            api_key = _resolve_api_key()
        except RuntimeError as exc:
            return [{"error": str(exc), "source": "linkedin_profile"}]
        max_results = min(int(config.get("max_results", 10)), 50)

        search_url = config.get("search_url", "").strip()
        if not search_url:
            search_url = _build_linkedin_search_url(
                location=config.get("location", "Philippines"),
                title_filter=config.get("title_filter", ""),
            )

        actor_input = {
            "searchUrl": search_url,
            "maxResults": max_results,
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
        log.info("LinkedInProfileNode: starting actor %s input=%s", slug, actor_input)

        try:
            run = client.actor(slug).call(run_input=actor_input)
        except Exception as exc:
            log.error("LinkedInProfileNode: actor call failed: %s", exc)
            return [{"error": str(exc), "source": "linkedin_profile"}]

        if not run:
            return [{"error": "Apify actor returned no run result", "source": "linkedin_profile"}]

        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            return [{"error": "Apify run has no dataset", "source": "linkedin_profile"}]

        items = list(client.dataset(dataset_id).iterate_items())
        log.info("LinkedInProfileNode: actor returned %d items", len(items))
        return [_map_item(item) for item in items]


def _build_linkedin_search_url(location: str, title_filter: str) -> str:
    """Construct a LinkedIn people-search URL from human-readable filters."""
    from urllib.parse import urlencode

    params: dict[str, str] = {
        "keywords": title_filter or "",
        "origin": "GLOBAL_SEARCH_HEADER",
        "geoUrn": "",  # LinkedIn geo URNs require a separate lookup; leave as keyword
    }
    if location:
        params["keywords"] = f"{title_filter} {location}".strip() if title_filter else location

    # Build a basic LinkedIn search URL — the Apify actor accepts the full URL
    base = "https://www.linkedin.com/search/results/people/?"
    return base + urlencode({k: v for k, v in params.items() if v})


def _map_item(item: dict) -> dict:
    """Normalise a harvestapi~linkedin-profile-search response item."""
    current = (
        (item.get("currentPosition") or [{}])[0]
        if item.get("currentPosition")
        else {}
    )
    return {
        "id": item.get("profileUrl") or item.get("linkedinUrl") or "",
        "full_name": item.get("fullName") or item.get("name", ""),
        "first_name": item.get("firstName") or item.get("first_name", ""),
        "last_name": item.get("lastName") or item.get("last_name", ""),
        "title": current.get("title") or item.get("currentPositionTitle") or item.get("headline", ""),
        "company": current.get("companyName") or item.get("currentCompanyName") or item.get("company", ""),
        "linkedin_url": item.get("profileUrl") or item.get("linkedinUrl", ""),
        "headline": item.get("headline", ""),
        "location": item.get("location", ""),
        "source": "linkedin_profile",
        "_raw": item,
    }
