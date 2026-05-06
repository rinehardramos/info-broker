"""Thin async HTTP client for the info-broker REST API."""
from __future__ import annotations

import os

import httpx

API_URL = os.getenv("INFO_BROKER_URL", "http://localhost:8000")
API_KEY = os.getenv("INFO_BROKER_API_KEY", "changeme")


async def api_call(method: str, path: str, **kwargs) -> dict:
    """Make an authenticated request to the info-broker API.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path, e.g. "/v3/nodes/ddg_search/execute"
        **kwargs: Passed directly to httpx.AsyncClient.request (json=, params=, etc.)

    Returns:
        Parsed JSON response as a dict.

    Raises:
        httpx.HTTPStatusError: on 4xx/5xx responses.
    """
    async with httpx.AsyncClient(base_url=API_URL, timeout=60) as client:
        headers = {"X-API-Key": API_KEY}
        resp = await client.request(method, path, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()
