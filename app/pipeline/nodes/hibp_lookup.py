"""HIBP breach lookup enrich node — checks emails against HaveIBeenPwned."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "HaveIBeenPwned reveals whether an email address appears in known data breaches"
    " — critical for security posture and credential exposure assessment"
)
_HIBP_API_URL = "https://haveibeenpwned.com/api/v3/breachedaccount"
_DDG_URL = "https://html.duckduckgo.com/html/"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("HIBP_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'hibp_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class HibpLookupNode:
    node_type = "hibp_lookup"
    display_name = "HIBP Breach Lookup"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "HIBP API Key",
                "description": "Leave blank to use HIBP_API_KEY env var or DB setting.",
            },
            "email": {
                "type": "string",
                "title": "Email Address",
                "description": "Email to check. Can also be provided via pipeline inputs.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        api_key = _resolve_api_key(config.get("api_key"))

        # Collect emails from config and inputs
        emails: list[str] = []
        if config.get("email"):
            emails.append(config["email"].strip())
        for item in inputs:
            email = (item.get("email") or "").strip()
            if email and email not in emails:
                emails.append(email)

        if not emails:
            log.warning("hibp_lookup: no email provided")
            return [{"error": "No email provided", "source": "hibp_lookup", "reason": _REASON}]

        loop = asyncio.get_running_loop()
        results: list[dict] = []

        for email in emails:
            if api_key:
                result = await loop.run_in_executor(None, _fetch_hibp_api, email, api_key)
            else:
                result = await loop.run_in_executor(None, _fetch_hibp_web, email)
            results.append(result)

        return results


def _fetch_hibp_api(email: str, key: str) -> dict:
    """Query HIBP v3 API for breach data. 404 = not breached, 200 = breached."""
    url = f"{_HIBP_API_URL}/{email}"
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                url,
                headers={
                    "hibp-api-key": key,
                    "user-agent": "info-broker/1.0",
                },
                params={"truncateResponse": "false"},
            )
            if response.status_code == 404:
                return {
                    "email": email,
                    "breached": False,
                    "breaches": [],
                    "source": "hibp_api",
                    "reason": _REASON,
                }
            response.raise_for_status()
            raw_breaches = response.json() or []
    except httpx.HTTPStatusError as exc:
        log.warning("hibp_lookup: HTTP error for %r: %s", email, exc)
        return {"email": email, "error": str(exc), "source": "hibp_api", "reason": _REASON}
    except Exception as exc:
        log.warning("hibp_lookup: unexpected error for %r: %s", email, exc)
        return {"email": email, "error": str(exc), "source": "hibp_api", "reason": _REASON}

    breaches = [
        {
            "name": b.get("Name", ""),
            "date": b.get("BreachDate", ""),
            "data_classes": b.get("DataClasses", []),
        }
        for b in raw_breaches
    ]
    return {
        "email": email,
        "breached": True,
        "breaches": breaches,
        "source": "hibp_api",
        "reason": _REASON,
    }


def _fetch_hibp_web(email: str) -> dict:
    """Fallback: DuckDuckGo HTML search for HIBP results when no API key is available."""
    query = f'"{email}" site:haveibeenpwned.com'
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                _DDG_URL,
                params={"q": query},
                headers={"user-agent": "info-broker/1.0"},
            )
            response.raise_for_status()
            breached: bool | None = True if "haveibeenpwned.com" in response.text else None
    except Exception as exc:
        log.warning("hibp_lookup: web fallback error for %r: %s", email, exc)
        return {
            "email": email,
            "breached": None,
            "breaches": [],
            "source": "web_search",
            "reason": _REASON,
            "error": str(exc),
        }

    return {
        "email": email,
        "breached": breached,
        "breaches": [],
        "source": "web_search",
        "reason": _REASON,
    }
