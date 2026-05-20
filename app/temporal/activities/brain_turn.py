"""Per-turn brain activity for the orchestrated IS-brain loop (Path B, Slice 1).

Two activities:
  - init_working_memory: seeds WM with A-graded priors via fused_retrieve, snapshots turn 0
  - run_brain_turn:      reads WM → builds turn prompt → spawns short brain subprocess
                         → parses WorkingMemoryDelta → applies → snapshots → returns

The subprocess plumbing here is a minimal cousin of `app/is_brain.py::run_research`.
Differences: 180s timeout (vs 1800s), no streaming event callback (per-turn UI updates
land via the snapshot endpoint), and the brain emits a WorkingMemoryDelta JSON instead
of the full research envelope.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from temporalio import activity

from app.is_prompt_turn import build_turn_prompt
from app.claude_auth_setup import ensure_claude_credentials
from app.pipeline.runners.working_memory import (
    WorkingMemory,
    WorkingMemoryDelta,
)

log = logging.getLogger(__name__)

_CLAUDE_BIN = os.getenv("CLAUDE_CODE_BIN", "claude")
_MCP_CONFIG = Path(os.getenv(
    "IS_MCP_CONFIG",
    str(Path(__file__).parent.parent.parent.parent / "config" / "is-mcp-config.json"),
))
_TURN_TIMEOUT_SECONDS = int(os.getenv("IS_BRAIN_TURN_TIMEOUT", "180"))


# ── Activity I/O dataclasses (match existing brain.py convention) ─────────────
@dataclass
class InitWorkingMemoryInput:
    run_id: str
    user_id: str
    query: str
    past_research: list[dict] | None = field(default_factory=list)


@dataclass
class BrainTurnInput:
    run_id: str
    user_id: str
    working_memory_json: str        # serialized WorkingMemory (passed via workflow I/O)
    past_research: list[dict] | None = field(default_factory=list)


@dataclass
class BrainTurnOutput:
    working_memory_json: str        # serialized WorkingMemory after apply()
    raw_delta: dict = field(default_factory=dict)
    tool_call_count: int = 0
    error: str | None = None


# ── init_working_memory ───────────────────────────────────────────────────────
@activity.defn(name="init_working_memory")
async def init_working_memory(inp: InitWorkingMemoryInput) -> str:
    """Seed a WorkingMemory at turn 0 with A-graded prior facts + cross-run
    priors retrieved via fused_retrieve. Returns JSON.

    Two channels of prior knowledge:
      · past_research (input) — dispatcher-provided session/parent-run context
      · cross_run_priors (this activity) — semantic + entity + temporal +
        feedback retrieval across the user's full research history
    """
    from app.pipeline.runners.working_memory import Fact

    wm = WorkingMemory(run_id=UUID(inp.run_id), question=inp.query)

    # ── (1) Seed from dispatcher-provided past_research (A-graded only) ──────
    seeded: list[Fact] = []
    for prior in (inp.past_research or []):
        if prior.get("grade") not in ("A", "A1", "A2"):
            continue
        for finding in (prior.get("findings") or [])[:3]:
            claim = (finding.get("title") or finding.get("content") or "").strip()
            if not claim:
                continue
            seeded.append(Fact(
                claim=claim[:500],
                source_url=finding.get("source_url") or finding.get("url"),
                source_tool=finding.get("source_tool") or "prior_research",
                confidence=float(finding.get("confidence", 80)) / 100.0,
                verified_by="user_grade_A",
            ))

    # ── (2) Cross-run memory via fused_retrieve (Tier 1 #1) ──────────────────
    # Best-effort: never fail the run if retrieval errors out.
    # Each prior is decayed by its observed_at + source_tool's shelf life so
    # stale facts (old phone numbers, old social media data) don't get
    # injected with their original confidence.
    cross_run_priors: list[dict] = []
    try:
        from app.memory.retriever import fused_retrieve
        from app.pipeline.fusion.decay import calculate_decay, _SOURCE_TO_TYPE, get_shelf_life
        from datetime import datetime, timezone as _tz
        results = await fused_retrieve(
            query=inp.query, limit=8, user_id=inp.user_id,
        )
        # Dedup by (run_id, title) — the writer doesn't set payload.ref, so
        # all results come back with ref="" and using ref as a dedup key
        # collapses every same-run finding into one. (run_id, title) is the
        # right semantic key for "same observation".
        seen_keys: set[tuple[str, str]] = set()
        for r in results:
            key = (r.run_id or "", (r.title or "").strip().lower())
            if key in seen_keys:
                continue
            seen_keys.add(key)
            # Decay: shelf-life by source_tool. Falls back to default
            # (365 days, linear) when the tool isn't in the registered taxonomy.
            data_type = _SOURCE_TO_TYPE.get(r.source_tool or "", "unknown")
            collected = datetime.now(_tz.utc)   # default: treat as fresh
            if r.observed_at:
                try:
                    collected = datetime.fromisoformat(r.observed_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass
            # base_confidence: use the original payload's confidence if we had
            # it, otherwise 80 (typical for indexed findings).
            base_conf = 80
            decayed = calculate_decay(base_conf, collected, data_type)
            shelf = get_shelf_life(data_type)
            cross_run_priors.append({
                "ref": r.ref,
                "title": r.title,
                "content": (r.content or "")[:500],
                "source": r.source,
                "score": float(r.score),
                "run_id": r.run_id,
                "user_score": r.user_score,
                "observed_at": r.observed_at,
                "source_tool": r.source_tool,
                "data_type": data_type,
                "shelf_life_days": shelf["days"],
                "decayed_confidence": decayed,
                "base_confidence": base_conf,
            })
            # A-graded (user_score > 0) also seeds established_facts. Apply
            # decay so a 2-year-old phone-number fact doesn't get injected as
            # 90% confidence today.
            if r.user_score > 0 and decayed > 0:
                seeded.append(Fact(
                    claim=(r.title or r.content[:200] or "").strip()[:500],
                    source_url=None,
                    source_tool=r.source_tool or "prior_research",
                    confidence=decayed / 100.0,    # ← was hardcoded 0.9
                    verified_by="user_grade_A",
                ))
    except Exception as exc:
        log.warning("init_working_memory: fused_retrieve failed (non-fatal): %s", exc)

    update: dict = {}
    if seeded:
        # Dedup facts by claim before assignment
        seen_claims: set[str] = set()
        unique = []
        for f in seeded:
            k = f.claim.strip().lower()
            if k in seen_claims:
                continue
            seen_claims.add(k)
            unique.append(f)
        update["established_facts"] = unique
    if cross_run_priors:
        update["cross_run_priors"] = cross_run_priors
    if update:
        wm = wm.model_copy(update=update)

    log.info(
        "init_working_memory run=%s seeded_facts=%d cross_run_priors=%d graded=%d",
        inp.run_id, len(seeded),
        len(cross_run_priors),
        sum(1 for p in cross_run_priors if (p.get("user_score") or 0) > 0),
    )
    _snapshot_to_db(inp.run_id, wm)
    return wm.model_dump_json()


# ── run_brain_turn ────────────────────────────────────────────────────────────
@activity.defn(name="run_brain_turn")
async def run_brain_turn(inp: BrainTurnInput) -> BrainTurnOutput:
    """Run one brain turn: read WM, build prompt, spawn subprocess, parse delta, apply."""
    wm = WorkingMemory.model_validate_json(inp.working_memory_json)
    wm = wm.model_copy(update={"turn": wm.turn + 1})  # increment turn counter

    prompt = build_turn_prompt(wm, past_research=inp.past_research or [])

    heartbeat_task = asyncio.create_task(_heartbeat_loop())
    try:
        result_text, tool_call_count, err = await _spawn_brain_turn_subprocess(
            prompt, phase=wm.phase,
        )
        if err:
            return BrainTurnOutput(
                working_memory_json=wm.model_dump_json(),
                error=err,
                tool_call_count=tool_call_count,
            )

        delta_dict = _parse_delta_from_result(result_text)
        # Empty-delta observability: this is the silent-regression failure mode
        # (brain produces JSON but it has no actual changes — usually means the
        # prompt overwhelmed it). Log the raw text length and a head so we can
        # diagnose without re-running.
        if not delta_dict:
            log.warning(
                "brain_turn run=%s turn=%s phase=%s EMPTY DELTA (parse=%s, raw_len=%d, head=%r)",
                inp.run_id, wm.turn, wm.phase,
                "no-json" if delta_dict == {} else "empty",
                len(result_text), result_text[:200],
            )
        try:
            delta = WorkingMemoryDelta.model_validate(delta_dict)
        except Exception as exc:
            log.warning("brain_turn: delta validation failed: %s; treating as no-op", exc)
            return BrainTurnOutput(
                working_memory_json=wm.model_dump_json(),
                raw_delta=delta_dict,
                tool_call_count=tool_call_count,
                error=f"delta_validation_failed: {exc}",
            )

        new_wm = wm.apply(delta)
        _snapshot_to_db(inp.run_id, new_wm)

        # Per-turn cost recording — best-effort, never fails the run.
        # RU cost estimate: 2 baseline + 5 per tool call (rough but consistent).
        # Phase-indexed for the /cost_breakdown endpoint (which aggregates by phase).
        _record_turn_cost(
            run_id=inp.run_id, user_id=inp.user_id,
            phase=new_wm.phase, turn=new_wm.turn,
            tool_call_count=tool_call_count,
        )

        # Observability: log a compact line per turn so we can audit whether
        # the brain emitted hypothesis_updates (the load-bearing analytical
        # signal) and which IDs it used.
        hup = delta.hypothesis_updates or []
        log.info(
            "brain_turn run=%s turn=%s phase=%s "
            "new_hyps=%d hyp_updates=%d (ids=%s) "
            "new_findings=%d new_facts=%d strategies=%d synthesis_len=%d",
            inp.run_id, new_wm.turn, new_wm.phase,
            len(delta.new_hypotheses), len(hup),
            ",".join(u.id[:8] for u in hup) or "-",
            len(delta.new_findings_data), len(delta.new_facts),
            len(delta.new_strategies),
            len(delta.synthesis_summary or ""),
        )
        return BrainTurnOutput(
            working_memory_json=new_wm.model_dump_json(),
            raw_delta=delta.model_dump(),
            tool_call_count=tool_call_count,
        )
    finally:
        heartbeat_task.cancel()


# ── subprocess plumbing (minimal version of is_brain.run_research) ────────────
async def _spawn_brain_turn_subprocess(
    prompt: str,
    *,
    phase: str = "explore",
) -> tuple[str, int, str | None]:
    """Spawn claude with the turn prompt + phase-gated tool allowlist.

    The allowlist is hard-enforced via the --allowedTools CLI arg. Synthesize
    phase has no research tools at all, forcing the brain to produce the answer
    from accumulated findings rather than re-searching.
    """
    from app.pipeline.runners.working_memory import allowed_tools_for_phase

    cmd = [_CLAUDE_BIN, "-p", prompt, "--output-format", "stream-json", "--verbose"]
    allowed_count = 0
    if _MCP_CONFIG.exists():
        cmd.extend(["--mcp-config", str(_MCP_CONFIG)])
        allowed = allowed_tools_for_phase(phase)
        if allowed:
            cmd.extend(["--allowedTools", ",".join(allowed)])
            allowed_count = len(allowed)
    log.info(
        "brain_turn spawn phase=%s allowed_tools=%d (gated)",
        phase, allowed_count,
    )

    ensure_claude_credentials()
    spawn_env = {**os.environ, "CLAUDE_CODE_HEADLESS": "1"}
    # Subscription auth path: clear stale env vars so credentials file is used.
    spawn_env.pop("ANTHROPIC_API_KEY", None)
    spawn_env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    spawn_env.pop("CLAUDE_CODE_OAUTH_REFRESH_TOKEN", None)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=spawn_env,
            limit=10 * 1024 * 1024,
        )
    except FileNotFoundError:
        return ("", 0, f"claude binary not found at {_CLAUDE_BIN}")

    result_line: str | None = None
    tool_calls = 0

    async def _read_lines() -> None:
        nonlocal result_line, tool_calls
        try:
            async for raw in proc.stdout:
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = event.get("type", "")
                if etype in ("assistant", "user"):
                    for content in event.get("message", {}).get("content", []):
                        if content.get("type") == "tool_use":
                            tool_calls += 1
                if etype == "result":
                    result_line = line
        except asyncio.LimitOverrunError:
            pass

    timed_out = False
    try:
        await asyncio.wait_for(_read_lines(), timeout=_TURN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        timed_out = True
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    await proc.wait()

    if proc.returncode != 0 and not result_line:
        try:
            stderr_out = (await asyncio.wait_for(proc.stderr.read(), timeout=2)).decode(errors="replace")
        except Exception:
            stderr_out = ""
        return ("", tool_calls, f"claude exit {proc.returncode}: {stderr_out[:200]}")
    if timed_out and not result_line:
        return ("", tool_calls, f"turn timed out after {_TURN_TIMEOUT_SECONDS}s")
    if not result_line:
        return ("", tool_calls, "claude produced no result line")
    return (result_line, tool_calls, None)


def _parse_delta_from_result(line: str) -> dict:
    """Pull the WorkingMemoryDelta JSON object out of the claude result line."""
    try:
        envelope = json.loads(line)
    except json.JSONDecodeError:
        return {}
    result_text = envelope.get("result", "") if isinstance(envelope, dict) else ""
    # Try as JSON first; fall back to first-{ ... last-} extraction.
    for candidate in (result_text, _extract_json(result_text or "")):
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return {}


def _extract_json(text: str) -> str | None:
    import re
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return None


# Phase → numeric phase index for the consume() API. Stable so the
# /cost_breakdown endpoint can resolve op="consume_phase_N" back to a phase
# name for the UI.
_PHASE_TO_INDEX = {"explore": 0, "test": 1, "synthesize": 2}


def _record_turn_cost(
    *, run_id: str, user_id: str, phase: str, turn: int, tool_call_count: int,
) -> None:
    """Charge the user's wallet for this turn. RU = 2 base + 5 * tool_calls.

    Best-effort: failures are logged but never bubble up. Per-turn idempotency
    key prevents double-charging on Temporal activity retries.
    """
    actual_ru = 2 + 5 * max(0, tool_call_count)
    phase_n = _PHASE_TO_INDEX.get(phase, 0)
    try:
        from app.pipeline.budget import consume
        result = consume(
            user_id=user_id, run_id=run_id, phase_n=phase_n,
            actual_ru=actual_ru,
            idempotency_key=f"{run_id}-turn-{turn}",
        )
        if not result.ok:
            log.warning(
                "turn cost record failed (non-fatal): %s",
                getattr(result, "reason", ""),
            )
    except Exception as exc:
        log.warning("turn cost record errored (non-fatal): %s", exc)


def _snapshot_to_db(run_id: str, wm: WorkingMemory) -> None:
    """Insert one row per turn. Idempotent on (run_id, turn) via ON CONFLICT."""
    try:
        from app.routers.v3.db import execute
        execute(
            """
            INSERT INTO working_memory_snapshots (run_id, turn, phase, working_memory)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (run_id, turn) DO UPDATE
              SET phase = EXCLUDED.phase,
                  working_memory = EXCLUDED.working_memory,
                  created_at = now()
            """,
            (run_id, wm.turn, wm.phase, wm.model_dump_json()),
        )
    except Exception as exc:
        # Snapshot failure must not kill the turn — log + continue.
        log.warning("brain_turn: snapshot write failed (run=%s turn=%s): %s",
                    run_id, wm.turn, exc)


async def _heartbeat_loop() -> None:
    while True:
        await asyncio.sleep(30)
        try:
            activity.heartbeat("brain turn running")
        except Exception:
            break
