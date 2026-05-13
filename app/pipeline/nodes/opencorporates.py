"""OpenCorporates enrich node — company registry lookups via the OpenCorporates REST API."""

from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import quote

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "OpenCorporates indexes 200+ jurisdictions including Philippine SEC — authoritative company registration data"
_BASE_URL = "https://api.opencorporates.com/v0.4"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("OPENCORPORATES_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'opencorporates_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class OpenCorporatesNode:
    node_type = "opencorporates"
    display_name = "OpenCorporates Registry"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "OpenCorporates API Key",
                "description": "Leave blank to use OPENCORPORATES_API_KEY env var or DB setting. Free tier available.",
            },
            "jurisdiction_code": {
                "type": "string",
                "title": "Jurisdiction Code",
                "default": "ph",
                "description": "ISO country code or OpenCorporates jurisdiction (e.g. 'ph', 'us_de', 'gb')",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 30,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        api_key = _resolve_api_key(config.get("api_key"))
        jurisdiction = (config.get("jurisdiction_code") or "ph").strip()
        max_results = min(int(config.get("max_results", 10)), 30)

        loop = asyncio.get_running_loop()
        results: list[dict] = []

        for item in inputs:
            query = (
                item.get("company")
                or item.get("title")
                or item.get("query")
                or item.get("name")
                or ""
            ).strip()
            if not query:
                log.debug("opencorporates: skipping item with no company/query: %s", item)
                continue

            batch = await loop.run_in_executor(
                None, _search_companies, api_key, query, jurisdiction, max_results
            )
            results.extend(batch)

        return results


def _search_companies(
    api_key: str | None,
    query: str,
    jurisdiction: str,
    max_results: int,
) -> list[dict]:
    """Synchronous OpenCorporates company search — run in executor."""
    params: dict = {
        "q": query,
        "jurisdiction_code": jurisdiction,
        "per_page": max_results,
        "format": "json",
    }
    if api_key:
        params["api_token"] = api_key

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(
                f"{_BASE_URL}/companies/search",
                params=params,
                headers={"User-Agent": "info-broker/1.0"},
            )
            if response.status_code == 401:
                log.warning("opencorporates: unauthorized — check API key")
                return [
                    {
                        "query": query,
                        "source": "opencorporates",
                        "reason": _REASON,
                        "error": "Unauthorized — invalid or missing API key",
                    }
                ]
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("opencorporates: HTTP error for %r: %s", query, exc)
        return [{"query": query, "source": "opencorporates", "reason": _REASON, "error": str(exc)}]
    except Exception as exc:
        log.warning("opencorporates: unexpected error for %r: %s", query, exc)
        return [{"query": query, "source": "opencorporates", "reason": _REASON, "error": str(exc)}]

    raw_companies = (
        data.get("results", {}).get("companies")
        or data.get("companies")
        or []
    )
    return [_map_company(c) for c in raw_companies[:max_results]]


def _map_company(raw: dict) -> dict:
    """Normalise an OpenCorporates company search result."""
    company = raw.get("company") or raw
    return {
        "name": company.get("name") or "",
        "company_number": company.get("company_number") or "",
        "jurisdiction_code": company.get("jurisdiction_code") or "",
        "incorporation_date": company.get("incorporation_date") or "",
        "dissolution_date": company.get("dissolution_date") or None,
        "company_type": company.get("company_type") or "",
        "status": company.get("current_status") or company.get("status") or "",
        "registered_address": (company.get("registered_address") or {}).get("in_full") or "",
        "opencorporates_url": company.get("opencorporates_url") or "",
        "source": "opencorporates",
        "reason": _REASON,
    }
