"""Clearbit Enrichment node — company/person enrichment via Clearbit API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Clearbit provides firmographic and demographic enrichment from email and domain lookups"
    " — useful for qualifying prospects and resolving company identity"
)
_CLEARBIT_PERSON_URL = "https://person.clearbit.com/v2/people/find"
_CLEARBIT_COMPANY_URL = "https://company.clearbit.com/v2/companies/find"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("CLEARBIT_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'clearbit_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class ClearbitEnrichNode:
    node_type = "clearbit_enrich"
    display_name = "Clearbit Enrichment"
    category = "datastore"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Clearbit API Key",
                "description": "Leave blank to use CLEARBIT_API_KEY env var or DB setting.",
                "default": "",
            },
            "lookup_type": {
                "type": "string",
                "title": "Lookup Type",
                "enum": ["email", "domain", "company_name"],
                "default": "email",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        api_key = _resolve_api_key(config.get("api_key"))
        if not api_key:
            log.warning("clearbit_enrich: no API key configured")
            return [
                {
                    "error": "CLEARBIT_API_KEY not configured",
                    "source": "clearbit",
                    "reason": _REASON,
                }
            ]

        lookup_type = config.get("lookup_type", "email")

        # Collect query params from inputs
        params_list: list[dict] = []
        for item in inputs:
            p = _build_params(item, lookup_type)
            if p:
                params_list.append(p)

        # Fallback: use query from config or first input
        if not params_list:
            query_str = config.get("query", "")
            if not query_str and inputs:
                query_str = inputs[0].get("query", "")
            if query_str:
                p = _build_params({"query": query_str}, lookup_type)
                if p:
                    params_list.append(p)

        if not params_list:
            return [{"error": "No query provided", "source": "clearbit", "reason": _REASON}]

        loop = asyncio.get_running_loop()
        results: list[dict] = []
        for params in params_list:
            is_company = lookup_type in ("domain", "company_name")
            result = await loop.run_in_executor(
                None, _call_clearbit, api_key, params, is_company
            )
            results.append(result)

        return results


def _build_params(item: dict, lookup_type: str) -> dict | None:
    """Build Clearbit query params from an input item."""
    query = item.get("query", "")
    if lookup_type == "email":
        email = item.get("email") or query
        if email:
            return {"email": email}
    elif lookup_type == "domain":
        domain = item.get("domain") or item.get("website") or query
        if domain:
            return {"domain": domain}
    elif lookup_type == "company_name":
        name = item.get("company") or item.get("name") or query
        if name:
            return {"name": name}
    return None


def _call_clearbit(api_key: str, params: dict, is_company: bool) -> dict:
    """Synchronous Clearbit API GET — run in executor."""
    url = _CLEARBIT_COMPANY_URL if is_company else _CLEARBIT_PERSON_URL
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                url,
                params=params,
                auth=(api_key, ""),
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("clearbit_enrich: HTTP error: %s", exc)
        return {"error": str(exc), "source": "clearbit", "reason": _REASON}
    except Exception as exc:
        log.warning("clearbit_enrich: unexpected error: %s", exc)
        return {"error": str(exc), "source": "clearbit", "reason": _REASON}

    if is_company:
        return _map_company(data)
    return _map_person(data)


def _map_person(data: dict) -> dict:
    company_obj = data.get("employment") or {}
    return {
        "name": data.get("name", {}).get("fullName", "") if isinstance(data.get("name"), dict) else data.get("name", ""),
        "email": data.get("email", ""),
        "title": company_obj.get("title", ""),
        "company": company_obj.get("name", ""),
        "linkedin_url": (data.get("linkedin") or {}).get("handle", ""),
        "twitter_url": (data.get("twitter") or {}).get("handle", ""),
        "location": data.get("location", ""),
        "bio": data.get("bio", ""),
        "source": "clearbit",
        "reason": _REASON,
    }


def _map_company(data: dict) -> dict:
    return {
        "name": data.get("name", ""),
        "domain": data.get("domain", ""),
        "industry": data.get("category", {}).get("industry", "") if isinstance(data.get("category"), dict) else "",
        "employees": data.get("metrics", {}).get("employees", "") if isinstance(data.get("metrics"), dict) else "",
        "founded": data.get("foundedYear", ""),
        "description": data.get("description", ""),
        "linkedin_url": (data.get("linkedin") or {}).get("handle", ""),
        "twitter_url": (data.get("twitter") or {}).get("handle", ""),
        "location": data.get("location", ""),
        "source": "clearbit",
        "reason": _REASON,
    }
