"""Hunter.io enrich node — find verified business email addresses for a domain or person."""

from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlencode

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Hunter.io surfaces verified email patterns and individual addresses — critical for B2B outreach"
_BASE_URL = "https://api.hunter.io/v2"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("HUNTER_IO_API_KEY") or os.getenv("HUNTER_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'hunter_io_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class HunterIoNode:
    node_type = "hunter_io"
    display_name = "Hunter.io Email Finder"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Hunter.io API Key",
                "description": "Leave blank to use HUNTER_IO_API_KEY env var or DB setting.",
            },
            "lookup_type": {
                "type": "string",
                "title": "Lookup Type",
                "enum": ["domain", "email_finder"],
                "default": "domain",
                "description": (
                    "domain: list all emails for a company domain; "
                    "email_finder: find a specific person's email by name + domain"
                ),
            },
            "domain": {
                "type": "string",
                "title": "Domain",
                "description": "Company domain to search (e.g. 'acme.com')",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        api_key = _resolve_api_key(config.get("api_key"))
        if not api_key:
            log.warning("hunter_io: no API key configured")
            return [
                {
                    "error": "HUNTER_IO_API_KEY not configured",
                    "source": "hunter_io",
                    "reason": _REASON,
                }
            ]

        lookup_type = config.get("lookup_type", "domain")
        domain = (config.get("domain") or "").strip()
        max_results = min(int(config.get("max_results", 10)), 100)

        loop = asyncio.get_running_loop()
        results: list[dict] = []

        if lookup_type == "domain":
            # Use configured domain, or extract from upstream input
            domains: list[str] = [domain] if domain else []
            for item in inputs:
                d = (
                    item.get("domain")
                    or item.get("website")
                    or ""
                ).strip()
                # Normalise "https://acme.com" → "acme.com"
                if d:
                    d = d.replace("https://", "").replace("http://", "").split("/")[0]
                    if d and d not in domains:
                        domains.append(d)

            for d in domains:
                batch = await loop.run_in_executor(
                    None, _domain_search, api_key, d, max_results
                )
                results.extend(batch)

        else:  # email_finder
            for item in inputs:
                first = (item.get("first_name") or "").strip()
                last = (item.get("last_name") or "").strip()
                if not first and not last:
                    full = (item.get("full_name") or item.get("name") or "").strip()
                    parts = full.split(None, 1)
                    first = parts[0] if parts else ""
                    last = parts[1] if len(parts) > 1 else ""

                item_domain = domain or (
                    item.get("domain") or item.get("website") or ""
                ).strip().replace("https://", "").replace("http://", "").split("/")[0]

                if not first or not item_domain:
                    log.debug("hunter_io: skipping item — missing name or domain: %s", item)
                    continue

                result = await loop.run_in_executor(
                    None, _email_finder, api_key, first, last, item_domain
                )
                results.append(result)

        return results


def _domain_search(api_key: str, domain: str, limit: int) -> list[dict]:
    """Domain search — list all known emails for a domain."""
    params = {"domain": domain, "api_key": api_key, "limit": limit}
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(f"{_BASE_URL}/domain-search", params=params)
            if response.status_code == 401:
                return [{"error": "Hunter.io: unauthorized", "source": "hunter_io", "reason": _REASON}]
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("hunter_io: domain search HTTP error for %r: %s", domain, exc)
        return [{"error": str(exc), "source": "hunter_io", "reason": _REASON}]
    except Exception as exc:
        log.warning("hunter_io: unexpected error for %r: %s", domain, exc)
        return [{"error": str(exc), "source": "hunter_io", "reason": _REASON}]

    payload = data.get("data") or {}
    emails = payload.get("emails") or []
    return [_map_email(e, domain) for e in emails]


def _email_finder(api_key: str, first_name: str, last_name: str, domain: str) -> dict:
    """Email Finder — find a specific person's email."""
    params = {
        "domain": domain,
        "first_name": first_name,
        "last_name": last_name,
        "api_key": api_key,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(f"{_BASE_URL}/email-finder", params=params)
            if response.status_code == 401:
                return {"error": "Hunter.io: unauthorized", "source": "hunter_io", "reason": _REASON}
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("hunter_io: email finder HTTP error: %s", exc)
        return {"error": str(exc), "source": "hunter_io", "reason": _REASON}
    except Exception as exc:
        log.warning("hunter_io: unexpected error in email finder: %s", exc)
        return {"error": str(exc), "source": "hunter_io", "reason": _REASON}

    payload = data.get("data") or {}
    return {
        "email": payload.get("email") or "",
        "score": payload.get("score") or None,
        "first_name": first_name,
        "last_name": last_name,
        "domain": domain,
        "position": payload.get("position") or "",
        "linkedin_url": payload.get("linkedin") or "",
        "source": "hunter_io",
        "reason": _REASON,
    }


def _map_email(item: dict, domain: str) -> dict:
    """Normalise a domain-search email entry."""
    return {
        "email": item.get("value") or "",
        "first_name": item.get("first_name") or "",
        "last_name": item.get("last_name") or "",
        "position": item.get("position") or "",
        "department": item.get("department") or "",
        "confidence": item.get("confidence") or None,
        "linkedin_url": item.get("linkedin") or "",
        "domain": domain,
        "source": "hunter_io",
        "reason": _REASON,
    }
