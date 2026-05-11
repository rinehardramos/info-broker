"""Name origin lookup node — infers nationality probability from name using Forebears.io and Namsor."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Name origin analysis reveals likely nationality/ethnicity from naming patterns"
    " — critical for geographic widening before committing to a locale in person investigations"
)
_NAMSOR_API_URL = "https://v2.namsor.com/NamSorAPIv2/api2/json/diaspora"
_DDG_URL = "https://html.duckduckgo.com/html/"
_FOREBEARS_BASE = "https://forebears.io"


def _resolve_namsor_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("NAMSOR_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'namsor_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


def _parse_name(config: dict) -> tuple[str, str]:
    """Return (first_name, last_name) from config, falling back to full_name split."""
    first = config.get("first_name", "").strip()
    last = config.get("last_name", "").strip()
    if not first and not last:
        full = config.get("full_name", "").strip()
        if " " in full:
            parts = full.rsplit(" ", 1)
            first, last = parts[0].strip(), parts[1].strip()
        else:
            last = full
    return first, last


class NameOriginLookupNode:
    node_type = "name_origin_lookup"
    display_name = "Name Origin Lookup"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "first_name": {
                "type": "string",
                "title": "First Name",
                "description": "Given name of the person.",
            },
            "last_name": {
                "type": "string",
                "title": "Last Name",
                "description": "Surname / family name of the person.",
            },
            "full_name": {
                "type": "string",
                "title": "Full Name",
                "description": "Alternative to first/last — last space is used to split.",
            },
            "namsor_api_key": {
                "type": "string",
                "title": "Namsor API Key",
                "description": "Leave blank to use NAMSOR_API_KEY env var or DB setting.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        namsor_key = _resolve_namsor_key(config.get("namsor_api_key"))

        # Collect name(s) from config and pipeline inputs
        names: list[tuple[str, str]] = []
        first, last = _parse_name(config)
        if first or last:
            names.append((first, last))

        for item in inputs:
            # Accept first_name/last_name, full_name, or name from upstream items
            f = item.get("first_name", "").strip()
            l = item.get("last_name", "").strip()
            if not f and not l:
                full = (item.get("full_name") or item.get("name") or "").strip()
                if " " in full:
                    parts = full.rsplit(" ", 1)
                    f, l = parts[0].strip(), parts[1].strip()
                else:
                    l = full
            if (f or l) and (f, l) not in names:
                names.append((f, l))

        if not names:
            log.warning("name_origin_lookup: no name provided")
            return [{"error": "No name provided", "source": "name_origin_lookup", "reason": _REASON}]

        loop = asyncio.get_running_loop()
        results: list[dict] = []
        for first_name, last_name in names:
            if namsor_key:
                result = await loop.run_in_executor(
                    None, _fetch_namsor, first_name, last_name, namsor_key
                )
            else:
                result = await loop.run_in_executor(
                    None, _fetch_forebears_web, first_name, last_name
                )
            results.append(result)

        return results


def _fetch_namsor(first_name: str, last_name: str, api_key: str) -> dict:
    """Query Namsor v2 diaspora endpoint for origin probability distribution."""
    url = f"{_NAMSOR_API_URL}/{first_name}/{last_name}"
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                url,
                headers={
                    "X-API-KEY": api_key,
                    "Accept": "application/json",
                    "user-agent": "info-broker/1.0",
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("name_origin_lookup: Namsor HTTP error for %r %r: %s", first_name, last_name, exc)
        return {
            "first_name": first_name,
            "last_name": last_name,
            "error": str(exc),
            "source": "namsor_api",
            "reason": _REASON,
        }
    except Exception as exc:
        log.warning("name_origin_lookup: Namsor unexpected error for %r %r: %s", first_name, last_name, exc)
        return {
            "first_name": first_name,
            "last_name": last_name,
            "error": str(exc),
            "source": "namsor_api",
            "reason": _REASON,
        }

    countries: list[dict] = []
    for entry in data.get("countriesOriginTop", []) or []:
        countries.append(
            {
                "country": entry.get("countryIso2", ""),
                "probability": round(entry.get("probability", 0.0), 4),
            }
        )

    return {
        "first_name": first_name,
        "last_name": last_name,
        "likely_origin": data.get("countryIso2", ""),
        "script": data.get("script", ""),
        "romanization_artifact": data.get("romanizationArtifact", False),
        "diaspora_ambiguous": len(countries) > 3,
        "top_countries": countries,
        "source": "namsor_api",
        "reason": _REASON,
    }


def _fetch_forebears_web(first_name: str, last_name: str) -> dict:
    """Fallback: scrape Forebears.io surname page and DDG for nationality hints."""
    results: dict = {
        "first_name": first_name,
        "last_name": last_name,
        "source": "forebears_web",
        "reason": _REASON,
        "top_countries": [],
    }

    # Try Forebears surname lookup
    if last_name:
        surname_slug = last_name.lower().replace(" ", "-")
        forebears_url = f"{_FOREBEARS_BASE}/surnames/{surname_slug}"
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(
                    forebears_url,
                    headers={"user-agent": "info-broker/1.0"},
                )
                if resp.status_code == 200:
                    results["forebears_url"] = forebears_url
                    # Extract country hints from the page text (lightweight parse)
                    text = resp.text
                    # Forebears lists "Most Common in:" with country names in title tags
                    import re
                    countries_raw = re.findall(
                        r'<td[^>]*>\s*([A-Z][a-zA-Z\s]+)\s*</td>\s*<td[^>]*>\s*([\d,]+)\s*</td>',
                        text,
                    )
                    for country, count in countries_raw[:10]:
                        results["top_countries"].append(
                            {"country": country.strip(), "count": int(count.replace(",", ""))}
                        )
        except Exception as exc:
            log.debug("name_origin_lookup: Forebears fetch failed for %r: %s", last_name, exc)
            results["forebears_error"] = str(exc)

    # DDG supplemental search
    query = f'"{last_name}" surname origin nationality site:forebears.io OR site:ancestry.com'
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                _DDG_URL,
                params={"q": query},
                headers={"user-agent": "info-broker/1.0"},
            )
            resp.raise_for_status()
            results["ddg_query"] = query
            results["ddg_hit"] = "forebears.io" in resp.text or "ancestry.com" in resp.text
    except Exception as exc:
        log.debug("name_origin_lookup: DDG search failed: %s", exc)

    results["diaspora_ambiguous"] = len(results["top_countries"]) > 3

    return results
