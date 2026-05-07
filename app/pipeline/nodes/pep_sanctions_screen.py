"""PEP/Sanctions Screen enrich node — screens a person against PEP and sanctions lists.

SENTINEL tactic: low frequency, high value when a match is found.
Uses the OpenSanctions API with a DuckDuckGo web search fallback when no API key
is configured.
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "SENTINEL: PEP/sanctions screening is low-frequency but high-value — a match against "
    "OFAC, UN, EU, or national sanctions lists, or a politically exposed person flag, "
    "represents critical compliance and due-diligence risk signal"
)
_OPENSANCTIONS_URL = "https://api.opensanctions.org/match/default"
_DDG_URL = "https://html.duckduckgo.com/html/"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var OPENSANCTIONS_API_KEY, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("OPENSANCTIONS_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'opensanctions_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class PepSanctionsScreenNode:
    node_type = "pep_sanctions_screen"
    display_name = "PEP/Sanctions Screen"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "OpenSanctions API Key",
                "description": "Leave blank to use OPENSANCTIONS_API_KEY env var or DB setting.",
            },
            "name": {
                "type": "string",
                "title": "Full Name",
                "description": "Person's full name to screen. Can also be provided via pipeline inputs.",
            },
            "dob": {
                "type": "string",
                "title": "Date of Birth",
                "description": "Optional. Format: YYYY-MM-DD",
            },
            "nationality": {
                "type": "string",
                "title": "Nationality",
                "description": "Optional. ISO 3166-1 alpha-2 country code (e.g. 'PH', 'US').",
            },
        },
        "required": ["name"],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        # Resolve name from config, then from upstream inputs
        name = (config.get("name") or "").strip()
        if not name:
            for item in inputs:
                candidate = (item.get("name") or item.get("full_name") or "").strip()
                if candidate:
                    name = candidate
                    break

        if not name:
            log.warning("pep_sanctions_screen: no name provided")
            return [
                {
                    "error": "No name provided for PEP/sanctions screening",
                    "source": "opensanctions",
                    "reason": _REASON,
                }
            ]

        api_key = _resolve_api_key(config.get("api_key"))

        loop = asyncio.get_running_loop()

        if api_key:
            result = await loop.run_in_executor(
                None, _search_opensanctions, name, api_key
            )
        else:
            log.info(
                "pep_sanctions_screen: no API key — falling back to web search for %r", name
            )
            result = await loop.run_in_executor(None, _search_web_fallback, name)

        return [result]


def _search_opensanctions(name: str, api_key: str) -> dict:
    """Query the OpenSanctions /match/default endpoint for *name*.

    Returns a normalised dict with keys: name, matched, matches, source, reason.
    """
    params = {"q": name}
    headers = {"Authorization": f"ApiKey {api_key}"}

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(_OPENSANCTIONS_URL, params=params, headers=headers)
            if response.status_code == 401:
                log.warning("pep_sanctions_screen: OpenSanctions unauthorised — check API key")
                return {
                    "name": name,
                    "matched": None,
                    "matches": [],
                    "source": "opensanctions",
                    "reason": _REASON,
                    "error": "OpenSanctions: unauthorised (check API key)",
                }
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("pep_sanctions_screen: HTTP error for %r: %s", name, exc)
        return {
            "name": name,
            "matched": None,
            "matches": [],
            "source": "opensanctions",
            "reason": _REASON,
            "error": str(exc),
        }
    except Exception as exc:
        log.warning("pep_sanctions_screen: unexpected error for %r: %s", name, exc)
        return {
            "name": name,
            "matched": None,
            "matches": [],
            "source": "opensanctions",
            "reason": _REASON,
            "error": str(exc),
        }

    raw_results: list[dict] = (
        data.get("responses", {}).get("default", {}).get("results") or []
    )

    matches = [_map_match(r) for r in raw_results]

    return {
        "name": name,
        "matched": len(matches) > 0,
        "matches": matches,
        "source": "opensanctions",
        "reason": _REASON,
    }


def _map_match(result: dict) -> dict:
    """Normalise a single OpenSanctions result entry."""
    props = result.get("properties") or {}
    topics_raw = props.get("topics") or []
    # topics may be a list of lists or a flat list
    topics: list[str] = []
    for t in topics_raw:
        if isinstance(t, list):
            topics.extend(t)
        else:
            topics.append(str(t))

    return {
        "id": result.get("id") or "",
        "caption": result.get("caption") or "",
        "datasets": result.get("datasets") or [],
        "topics": topics,
        "score": result.get("score"),
        "confidence": result.get("match_score") or result.get("score"),
    }


def _search_web_fallback(name: str) -> dict:
    """Fallback when no API key is available.

    Performs a DuckDuckGo HTML search for the name combined with common
    sanctions/PEP keywords. Returns matched=None (inconclusive) to signal
    that manual review is warranted.
    """
    query = f'"{name}" (sanctions OR "politically exposed" OR OFAC OR "wanted list")'
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                _DDG_URL,
                params={"q": query},
                headers={"user-agent": "info-broker/1.0"},
            )
            response.raise_for_status()
            snippet = response.text[:4000]  # limit parse scope
    except Exception as exc:
        log.warning("pep_sanctions_screen: web fallback error for %r: %s", name, exc)
        return {
            "name": name,
            "matched": None,
            "matches": [],
            "source": "web_search",
            "reason": _REASON,
            "error": str(exc),
        }

    # Surface the raw snippet so downstream nodes can inspect it
    return {
        "name": name,
        "matched": None,  # inconclusive — web search cannot confirm or deny
        "matches": [],
        "snippet": snippet,
        "source": "web_search",
        "reason": _REASON,
        "note": (
            "No OpenSanctions API key configured. Result is inconclusive. "
            "Configure OPENSANCTIONS_API_KEY for authoritative screening."
        ),
    }
