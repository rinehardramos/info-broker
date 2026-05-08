"""Google Maps Places search node — fetch business info via the Places API (New)."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Google Maps Places surfaces business ratings, reviews, hours, and contact info "
    "— ideal for local business prospecting and due diligence"
)
_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = (
    "places.displayName,places.formattedAddress,places.rating,"
    "places.userRatingCount,places.types,places.googleMapsUri"
)


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'google_maps_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class GoogleMapsPlacesNode:
    node_type = "google_maps_places"
    display_name = "Google Maps Places"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Google Maps API Key",
                "description": "Leave blank to use GOOGLE_MAPS_API_KEY env var or DB setting.",
            },
            "query": {
                "type": "string",
                "title": "Text Search Query",
                "description": "E.g. 'coffee shops Manila' or 'Acme Corp Makati'",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        query = (config.get("query") or "").strip()
        if not query:
            return [{"error": "No query provided", "source": "google_maps_places", "reason": _REASON}]

        api_key = _resolve_api_key(config.get("api_key"))
        if not api_key:
            log.warning("google_maps_places: no API key configured")
            return [
                {
                    "error": "GOOGLE_MAPS_API_KEY not configured",
                    "source": "google_maps_places",
                    "reason": _REASON,
                }
            ]

        max_results = min(int(config.get("max_results", 5)), 20)
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, _search_places, query, api_key, max_results)
        return results


def _search_places(query: str, api_key: str, max_results: int) -> list[dict]:
    """POST to the Places API (New) text search endpoint and normalise results."""
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": _FIELD_MASK,
        "Content-Type": "application/json",
    }
    body = {"textQuery": query, "maxResultCount": max_results}
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(_PLACES_URL, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("google_maps_places: HTTP error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "google_maps_places", "reason": _REASON}]
    except Exception as exc:
        log.warning("google_maps_places: unexpected error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "google_maps_places", "reason": _REASON}]

    places = data.get("places") or []
    return [_map_place(p) for p in places]


def _map_place(place: dict) -> dict:
    """Normalise a Places API record to the standard output shape."""
    return {
        "name": (place.get("displayName") or {}).get("text") or "",
        "address": place.get("formattedAddress") or "",
        "rating": place.get("rating"),
        "review_count": place.get("userRatingCount"),
        "types": place.get("types") or [],
        "maps_url": place.get("googleMapsUri") or "",
        "source": "google_maps_places",
        "reason": _REASON,
    }
