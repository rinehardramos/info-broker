"""Apollo/ZoomInfo Enrichment node — people and company search via Apollo.io API."""

from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Required to filter SMEs that actively need third-party IT services via tech stack and intent data"
_APOLLO_PEOPLE_URL = "https://api.apollo.io/v1/mixed_people/search"
_APOLLO_COMPANIES_URL = "https://api.apollo.io/v1/mixed_companies/search"


def _resolve_api_key() -> str | None:
    """Env var takes priority; fall back to DB setting."""
    key = os.getenv("APOLLO_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'apollo_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class ApolloZoominfoNode:
    node_type = "apollo_zoominfo"
    display_name = "Apollo/ZoomInfo Enrichment"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Apollo API Key",
                "description": "Leave blank to use APOLLO_API_KEY env var or DB setting",
            },
            "search_type": {
                "type": "string",
                "title": "Search Type",
                "enum": ["people", "companies"],
                "default": "people",
            },
            "filters": {
                "type": "string",
                "title": "Filters (JSON)",
                "description": (
                    "Apollo filter payload as a JSON object. "
                    "E.g. {\"person_titles\": [\"CTO\"], \"organization_num_employees_ranges\": [\"1,200\"]}"
                ),
                "default": "{}",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        api_key = config.get("api_key") or _resolve_api_key()
        if not api_key:
            log.warning("apollo_zoominfo: no API key configured")
            return [
                {
                    "error": "APOLLO_API_KEY not configured",
                    "source": "apollo",
                    "reason": _REASON,
                }
            ]

        search_type = config.get("search_type", "people")
        raw_filters = config.get("filters", "{}")
        try:
            filters: dict = json.loads(raw_filters) if isinstance(raw_filters, str) else raw_filters
        except json.JSONDecodeError as exc:
            log.warning("apollo_zoominfo: invalid filters JSON: %s", exc)
            filters = {}

        # Merge per-item context into filters when inputs carry relevant fields
        merged_filters = dict(filters)
        for item in inputs:
            if item.get("company") and "q_organization_name" not in merged_filters:
                merged_filters["q_organization_name"] = item["company"]
            if item.get("query") and "q_keywords" not in merged_filters:
                merged_filters["q_keywords"] = item["query"]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _call_apollo, api_key, search_type, merged_filters
        )


def _call_apollo(api_key: str, search_type: str, filters: dict) -> list[dict]:
    """Synchronous Apollo API POST — run in executor."""
    url = _APOLLO_PEOPLE_URL if search_type == "people" else _APOLLO_COMPANIES_URL
    payload = {"api_key": api_key, **filters}

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("apollo_zoominfo: HTTP error: %s", exc)
        return [{"error": str(exc), "source": "apollo", "reason": _REASON}]
    except Exception as exc:
        log.warning("apollo_zoominfo: unexpected error: %s", exc)
        return [{"error": str(exc), "source": "apollo", "reason": _REASON}]

    if search_type == "people":
        raw_items = data.get("people") or data.get("contacts") or []
        return [_map_person(p) for p in raw_items]
    else:
        raw_items = data.get("organizations") or data.get("accounts") or []
        return [_map_company(c) for c in raw_items]


def _map_person(item: dict) -> dict:
    return {
        "name": item.get("name") or f"{item.get('first_name', '')} {item.get('last_name', '')}".strip(),
        "title": item.get("title") or item.get("headline", ""),
        "company": (item.get("organization") or {}).get("name") or item.get("organization_name", ""),
        "email": item.get("email", ""),
        "linkedin_url": item.get("linkedin_url", ""),
        "phone": (item.get("phone_numbers") or [{}])[0].get("raw_number", "") if item.get("phone_numbers") else "",
        "source": "apollo",
        "reason": _REASON,
    }


def _map_company(item: dict) -> dict:
    return {
        "name": item.get("name", ""),
        "title": "",
        "company": item.get("name", ""),
        "email": item.get("contact_email", ""),
        "linkedin_url": item.get("linkedin_url", ""),
        "phone": item.get("phone", ""),
        "website": item.get("website_url", ""),
        "industry": item.get("industry", ""),
        "employees": item.get("num_employees", ""),
        "source": "apollo",
        "reason": _REASON,
    }
