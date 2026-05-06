"""Wayback Machine enrich node — Internet Archive snapshots and availability lookup."""

from __future__ import annotations

import logging

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Wayback Machine provides historical snapshots of websites — useful for change tracking and deleted content recovery"
_CDX_URL = "http://web.archive.org/cdx/search/cdx"
_AVAILABILITY_URL = "https://archive.org/wayback/available"


class WaybackMachineNode:
    node_type = "wayback_machine"
    display_name = "Wayback Machine"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "title": "URL",
                "description": "The URL to look up in the Wayback Machine",
            },
            "mode": {
                "type": "string",
                "title": "Mode",
                "enum": ["snapshots", "diff"],
                "default": "snapshots",
                "description": "'snapshots' returns a list of archived snapshots; 'diff' returns availability check",
            },
            "limit": {
                "type": "integer",
                "title": "Limit",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
                "description": "Maximum number of snapshots to return",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        url = (config.get("url") or "").strip()
        mode = (config.get("mode") or "snapshots").strip()
        limit = min(int(config.get("limit", 10)), 50)

        # Pull URL from upstream inputs if not set in config
        urls: list[str] = [url] if url else []
        for item in inputs:
            u = (
                item.get("url")
                or item.get("website")
                or item.get("query")
                or ""
            ).strip()
            if u and u not in urls:
                urls.append(u)

        if not urls:
            log.warning("wayback_machine: no URL provided")
            return [{"error": "No URL provided", "source": "wayback_machine", "confidence": 0, "error_flagged": True}]

        results: list[dict] = []
        for target_url in urls:
            if mode == "diff":
                batch = await _check_availability(target_url)
            else:
                batch = await _fetch_snapshots(target_url, limit)
            results.extend(batch)

        return results


async def _fetch_snapshots(url: str, limit: int) -> list[dict]:
    """Fetch a list of Wayback Machine snapshots for a URL via the CDX API."""
    params = {
        "url": url,
        "output": "json",
        "limit": limit,
        "fl": "timestamp,original,statuscode,mimetype",
        "filter": "statuscode:200",
        "collapse": "timestamp:8",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                _CDX_URL,
                params=params,
                headers={"User-Agent": "info-broker/1.0"},
            )
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("wayback_machine: HTTP error for %r: %s", url, exc)
        return [{"url": url, "source": "wayback_machine", "error": str(exc), "confidence": 0, "error_flagged": True}]
    except Exception as exc:
        log.warning("wayback_machine: unexpected error for %r: %s", url, exc)
        return [{"url": url, "source": "wayback_machine", "error": str(exc), "confidence": 0, "error_flagged": True}]

    # CDX returns a list of lists; first row is headers
    if not data or len(data) < 2:
        return []

    headers = data[0]
    rows = data[1:]

    results: list[dict] = []
    for row in rows:
        row_dict = dict(zip(headers, row))
        timestamp = row_dict.get("timestamp", "")
        original = row_dict.get("original", url)
        status = row_dict.get("statuscode", "")
        mimetype = row_dict.get("mimetype", "")

        # Format: YYYYMMDDHHmmss
        date_str = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}" if len(timestamp) >= 8 else timestamp
        archive_url = f"https://web.archive.org/web/{timestamp}/{original}"

        results.append({
            "source": "wayback_machine",
            "title": f"Snapshot of {original} on {date_str}",
            "content": f"Archived snapshot | Status: {status} | Type: {mimetype} | Date: {date_str}",
            "url": archive_url,
            "snapshot_date": date_str,
            "status_code": status,
            "mime_type": mimetype,
            "original_url": original,
            "confidence": 90,
            "reason": _REASON,
        })

    return results


async def _check_availability(url: str) -> list[dict]:
    """Check if a URL is available in the Wayback Machine (closest snapshot)."""
    params = {"url": url}

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                _AVAILABILITY_URL,
                params=params,
                headers={"User-Agent": "info-broker/1.0"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("wayback_machine: HTTP error for availability check %r: %s", url, exc)
        return [{"url": url, "source": "wayback_machine", "error": str(exc), "confidence": 0, "error_flagged": True}]
    except Exception as exc:
        log.warning("wayback_machine: unexpected error for availability check %r: %s", url, exc)
        return [{"url": url, "source": "wayback_machine", "error": str(exc), "confidence": 0, "error_flagged": True}]

    archived = data.get("archived_snapshots", {})
    closest = archived.get("closest", {})

    if not closest:
        return [{
            "source": "wayback_machine",
            "title": f"No snapshot found for {url}",
            "content": "No archived snapshot available in the Wayback Machine",
            "url": url,
            "available": False,
            "confidence": 80,
            "reason": _REASON,
        }]

    snapshot_url = closest.get("url", "")
    timestamp = closest.get("timestamp", "")
    status = closest.get("status", "")
    date_str = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}" if len(timestamp) >= 8 else timestamp

    return [{
        "source": "wayback_machine",
        "title": f"Latest snapshot of {url} ({date_str})",
        "content": f"Most recent Wayback Machine snapshot | Date: {date_str} | HTTP Status: {status}",
        "url": snapshot_url,
        "available": True,
        "snapshot_date": date_str,
        "status_code": status,
        "original_url": url,
        "confidence": 90,
        "reason": _REASON,
    }]
