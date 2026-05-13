"""HMAC-SHA256 verification for MCP requests.

Mirrors app/services/webhook.py signing pattern. Wraps existing bearer-token
auth — does not replace it. Bearer identifies the caller; HMAC proves the
request body is intact and recent.

NOTE: MCP traffic is served by mcp_server/server.py (FastMCP), not via this
FastAPI app. This dependency is exported so a future /v3/mcp/* router can adopt
it directly. The client-side signing in mcp_server/client.py is the active
enforcement point; server-side enforcement happens inside FastMCP middleware
(out of scope for this PR).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time

from fastapi import Header, HTTPException, Request

log = logging.getLogger(__name__)

_MCP_SECRET = os.environ.get("MCP_SIGNING_SECRET", "")
_MAX_SKEW_SECONDS = 300

if not _MCP_SECRET:
    log.warning(
        "MCP_SIGNING_SECRET not set — MCP request signing is DISABLED. "
        "This is acceptable in development only."
    )


async def verify_mcp_signature(
    request: Request,
    x_mcp_signature: str | None = Header(default=None),
    x_mcp_timestamp: str | None = Header(default=None),
) -> None:
    if not _MCP_SECRET:
        return  # dev mode bypass

    if not x_mcp_signature or not x_mcp_timestamp:
        raise HTTPException(status_code=401, detail="missing MCP signature headers")

    try:
        ts = int(x_mcp_timestamp)
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid MCP timestamp")

    if abs(time.time() - ts) > _MAX_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="MCP timestamp outside window")

    body = await request.body()
    expected = hmac.new(
        _MCP_SECRET.encode("utf-8"),
        f"{ts}.".encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()

    provided = x_mcp_signature.removeprefix("sha256=")
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="MCP signature mismatch")
