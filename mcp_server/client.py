"""Thin async HTTP client for the info-broker REST API."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time

import httpx

API_URL = os.getenv("INFO_BROKER_URL", "http://localhost:8000")
API_KEY = os.getenv("INFO_BROKER_API_KEY", "changeme")

# Observability: caller identity and session correlation
_CALLER_IDENTITY = os.getenv("MCP_CALLER_IDENTITY", "mcp-server")
_SESSION_ID: str | None = None
_MCP_SECRET = os.environ.get("MCP_SIGNING_SECRET", "")


def _sign_request(body: bytes) -> dict[str, str]:
    """Return HMAC-SHA256 signing headers. No-op if MCP_SIGNING_SECRET not set."""
    if not _MCP_SECRET:
        return {}
    ts = str(int(time.time()))
    mac = hmac.new(
        _MCP_SECRET.encode("utf-8"),
        f"{ts}.".encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()
    return {"X-MCP-Timestamp": ts, "X-MCP-Signature": f"sha256={mac}"}


def set_session(session_id: str, caller_identity: str | None = None) -> None:
    """Set the current session ID and optional caller identity for observability."""
    global _SESSION_ID, _CALLER_IDENTITY
    _SESSION_ID = session_id
    if caller_identity:
        _CALLER_IDENTITY = caller_identity


async def api_call(method: str, path: str, **kwargs) -> dict:
    """Make an authenticated request to the info-broker API."""
    async with httpx.AsyncClient(base_url=API_URL, timeout=60) as client:
        # Pre-serialize body so HMAC is computed over exact wire bytes
        body_bytes = b""
        if "json" in kwargs:
            body_bytes = json.dumps(kwargs.pop("json"), separators=(",", ":")).encode()
            kwargs["content"] = body_bytes
            kwargs["headers"] = {**kwargs.get("headers", {}), "Content-Type": "application/json"}

        headers = {
            "X-API-Key": API_KEY,
            "X-Caller-Identity": _CALLER_IDENTITY,
            **_sign_request(body_bytes),
            **kwargs.pop("headers", {}),
        }
        if _SESSION_ID:
            headers["X-Session-Id"] = _SESSION_ID
        resp = await client.request(method, path, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()
