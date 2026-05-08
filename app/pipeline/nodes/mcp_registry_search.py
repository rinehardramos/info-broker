"""MCP registry search node — discover available MCP servers for new capabilities."""

from __future__ import annotations

import asyncio
import logging
import urllib.parse

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "MCP registry search discovers available MCP servers (tools/capabilities) "
    "from public registries like Smithery and mcp.so — useful for expanding "
    "the agent's toolset dynamically"
)
_SMITHERY_URL = "https://registry.smithery.ai/api/v1/servers"
_DDG_URL = "https://api.duckduckgo.com/"


class MCPRegistrySearchNode:
    node_type = "mcp_registry_search"
    display_name = "MCP Registry Search"
    category = "source"

    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Keyword(s) to search for in MCP registries (e.g. 'github', 'database').",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        query = (config.get("query") or "").strip()
        if not query:
            # Try to derive query from upstream inputs
            for item in inputs:
                q = item.get("query") or item.get("capability") or item.get("name") or ""
                if q:
                    query = str(q).strip()
                    break

        if not query:
            log.warning("mcp_registry_search: no query provided")
            return [
                {
                    "error": "No query provided for MCP registry search",
                    "source": "mcp_registry_search",
                    "reason": _REASON,
                }
            ]

        max_results = min(int(config.get("max_results", 10)), 50)

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, _search_mcp_registry, query, max_results
        )
        return results


def _search_mcp_registry(query: str, max_results: int) -> list[dict]:
    """Search MCP server registries, falling back to DuckDuckGo if needed."""
    results = _search_smithery(query, max_results)
    if not results:
        log.info("mcp_registry_search: Smithery returned no results, trying DDG fallback")
        results = _search_ddg_fallback(query, max_results)
    return results


def _search_smithery(query: str, max_results: int) -> list[dict]:
    """Query the Smithery registry API."""
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                _SMITHERY_URL,
                params={"q": query, "limit": max_results},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("mcp_registry_search: Smithery HTTP error %s", exc)
        return []
    except Exception as exc:
        log.warning("mcp_registry_search: Smithery request failed: %s", exc)
        return []

    servers = data.get("servers") or data.get("results") or data.get("items") or []
    return [_map_server(s, "smithery") for s in servers[:max_results]]


def _search_ddg_fallback(query: str, max_results: int) -> list[dict]:
    """DuckDuckGo instant-answer fallback for mcp.so / smithery.ai / glama.ai."""
    ddg_query = f'"{query}" site:mcp.so OR site:smithery.ai OR site:glama.ai'
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                _DDG_URL,
                params={"q": ddg_query, "format": "json", "no_redirect": "1"},
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        log.warning("mcp_registry_search: DDG fallback failed: %s", exc)
        return []

    results: list[dict] = []
    for topic in (data.get("RelatedTopics") or [])[:max_results]:
        if not isinstance(topic, dict):
            continue
        text = topic.get("Text") or ""
        url = topic.get("FirstURL") or ""
        if not text:
            continue
        results.append(
            {
                "name": _extract_name_from_url(url) or text[:60],
                "description": text,
                "url": url,
                "tools": [],
                "category": "",
                "registry": "duckduckgo_mcp",
                "source": "mcp_registry_search",
                "reason": _REASON,
            }
        )
    return results


def _map_server(server: dict, registry: str) -> dict:
    """Normalise a registry server record to a common shape."""
    tools = server.get("tools") or []
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]
    return {
        "name": server.get("name") or server.get("id") or "",
        "description": server.get("description") or server.get("summary") or "",
        "url": server.get("url") or server.get("homepage") or server.get("repo_url") or "",
        "tools": list(tools),
        "category": server.get("category") or server.get("tags") or "",
        "registry": registry,
        "source": "mcp_registry_search",
        "reason": _REASON,
    }


def _extract_name_from_url(url: str) -> str:
    """Best-effort: pull a readable name from a registry URL path."""
    try:
        path = urllib.parse.urlparse(url).path.rstrip("/")
        return path.split("/")[-1] if path else ""
    except Exception:
        return ""
