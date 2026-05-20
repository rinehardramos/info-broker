"""Intelligence X node — leaked data, paste sites, and dark web search via Intelligence X API."""

from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Intelligence X indexes leaked databases, paste sites, and dark web sources"
    " — critical for finding exposed credentials, PII, and illicit mentions of a target"
)
_INTELX_SEARCH_URL = "https://2.intelx.io/intelligent/search"
_INTELX_RESULT_URL = "https://2.intelx.io/intelligent/search/result"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("INTELLIGENCE_X_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'intelligence_x_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class IntelligenceXNode:
    node_type = "intelligence_x"
    display_name = "Intelligence X Dark Web Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Intelligence X API Key",
                "description": "Leave blank to use INTELLIGENCE_X_API_KEY env var or DB setting.",
                "default": "",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "description": "Maximum number of results to return.",
                "default": 10,
            },
            "buckets": {
                "type": "string",
                "title": "Buckets (comma-separated)",
                "description": (
                    "Limit search to specific buckets: pastes, darkweb, leaks, etc. "
                    "Leave blank to search all."
                ),
                "default": "",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        api_key = _resolve_api_key(config.get("api_key"))
        if not api_key:
            log.warning("intelligence_x: no API key configured")
            return [
                {
                    "error": "INTELLIGENCE_X_API_KEY not configured",
                    "source": "intelligence_x",
                    "reason": _REASON,
                }
            ]

        max_results = int(config.get("max_results", 10))
        raw_buckets = config.get("buckets", "")
        buckets = [b.strip() for b in raw_buckets.split(",") if b.strip()] if raw_buckets else []

        # Collect queries
        queries: list[str] = []
        for item in inputs:
            q = item.get("query") or item.get("email") or item.get("name") or ""
            if q and q not in queries:
                queries.append(q)

        if not queries:
            q = config.get("query", "")
            if q:
                queries.append(q)

        if not queries:
            return [{"error": "No query provided", "source": "intelligence_x", "reason": _REASON}]

        loop = asyncio.get_running_loop()
        results: list[dict] = []
        for query in queries:
            batch = await loop.run_in_executor(
                None, _search_intelx, api_key, query, max_results, buckets
            )
            results.extend(batch)

        return results


def _search_intelx(
    api_key: str, query: str, max_results: int, buckets: list[str]
) -> list[dict]:
    """Submit search and poll for results — run in executor."""
    payload: dict = {
        "term": query,
        "maxresults": max_results,
        "media": 0,
        "sort": 4,  # newest first
        "terminate": [],
    }
    if buckets:
        payload["buckets"] = buckets

    try:
        with httpx.Client(timeout=30.0) as client:
            # Step 1: submit search
            submit_resp = client.post(
                _INTELX_SEARCH_URL,
                json=payload,
                headers={"x-key": api_key, "Content-Type": "application/json"},
            )
            submit_resp.raise_for_status()
            search_id = submit_resp.json().get("id")
            if not search_id:
                return [
                    {
                        "error": "No search ID returned",
                        "query": query,
                        "source": "intelligence_x",
                        "reason": _REASON,
                    }
                ]

            # Step 2: poll for results (simple single poll with brief wait)
            time.sleep(2)
            result_resp = client.get(
                _INTELX_RESULT_URL,
                params={"id": search_id, "limit": max_results},
                headers={"x-key": api_key},
            )
            result_resp.raise_for_status()
            data = result_resp.json()
    except httpx.HTTPStatusError as exc:
        log.warning("intelligence_x: HTTP error for %r: %s", query, exc)
        return [{"error": str(exc), "query": query, "source": "intelligence_x", "reason": _REASON}]
    except Exception as exc:
        log.warning("intelligence_x: unexpected error for %r: %s", query, exc)
        return [{"error": str(exc), "query": query, "source": "intelligence_x", "reason": _REASON}]

    records = data.get("records") or []
    return [_map_record(r, query) for r in records] or [
        {"query": query, "results": 0, "source": "intelligence_x", "reason": _REASON}
    ]


def _map_record(record: dict, query: str) -> dict:
    return {
        "query": query,
        "name": record.get("name", ""),
        "bucket": record.get("bucket", ""),
        "date": record.get("date", ""),
        "media_type": record.get("media", ""),
        "size": record.get("size", 0),
        "source": "intelligence_x",
        "reason": _REASON,
    }
