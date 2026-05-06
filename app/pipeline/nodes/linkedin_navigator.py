"""LinkedIn Navigator (Proxycurl) enrich node — profile lookup and people search."""

from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Core capability for B2B prospecting; the existing Apify actor returned limited results for PH market"
_PROXYCURL_PROFILE_URL = "https://nubela.co/proxycurl/api/v2/linkedin"
_PROXYCURL_SEARCH_URL = "https://nubela.co/proxycurl/api/search/person"


def _resolve_api_key(config_key: str | None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("PROXYCURL_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'proxycurl_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class LinkedinNavigatorNode:
    node_type = "linkedin_navigator"
    display_name = "LinkedIn Navigator (Proxycurl)"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Proxycurl API Key",
                "description": "Leave blank to use PROXYCURL_API_KEY env var or DB setting",
            },
            "lookup_type": {
                "type": "string",
                "title": "Lookup Type",
                "enum": ["profile", "search"],
                "default": "profile",
                "description": (
                    "profile: fetch a single LinkedIn profile by URL; "
                    "search: search for people using filters"
                ),
            },
            "search_filters": {
                "type": "string",
                "title": "Search Filters (JSON)",
                "description": (
                    "Proxycurl search filters as JSON. "
                    "E.g. {\"country\": \"PH\", \"current_role_title\": \"CTO\"}"
                ),
                "default": "{}",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        api_key = _resolve_api_key(config.get("api_key"))
        if not api_key:
            log.warning("linkedin_navigator: no API key configured")
            return [
                {
                    "error": "PROXYCURL_API_KEY not configured",
                    "source": "proxycurl",
                    "reason": _REASON,
                }
            ]

        lookup_type = config.get("lookup_type", "profile")
        raw_filters = config.get("search_filters", "{}")
        try:
            search_filters: dict = (
                json.loads(raw_filters) if isinstance(raw_filters, str) else raw_filters
            )
        except json.JSONDecodeError as exc:
            log.warning("linkedin_navigator: invalid search_filters JSON: %s", exc)
            search_filters = {}

        loop = asyncio.get_running_loop()
        results: list[dict] = []

        if lookup_type == "profile":
            for item in inputs:
                linkedin_url = (
                    item.get("linkedin_url")
                    or item.get("url")
                    or item.get("profileUrl")
                    or ""
                ).strip()
                if not linkedin_url or "linkedin.com" not in linkedin_url:
                    log.debug(
                        "linkedin_navigator: skipping item with no LinkedIn URL: %s", item
                    )
                    continue
                result = await loop.run_in_executor(
                    None, _fetch_profile, api_key, linkedin_url
                )
                results.append(result)

        else:  # search
            # Merge per-item fields into filters when sensible
            merged = dict(search_filters)
            for item in inputs:
                if item.get("query") and "keyword" not in merged:
                    merged["keyword"] = item["query"]
                if item.get("company") and "current_company_name" not in merged:
                    merged["current_company_name"] = item["company"]

            result_list = await loop.run_in_executor(
                None, _search_people, api_key, merged
            )
            results.extend(result_list)

        return results


def _fetch_profile(api_key: str, linkedin_url: str) -> dict:
    """Fetch a single LinkedIn profile via Proxycurl."""
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                _PROXYCURL_PROFILE_URL,
                params={"url": linkedin_url},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code == 404:
                return {
                    "linkedin_url": linkedin_url,
                    "source": "proxycurl",
                    "reason": _REASON,
                    "error": "Profile not found",
                }
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("linkedin_navigator: HTTP error fetching profile %r: %s", linkedin_url, exc)
        return {
            "linkedin_url": linkedin_url,
            "source": "proxycurl",
            "reason": _REASON,
            "error": str(exc),
        }
    except Exception as exc:
        log.warning("linkedin_navigator: unexpected error for profile %r: %s", linkedin_url, exc)
        return {
            "linkedin_url": linkedin_url,
            "source": "proxycurl",
            "reason": _REASON,
            "error": str(exc),
        }

    return _map_profile(data, linkedin_url)


def _search_people(api_key: str, filters: dict) -> list[dict]:
    """Search for people via Proxycurl search endpoint."""
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                _PROXYCURL_SEARCH_URL,
                json=filters,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("linkedin_navigator: HTTP error during search: %s", exc)
        return [{"error": str(exc), "source": "proxycurl", "reason": _REASON}]
    except Exception as exc:
        log.warning("linkedin_navigator: unexpected error during search: %s", exc)
        return [{"error": str(exc), "source": "proxycurl", "reason": _REASON}]

    results = data.get("results") or []
    return [_map_search_result(r) for r in results]


def _map_profile(data: dict, linkedin_url: str) -> dict:
    """Normalise a Proxycurl profile response."""
    experiences = data.get("experiences") or []
    current_exp = next(
        (e for e in experiences if e.get("ends_at") is None), experiences[0] if experiences else {}
    )
    return {
        "name": (
            f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
            or data.get("full_name", "")
        ),
        "title": current_exp.get("title") or data.get("occupation", ""),
        "company": current_exp.get("company") or data.get("company", ""),
        "location": data.get("city") or data.get("location", ""),
        "summary": data.get("summary") or data.get("headline", ""),
        "linkedin_url": data.get("public_identifier")
            and f"https://www.linkedin.com/in/{data['public_identifier']}"
            or linkedin_url,
        "source": "proxycurl",
        "reason": _REASON,
    }


def _map_search_result(item: dict) -> dict:
    """Normalise a Proxycurl search result item."""
    profile = item.get("profile") or item
    linkedin_url = (
        profile.get("linkedin_profile_url")
        or item.get("linkedin_profile_url")
        or (
            profile.get("public_identifier")
            and f"https://www.linkedin.com/in/{profile['public_identifier']}"
        )
        or ""
    )
    return {
        "name": (
            f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
            or profile.get("full_name", "")
        ),
        "title": profile.get("occupation") or profile.get("title", ""),
        "company": profile.get("company", ""),
        "location": profile.get("city") or profile.get("location", ""),
        "summary": profile.get("summary") or profile.get("headline", ""),
        "linkedin_url": linkedin_url,
        "source": "proxycurl",
        "reason": _REASON,
    }
