"""Google Drive file search datastore node — search files via the Drive API v3."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = "Google Drive surfaces documents, spreadsheets, and files stored in a Google Workspace — useful for document intelligence and collaboration data"
_DRIVE_SEARCH_URL = "https://www.googleapis.com/drive/v3/files"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _resolve_credentials_path(config_path: str | None = None) -> str | None:
    """Config value takes priority, then env var."""
    if config_path:
        return config_path
    return os.getenv("GOOGLE_APPLICATION_CREDENTIALS")


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Simple API key for public/shared Drive access."""
    if config_key:
        return config_key
    key = os.getenv("GOOGLE_DRIVE_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'google_drive_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class GoogleDriveSearchNode:
    node_type = "google_drive_search"
    display_name = "Google Drive File Search"
    category = "datastore"

    config_schema = {
        "type": "object",
        "properties": {
            "credentials_path": {
                "type": "string",
                "title": "Service Account Credentials Path",
                "description": (
                    "Path to a Google service account JSON file. "
                    "Leave blank to use GOOGLE_APPLICATION_CREDENTIALS env var."
                ),
                "default": "",
            },
            "api_key": {
                "type": "string",
                "title": "Google Drive API Key",
                "description": (
                    "Simple API key for querying shared/public drives. "
                    "Leave blank to use GOOGLE_DRIVE_API_KEY env var or service account auth."
                ),
                "default": "",
            },
            "query": {
                "type": "string",
                "title": "Search Query",
                "description": "Full-text search query or Drive query syntax (e.g. 'name contains \"report\"').",
                "default": "",
            },
            "max_results": {
                "type": "integer",
                "title": "Max Results",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
            },
            "drive_id": {
                "type": "string",
                "title": "Shared Drive ID",
                "description": "Optional shared drive ID to restrict search scope.",
                "default": "",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        credentials_path = _resolve_credentials_path(config.get("credentials_path"))
        api_key = _resolve_api_key(config.get("api_key"))

        if not credentials_path and not api_key:
            log.warning("google_drive_search: no credentials or API key configured")
            return [
                {
                    "error": (
                        "Google Drive auth not configured — set GOOGLE_APPLICATION_CREDENTIALS "
                        "or GOOGLE_DRIVE_API_KEY"
                    ),
                    "source": "google_drive",
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
            return [{"error": "No query provided for Google Drive search", "source": "google_drive"}]

        max_results = min(int(config.get("max_results", 20)), 100)
        drive_id = (config.get("drive_id") or "").strip()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _search_drive, credentials_path, api_key, query, max_results, drive_id
        )

    # -- ToolCallable interface ------------------------------------------------

    def tool_schema(self) -> dict:
        return {
            "name": "search_google_drive",
            "description": (
                "Search for files and documents in Google Drive by keyword or Drive query syntax. "
                "Returns file metadata including name, type, owner, and web link."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query — plain text or Drive query syntax "
                            "(e.g. 'name contains \"budget\" and mimeType = \"application/vnd.google-apps.spreadsheet\"')"
                        ),
                    },
                    "drive_id": {
                        "type": "string",
                        "description": "Optional shared drive ID to restrict search",
                    },
                },
                "required": ["query"],
            },
        }

    async def tool_invoke(self, params: dict, context: RunContext) -> list[dict]:
        config = getattr(self, "_active_config", {})
        merged = {**config, **params}
        return await self.execute(merged, [], context)


def _get_service_account_token(credentials_path: str) -> str | None:
    """Obtain an OAuth2 bearer token from a service account JSON key file."""
    try:
        import json
        import time

        with open(credentials_path) as f:
            creds = json.load(f)

        # Use google-auth if available (preferred)
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request as GoogleRequest

            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/drive.readonly"],
            )
            credentials.refresh(GoogleRequest())
            return credentials.token
        except ImportError:
            pass

        # Fallback: manual JWT (RS256) — requires PyJWT + cryptography
        try:
            import jwt

            now = int(time.time())
            payload = {
                "iss": creds["client_email"],
                "scope": "https://www.googleapis.com/auth/drive.readonly",
                "aud": _TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            }
            private_key = creds["private_key"]
            assertion = jwt.encode(payload, private_key, algorithm="RS256")

            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    _TOKEN_URL,
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": assertion,
                    },
                )
                resp.raise_for_status()
                return resp.json().get("access_token")
        except Exception as exc:
            log.warning("google_drive_search: JWT auth failed: %s", exc)
            return None

    except Exception as exc:
        log.warning("google_drive_search: service account token error: %s", exc)
        return None


def _search_drive(
    credentials_path: str | None,
    api_key: str | None,
    query: str,
    max_results: int,
    drive_id: str,
) -> list[dict]:
    """Synchronous Google Drive file search."""
    headers: dict = {}
    params: dict = {
        "q": query,
        "pageSize": max_results,
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime,owners,size,parents)",
    }

    if credentials_path:
        token = _get_service_account_token(credentials_path)
        if not token:
            return [
                {
                    "error": "Google Drive: could not obtain access token from service account — install google-auth or PyJWT+cryptography",
                    "source": "google_drive",
                    "reason": _REASON,
                }
            ]
        headers["Authorization"] = f"Bearer {token}"
        if drive_id:
            params["driveId"] = drive_id
            params["includeItemsFromAllDrives"] = "true"
            params["supportsAllDrives"] = "true"
            params["corpora"] = "drive"
    elif api_key:
        params["key"] = api_key
        if drive_id:
            params["driveId"] = drive_id
            params["includeItemsFromAllDrives"] = "true"
            params["supportsAllDrives"] = "true"
            params["corpora"] = "drive"

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(_DRIVE_SEARCH_URL, headers=headers, params=params)
            if response.status_code == 401:
                return [{"error": "Google Drive: unauthorized — check credentials", "source": "google_drive"}]
            if response.status_code == 403:
                return [{"error": "Google Drive: forbidden — check API key or scopes", "source": "google_drive"}]
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("google_drive_search: HTTP error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "google_drive", "reason": _REASON}]
    except Exception as exc:
        log.warning("google_drive_search: unexpected error for query %r: %s", query, exc)
        return [{"error": str(exc), "source": "google_drive", "reason": _REASON}]

    files = data.get("files") or []
    results = []
    for f in files:
        owners = [o.get("displayName", o.get("emailAddress", "")) for o in (f.get("owners") or [])]
        results.append(
            {
                "title": f.get("name", ""),
                "url": f.get("webViewLink", ""),
                "mime_type": f.get("mimeType", ""),
                "modified": f.get("modifiedTime", ""),
                "owners": owners,
                "size": f.get("size"),
                "drive_id": f.get("id", ""),
                "source": "google_drive",
                "reason": _REASON,
            }
        )
    return results
