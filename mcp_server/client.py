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

# Non-secret user/org IDs — set by scoped_brain.py in the subprocess spawn_env.
# Forwarded as HTTP headers on every api_call so the API layer can resolve
# user-scoped and org-scoped API keys from the vault.  Values are opaque UUIDs;
# decrypted key values NEVER enter the subprocess env or the MCP client.
_RUN_USER_ID: str | None = os.environ.get("IS_RUN_USER_ID") or None
_RUN_ORG_ID: str | None = os.environ.get("IS_RUN_ORG_ID") or None


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
        if _RUN_USER_ID:
            headers["X-Caller-User-Id"] = _RUN_USER_ID
        if _RUN_ORG_ID:
            headers["X-Caller-Org-Id"] = _RUN_ORG_ID
        resp = await client.request(method, path, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()
