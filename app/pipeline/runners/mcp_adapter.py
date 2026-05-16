"""mcp_adapter.py — real mcp_invoke_fn for the specialist in engine_v2 (MVP-M9).

Calls the project's existing MCP invocation layer using the same HTTP transport
pattern that is_brain.py relies on for tool results.  The specialist calls this
with (tool_name, params) and expects a dict back.

Design ref: docs/intelligence/three-tier-brain-architecture.md §7.3, §10.1 M9
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP server config (mirror is_brain.py environment vars)
# ---------------------------------------------------------------------------

_MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
_MCP_TOOL_TIMEOUT = int(os.getenv("MCP_TOOL_TIMEOUT", "30"))

# Tool name prefix used by Claude Code MCP config — strip when calling directly
_MCP_PREFIX = "mcp__info-broker-mcp__"


def _clean_tool_name(tool_name: str) -> str:
    """Strip MCP prefix: mcp__info-broker-mcp__web_search → web_search."""
    if tool_name.startswith(_MCP_PREFIX):
        return tool_name[len(_MCP_PREFIX):]
    return tool_name


# ---------------------------------------------------------------------------
# HTTP-based MCP invocation
# ---------------------------------------------------------------------------

def invoke_mcp_tool(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Invoke an MCP tool and return its response as a dict.

    Raises:
        ConnectionError: if the MCP server is unreachable (triggers specialist retry).
        TimeoutError:    if the call exceeds _MCP_TOOL_TIMEOUT (triggers specialist retry).
        RuntimeError:    for tool-level errors (not retried).

    This function is synchronous because specialist.execute_task is synchronous.
    """
    import urllib.request
    import urllib.error

    clean = _clean_tool_name(tool_name)

    payload = json.dumps({
        "tool": clean,
        "params": params,
    }).encode()

    url = f"{_MCP_SERVER_URL}/mcp/invoke"

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_MCP_TOOL_TIMEOUT) as resp:
            body = resp.read().decode(errors="replace")
            try:
                result = json.loads(body)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"MCP server returned non-JSON response for tool {clean!r}: {body[:200]}"
                ) from exc

            # Normalize: wrap scalar/list results in a dict so specialist schema
            # validation doesn't fail on non-dict returns.
            if not isinstance(result, dict):
                return {"results": result if isinstance(result, list) else [result]}
            return result

    except urllib.error.URLError as exc:
        raise ConnectionError(f"MCP server unreachable at {url}: {exc}") from exc
    except TimeoutError:
        raise TimeoutError(f"MCP tool {clean!r} timed out after {_MCP_TOOL_TIMEOUT}s")
