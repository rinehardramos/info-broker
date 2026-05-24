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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.pipeline.catalogs.schemas import Tactic
from app.claude_auth_setup import ensure_claude_credentials

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Brain-subprocess failure detection
# ---------------------------------------------------------------------------
#
# When the Claude Code subprocess hits an auth / HTTP / network error, its
# stream-json event sequence still LOOKS structured: an init event, retries,
# a synthetic assistant message, then a result event with is_error=true. The
# legacy diagnostic just logged "produced 0 task_calls" at WARNING — so the
# strategist's gather gate failed with "checks did not pass" and the real
# 401 / 429 / 500 was invisible. This function pulls the failure out
# explicitly so admin logs name the actual cause early.


@dataclass(frozen=True)
class BrainFailure:
    """Structured summary of a brain-subprocess outcome.

    Fields:
        is_fatal:        True if the subprocess produced no usable output
        kind:            "ok" | "auth_failed" | "rate_limited" | "upstream_error"
                         | "no_result_event"
        api_status:      Final HTTP status from the result event (None on ok)
        retry_count:     Number of api_retry events observed (for observability;
                         non-zero on transient errors that ultimately succeeded)
        api_key_source:  apiKeySource from the init event ("none" is itself
                         diagnostic — Claude CLI found no auth)
        message:         Short human-readable summary suitable for admin logs
    """
    is_fatal: bool
    kind: str
    api_status: int | None
    retry_count: int
    api_key_source: str
    message: str


# Human-facing message templates for pipeline_runs.error_message.
# Keep concise; no file paths or stack traces (this surfaces in the UI).
_USER_FACING_MESSAGES = {
    "auth_failed": (
        "Brain authentication failed (HTTP {status}). "
        "Claude credentials are missing or expired in the API container — "
        "ask an admin to refresh ~/.claude/.credentials.json or set "
        "ANTHROPIC_API_KEY."
    ),
    "rate_limited": (
        "Brain rate limited (HTTP {status}). "
        "The Anthropic API throttled the request after {retries} retries — "
        "wait a few minutes and try again, or upgrade the API tier."
    ),
    "upstream_error": (
        "Brain upstream error (HTTP {status}). "
        "The Anthropic API returned a server error — likely transient; "
        "if it repeats, check status.anthropic.com."
    ),
    "no_result_event": (
        "Brain subprocess crashed or timed out before completing. "
        "Check the API container's recent logs for an exit code or "
        "OOM-kill signal."
    ),
}


def summarize_brain_failures(failures: list[BrainFailure]) -> str | None:
    """Turn a list of per-slot BrainFailures into one user-facing string.

    Returns None when there are no fatal failures — the caller can keep
    the strategist's terminate_reason. Returns a short, UI-safe message
    when at least one fatal failure happened. The FIRST fatal failure
    wins (the run already terminated; no point listing every slot).
    """
    for f in failures:
        if not f.is_fatal:
            continue
        template = _USER_FACING_MESSAGES.get(
            f.kind,
            "Brain failed ({kind}). Check API logs for details.",
        )
        return template.format(
            kind=f.kind,
            status=f.api_status or "?",
            retries=f.retry_count,
        )
    return None


def detect_brain_failure(events: list[dict[str, Any]]) -> BrainFailure:
    """Inspect a Claude-Code stream-json event list and classify the outcome.

    The function is pure (no I/O) so it can be unit-tested without spawning
    the subprocess. The caller (scoped_brain_runner) escalates the log
    level to ERROR when ``is_fatal`` is True.
    """
    api_src = ""
    retry_count = 0
    final_status: int | None = None
    final_is_error = False
    final_message = ""
    saw_result = False

    for e in events:
        if e.get("type") == "system":
            if e.get("subtype") == "init" and not api_src:
                api_src = e.get("apiKeySource", "?")
            elif e.get("subtype") == "api_retry":
                retry_count += 1
        elif e.get("type") == "result":
            saw_result = True
            final_is_error = bool(e.get("is_error"))
            final_status = e.get("api_error_status")
            final_message = str(e.get("result", ""))[:300]

    if not saw_result:
        return BrainFailure(
            is_fatal=True, kind="no_result_event", api_status=None,
            retry_count=retry_count, api_key_source=api_src or "?",
            message="brain subprocess emitted no `result` event — possible crash / timeout",
        )

    if not final_is_error:
        return BrainFailure(
            is_fatal=False, kind="ok", api_status=None,
            retry_count=retry_count, api_key_source=api_src or "?",
            message="",
        )

    # is_error is true — classify by HTTP status
    if final_status == 401:
        kind = "auth_failed"
    elif final_status == 429:
        kind = "rate_limited"
    elif final_status and final_status >= 500:
        kind = "upstream_error"
    else:
        # is_error with no api_error_status set — generic failure
        kind = "upstream_error"

    return BrainFailure(
        is_fatal=True, kind=kind, api_status=final_status,
        retry_count=retry_count, api_key_source=api_src or "?",
        message=final_message or f"brain failed (HTTP {final_status})",
    )

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

