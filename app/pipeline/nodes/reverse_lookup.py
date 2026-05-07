"""Reverse identity lookup node — maps an email, phone, or username to linked identities."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Reverse lookup cross-references an email, phone, or username against public sources "
    "to surface linked profiles and identities across platforms"
)

_PLATFORMS = [
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "github.com",
    "instagram.com",
]

_PHONE_RE = re.compile(r"^[\+\-\s\(\)]*\d[\d\s\-\(\)]{5,}\d$")


def _detect_type(query: str) -> str:
    """Detect whether a query string is an email, phone number, or username."""
    if "@" in query:
        parts = query.split("@", 1)
        if len(parts) == 2 and "." in parts[1]:
            return "email"
    if _PHONE_RE.match(query) and len(re.sub(r"\D", "", query)) >= 7:
        return "phone"
    return "username"


def _build_search_queries(query: str, query_type: str) -> list[str]:
    """Return a list of search strings appropriate for the query type."""
    if query_type == "email":
        return [
            f'"{query}" site:linkedin.com',
            f'"{query}" site:facebook.com OR site:twitter.com',
            f'"{query}" profile',
        ]
    if query_type == "phone":
        return [
            f'"{query}" site:linkedin.com OR site:facebook.com',
            f'"{query}" contact profile',
        ]
    # username
    return [
        f'"{query}" site:github.com OR site:twitter.com OR site:instagram.com',
        f'"{query}" profile site:linkedin.com',
    ]


def _extract_identities(html: str) -> list[dict]:
    """Scan HTML for mentions of known social platforms and return identity stubs."""
    found: list[dict] = []
    for platform_domain in _PLATFORMS:
        if platform_domain in html:
            platform_name = platform_domain.split(".")[0]
            found.append({"platform": platform_name, "name": "", "confidence": 50})
    return found


def _web_search_reverse(query: str, query_type: str) -> dict:
    """Search DuckDuckGo HTML to find identity mentions for *query*."""
    search_queries = _build_search_queries(query, query_type)
    all_identities: list[dict] = []

    for search_q in search_queries:
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                response = client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": search_q},
                    headers={"User-Agent": "Mozilla/5.0 (compatible; info-broker/1.0)"},
                )
                if response.status_code == 200:
                    identities = _extract_identities(response.text)
                    all_identities.extend(identities)
        except Exception as exc:
            log.warning("reverse_lookup: search error for %r: %s", search_q, exc)

    # Deduplicate by (platform, name)
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for identity in all_identities:
        key = (identity["platform"], identity["name"])
        if key not in seen:
            seen.add(key)
            unique.append(identity)

    return {
        "query": query,
        "query_type": query_type,
        "identities": unique,
        "source": "web_search",
        "reason": _REASON,
    }


class ReverseLookupNode:
    node_type = "reverse_lookup"
    display_name = "Reverse Lookup"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Query",
                "description": "Email address, phone number, or username to reverse-look up.",
            },
            "query_type": {
                "type": "string",
                "title": "Query Type",
                "enum": ["email", "phone", "username", "auto"],
                "default": "auto",
                "description": "Force a type or let the node auto-detect.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        query_type_cfg = config.get("query_type", "auto")

        # Collect queries from config and input items
        queries: list[str] = []
        if config.get("query"):
            queries.append(config["query"].strip())

        for item in inputs:
            for field in ("email", "phone", "username", "query"):
                value = item.get(field)
                if value and isinstance(value, str):
                    queries.append(value.strip())
                    break  # one query per input item

        if not queries:
            return [{"error": "No query provided", "source": "reverse_lookup", "reason": _REASON}]

        loop = asyncio.get_running_loop()
        results: list[dict] = []

        for query in queries:
            qt = query_type_cfg if query_type_cfg != "auto" else _detect_type(query)
            result = await loop.run_in_executor(None, _web_search_reverse, query, qt)
            results.append(result)

        return results
