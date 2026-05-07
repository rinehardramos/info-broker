"""Face search enrich node — reverse facial recognition via the PimEyes REST API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Reverse facial recognition finds other photos and linked profiles of a person "
    "across the web, surfacing identities and social presence from a single face image"
)
_PIMEYES_SEARCH_URL = "https://pimeyes.com/api/search/url"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("PIMEYES_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'pimeyes_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class FaceSearchNode:
    node_type = "face_search"
    display_name = "Face Search"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "PimEyes API Key",
                "description": "Leave blank to use PIMEYES_API_KEY env var or DB setting.",
            },
            "image_url": {
                "type": "string",
                "title": "Image URL",
                "description": "URL of the face image to search.",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        image_url = (config.get("image_url") or "").strip()
        if not image_url:
            for item in inputs:
                candidate = (
                    item.get("image_url")
                    or item.get("photo_url")
                    or item.get("avatar_url")
                    or ""
                ).strip()
                if candidate:
                    image_url = candidate
                    break

        if not image_url:
            return [{"error": "No image_url provided", "source": "face_search", "reason": _REASON}]

        api_key = _resolve_api_key(config.get("api_key"))
        if not api_key:
            log.warning("face_search: no API key configured")
            return [
                {
                    "note": "Face search requires a PimEyes or FaceCheck API key — configure PIMEYES_API_KEY",
                    "source": "face_search",
                    "reason": _REASON,
                }
            ]

        max_results = min(int(config.get("max_results", 20)), 100)
        loop = asyncio.get_running_loop()

        matches = await loop.run_in_executor(
            None, _search_pimeyes, image_url, api_key
        )
        return [
            {
                "image_url": image_url,
                "matches": matches[:max_results],
                "source": "face_search",
                "reason": _REASON,
            }
        ]


def _search_pimeyes(image_url: str, api_key: str) -> list[dict]:
    """POST to PimEyes search API with the image URL and return normalised matches."""
    payload = {"url": image_url}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(_PIMEYES_SEARCH_URL, json=payload, headers=headers)
            if response.status_code == 401:
                log.warning("face_search: PimEyes unauthorized")
                return [{"error": "PimEyes: unauthorized — check your API key", "source": "face_search"}]
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("face_search: HTTP error: %s", exc)
        return [{"error": str(exc), "source": "face_search", "reason": _REASON}]
    except Exception as exc:
        log.warning("face_search: unexpected error: %s", exc)
        return [{"error": str(exc), "source": "face_search", "reason": _REASON}]

    raw_results = data.get("results") or []
    return [
        {
            "source_url": r.get("sourceUrl") or r.get("source_url") or "",
            "thumbnail_url": r.get("thumbnailUrl") or r.get("thumbnail_url") or "",
            "confidence": r.get("score") or r.get("confidence") or 0.0,
        }
        for r in raw_results
    ]
