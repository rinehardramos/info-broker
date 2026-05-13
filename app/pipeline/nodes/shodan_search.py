"""Shodan search enrich node — network/IP reconnaissance via the Shodan REST API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Shodan reveals exposed services, open ports, and CVEs for a target IP or domain — key for security-aware IT prospecting"
_SHODAN_HOST_URL = "https://api.shodan.io/shodan/host"
_SHODAN_SEARCH_URL = "https://api.shodan.io/shodan/host/search"
_SHODAN_DNS_URL = "https://api.shodan.io/dns/resolve"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("SHODAN_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'shodan_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class ShodanSearchNode:
    node_type = "shodan_search"
    display_name = "Shodan Network Scan"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Shodan API Key",
                "description": "Leave blank to use SHODAN_API_KEY env var or DB setting.",
            },
            "lookup_type": {
                "type": "string",
                "title": "Lookup Type",
                "enum": ["host", "search"],
                "default": "host",
                "description": (
                    "host: fetch details for a specific IP address or hostname; "
                    "search: run a Shodan search query"
                ),
            },
            "query": {
                "type": "string",
                "title": "Shodan Query",
                "description": "Used only for 'search' type. E.g. 'org:Acme Corp country:PH'",
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
            log.warning("shodan_search: no API key configured")
            return [
                {
                    "error": "SHODAN_API_KEY not configured",
                    "source": "shodan",
                    "reason": _REASON,
                }
            ]

        lookup_type = config.get("lookup_type", "host")
        query = (config.get("query") or "").strip()
        max_results = min(int(config.get("max_results", 10)), 100)

        loop = asyncio.get_running_loop()
        results: list[dict] = []

        if lookup_type == "host":
            for item in inputs:
                target = (
                    item.get("ip")
                    or item.get("domain")
                    or item.get("website")
                    or item.get("host")
                    or ""
                ).strip()
                if not target:
                    log.debug("shodan_search: skipping item with no ip/domain: %s", item)
                    continue

                result = await loop.run_in_executor(
                    None, _fetch_host, api_key, target
                )
                results.append(result)

        else:  # search
            if not query:
                for item in inputs:
                    q = item.get("query") or item.get("company") or ""
                    if q:
                        query = f"org:{q}"
                        break

            if query:
                batch = await loop.run_in_executor(
                    None, _search_shodan, api_key, query, max_results
                )
                results.extend(batch)
            else:
                log.warning("shodan_search: no query for search mode")
                results.append({"error": "No query for Shodan search", "source": "shodan"})

        return results


def _fetch_host(api_key: str, target: str) -> dict:
    """Fetch host details from Shodan by IP or resolve hostname first."""
    # If it looks like a domain, resolve to IP
    ip = target
    if not _is_ip(target):
        ip = _resolve_hostname(api_key, target) or target

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                f"{_SHODAN_HOST_URL}/{ip}",
                params={"key": api_key},
            )
            if response.status_code == 404:
                return {
                    "ip": ip,
                    "original": target,
                    "source": "shodan",
                    "reason": _REASON,
                    "error": "No information available for this IP",
                }
            if response.status_code == 401:
                return {"error": "Shodan: unauthorized", "source": "shodan", "reason": _REASON}
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("shodan_search: HTTP error for host %r: %s", ip, exc)
        return {"ip": ip, "source": "shodan", "reason": _REASON, "error": str(exc)}
    except Exception as exc:
        log.warning("shodan_search: unexpected error for host %r: %s", ip, exc)
        return {"ip": ip, "source": "shodan", "reason": _REASON, "error": str(exc)}

    return _map_host(data, target)


def _search_shodan(api_key: str, query: str, max_results: int) -> list[dict]:
    """Run a Shodan search query."""
    params = {"key": api_key, "query": query, "minify": True}
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(_SHODAN_SEARCH_URL, params=params)
            if response.status_code == 401:
                return [{"error": "Shodan: unauthorized", "source": "shodan", "reason": _REASON}]
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("shodan_search: HTTP error for search %r: %s", query, exc)
        return [{"error": str(exc), "source": "shodan", "reason": _REASON}]
    except Exception as exc:
        log.warning("shodan_search: unexpected error for search %r: %s", query, exc)
        return [{"error": str(exc), "source": "shodan", "reason": _REASON}]

    matches = data.get("matches") or []
    return [_map_host(m, m.get("ip_str", "")) for m in matches[:max_results]]


def _resolve_hostname(api_key: str, hostname: str) -> str | None:
    """Resolve a hostname to an IP using Shodan DNS."""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                _SHODAN_DNS_URL,
                params={"hostnames": hostname, "key": api_key},
            )
            response.raise_for_status()
            data = response.json()
            return data.get(hostname)
    except Exception:
        return None


def _is_ip(value: str) -> bool:
    import re
    return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", value))


def _map_host(data: dict, original: str) -> dict:
    """Normalise a Shodan host record."""
    vulns = list(data.get("vulns") or {})
    ports = data.get("ports") or [s.get("port") for s in (data.get("data") or []) if s.get("port")]
    return {
        "ip": data.get("ip_str") or original,
        "original": original,
        "organization": data.get("org") or "",
        "country": data.get("country_name") or data.get("country_code") or "",
        "city": data.get("city") or "",
        "isp": data.get("isp") or "",
        "open_ports": ports,
        "hostnames": data.get("hostnames") or [],
        "domains": data.get("domains") or [],
        "os": data.get("os") or "",
        "vulnerabilities": vulns,
        "last_update": data.get("last_update") or "",
        "source": "shodan",
        "reason": _REASON,
    }
