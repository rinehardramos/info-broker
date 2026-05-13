"""Dropbox file search datastore node — search files in a Dropbox account via the Dropbox API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Dropbox surfaces files and documents stored in a user's cloud drive — useful for document intelligence and data retrieval"
_SEARCH_URL = "https://api.dropboxapi.com/2/files/search_v2"


def _resolve_token(config_token: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_token:
        return config_token
    token = os.getenv("DROPBOX_ACCESS_TOKEN")
    if token:
        return token
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'dropbox_access_token'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class DropboxSearchNode:
    node_type = "dropbox_search"
    display_name = "Dropbox File Search"
    category = "datastore"

    config_schema = {
        "type": "object",
        "properties": {
            "access_token": {
                "type": "string",
                "title": "Dropbox Access Token",
                "description": "Leave blank to use DROPBOX_ACCESS_TOKEN env var or DB setting.",
                "default": "",
            },
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Keywords to search for in filenames and content.",
                "default": "",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
            },
            "path": {
                "type": "string",
                "title": "Search Path",
                "description": "Restrict search to this Dropbox path (e.g. '/Documents'). Leave blank for entire account.",
                "default": "",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        token = _resolve_token(config.get("access_token"))
        if not token:
            log.warning("dropbox_search: no access token configured")
            return [
                {
                    "error": "DROPBOX_ACCESS_TOKEN not configured",
                    "source": "dropbox",
                    "reason": _REASON,
                }
            ]

        query = (config.get("query") or "").strip()
        if not query and inputs:
            query = (
                inputs[0].get("query")
                or inputs[0].get("name")
                or inputs[0].get("company")
                or ""
            ).strip()

        if not query:
            return [{"error": "No query provided for Dropbox search", "source": "dropbox"}]

        max_results = min(int(config.get("max_results", 20)), 100)
        path = (config.get("path") or "").strip()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _search_dropbox, token, query, path, max_results
        )

    # -- ToolCallable interface ------------------------------------------------

    def tool_schema(self) -> dict:
        return {
            "name": "search_dropbox",
            "description": (
                "Search for files and documents in a Dropbox account by keyword. "
                "Returns file metadata including name, path, and modification date."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords to search for in filenames or content",
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional Dropbox folder path to restrict search (e.g. '/Documents')",
                    },
                },
                "required": ["query"],
            },
        }

    async def tool_invoke(self, params: dict, context: RunContext) -> list[dict]:
        config = getattr(self, "_active_config", {})
        merged = {**config, **params}
        return await self.execute(merged, [], context)


def _search_dropbox(token: str, query: str, path: str, max_results: int) -> list[dict]:
    """Synchronous Dropbox file search via the HTTP API."""
    payload: dict = {
        "query": query,
        "options": {
            "max_results": max_results,
        },
    }
    if path:
        payload["options"]["path"] = path

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                _SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code == 401:
                return [{"error": "Dropbox: unauthorized — check access token", "source": "dropbox"}]
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("dropbox_search: HTTP error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "dropbox", "reason": _REASON}]
    except Exception as exc:
        log.warning("dropbox_search: unexpected error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "dropbox", "reason": _REASON}]

    matches = data.get("matches") or []
    results = []
    for match in matches:
        meta = match.get("metadata", {}).get("metadata", {})
        if not meta:
            continue
        results.append(
            {
                "title": meta.get("name", ""),
                "path": meta.get("path_display", ""),
                "type": meta.get(".tag", ""),
                "size": meta.get("size"),
                "modified": meta.get("client_modified") or meta.get("server_modified"),
                "source": "dropbox",
                "reason": _REASON,
            }
        )
    return results
