"""GitHub search node — search repos, code, issues, users via the GitHub REST API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "GitHub surfaces open-source projects, code snippets, and developer profiles "
    "— useful for tech-stack reconnaissance and finding relevant repositories"
)
_GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


def _resolve_token(config_token: str | None = None) -> str | None:
    """Config value takes priority, then env var."""
    if config_token:
        return config_token
    return os.getenv("GITHUB_TOKEN")


class GithubSearchNode:
    node_type = "github_search"
    display_name = "GitHub Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Search term for GitHub repositories.",
            },
            "search_type": {
                "type": "string",
                "title": "Search Type",
                "enum": ["repositories", "code", "users"],
                "default": "repositories",
                "description": "Type of GitHub search to perform.",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
            },
            "github_token": {
                "type": "string",
                "title": "GitHub Token",
                "description": "Optional. Leave blank to use GITHUB_TOKEN env var. Increases rate limit from 10 to 30 req/min.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        query = (config.get("query") or "").strip()
        if not query:
            # Fall back to query from upstream inputs
            for item in inputs:
                q = item.get("query") or item.get("company") or item.get("name") or ""
                if q:
                    query = q
                    break

        if not query:
            log.warning("github_search: no query provided")
            return [{"error": "No query provided", "source": "github_search", "reason": _REASON}]

        token = _resolve_token(config.get("github_token"))
        max_results = min(int(config.get("max_results", 10)), 100)

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, _search_repos, query, token, max_results)
        return results


def _search_repos(query: str, token: str | None, max_results: int) -> list[dict]:
    """Search GitHub repositories via the REST API."""
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {"q": query, "per_page": max_results, "sort": "stars"}

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(_GITHUB_SEARCH_URL, params=params, headers=headers)
            if response.status_code == 403:
                return [{"error": "GitHub: rate limit exceeded or forbidden", "source": "github_search", "reason": _REASON}]
            if response.status_code == 422:
                return [{"error": "GitHub: invalid query", "source": "github_search", "reason": _REASON}]
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("github_search: HTTP error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "github_search", "reason": _REASON}]
    except Exception as exc:
        log.warning("github_search: unexpected error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "github_search", "reason": _REASON}]

    items = data.get("items") or []
    return [_map_repo(item) for item in items]


def _map_repo(item: dict) -> dict:
    """Normalise a GitHub repository search result."""
    return {
        "full_name": item.get("full_name") or "",
        "url": item.get("html_url") or "",
        "description": item.get("description") or "",
        "stars": item.get("stargazers_count") or 0,
        "language": item.get("language") or "",
        "updated_at": item.get("updated_at") or "",
        "source": "github_search",
        "reason": _REASON,
    }
