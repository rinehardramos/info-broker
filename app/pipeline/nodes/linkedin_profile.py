"""LinkedIn Profile Search node — search LinkedIn profiles via Apify harvestapi actor."""

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
            "job_titles": {
                "type": "string",
                "title": "Job Titles (comma-separated)",
                "description": "e.g. 'CEO, CTO, Founder, Managing Director'",
                "default": "CEO, CTO, Founder",
            },
            "locations": {
                "type": "string",
                "title": "Locations (comma-separated)",
                "description": "e.g. 'Philippines, United States'",
                "default": "Philippines",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 300,
            },
            "scraper_mode": {
                "type": "string",
                "title": "Scraper Mode",
                "enum": ["Fast", "Full", "Full + email search"],
                "default": "Full",
            },
            "recently_changed_jobs": {
                "type": "boolean",
                "title": "Recently Changed Jobs",
                "default": False,
            },
            "recently_posted": {
                "type": "boolean",
                "title": "Recently Posted on LinkedIn",
                "default": False,
            },
        },
        "required": [],
    }

    async def health_check(self) -> "HealthStatus":
        from app.pipeline.nodes.base import HealthStatus
        from app.pipeline.nodes.apify_actor import _resolve_api_key
        import httpx

        try:
            key = _resolve_api_key()
        except RuntimeError:
            return HealthStatus(
                healthy=False,
                error="Apify API key not configured",
                requires_key="APIFY_API_TOKEN",
                setup_url="https://console.apify.com/account#/integrations",
                setup_instructions="Add your Apify API token in Settings > Integrations.",
            )
        # Verify actor is accessible
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                slug = _DEFAULT_ACTOR.replace("/", "~")
                resp = await client.get(
                    f"https://api.apify.com/v2/acts/{slug}",
                    params={"token": key},
                )
                if resp.status_code == 403:
                    approval_url = resp.json().get("error", {}).get("data", {}).get("approvalUrl", "")
                    return HealthStatus(
                        healthy=False,
                        error="Actor permissions not approved.",
                        requires_key="APIFY_API_TOKEN",
                        setup_url=approval_url or f"https://console.apify.com/actors/{slug}",
                        setup_instructions="Visit the link above and approve the actor's permissions.",
                    )
                if resp.status_code != 200:
                    return HealthStatus(
                        healthy=False,
                        error=f"Apify actor check failed: HTTP {resp.status_code}",
                        requires_key="APIFY_API_TOKEN",
                        setup_url=None, setup_instructions=None,
                    )
        except Exception as exc:
            return HealthStatus(
                healthy=False, error=f"Apify connectivity error: {exc}",
                requires_key=None, setup_url=None, setup_instructions=None,
            )
        return HealthStatus(
            healthy=True, error=None, requires_key="APIFY_API_TOKEN",
            setup_url=None, setup_instructions=None,
        )

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        from app.pipeline.nodes.apify_actor import _resolve_api_key

        try:
            api_key = _resolve_api_key()
        except RuntimeError as exc:
            return [_error_item(str(exc))]

        # Parse comma-separated lists
        raw_titles = config.get("job_titles") or config.get("title_filter") or ""
        raw_locations = config.get("locations") or config.get("location") or "Philippines"
        job_titles = [t.strip() for t in raw_titles.split(",") if t.strip()]
        locations = [l.strip() for l in raw_locations.split(",") if l.strip()]
        max_results = min(int(config.get("max_results", 10)), 300)
        scraper_mode = config.get("scraper_mode", "Full")

        # Build harvestapi actor input
        actor_input = {
            "currentJobTitles": job_titles,
            "locations": locations,
            "maxItems": max_results,
            "profileScraperMode": scraper_mode,
            "recentlyChangedJobs": bool(config.get("recently_changed_jobs", False)),
            "recentlyPostedOnLinkedIn": bool(config.get("recently_posted", False)),
        }

        # Also support raw query from IS brain (backwards compat)
        query = config.get("query", "")
        if query and not job_titles:
            actor_input["currentJobTitles"] = [query]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._run_sync, api_key, actor_input
        )

    def _run_sync(self, api_key: str, actor_input: dict) -> list[dict]:
        from apify_client import ApifyClient
        from app.pipeline.nodes.apify_actor import _actor_slug

        client = ApifyClient(api_key)
        slug = _actor_slug(_DEFAULT_ACTOR)
        log.info("LinkedInProfileNode: starting %s with titles=%s locations=%s max=%s",
                 slug, actor_input.get("currentJobTitles"), actor_input.get("locations"),
                 actor_input.get("maxItems"))

        try:
            run = client.actor(slug).call(run_input=actor_input)
        except Exception as exc:
            err = str(exc)
            log.error("LinkedInProfileNode: actor failed: %s", err)
            return [_error_item(err)]

        if not run:
            return [_error_item("Apify actor returned no run result")]

        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            return [_error_item("Apify run has no dataset")]

        items = list(client.dataset(dataset_id).iterate_items())
        log.info("LinkedInProfileNode: got %d profiles", len(items))

        if not items:
            return [{"title": "No LinkedIn profiles found", "content": f"Search returned 0 results for titles={actor_input.get('currentJobTitles')}, locations={actor_input.get('locations')}", "source": "linkedin_profile", "confidence": 30}]

        return [_map_item(item) for item in items]


def _error_item(msg: str) -> dict:
    return {
        "title": f"LinkedIn error: {msg[:100]}",
        "content": msg,
        "source": "linkedin_profile",
        "confidence": 0,
        "error_flagged": True,
    }


def _map_item(item: dict) -> dict:
    """Normalise a harvestapi~linkedin-profile-search response item."""
    # Handle nested currentPosition
    current = (
        (item.get("currentPosition") or [{}])[0]
        if item.get("currentPosition")
        else {}
    )
    # Handle email from various fields
    email = item.get("email") or item.get("emailAddress") or ""
    if not email and item.get("emails"):
        emails = item["emails"]
        email = emails[0] if isinstance(emails, list) and emails else ""

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
        "email": email,
        "source": "linkedin_profile",
        "confidence": 85,
        "_raw": item,
    }
