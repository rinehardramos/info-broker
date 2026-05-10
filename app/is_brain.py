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

# 30-min absolute safety net - should never hit this normally
_SAFETY_NET_TIMEOUT = int(os.getenv("IS_BRAIN_TIMEOUT", "1800"))


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
    on_event: Any = None,  # async callable(dict) for streaming tool call events
    available_nodes: list[dict] | None = None,  # healthy+enabled nodes for prompt
    strategies_section: str = "",  # procedural memory strategies for the prompt
    entity_strategy: str = "",  # entity-specific strategy block for the prompt
    techniques_section: str = "",  # technique catalog for the prompt
    meta_strategies_section: str = "",  # compiled meta-strategies for the prompt
    research_plan: str = "",  # formatted plan string for prompt injection
    user_sources: str = "",  # user-uploaded file context for prompt injection
    session_context: str = "",  # prior session turns for prompt injection
) -> dict[str, Any]:
    """Run a research query via Claude Code subprocess.

    Returns a dict with: summary, findings, tree, pipeline,
    suggested_plugins, gaps. On error, returns a minimal result
    with the error in summary.

    If on_event is provided, tool call events are pushed in real-time.
    On timeout, partial results are returned instead of an empty error.
    """
    prompt = build_prompt(
        query=query,
        max_depth=max_depth,
        max_branches=max_branches,
        past_research=past_research,
        user_preferences=user_preferences,
        available_nodes=available_nodes,
        strategies_section=strategies_section,
        entity_strategy=entity_strategy,
        techniques_section=techniques_section,
        meta_strategies_section=meta_strategies_section,
        research_plan=research_plan,
        user_sources=user_sources,
        session_context=session_context,
    )

    # Resolve API key — DB first, then env. Skip expired OAuth tokens.
    api_key = ""
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one("SELECT value FROM core_settings WHERE key = 'anthropic_api_key'", ())
        if row and row["value"] and "REDACTED" not in row["value"] and row["value"].startswith("sk-ant-api"):
            api_key = row["value"]
    except Exception:
        pass
    if not api_key:
        env_key = os.getenv("ANTHROPIC_API_KEY", "")
        if env_key.startswith("sk-ant-api"):
            api_key = env_key

    # Use stream-json for real-time tool call events + checkpointing
    cmd = [_CLAUDE_BIN, "-p", prompt, "--output-format", "stream-json", "--verbose"]

    # Only use --bare with a real API key (not OAuth tokens which expire)
    if api_key:
        cmd.append("--bare")

    # Add MCP config and allow all MCP tools
    if _MCP_CONFIG.exists():
        cmd.extend(["--mcp-config", str(_MCP_CONFIG)])
        cmd.extend(["--allowedTools", "mcp__info-broker-mcp__*"])

    log.info("IS Brain: spawning Claude Code (api_key=%s, bare=%s) for query: %s",
             "yes" if api_key else "subscription", "--bare" in cmd, query[:80])

    # Build spawn env — strip any stale ANTHROPIC_API_KEY so Claude Code uses subscription auth
    spawn_env = {**os.environ, "CLAUDE_CODE_HEADLESS": "1"}
    if api_key:
        spawn_env["ANTHROPIC_API_KEY"] = api_key
    else:
        spawn_env.pop("ANTHROPIC_API_KEY", None)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=spawn_env,
            limit=10 * 1024 * 1024,  # 10MB buffer — Claude Code emits large JSON lines
        )

        # Read stdout line-by-line for streaming events + checkpointing
        result_line = None
        tool_calls: list[dict] = []
        timed_out = False

        async def _read_lines():
            nonlocal result_line
            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                # Capture tool call events for streaming
                if etype == "assistant":
                    for content in event.get("message", {}).get("content", []):
                        if content.get("type") == "tool_use":
                            tool_name = content.get("name", "")
                            tc = {"tool": tool_name, "status": "calling", "id": content.get("id", "")}
                            tool_calls.append(tc)
                            if on_event:
                                await on_event(tc)
                        elif content.get("type") == "tool_result":
                            tool_result_data = content.get("content", "")
                            # Truncate large results for WS transport
                            preview = str(tool_result_data)[:2000] if tool_result_data else ""
                            tc = {
                                "type": "tool_result",
                                "tool_use_id": content.get("tool_use_id", ""),
                                "preview": preview,
                            }
                            if on_event:
                                await on_event(tc)

                # Capture final result
                if etype == "result":
                    result_line = line

        try:
            await asyncio.wait_for(_read_lines(), timeout=_SAFETY_NET_TIMEOUT)
        except asyncio.TimeoutError:
            timed_out = True
            log.warning("IS Brain: hit %d-min safety limit, terminating", _SAFETY_NET_TIMEOUT // 60)
            proc.terminate()  # graceful terminate, not kill
            await asyncio.sleep(5)
            if proc.returncode is None:
                proc.kill()

        await proc.wait()

        if timed_out:
            # Use whatever result_line we got, or return partial
            if result_line:
                log.info("IS Brain: timed out but have result line, parsing")
                parsed = _parse_stream_result(result_line)
                parsed.setdefault("gaps", []).append("Research timed out — partial results")
                return parsed
            return _error_result(f"Research timed out after {_SAFETY_NET_TIMEOUT}s")

        if proc.returncode != 0:
            stderr_out = ""
            if proc.stderr:
                try:
                    stderr_out = (await asyncio.wait_for(proc.stderr.read(), timeout=5)).decode(errors="replace")
                except Exception:
                    pass
            if result_line and "Not logged in" in result_line:
                return _error_result("Claude Code not authenticated. Run 'claude auth login' or set ANTHROPIC_API_KEY.")
            log.error("IS Brain: Claude Code exited %d: %s", proc.returncode, stderr_out[:200])
            return _error_result(f"Claude Code error (exit {proc.returncode}): {stderr_out[:200]}")

        if not result_line:
            return _error_result("Claude Code produced no result")

        if "Not logged in" in result_line:
            return _error_result("Claude Code not authenticated. Run 'claude auth login' or set ANTHROPIC_API_KEY.")

        log.info("IS Brain: completed with %d tool calls", len(tool_calls))
        return _parse_stream_result(result_line)

    except FileNotFoundError:
        log.error("IS Brain: claude binary not found at %s", _CLAUDE_BIN)
        return _error_result(f"Claude Code not found at {_CLAUDE_BIN}")
    except Exception as exc:
        log.error("IS Brain: unexpected error: %s", exc)
        return _error_result(str(exc))


def _parse_stream_result(line: str) -> dict[str, Any]:
    """Parse a stream-json result line into research results."""
    return _parse_output(line)


_ERROR_PATTERNS = [
    "blocked", "403 forbidden", "404 not found", "422 unprocessable",
    "not configured", "api key", "api_key", "permission error",
    "authentication", "timed out", "connection refused", "rate limit",
    "rate_limit", "access denied", "unauthorized", "quota exceeded",
    "requires full access", "token is not valid", "user was not found",
]


def _classify_finding(finding: dict) -> dict:
    """Detect error findings that the brain mistakenly scored as high-confidence."""
    title = (finding.get("title") or "").lower()
    content = (finding.get("content") or "").lower()
    combined = f"{title} {content}"

    is_error = any(p.lower() in combined for p in _ERROR_PATTERNS)
    if is_error:
        finding["finding_type"] = "error"
        finding["confidence"] = 0
        finding["error_flagged"] = True
    else:
        finding.setdefault("finding_type", "result")
        finding["error_flagged"] = False
    return finding


def _parse_output(raw: str) -> dict[str, Any]:
    """Parse Claude Code JSON output into research results."""
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("IS Brain: non-JSON output, using raw text as summary")
        return _fallback_result(raw)

    # Claude Code wraps output in {"result": "...", "type": "result", ...}
    result_text = envelope.get("result", "")
    log.info("IS Brain: envelope type=%s, result length=%d, is_error=%s",
             envelope.get("type"), len(result_text), envelope.get("is_error"))

    # The result field may itself be JSON (our structured output)
    for text in [result_text, _extract_json(result_text)]:
        if not text:
            continue
        try:
            research = json.loads(text)
            if isinstance(research, dict) and "findings" in research:
                research["findings"] = [_classify_finding(f) for f in research["findings"]]
                error_count = sum(1 for f in research["findings"] if f.get("error_flagged"))
                log.info("IS Brain: parsed structured output with %d findings (%d errors filtered)",
                         len(research["findings"]), error_count)
                # Add topic clusters to result
                try:
                    from app.pipeline.fusion.topic_clustering import cluster_findings
                    research["topic_clusters"] = cluster_findings(research.get("findings") or [])
                except Exception:
                    research.setdefault("topic_clusters", [])
                # Annotate findings with Pyramid of Pain level
                try:
                    from app.pipeline.fusion.pyramid_scoring import annotate_findings
                    if research.get("findings"):
                        annotate_findings(research["findings"])
                except Exception:
                    pass
                return research
            log.info("IS Brain: parsed JSON but no 'findings' key, keys=%s",
                     list(research.keys()) if isinstance(research, dict) else type(research))
        except (json.JSONDecodeError, TypeError):
            continue

    log.info("IS Brain: result is plain text (%d chars), using fallback", len(result_text))
    return _fallback_result(result_text or raw)


def _extract_json(text: str) -> str | None:
    """Try to extract a JSON object from text that may contain markdown fences or preamble."""
    import re
    # Try ```json ... ``` blocks
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        return m.group(1)
    # Try first { ... last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end > start:
        return text[start:end + 1]
    return None


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
        "topic_clusters": [],
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
        "topic_clusters": [],
    }
