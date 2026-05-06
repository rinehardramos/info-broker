"""IS Brain -- Claude Code subprocess orchestrator.

Spawns Claude Code with a recursive tree search prompt and
info-broker MCP tools. Parses structured JSON output into
findings, pipeline definition, and plugin suggestions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.is_prompt import build_prompt

log = logging.getLogger(__name__)

# Path to MCP config for spawned Claude Code instance
_MCP_CONFIG = Path(os.getenv(
    "IS_MCP_CONFIG",
    str(Path(__file__).parent.parent / "config" / "is-mcp-config.json"),
))

# Claude Code binary
_CLAUDE_BIN = os.getenv("CLAUDE_CODE_BIN", "claude")


async def check_auth() -> dict[str, Any]:
    """Check Claude Code authentication status."""
    try:
        proc = await asyncio.create_subprocess_exec(
            _CLAUDE_BIN, "auth", "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return json.loads(stdout.decode(errors="replace"))
    except FileNotFoundError:
        return {"loggedIn": False, "error": f"Claude Code not found at {_CLAUDE_BIN}"}
    except Exception as exc:
        return {"loggedIn": False, "error": str(exc)}


async def run_research(
    query: str,
    user_id: str,
    max_depth: int = 3,
    max_branches: int = 20,
    past_research: list[dict] | None = None,
    user_preferences: dict | None = None,
) -> dict[str, Any]:
    """Run a research query via Claude Code subprocess.

    Returns a dict with: summary, findings, tree, pipeline,
    suggested_plugins, gaps. On error, returns a minimal result
    with the error in summary.
    """
    prompt = build_prompt(
        query=query,
        max_depth=max_depth,
        max_branches=max_branches,
        past_research=past_research,
        user_preferences=user_preferences,
    )

    cmd = [_CLAUDE_BIN, "-p", prompt, "--output-format", "json"]

    # Use --bare only when API key auth is available (Docker/CI).
    # Without --bare, Claude Code uses OAuth/keychain (subscription mode).
    if os.getenv("ANTHROPIC_API_KEY"):
        cmd.append("--bare")

    # Add MCP config if it exists
    if _MCP_CONFIG.exists():
        cmd.extend(["--mcp-config", str(_MCP_CONFIG)])

    log.info("IS Brain: spawning Claude Code for query: %s", query[:80])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "CLAUDE_CODE_HEADLESS": "1"},
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=int(os.getenv("IS_BRAIN_TIMEOUT", "300")),
        )

        raw_out = stdout.decode(errors="replace")

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="replace").strip()
            # Check for auth failure — Claude Code returns this in stdout JSON
            if "Not logged in" in raw_out or "Not logged in" in err_msg:
                log.error("IS Brain: Claude Code not authenticated")
                return _error_result(
                    "Claude Code not authenticated. "
                    "Run 'claude auth login' on the server, or set ANTHROPIC_API_KEY."
                )
            log.error("IS Brain: Claude Code exited %d: %s", proc.returncode, err_msg)
            return _error_result(f"Claude Code error (exit {proc.returncode}): {err_msg}")

        # Also check successful exit but with auth error in response
        if "Not logged in" in raw_out:
            return _error_result(
                "Claude Code not authenticated. "
                "Run 'claude auth login' on the server, or set ANTHROPIC_API_KEY."
            )

        return _parse_output(raw_out)

    except asyncio.TimeoutError:
        log.error("IS Brain: timed out after %ss", os.getenv("IS_BRAIN_TIMEOUT", "300"))
        return _error_result("Research timed out")
    except FileNotFoundError:
        log.error("IS Brain: claude binary not found at %s", _CLAUDE_BIN)
        return _error_result(f"Claude Code not found at {_CLAUDE_BIN}")
    except Exception as exc:
        log.error("IS Brain: unexpected error: %s", exc)
        return _error_result(str(exc))


def _parse_output(raw: str) -> dict[str, Any]:
    """Parse Claude Code JSON output into research results."""
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("IS Brain: non-JSON output, using raw text as summary")
        return _fallback_result(raw)

    # Claude Code wraps output in {"result": "...", "type": "result", ...}
    result_text = envelope.get("result", "")

    # The result field may itself be JSON (our structured output)
    try:
        research = json.loads(result_text)
        if isinstance(research, dict) and "findings" in research:
            return research
    except (json.JSONDecodeError, TypeError):
        pass

    # If result is plain text, wrap it
    return _fallback_result(result_text or raw)


_EMPTY_TREE: dict[str, Any] = {
    "total_branches": 0, "resolved": 0, "dead_ends": 0,
    "needs_tool": 0, "max_depth_reached": 0, "branches": [],
    "can_go_deeper": False, "deeper_leads": [],
}


def _fallback_result(text: str) -> dict[str, Any]:
    """Wrap unstructured text into the expected output format."""
    return {
        "summary": text[:2000],
        "entity_type": "unknown",
        "findings": [],
        "tree": {**_EMPTY_TREE},
        "pipeline": None,
        "suggested_plugins": [],
        "gaps": ["Research output was unstructured"],
    }


def _error_result(error: str) -> dict[str, Any]:
    """Return error as a research result."""
    return {
        "summary": f"Research failed: {error}",
        "entity_type": "unknown",
        "findings": [],
        "tree": {**_EMPTY_TREE},
        "pipeline": None,
        "suggested_plugins": [],
        "gaps": [error],
    }
