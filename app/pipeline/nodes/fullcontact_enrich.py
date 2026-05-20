"""FullContact Identity Resolution node — person/company enrichment via FullContact Enrich API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "FullContact resolves partial identifiers (email, phone, domain) into unified person"
    " or company profiles — essential for identity resolution and contact enrichment"
)
_FULLCONTACT_PERSON_URL = "https://api.fullcontact.com/v3/person.enrich"
_FULLCONTACT_COMPANY_URL = "https://api.fullcontact.com/v3/company.enrich"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("FULLCONTACT_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'fullcontact_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class FullContactEnrichNode:
    node_type = "fullcontact_enrich"
    display_name = "FullContact Identity Resolution"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "FullContact API Key",
                "description": "Leave blank to use FULLCONTACT_API_KEY env var or DB setting.",
                "default": "",
            },
            "lookup_type": {
                "type": "string",
                "title": "Lookup Type",
                "enum": ["email", "phone", "name+location", "domain"],
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
            log.warning("fullcontact_enrich: no API key configured")
            return [
                {
                    "error": "FULLCONTACT_API_KEY not configured",
                    "source": "fullcontact",
                    "reason": _REASON,
                }
            ]

        lookup_type = config.get("lookup_type", "email")

        # Collect queries from inputs and config
        queries: list[dict] = []
        for item in inputs:
            payload = _build_payload(item, lookup_type)
            if payload:
                queries.append(payload)

        # Fallback: use query field from config or first input
        if not queries:
            query_str = config.get("query", "")
            if not query_str and inputs:
                query_str = inputs[0].get("query", "")
            if query_str:
                payload = _build_payload({"query": query_str}, lookup_type)
                if payload:
                    queries.append(payload)

        if not queries:
            return [{"error": "No query provided", "source": "fullcontact", "reason": _REASON}]

        loop = asyncio.get_running_loop()
        results: list[dict] = []
        for payload in queries:
            is_company = lookup_type == "domain"
            result = await loop.run_in_executor(
                None, _call_fullcontact, api_key, payload, is_company
            )
            results.append(result)

        return results


def _build_payload(item: dict, lookup_type: str) -> dict | None:
    """Build a FullContact query payload from an input item."""
    query = item.get("query", "")
    if lookup_type == "email":
        email = item.get("email") or query
        if email:
            return {"email": email}
    elif lookup_type == "phone":
        phone = item.get("phone") or query
        if phone:
            return {"phone": phone}
    elif lookup_type == "name+location":
        name = item.get("name") or query
        location = item.get("location", "")
        if name:
            payload: dict = {"fullName": name}
            if location:
                payload["location"] = location
            return payload
    elif lookup_type == "domain":
        domain = item.get("domain") or item.get("website") or query
        if domain:
            return {"domain": domain}
    return None


def _call_fullcontact(api_key: str, payload: dict, is_company: bool) -> dict:
    """Synchronous FullContact API POST — run in executor."""
    url = _FULLCONTACT_COMPANY_URL if is_company else _FULLCONTACT_PERSON_URL
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("fullcontact_enrich: HTTP error: %s", exc)
        return {"error": str(exc), "source": "fullcontact", "reason": _REASON}
    except Exception as exc:
        log.warning("fullcontact_enrich: unexpected error: %s", exc)
        return {"error": str(exc), "source": "fullcontact", "reason": _REASON}

    if is_company:
        return _map_company(data)
    return _map_person(data)


def _map_person(data: dict) -> dict:
    name_obj = data.get("fullName") or ""
    details = data.get("details") or {}
    phones = details.get("phones") or []
    emails = details.get("emails") or []
    profiles = details.get("profiles") or {}
    return {
        "name": name_obj,
        "email": emails[0].get("value", "") if emails else "",
        "phone": phones[0].get("value", "") if phones else "",
        "linkedin_url": (profiles.get("linkedin") or {}).get("url", ""),
        "twitter_url": (profiles.get("twitter") or {}).get("url", ""),
        "age_range": data.get("ageRange", ""),
        "gender": data.get("gender", ""),
        "location": data.get("location", ""),
        "source": "fullcontact",
        "reason": _REASON,
    }


def _map_company(data: dict) -> dict:
    return {
        "name": data.get("name", ""),
        "domain": data.get("website", ""),
        "industry": data.get("category", ""),
        "employees": data.get("employees", ""),
        "founded": data.get("founded", ""),
        "description": data.get("bio", ""),
        "linkedin_url": (data.get("details") or {}).get("linkedin", ""),
        "source": "fullcontact",
        "reason": _REASON,
    }
