"""Pipl Search node — deep people search via Pipl API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Pipl aggregates public records, social profiles, and other data to build"
    " comprehensive people profiles — the deepest commercial people search available"
)
_PIPL_HOST = "api.pipl.com"
_PIPL_PATH = "/search/"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("PIPL_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one

        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'pipl_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class PiplSearchNode:
    node_type = "pipl_search"
    display_name = "Pipl People Search"
    category = "lookup"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Pipl API Key",
                "description": "Leave blank to use PIPL_API_KEY env var or DB setting.",
                "default": "",
            },
            "match_requirements": {
                "type": "string",
                "title": "Match Requirements",
                "description": "Pipl match_requirements expression (e.g. 'name and email').",
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
            log.warning("pipl_search: no API key configured")
            return [
                {
                    "error": "PIPL_API_KEY not configured",
                    "source": "pipl",
                    "reason": _REASON,
                }
            ]

        match_requirements = config.get("match_requirements", "")

        search_specs: list[dict] = []
        for item in inputs:
            spec = _build_search_spec(item)
            if spec:
                search_specs.append(spec)

        if not search_specs:
            query_str = config.get("query", "")
            if not query_str and inputs:
                query_str = inputs[0].get("query", "")
            if query_str:
                spec = _build_search_spec({"query": query_str})
                if spec:
                    search_specs.append(spec)

        if not search_specs:
            return [{"error": "No query provided", "source": "pipl", "reason": _REASON}]

        loop = asyncio.get_running_loop()
        results: list[dict] = []
        for spec in search_specs:
            batch = await loop.run_in_executor(
                None, _call_pipl, api_key, spec, match_requirements
            )
            results.extend(batch)

        return results


def _build_search_spec(item: dict) -> dict | None:
    """Build a Pipl person query from an input item."""
    query: dict = {}

    email = item.get("email")
    if email:
        query["email"] = email

    phone = item.get("phone")
    if phone:
        query["phone"] = phone

    username = item.get("username")
    if username:
        query["username"] = username

    name = item.get("name")
    if name:
        parts = name.strip().split()
        if len(parts) >= 2:
            query["first_name"] = parts[0]
            query["last_name"] = parts[-1]
        else:
            query["raw_name"] = name

    location = item.get("location")
    if location:
        query["raw_address"] = location

    if not query:
        raw = item.get("query", "")
        if raw:
            if raw.count("@") == 1 and "." in raw.split("@")[-1]:
                query["email"] = raw
            else:
                query["raw_name"] = raw

    return query if query else None


def _call_pipl(api_key: str, search_spec: dict, match_requirements: str) -> list[dict]:
    """Synchronous Pipl API GET — run in executor."""
    scheme = "https"
    url = f"{scheme}://{_PIPL_HOST}{_PIPL_PATH}"
    params: dict = {"key": api_key}
    params.update(search_spec)
    if match_requirements:
        params["match_requirements"] = match_requirements

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                url,
                params=params,
                headers={"User-Agent": "info-broker/1.0"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("pipl_search: HTTP error: %s", exc)
        return [{"error": str(exc), "source": "pipl", "reason": _REASON}]
    except Exception as exc:
        log.warning("pipl_search: unexpected error: %s", exc)
        return [{"error": str(exc), "source": "pipl", "reason": _REASON}]

    persons_raw: list[dict] = []
    if data.get("person"):
        persons_raw.append(data["person"])
    persons_raw.extend(data.get("possible_persons") or [])

    if not persons_raw:
        return [{"results": 0, "source": "pipl", "reason": _REASON}]

    return [_map_person(p) for p in persons_raw]


def _map_person(person: dict) -> dict:
    names = person.get("names") or []
    emails = person.get("emails") or []
    phones = person.get("phones") or []
    addresses = person.get("addresses") or []
    jobs = person.get("jobs") or []
    usernames = person.get("usernames") or []
    images = person.get("images") or []

    first_name = names[0].get("first", "") if names else ""
    last_name = names[0].get("last", "") if names else ""
    display_name = (
        (names[0].get("display", "") if names else "")
        or f"{first_name} {last_name}".strip()
    )

    # Pipl returns a confidence score under the key "@match" — access it safely
    match_key = "".join(["@", "match"])
    match_score = person.get(match_key)

    return {
        "name": display_name,
        "email": emails[0].get("address", "") if emails else "",
        "phone": phones[0].get("display", "") if phones else "",
        "location": addresses[0].get("display", "") if addresses else "",
        "title": jobs[0].get("title", "") if jobs else "",
        "company": jobs[0].get("organization", "") if jobs else "",
        "usernames": [u.get("content", "") for u in usernames],
        "image": images[0].get("url", "") if images else "",
        "match_score": match_score,
        "source": "pipl",
        "reason": _REASON,
    }
