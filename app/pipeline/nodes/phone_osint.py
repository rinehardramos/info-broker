"""Phone OSINT enrich node — carrier, line type, region, and caller ID via NumVerify."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Phone OSINT reveals carrier, line type, and region for a number — "
    "useful for validating contact data and identifying mobile vs landline leads"
)
_NUMVERIFY_URL = "http://apilayer.net/api/validate"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("NUMVERIFY_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'numverify_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class PhoneOsintNode:
    node_type = "phone_osint"
    display_name = "Phone OSINT"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "NumVerify API Key",
                "description": "Leave blank to use NUMVERIFY_API_KEY env var or DB setting.",
            },
            "phone": {
                "type": "string",
                "title": "Phone Number",
                "description": "Phone number to look up (e.g. +14155552671).",
            },
            "country_code": {
                "type": "string",
                "title": "Default Country Code",
                "description": "Optional ISO 3166-1 alpha-2 country code for local number formatting.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        api_key = _resolve_api_key(config.get("api_key"))

        # Collect phone numbers from config and inputs
        phones: list[str] = []
        if config.get("phone"):
            phones.append(str(config["phone"]).strip())
        for item in inputs:
            phone = (item.get("phone") or "").strip()
            if phone:
                phones.append(phone)

        if not phones:
            return [{"error": "No phone number provided", "source": "numverify", "reason": _REASON}]

        if not api_key:
            log.warning("phone_osint: no API key configured — returning basic records")
            return [
                {
                    "phone": phone,
                    "source": "phone_osint",
                    "reason": "Set NUMVERIFY_API_KEY for carrier and line type enrichment",
                }
                for phone in phones
            ]

        loop = asyncio.get_running_loop()
        results: list[dict] = []
        for phone in phones:
            result = await loop.run_in_executor(None, _lookup_numverify, phone, api_key)
            results.append(result)
        return results


def _lookup_numverify(phone: str, api_key: str) -> dict:
    """GET NumVerify validate endpoint and normalise the response."""
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                _NUMVERIFY_URL,
                params={"access_key": api_key, "number": phone},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("phone_osint: HTTP error for %r: %s", phone, exc)
        return {"phone": phone, "source": "numverify", "reason": _REASON, "error": str(exc)}
    except Exception as exc:
        log.warning("phone_osint: unexpected error for %r: %s", phone, exc)
        return {"phone": phone, "source": "numverify", "reason": _REASON, "error": str(exc)}

    if data.get("error"):
        err = data["error"]
        code = err.get("code") if isinstance(err, dict) else err
        return {
            "phone": phone,
            "source": "numverify",
            "reason": _REASON,
            "error": f"NumVerify error {code}",
        }

    return {
        "phone": data.get("number") or phone,
        "valid": data.get("valid", False),
        "country": data.get("country_name") or data.get("country_code") or "",
        "country_code": data.get("country_code") or "",
        "carrier": data.get("carrier") or "",
        "line_type": data.get("line_type") or "",
        "source": "numverify",
        "reason": _REASON,
    }
