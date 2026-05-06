"""Thin async HTTP client for the info-broker REST API."""
from __future__ import annotations

import os

import httpx

API_URL = os.getenv("INFO_BROKER_URL", "http://localhost:8000")
API_KEY = os.getenv("INFO_BROKER_API_KEY", "changeme")

# Observability: caller identity and session correlation
_CALLER_IDENTITY = os.getenv("MCP_CALLER_IDENTITY", "mcp-server")
_SESSION_ID: str | None = None


def set_session(session_id: str, caller_identity: str | None = None) -> None:
    """Set the current session ID and optional caller identity for observability."""
    global _SESSION_ID, _CALLER_IDENTITY
    _SESSION_ID = session_id
    if caller_identity:
        _CALLER_IDENTITY = caller_identity


async def api_call(method: str, path: str, **kwargs) -> dict:
    """Make an authenticated request to the info-broker API."""
    async with httpx.AsyncClient(base_url=API_URL, timeout=60) as client:
        headers = {
            "X-API-Key": API_KEY,
            "X-Caller-Identity": _CALLER_IDENTITY,
        }
        if _SESSION_ID:
            headers["X-Session-Id"] = _SESSION_ID
        resp = await client.request(method, path, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()
