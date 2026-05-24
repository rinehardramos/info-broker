"""WHOIS Lookup enrich node — domain registration and ownership data."""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "WHOIS data reveals domain registration dates, registrar, and registrant contact info for due diligence"
_WHOIS_JSON_URL = "https://www.whoisxmlapi.com/whoisserver/WhoisService"
_WHOIS_FREE_URL = "https://api.whois.vu/"


def _resolve_api_key(
    config_key: str | None = None,
    context: "RunContext | None" = None,
) -> str | None:
    """Return WHOISXML API key if configured; None falls back to free endpoint.

    Resolution order: user-scoped vault → org-scoped vault → global vault →
    core_settings → WHOISXML_API_KEY env var.  The resolved value is never logged.
    """
    if config_key:
        return config_key
    from app.lib.api_keys import resolve_api_key
    user_id = getattr(context, "user_id", None)
    org_id = getattr(context, "org_id", None)
    return resolve_api_key("whoisxml_api_key", user_id=user_id, org_id=org_id)


class WhoisLookupNode:
    node_type = "whois_lookup"
    display_name = "WHOIS Lookup"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "WhoisXML API Key (optional)",
                "description": (
                    "Leave blank to use WHOISXML_API_KEY env var or DB setting. "
                    "A free public endpoint is used as fallback."
                ),
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        api_key = _resolve_api_key(config.get("api_key"), context)
        loop = asyncio.get_running_loop()
        results: list[dict] = []

        for item in inputs:
            domain = _extract_domain(item)
            if not domain:
                log.debug("whois_lookup: skipping item with no domain: %s", item)
                continue

            result = await loop.run_in_executor(
                None, _fetch_whois, api_key, domain
            )
            results.append(result)

        return results


def _extract_domain(item: dict) -> str:
    """Pull the best domain value from an input item."""
    raw = (
        item.get("domain")
        or item.get("website")
        or item.get("url")
        or ""
    ).strip()
    if not raw:
        return ""
    # Strip protocol and path
    if "://" in raw:
        parsed = urlparse(raw)
        raw = parsed.netloc or parsed.path
    # Drop www prefix and trailing slashes
    raw = re.sub(r"^www\.", "", raw).split("/")[0].lower()
    return raw


def _fetch_whois(api_key: str | None, domain: str) -> dict:
    """Fetch WHOIS data — uses WhoisXML API if key present, else free endpoint."""
    if api_key:
        return _fetch_whoisxml(api_key, domain)
    return _fetch_whois_free(domain)


def _fetch_whoisxml(api_key: str, domain: str) -> dict:
    """WhoisXML API lookup."""
    params = {
        "apiKey": api_key,
        "domainName": domain,
        "outputFormat": "JSON",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(_WHOIS_JSON_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("whois_lookup: WhoisXML HTTP error for %r: %s", domain, exc)
        return {"domain": domain, "source": "whois", "reason": _REASON, "error": str(exc)}
    except Exception as exc:
        log.warning("whois_lookup: unexpected error for %r: %s", domain, exc)
        return {"domain": domain, "source": "whois", "reason": _REASON, "error": str(exc)}

    record = data.get("WhoisRecord") or data
    registrant = record.get("registrant") or {}
    return _map_whois(domain, record, registrant)


def _fetch_whois_free(domain: str) -> dict:
    """Free whois.vu JSON fallback."""
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                _WHOIS_FREE_URL,
                params={"q": domain},
                headers={"User-Agent": "info-broker/1.0"},
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        log.warning("whois_lookup: free endpoint error for %r: %s", domain, exc)
        return {"domain": domain, "source": "whois", "reason": _REASON, "error": str(exc)}

    return {
        "domain": domain,
        "registrar": data.get("registrar") or "",
        "creation_date": data.get("created") or data.get("creation_date") or "",
        "expiration_date": data.get("expires") or data.get("expiration_date") or "",
        "registrant_name": data.get("name") or "",
        "registrant_org": data.get("org") or "",
        "registrant_country": data.get("country") or "",
        "name_servers": data.get("nameservers") or [],
        "source": "whois",
        "reason": _REASON,
    }


def _map_whois(domain: str, record: dict, registrant: dict) -> dict:
    """Normalise a WhoisXML record."""
    name_servers_raw = record.get("nameServers") or {}
    name_servers = (
        name_servers_raw.get("hostNames")
        or name_servers_raw.get("nameServer")
        or []
    )
    if isinstance(name_servers, str):
        name_servers = [name_servers]

    return {
        "domain": domain,
        "registrar": (record.get("registrarName") or ""),
        "creation_date": record.get("createdDate") or "",
        "expiration_date": record.get("expiresDate") or "",
        "updated_date": record.get("updatedDate") or "",
        "registrant_name": registrant.get("name") or "",
        "registrant_org": registrant.get("organization") or "",
        "registrant_email": registrant.get("email") or "",
        "registrant_country": registrant.get("country") or "",
        "registrant_phone": registrant.get("phone") or "",
        "name_servers": name_servers,
        "status": record.get("status") or "",
        "source": "whois",
        "reason": _REASON,
    }