def _deep_parse_json(value: Any) -> Any:
    """Recursively decode JSON-encoded strings inside a value.

    MCP tools often wrap structured payloads as `{"result": "<json string>"}`
    where the inner string still contains JSON. A single json.loads only
    peels one layer; this function walks the tree and decodes any string
    that itself looks like JSON so the final payload is a fully-parsed
    object tree (no nested escape-soup when re-serialized for display).
    """
    if isinstance(value, str):
        s = value.strip()
        if s.startswith(("{", "[")) and s.endswith(("}", "]")):
            try:
                return _deep_parse_json(json.loads(s))
            except Exception:
                return value
        return value
    if isinstance(value, list):
        return [_deep_parse_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _deep_parse_json(v) for k, v in value.items()}
    return value


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
    ]

    # P3: inject corrective hint from prior failed attempt, if present
    corrective_hint = unit_of_work.get("corrective_hint")
    if corrective_hint:
        lines += [
            "### CORRECTIVE HINT FROM PREVIOUS ATTEMPT",
            corrective_hint,
            "",
        ]

    # Mid-run user directive: injected via POST /v3/runs/{run_id}/inject while
    # the research was already running.  Rendered prominently so the brain sees it.
    user_directive = unit_of_work.get("user_directive")
    if user_directive:
        lines += [
            "=== USER DIRECTIVE (mid-run steering) ===",
            "The user added this instruction while the research was running. Incorporate it now:",
            user_directive,
            "",
        ]

    # The user query is the de-facto objective when strategy doesn't define one.
    query_str = unit_of_work.get("query") or unit_of_work.get("objective", "")
    objective = unit_of_work.get("objective") or query_str
    lines += [
        "## Unit of Work",
        f"User query: {query_str}",
        f"Objective: {objective}",
        f"Briefing: {unit_of_work.get('briefing', '')}",
    ]
    if unit_of_work.get("scope_in"):
        lines.append(f"Scope in: {unit_of_work['scope_in']}")
    if unit_of_work.get("scope_out"):
        lines.append(f"Scope out: {unit_of_work['scope_out']}")
    lines.append("")

    prior_slice = unit_of_work.get("prior_findings_slice")
    if prior_slice:
        lines += ["### Prior findings (filtered)", str(prior_slice), ""]

    forbidden = unit_of_work.get("forbidden_candidates", [])
    if forbidden:
        lines += [
            "### FORBIDDEN_CANDIDATES (do not converge on any of these — explicitly investigate alternatives):",
        ]
        for name in forbidden:
            lines.append(f"- {name}")
        lines.append("")

    lines += [
        "## Tactic",
        f"tactic_id: {tactic.id}",
    ]

    # Tactics with no `produces` (extract, synthesize) are pure
    # analysis — explicitly tell the brain NOT to call tools.
    if not tactic.produces:
        lines += [
            "",
            "## EXECUTION MODE: ANALYSIS ONLY — DO NOT CALL ANY TOOLS",
            "This tactic is pure reasoning. Read the briefing, then emit a final",
            "text response with your analysis. Do NOT call any MCP tools.",
        ]
    else:
        # Tactics with `produces` MUST emit tool_use blocks. Be explicit about
        # which MCP-prefixed tool to call and what params to use.
        #
        # Health-aware ordering: partition into healthy vs unhealthy (no key /
        # requires_key set).  Healthy tools are listed first; unhealthy ones are
        # annotated with ⚠ UNAVAILABLE but still listed so required_techniques
        # can be called if no alternative exists.  Best-effort: unknown health
        # (cache miss) is treated as healthy — we never over-suppress.
        from app.pipeline.runners.tool_health import (
            is_unhealthy,
            missing_key as _missing_key,
        )

        healthy_prods = [p for p in tactic.produces if not is_unhealthy(p.technique_id)]
        unhealthy_prods = [p for p in tactic.produces if is_unhealthy(p.technique_id)]

        tool_header = [
            "",
            "## EXECUTION MODE: TOOL USE REQUIRED",
            f"You MUST call EXACTLY {len(tactic.produces)} MCP tool(s) for this tactic.",
            "Do NOT skip tool calls. Do NOT answer from training data alone.",
            "The user is asking BECAUSE they don't know the answer — answering",
            "from training is a guaranteed wrong answer.",
            "",
            "### Mandatory tool calls (call each one once with the params shown):",
        ]
        if unhealthy_prods:
            tool_header.append(
                "Prefer the healthy tools; treat ⚠ ones as last-resort — they will return empty without their API key."
            )
        lines += tool_header
        # Map technique_id → fully-qualified MCP tool name.
        # The actual search string is the user's query — never the briefing.
        sample_query = (
            unit_of_work.get("query")
            or unit_of_work.get("objective")
            or ""
        )

        # Emit healthy tools first (unchanged behaviour)
        for prod in healthy_prods:
            mcp_tool = f"mcp__info-broker-mcp__run_{prod.technique_id}"
            lines.append(
                f"  • {mcp_tool}  —  template params: {prod.params_template}"
            )
            lines.append(
                f"    Substitute {{hypothesis_query}}/{{original_query}}/etc. with: \"{sample_query}\""
            )

        # Emit unhealthy tools last, annotated with ⚠
        for prod in unhealthy_prods:
            mcp_tool = f"mcp__info-broker-mcp__run_{prod.technique_id}"
            key_label = _missing_key(prod.technique_id) or "API key"
            lines.append(
                f"  ⚠ {mcp_tool} — UNAVAILABLE (needs {key_label}); prefer the healthy tools above, use this only if no alternative."
            )
            lines.append(
                f"    Substitute {{hypothesis_query}}/{{original_query}}/etc. with: \"{sample_query}\""
            )

        lines += [
            "",
            "### After all tool calls complete:",
            "Emit a single fenced JSON code block (```json ... ```) containing",
            "an array of findings extracted from the tool results. Each finding:",
            "  {",
            '    "candidate":      "the entity/answer name (e.g. React, Wonyoung,',
            '                       Acme Corp). NOT the query string.",',
            '    "source_class":   "live_search",',
            '    "source_url":     "url from the tool result if present",',
            '    "evidence_snippet": "1-2 sentence quote from the result",',
            '    "confidence":     0.0..1.0',
            "  }",
            "",
            "Emit ONE finding per distinct candidate identified across all the",
            "tool results. If a tool returned no relevant data, omit it. The",
            "JSON block is the structured output of this tactic — only emit it",
            "after all tool calls are complete.",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stream-JSON parser (extract tool_use blocks as TaskSpec-compatible dicts)
# ---------------------------------------------------------------------------

def _parse_structured_findings(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract the brain's structured findings JSON block from assistant text.

    The prompt asks the brain to emit a ```json [...] ``` fenced block at the
    end of its response after all tool calls. We parse and return that list.
    Returns an empty list when no parseable block is found.
    """
    import re
    full_text = ""
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                full_text += block.get("text", "") + "\n"

    if not full_text:
        return []

    # Match ```json ... ``` or generic ``` ... ``` blocks containing a JSON array
    patterns = [
        r"```json\s*(\[[\s\S]*?\])\s*```",
        r"```\s*(\[[\s\S]*?\])\s*```",
    ]
    for pat in patterns:
        for match in re.finditer(pat, full_text):
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, list):
                    out = []
                    for item in parsed:
                        if isinstance(item, dict) and item.get("candidate"):
                            out.append(item)
                    if out:
                        return out
            except json.JSONDecodeError:
                continue

    # Fallback: try to find a bare JSON array in the text
    arr_match = re.search(r"\[\s*\{[\s\S]*?\}\s*\]", full_text)
    if arr_match:
        try:
            parsed = json.loads(arr_match.group(0))
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict) and item.get("candidate")]
        except json.JSONDecodeError:
            pass

    return []


def _parse_task_calls_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract tool_use blocks from stream-json events.

    Each tool_use becomes a TaskSpec-compatible dict:
      {technique_id, params_template, expect_schema, fail_modes, budget_ru}
    """
    task_calls: list[dict[str, Any]] = []
    # Index tool_results by their tool_use_id so we can pair them with calls
    results_by_id: dict[str, str] = {}
    for event in events:
        if event.get("type") not in ("assistant", "user"):
            continue
        for content in event.get("message", {}).get("content", []):
            if content.get("type") == "tool_result":
                tid = content.get("tool_use_id", "")
                data = content.get("content", "")
                if isinstance(data, list):
                    parts = [
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in data
                    ]
                    text = "\n".join(parts)
                elif isinstance(data, (dict, list)):
                    text = json.dumps(data)
                else:
                    text = str(data) if data else ""
                if tid:
                    results_by_id[tid] = text

    for event in events:
        etype = event.get("type", "")
        if etype not in ("assistant", "user"):
            continue
        for content in event.get("message", {}).get("content", []):
            if content.get("type") != "tool_use":
                continue
            tool_name = content.get("name", "")
            if not tool_name.startswith("mcp__info-broker-mcp__"):
                continue
            tail = tool_name.split("__")[-1]
            technique_id = tail[4:] if tail.startswith("run_") else tail
            tool_use_id = content.get("id", "")
            inline_result = results_by_id.get(tool_use_id, "")
            task_calls.append({
                "technique_id": technique_id,
                "params_template": content.get("input", {}),
                "expect_schema": {},
                "fail_modes": [],
                "budget_ru": 1,
                "_tool_use_id": tool_use_id,
                # Stdio MCP already returned the result inside the subprocess;
                # carry it forward so the tactician doesn't try to re-execute
                # via HTTP (which fails — see #19). When inline_result is set,
                # the tactician skips the specialist re-call.
                "inline_result": inline_result,
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
    on_failure: Callable[[BrainFailure], None] | None = None,
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

    ensure_claude_credentials()
    spawn_env = {**os.environ, "CLAUDE_CODE_HEADLESS": "1"}
    if api_key:
        spawn_env["ANTHROPIC_API_KEY"] = api_key
    else:
        spawn_env.pop("ANTHROPIC_API_KEY", None)
        # Prefer the auto-refreshing credentials FILE when one is present: its
        # token is kept fresh (by the host CLI via the ~/.claude bind-mount, or
        # a refresh flow), so a stale env token must not shadow it.
        # But when NO creds file is reachable — e.g. the bind-mount isn't
        # effective (Docker Desktop on WSL), or only a long-lived
        # `claude setup-token` env token is provisioned — KEEP
        # CLAUDE_CODE_OAUTH_TOKEN: the headless CLI authenticates with it
        # directly. Popping it unconditionally left the subprocess with no auth
        # ("Not logged in · Please run /login") whenever the file was absent.
        _creds_file = Path("/root/.claude/.credentials.json")
        if _creds_file.exists() and _creds_file.stat().st_size > 0:
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
                                # Build both a SHORT preview (for the card body)
                                # and a FULL output (for the modal). The modal
                                # gets to render the entire structured result;
                                # the card just shows a one-glance summary.
                                full_output: Any = tool_result_data
                                if isinstance(tool_result_data, list):
                                    parts = [
                                        block.get("text", "") if isinstance(block, dict) else str(block)
                                        for block in tool_result_data
                                    ]
                                    preview = "\n".join(p for p in parts if p)[:2000]
                                    if not preview.strip():
                                        try:
                                            preview = json.dumps(tool_result_data, default=str)[:2000]
                                        except Exception:
                                            preview = str(tool_result_data)[:2000]
                                    # Promote a single text block to a plain
                                    # string for the modal (often the MCP tool
                                    # returns one [{type:text, text:"..."}]).
                                    if len(parts) == 1 and parts[0]:
                                        full_output = parts[0]
                                    # If the single text block contains a JSON
                                    # object, expose it as structured data so
                                    # the modal can render findings rather
                                    # than a wall of escaped JSON.
                                    if isinstance(full_output, str) and full_output.strip().startswith(("{", "[")):
                                        try:
                                            full_output = json.loads(full_output)
                                        except Exception:
                                            pass
                                elif isinstance(tool_result_data, (dict, list)):
                                    preview = json.dumps(tool_result_data, default=str)[:2000]
                                else:
                                    preview = str(tool_result_data)[:2000] if tool_result_data else ""

                                # Recursively decode JSON-encoded string fields
                                # so the modal's Raw Output tab renders pretty
                                # JSON, not escape-soup like {"result":"{\\\"..."}.
                                full_output = _deep_parse_json(full_output)

                                # Cap the full output at ~50 KB to keep the
                                # WS frame reasonable. If it exceeds that,
                                # drop output (modal will fall back to
                                # preview); the modal still renders more
                                # than the line-clamped 4-line card body.
                                try:
                                    if len(json.dumps(full_output, default=str)) > 50_000:
                                        full_output = None
                                except Exception:
                                    full_output = None

                                await event_emit({
                                    "type": "is.tool_result",
                                    "run_id": run_id,
                                    "job_id": run_id,
                                    "call_id": content.get("tool_use_id", ""),
                                    "preview": preview,
                                    "output": full_output,
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

        # Surface stderr + event diversity to logs when nothing emitted.
        if proc.stderr is not None:
            try:
                stderr_bytes = await asyncio.wait_for(proc.stderr.read(), timeout=2)
                stderr_text = stderr_bytes.decode(errors="replace").strip()
                if stderr_text:
                    log.warning(
                        "scoped_brain: tactic=%s stderr (rc=%s): %s",
                        tactic.id, proc.returncode, stderr_text[:2000],
                    )
            except asyncio.TimeoutError:
                pass

    except FileNotFoundError:
        log.error("scoped_brain: claude binary not found at %s", _CLAUDE_BIN)
        return []
    except Exception as exc:
        log.error("scoped_brain: unexpected error tactic=%s: %s", tactic.id, exc)
        return []

    task_calls = _parse_task_calls_from_events(all_events)
    # Diagnostic: surface event type distribution when no task calls were produced
    if not task_calls:
        from collections import Counter
        event_types = Counter(e.get("type", "?") for e in all_events)
        tool_use_count = sum(
            1 for e in all_events
            if e.get("type") == "assistant"
            for block in (e.get("message", {}).get("content") or [])
            if isinstance(block, dict) and block.get("type") == "tool_use"
        )
        # Capture what the brain actually said — first assistant text block
        first_text = ""
        for e in all_events:
            if e.get("type") == "assistant":
                for block in (e.get("message", {}).get("content") or []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        first_text = block.get("text", "")[:500]
                        break
                if first_text:
                    break

        # Classify the failure so admin logs name the real cause early.
        # Without this the strategist would surface only "Gate failed on
        # phase X: checks did not pass" — auth / quota / upstream errors
        # would stay invisible until someone read raw stream-json.
        failure = detect_brain_failure(all_events)
        # Notify the caller (engine_v2) so it can override the run's
        # terminate_reason / error_message with the real cause.
        if on_failure is not None:
            try:
                on_failure(failure)
            except Exception as cb_exc:
                log.warning("on_failure callback raised (non-fatal): %s", cb_exc)
        if failure.is_fatal:
            hint = {
                "auth_failed": (
                    "Refresh Claude credentials in the container — "
                    "/root/.claude/.credentials.json OAuth token likely expired. "
                    "Re-run `claude auth login` on the host and copy the file in, "
                    "OR set a real ANTHROPIC_API_KEY (sk-ant-api03-…)."
                ),
                "rate_limited": (
                    "Anthropic API rate limit hit — back off or upgrade tier."
                ),
                "upstream_error": (
                    "Anthropic API returned a server error — transient unless "
                    "it keeps repeating."
                ),
                "no_result_event": (
                    "Subprocess exited without emitting a final result event — "
                    "check for timeout / killed process / stderr."
                ),
            }.get(failure.kind, "Check container logs around this run.")
            log.error(
                "BRAIN_FAILURE tactic=%s slot=%d kind=%s api_status=%s "
                "retries=%d apiKeySource=%s — %s\n"
                "  events=%s tool_use_blocks=%d\n"
                "  brain_message: %r\n"
                "  HINT: %s",
                tactic.id, slot_idx, failure.kind, failure.api_status,
                failure.retry_count, failure.api_key_source, failure.message,
                dict(event_types), tool_use_count,
                failure.message or first_text, hint,
            )
        else:
            # Brain returned cleanly but produced no task_calls — that's a
            # legitimate "model declined to call any tool" outcome, not a
            # failure. Keep at warning so it shows in admin logs but doesn't
            # crowd the error feed.
            log.warning(
                "scoped_brain: tactic=%s slot=%d produced 0 task_calls — "
                "events=%s tool_use_blocks=%d apiKeySource=%s\n"
                "  assistant text: %r",
                tactic.id, slot_idx, dict(event_types), tool_use_count,
                failure.api_key_source, first_text,
            )
    # Harvest the brain's structured-findings JSON block (post-tool-call output).
    # When present, attach to the first task_call so the tactician can prefer
    # these real entity-named findings over the query-as-candidate fallback.
    structured = _parse_structured_findings(all_events)
    if structured:
        log.info(
            "scoped_brain: tactic=%s slot=%d parsed %d structured findings from final JSON block",
            tactic.id, slot_idx, len(structured),
        )
        if task_calls:
            task_calls[0]["structured_findings"] = structured
        else:
            # No tool calls but findings present (rare; brain bypassed tools).
            # Synthesize a placeholder task_call to carry the findings.
            task_calls.append({
                "technique_id": "_structured_only",
                "params_template": {},
                "expect_schema": {},
                "fail_modes": [],
                "budget_ru": 0,
                "_tool_use_id": "",
                "inline_result": "",
                "structured_findings": structured,
            })

    log.info(
        "scoped_brain: tactic=%s slot=%d produced %d task_calls",
        tactic.id, slot_idx, len(task_calls),
    )
    return task_calls
