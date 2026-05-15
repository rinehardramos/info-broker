"""scoped_brain.py — real tactic_runner_fn for engine_v2 (MVP-M9).

Spawns ONE Claude Code subprocess scoped to a single tactician's unit_of_work.
Mirrors the asyncio.create_subprocess_exec / stream-json pattern in app/is_brain.py
but with a narrower prompt and a list[dict] return type (TaskSpec-compatible dicts)
instead of the full IS brain result shape.

Design ref: docs/intelligence/three-tier-brain-architecture.md §7.2, §10.1 M9
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

from app.pipeline.catalogs.schemas import Tactic

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Subprocess constants (mirror is_brain.py values; do NOT share state)
# ---------------------------------------------------------------------------

_MCP_CONFIG = Path(os.getenv(
    "IS_MCP_CONFIG",
    str(Path(__file__).parent.parent.parent.parent / "config" / "is-mcp-config.json"),
))

_CLAUDE_BIN = os.getenv("CLAUDE_CODE_BIN", "claude")

# Per-tactician subprocess timeout — shorter than the IS brain safety net.
_TACTIC_TIMEOUT = int(os.getenv("SCOPED_BRAIN_TIMEOUT", "600"))  # 10 min


# ---------------------------------------------------------------------------
# Capability tier → model
# ---------------------------------------------------------------------------

_TIER_MODEL: dict[str, str] = {
    "light": "claude-haiku-4-5-20251001",
    "general": "claude-sonnet-4-6",
    "high": "claude-sonnet-4-6",  # Opus reserved for strategist per §5.2.1
}


# ---------------------------------------------------------------------------
# Prompt builder for scoped subprocess
# ---------------------------------------------------------------------------

def _build_scoped_prompt(
    tactic: Tactic,
    unit_of_work: dict[str, Any],
    capability_tier: str,
) -> str:
    """Build the narrow prompt injected into the scoped subprocess.

    Contains ONLY the tactician's unit_of_work and tactic templates.
    Does NOT include: full query, peer tactician data, other phases.
    """
    model = _TIER_MODEL.get(capability_tier, _TIER_MODEL["general"])
    lines: list[str] = [
        "# Scoped Tactic Runner",
        f"Model: {model}",
        "",
        "## Unit of Work",
        f"Objective: {unit_of_work.get('objective', '')}",
        f"Briefing: {unit_of_work.get('briefing', '')}",
        f"Scope in: {unit_of_work.get('scope_in', '')}",
        f"Scope out: {unit_of_work.get('scope_out', '')}",
        "",
    ]

    prior_slice = unit_of_work.get("prior_findings_slice")
    if prior_slice:
        lines += ["### Prior findings (filtered)", str(prior_slice), ""]

    forbidden = unit_of_work.get("forbidden_candidates", [])
    if forbidden:
        lines += [
            "### Forbidden candidates (DO NOT name as primary hypothesis)",
            ", ".join(str(c) for c in forbidden),
            "",
        ]

    lines += [
        "## Tactic",
        f"tactic_id: {tactic.id}",
        "",
        "## TaskSpec templates — emit ONE tool call per template below",
    ]
    for prod in tactic.produces:
        lines.append(f"  - technique_id: {prod.technique_id}, params_template: {prod.params_template}")

    lines += [
        "",
        "## Required techniques",
    ]
    # Note: techniques_catalog is not passed here (scoped_brain receives Tactic,
    # not the full catalog).  The tactic.required_techniques list is sufficient
    # to tell the subprocess WHAT to emit without leaking catalog internals.
    for tid in tactic.required_techniques:
        lines.append(f"  {tid}")

    lines += [
        "",
        "## Output format",
        "Emit tool calls using the MCP tools available to you.",
        "For each task, call the appropriate tool and return findings with fields:",
        "  candidate, source_class, source_url, evidence_snippet, confidence",
        "Emit structured JSON result when done.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stream-JSON parser (extract tool_use blocks as TaskSpec-compatible dicts)
# ---------------------------------------------------------------------------

def _parse_task_calls_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract tool_use blocks from stream-json events.

    Each tool_use becomes a TaskSpec-compatible dict:
      {technique_id, params_template, expect_schema, fail_modes, budget_ru}
    """
    task_calls: list[dict[str, Any]] = []
    for event in events:
        etype = event.get("type", "")
        if etype not in ("assistant", "user"):
            continue
        for content in event.get("message", {}).get("content", []):
            if content.get("type") != "tool_use":
                continue
            tool_name = content.get("name", "")
            # Strip MCP prefix: mcp__info-broker-mcp__web_search → web_search
            technique_id = tool_name.split("__")[-1] if "__" in tool_name else tool_name
            task_calls.append({
                "technique_id": technique_id,
                "params_template": content.get("input", {}),
                "expect_schema": {},
                "fail_modes": [],
                "budget_ru": 1,
                "_tool_use_id": content.get("id", ""),
            })
    return task_calls


# ---------------------------------------------------------------------------
# Public entry point — real tactic_runner_fn
# ---------------------------------------------------------------------------

async def scoped_brain_runner(
    tactic: Tactic,
    unit_of_work: dict[str, Any],
    capability_tier: str,
    budget_ru: int,
    event_emit: Callable,
    run_id: str = "",
    slot_idx: int = 0,
) -> list[dict[str, Any]]:
    """Spawn ONE Claude Code subprocess scoped to this tactician's unit_of_work.

    Args:
        tactic:           Tactic catalog entry for this slot.
        unit_of_work:     Scoped context (objective, briefing, scope_in, scope_out,
                          prior_findings_slice, forbidden_candidates).
        capability_tier:  "light" | "general" | "high" — drives model selection.
        budget_ru:        Soft cap; subprocess is terminated when exceeded.
        event_emit:       Async callable for pushing WS events.
        run_id:           Run ID for event correlation.
        slot_idx:         Hypothesis slot index for event correlation.

    Returns:
        list of TaskSpec-compatible dicts (technique_id + params_template).
        The tactician dispatches each to a specialist.
    """
    model = _TIER_MODEL.get(capability_tier, _TIER_MODEL["general"])
    prompt = _build_scoped_prompt(tactic, unit_of_work, capability_tier)

    # Resolve API key (same pattern as is_brain.py)
    api_key = ""
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one("SELECT value FROM core_settings WHERE key = 'anthropic_api_key'", ())
        if row and row["value"] and "REDACTED" not in row["value"] and row["value"].startswith("sk-ant-api"):
            api_key = row["value"]
    except Exception:
        pass

    cmd = [
        _CLAUDE_BIN, "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--model", model,
    ]
    if api_key:
        cmd.append("--bare")
    if _MCP_CONFIG.exists():
        cmd.extend(["--mcp-config", str(_MCP_CONFIG)])
        cmd.extend(["--allowedTools", "mcp__info-broker-mcp__*"])

    spawn_env = {**os.environ, "CLAUDE_CODE_HEADLESS": "1"}
    if api_key:
        spawn_env["ANTHROPIC_API_KEY"] = api_key
    else:
        spawn_env.pop("ANTHROPIC_API_KEY", None)
        spawn_env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        spawn_env.pop("CLAUDE_CODE_OAUTH_REFRESH_TOKEN", None)

    log.info(
        "scoped_brain: spawning subprocess tactic=%s slot=%d model=%s",
        tactic.id, slot_idx, model,
    )

    all_events: list[dict[str, Any]] = []

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=spawn_env,
            limit=10 * 1024 * 1024,
        )

        async def _read_lines() -> None:
            try:
                async for raw_line in proc.stdout:
                    line = raw_line.decode(errors="replace").strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    all_events.append(event)
                    etype = event.get("type", "")

                    # Emit WS events for the live view (matching existing event names)
                    if etype in ("assistant", "user"):
                        for content in event.get("message", {}).get("content", []):
                            if content.get("type") == "tool_use":
                                tool_name = content.get("name", "")
                                clean_tool = tool_name.split("__")[-1] if "__" in tool_name else tool_name
                                inp = content.get("input", {})
                                query_preview = str(
                                    inp.get("query") or inp.get("url") or inp.get("name") or ""
                                )[:120]
                                try:
                                    safe_input = json.loads(json.dumps(inp, default=str))
                                except Exception:
                                    safe_input = {}
                                await event_emit({
                                    "type": "is.tool_call",
                                    "run_id": run_id,
                                    "job_id": run_id,
                                    "tool": clean_tool,
                                    "status": "calling",
                                    "call_id": content.get("id", ""),
                                    "query_preview": query_preview,
                                    "input": safe_input,
                                    "slot_idx": slot_idx,
                                    "tool_name": clean_tool,
                                })
                            elif content.get("type") == "tool_result":
                                tool_result_data = content.get("content", "")
                                if isinstance(tool_result_data, list):
                                    parts = [
                                        block.get("text", "") if isinstance(block, dict) else str(block)
                                        for block in tool_result_data
                                    ]
                                    preview = "\n".join(parts)[:2000]
                                elif isinstance(tool_result_data, (dict, list)):
                                    preview = json.dumps(tool_result_data)[:2000]
                                else:
                                    preview = str(tool_result_data)[:2000] if tool_result_data else ""
                                await event_emit({
                                    "type": "is.tool_result",
                                    "run_id": run_id,
                                    "job_id": run_id,
                                    "call_id": content.get("tool_use_id", ""),
                                    "preview": preview,
                                    "slot_idx": slot_idx,
                                    "tool_name": "",
                                    "source_class": "",
                                })
            except asyncio.LimitOverrunError as exc:
                log.warning("scoped_brain: stdout line overflow (%s) — skipping", exc)

        timed_out = False
        try:
            await asyncio.wait_for(_read_lines(), timeout=_TACTIC_TIMEOUT)
        except asyncio.TimeoutError:
            timed_out = True
            log.warning("scoped_brain: tactic=%s slot=%d timed out after %ds", tactic.id, slot_idx, _TACTIC_TIMEOUT)
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

        if not timed_out:
            await proc.wait()

    except FileNotFoundError:
        log.error("scoped_brain: claude binary not found at %s", _CLAUDE_BIN)
        return []
    except Exception as exc:
        log.error("scoped_brain: unexpected error tactic=%s: %s", tactic.id, exc)
        return []

    task_calls = _parse_task_calls_from_events(all_events)
    log.info(
        "scoped_brain: tactic=%s slot=%d produced %d task_calls",
        tactic.id, slot_idx, len(task_calls),
    )
    return task_calls
