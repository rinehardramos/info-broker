"""engine_v2.py — top-level orchestrator for the three-tier pipeline (MVP-M9).

Wired behind ?engine=v2 via the preflight/confirm endpoint.  Takes a preflight
hold_id (already reserved by preflight/confirm) and runs the full
Strategist → tactician_fn(real) → tactic_runner_fn(real) → specialist_fn(real)
end-to-end.

Budget contract:
  - hold_id was placed by preflight/confirm before engine_v2 is called.
  - After each completed phase: wallet.consume(...)
  - On success: wallet.release(remaining_ru)
  - On system error before any phase: wallet.refund(full_hold_amount_ru)

Event emission:
  All events go through the event_emit callable (which wraps push_event in
  production).  Event names MATCH the existing is.tool_call / is.tool_result
  names used by the legacy engine so the frontend live view renders without
  changes.

Design ref: docs/intelligence/three-tier-brain-architecture.md §3, §9, §10.1
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import uuid as _uuid_mod
from typing import Any, Callable

from app.pipeline.catalogs.budget import BudgetEnvelope
from app.pipeline.catalogs.schemas import PhaseSpec
from app.pipeline.catalogs.loader import load_catalog
from app.pipeline.strategist import Strategist, RunResult
from app.pipeline.tactician import execute_tactician
from app.pipeline.specialist import execute_task
from app.pipeline import budget as wallet
from app.pipeline.ach import ach_matrix_to_dict

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Catalog base path (resolved relative to this file)
# ---------------------------------------------------------------------------

from pathlib import Path as _Path

_CATALOG_BASE = _Path(__file__).parent / "catalogs" / "registries"


def _load_all_catalogs() -> tuple[dict, dict, dict]:
    """Return (strategies, tactics, techniques) from the catalog registries."""
    strategies = load_catalog("strategy", _CATALOG_BASE / "strategies")
    tactics = load_catalog("tactic", _CATALOG_BASE / "tactics")
    techniques = load_catalog("technique", _CATALOG_BASE / "techniques")
    return strategies, tactics, techniques


# ---------------------------------------------------------------------------
# Classifier stub (§10.1 — replace post-MVP with real LLM classifier)
# ---------------------------------------------------------------------------

def _classify_query_stub(query: str, *, retriever_fn: Any = None) -> dict[str, Any]:
    """MVP stub: returns celebrity_identification task_type with prior candidates.

    P4 extension: also returns rag_hits from the real RAG retriever (when
    available) and classifier_top_candidates (empty in MVP; populated by a
    future LLM-peek classifier).

    Args:
        query:        The sanitized user query.
        retriever_fn: Optional callable(query, user_id) -> list[str] for RAG
                      lookup.  In production this wraps app.memory.retriever.
                      In tests it is omitted (rag_hits returns empty list).

    Returns:
        {
            "task_type": "celebrity_identification",
            "rag_hits": [...],                    # candidate names from RAG
            "classifier_top_candidates": [...],  # candidate names from LLM peek (empty in MVP)
        }
    """
    rag_hits: list[str] = []
    if retriever_fn is not None:
        try:
            rag_hits = list(retriever_fn(query) or [])
        except Exception as exc:
            log.warning("_classify_query_stub: RAG retriever failed (non-fatal): %s", exc)

    return {
        "task_type": "celebrity_identification",
        "rag_hits": rag_hits,
        "classifier_top_candidates": [],  # TODO(post-MVP): LLM-peek classifier
    }


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------

async def _emit(event_emit: Callable, payload: dict) -> None:
    """Safely call event_emit; swallow errors so brain output is never lost."""
    try:
        if inspect.iscoroutinefunction(event_emit):
            await event_emit(payload)
        else:
            event_emit(payload)
    except Exception as exc:
        log.warning("engine_v2: event_emit failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_engine_v2(
    user_id: str,
    run_id: str,
    hold_id: str,
    hold_amount_ru: int,
    query: str,
    envelope: BudgetEnvelope,
    strategy_id: str,
    event_emit: Callable,
) -> RunResult:
    """Run the three-tier pipeline end-to-end.

    Args:
        user_id:        Authenticated user ID.
        run_id:         UUID for this run (created by preflight/confirm).
        hold_id:        Wallet hold idempotency key from preflight/confirm.
        hold_amount_ru: RU amount reserved by the hold.
        query:          Sanitized user query.
        envelope:       BudgetEnvelope from preflight.
        strategy_id:    Strategy catalog ID (e.g. "media_identification").
        event_emit:     Async callable(dict) — pushes events to the WS channel.

    Returns:
        RunResult with status, phases, and ranked_candidates.
    """
    log.info(
        "engine_v2: starting run_id=%s user_id=%s strategy=%s hold=%d RU",
        run_id, user_id, strategy_id, hold_amount_ru,
    )

    # Write pipeline_runs row so the research_trails FK is satisfied.
    # Uses the Agent Default pipeline (seeded id) — engine_v2 doesn't
    # belong to a user-authored pipeline.
    try:
        from app.routers.v3.db import execute
        execute(
            """INSERT INTO pipeline_runs (id, pipeline_id, user_id, status, trigger_type, query)
               VALUES (%s, '00000000-0000-4000-8000-000000000001', %s, 'running', 'agent', %s)
               ON CONFLICT (id) DO NOTHING""",
            (run_id, user_id, query),
        )
    except Exception as exc:
        log.warning("engine_v2: pipeline_runs insert failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # 1. Load catalogs
    # ------------------------------------------------------------------
    try:
        strategies, tactics, techniques = _load_all_catalogs()
    except Exception as exc:
        log.error("engine_v2: catalog load failed: %s", exc)
        wallet.refund(user_id, run_id, hold_amount_ru, idempotency_key=f"{run_id}:refund")
        raise

    strategy = strategies.get(strategy_id)
    if strategy is None:
        log.error("engine_v2: unknown strategy_id=%r", strategy_id)
        wallet.refund(user_id, run_id, hold_amount_ru, idempotency_key=f"{run_id}:refund")
        raise ValueError(f"Unknown strategy: {strategy_id!r}")

    # ------------------------------------------------------------------
    # 2. Classify query (stub in MVP)
    # ------------------------------------------------------------------
    classifier_output = _classify_query_stub(query)

    # ------------------------------------------------------------------
    # 3. Build real tactic_runner_fn (wraps scoped_brain_runner)
    # ------------------------------------------------------------------
    from app.pipeline.runners.scoped_brain import (
        scoped_brain_runner, BrainFailure, summarize_brain_failures,
    )

    # Collector for per-slot brain failures (HTTP 401 / 429 / 5xx / no-result).
    # Populated by scoped_brain_runner's on_failure callback. After the run
    # terminates we override terminate_reason with the user-facing summary so
    # admins + the UI see "Brain authentication failed (HTTP 401)" instead of
    # "Gate failed on phase 'broaden': checks did not pass".
    brain_failures: list[BrainFailure] = []

    def _record_brain_failure(f: BrainFailure) -> None:
        brain_failures.append(f)

    def _make_tactic_runner_fn(phase: PhaseSpec, slot_idx: int, unit_of_work: dict):
        """Return an async runner the tactician awaits.

        The unit_of_work IS passed through to scoped_brain so the subprocess
        prompt sees the actual query/objective/scope, not just the tactician's
        pre-formatted briefing.
        """
        async def _tactic_runner_fn(prompt: str, model: str) -> list[dict]:
            from app.pipeline.tactician import _select_tactic
            tactic = _select_tactic(slot_idx, unit_of_work, tactics, phase)
            if tactic is None:
                return []
            try:
                # Merge: the actual UoW (query/objective/scope/forbidden) + the
                # tactician's pre-built prompt as a fallback briefing reference.
                merged_uow = dict(unit_of_work)
                merged_uow.setdefault("briefing", prompt)
                return await scoped_brain_runner(
                    tactic=tactic,
                    unit_of_work=merged_uow,
                    capability_tier=envelope.capability,
                    budget_ru=hold_amount_ru,
                    event_emit=event_emit,
                    run_id=run_id,
                    slot_idx=slot_idx,
                    on_failure=_record_brain_failure,
                )
            except Exception as exc:
                log.error("scoped_brain_runner failed: %s", exc)
                return []

        return _tactic_runner_fn

    # ------------------------------------------------------------------
    # 4. Build real specialist_fn (wraps specialist.execute_task + mcp_adapter)
    # ------------------------------------------------------------------
    from app.pipeline.runners.mcp_adapter import invoke_mcp_tool

    def _specialist_fn(task_spec, technique, mcp_invoke_fn):
        return execute_task(task_spec, technique, mcp_invoke_fn)

    # ------------------------------------------------------------------
    # 5. Build tactician_fn injected into strategist
    # ------------------------------------------------------------------

    async def _tactician_fn(phase: PhaseSpec, unit_of_work: dict, slot_idx: int) -> dict:
        await _emit(event_emit, {
            "type": "is.tactician_start",
            "run_id": run_id,
            "job_id": run_id,
            "phase_id": phase.id,
            "slot_idx": slot_idx,
            "tactic_id": "",
            # P4 audit: UI-P2 TacticianSwimLanes can render forbidden list per slot
            "forbidden_candidates": unit_of_work.get("forbidden_candidates", []),
        })

        tactic_runner_fn = _make_tactic_runner_fn(phase, slot_idx, unit_of_work)

        output = await execute_tactician(
            phase=phase,
            unit_of_work=unit_of_work,
            slot_idx=slot_idx,
            tactics_catalog=tactics,
            techniques_catalog=techniques,
            specialist_fn=_specialist_fn,
            mcp_invoke_fn=invoke_mcp_tool,
            capability_tier=envelope.capability,
            budget_ru=hold_amount_ru // max(1, len(strategy.phases)),
            tactic_runner_fn=tactic_runner_fn,
        )

        await _emit(event_emit, {
            "type": "is.tactician_complete",
            "run_id": run_id,
            "job_id": run_id,
            "phase_id": phase.id,
            "slot_idx": slot_idx,
            "candidate_names": output.candidate_names,
            "findings_count": len(output.findings),
        })

        # Return the shape strategist._aggregate() expects. slot_idx is
        # included so _aggregate can tag findings with hypothesis_slot.
        # Pass tactician metadata through verbatim; only derive missing
        # fields (preserves test fakes that don't include them).
        meta = dict(output.metadata)
        # signal_extraction has no tool calls — the brain just analyzes.
        # Fall back to "1 if we got any output" rather than len(findings).
        if "primary_signals_count" not in meta:
            if phase.id == "signal_extraction":
                meta["primary_signals_count"] = 1
            else:
                meta["primary_signals_count"] = len(output.findings)
        meta.setdefault("hypotheses_explored", 1)
        meta.setdefault("disconfirm_count", 0)
        if "surviving_hypothesis_count" not in meta:
            meta["surviving_hypothesis_count"] = 1 if output.candidate_names else 0
        meta.setdefault("actual_ru", meta.get("ru_spent", 1))
        return {
            "slot_idx": slot_idx,
            "findings": output.findings,
            "metadata": meta,
            "candidate_names": output.candidate_names,
            "ranked_candidates": [],
        }

    # ------------------------------------------------------------------
    # 6. Wrap tactician_fn to emit phase start / complete events
    # ------------------------------------------------------------------

    _current_phase_id: list[str] = [""]  # mutable cell

    _orig_tactician_fn = _tactician_fn

    async def _tracked_tactician_fn(phase: PhaseSpec, unit_of_work: dict, slot_idx: int) -> dict:
        if phase.id != _current_phase_id[0]:
            _current_phase_id[0] = phase.id
            n_tacticians = 1  # emitted before actual gather — best-effort estimate
            await _emit(event_emit, {
                "type": "is.phase_start",
                "run_id": run_id,
                "job_id": run_id,
                "phase_id": phase.id,
                "n_tacticians": n_tacticians,
            })
        return await _orig_tactician_fn(phase, unit_of_work, slot_idx)

    # ------------------------------------------------------------------
    # 7. Phase-complete callback — emits is.phase_complete after gate eval
    # ------------------------------------------------------------------

    async def _phase_complete_cb(phase: PhaseSpec, phase_output: Any, gate_passed: bool) -> None:
        if gate_passed:
            gate_status = "pass"
        elif phase.gate.on_fail == "ask_user":
            gate_status = "ask_user"
        else:
            gate_status = "fail"

        await _emit(event_emit, {
            "type": "is.phase_complete",
            "run_id": run_id,
            "phase_id": phase.id,
            "gate_status": gate_status,
            "distinct_candidate_names": phase_output.distinct_candidate_names,
            "n_tacticians": phase_output.metadata.get("num_tacticians", 0),
        })

    # ------------------------------------------------------------------
    # 8. Run the strategist
    # ------------------------------------------------------------------
    strategist = Strategist(
        strategy=strategy,
        envelope=envelope,
        run_id=run_id,
        user_id=user_id,
        hold_id=hold_id,
    )

    sum_consumed_ru = 0
    original_consume = wallet.consume

    def _tracked_consume(
        user_id: str,
        run_id: str,
        phase_n: int,
        actual_ru: int,
        idempotency_key: str,
    ):
        nonlocal sum_consumed_ru
        sum_consumed_ru += actual_ru
        return original_consume(user_id, run_id, phase_n, actual_ru, idempotency_key)

    try:
        # Patch wallet.consume to track RU consumed across phases
        import app.pipeline.strategist as _strat_mod
        _orig_wallet_consume = _strat_mod.wallet.consume
        _strat_mod.wallet.consume = _tracked_consume

        result = await strategist.execute(
            query=query,
            classifier_output=classifier_output,
            tactician_fn=_tracked_tactician_fn,
            phase_complete_cb=_phase_complete_cb,
            event_emit=event_emit,
        )

    except Exception as exc:
        log.error("engine_v2: strategist raised system error: %s", exc)
        # Emit phase-level events are best-effort; refund the full hold
        wallet.refund(user_id, run_id, hold_amount_ru, idempotency_key=f"{run_id}:refund")
        raise

    finally:
        # Restore wallet.consume
        try:
            _strat_mod.wallet.consume = _orig_wallet_consume  # type: ignore[possibly-undefined]
        except Exception:
            pass

    # Backfill ranked_candidates + ach_matrix when the strategist exited via an
    # early-return path (ask_user, terminated) that bypassed enrichment. The
    # broaden phase's distinct_candidate_names are the surviving hypotheses;
    # ACH scoring works from the aggregated findings regardless of which exit
    # path was taken.
    if not result.ranked_candidates and result.phases:
        try:
            from app.pipeline.strategist import _enrich_ranked_candidates
            from app.pipeline.ach import ACHSignal
            broaden = next((p for p in result.phases if p.phase_id == "broaden"), None)
            raw_ranked: list[dict] = []
            if broaden and broaden.distinct_candidate_names:
                raw_ranked = [
                    {"name": n, "confidence": 0.5}
                    for n in broaden.distinct_candidate_names
                ]
            if raw_ranked:
                ach_signals_dicts = getattr(strategy, "ach_signals", []) or []
                ach_signals = None
                if ach_signals_dicts:
                    ach_signals = [
                        ACHSignal(
                            id=s["id"], label=s["label"],
                            weight=float(s["weight"]),
                            penalty_on_mismatch=float(s["penalty_on_mismatch"]),
                        )
                        for s in ach_signals_dicts
                    ]
                ranked, ach = _enrich_ranked_candidates(
                    raw_ranked=raw_ranked,
                    all_phase_outputs=result.phases,
                    strategy_id=strategy.id,
                    ach_signals=ach_signals,
                )
                if ranked:
                    result.ranked_candidates = ranked
                    if ach is not None:
                        result.ach_matrix = ach
                    log.info(
                        "engine_v2: backfilled %d ranked_candidates + ACH matrix from broaden phase",
                        len(ranked),
                    )
        except Exception as exc:
            log.warning("engine_v2: ranked_candidates backfill failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # 9. Release unused hold
    # ------------------------------------------------------------------
    remaining_ru = max(0, hold_amount_ru - sum_consumed_ru)
    if remaining_ru > 0:
        wallet.release(
            user_id, run_id, remaining_ru,
            idempotency_key=f"{run_id}:release",
        )

    # ------------------------------------------------------------------
    # 10. Write to research_trails + finalize pipeline_runs
    # ------------------------------------------------------------------
    try:
        _write_research_trail(run_id, user_id, query, result)
    except Exception as exc:
        log.warning("engine_v2: research_trail write failed (non-fatal): %s", exc)

    try:
        from app.routers.v3.db import execute
        terminal_status = {
            "completed": "succeeded",
            "terminated": "failed",
            "ask_user": "ask_user",
        }.get(result.status, "failed")
        # Override terminate_reason with the structured brain-failure summary
        # when one was recorded. Without this the user sees "Gate failed on
        # phase 'broaden': checks did not pass" — the strategist's downstream
        # symptom — instead of the actual upstream cause (auth / rate-limit /
        # upstream / no-result). Only kicks in for terminated runs; completed
        # and ask_user runs use the original reason.
        error_message = result.terminate_reason
        if terminal_status == "failed":
            brain_summary = summarize_brain_failures(brain_failures)
            if brain_summary:
                error_message = brain_summary
                log.info(
                    "engine_v2: overrode terminate_reason with brain-failure summary: %s",
                    brain_summary,
                )
        execute(
            """UPDATE pipeline_runs
                  SET status = %s, finished_at = now(),
                      error_message = %s
                WHERE id = %s""",
            (terminal_status, error_message, run_id),
        )
    except Exception as exc:
        log.warning("engine_v2: pipeline_runs update failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # 11. Emit run_complete event
    # ------------------------------------------------------------------
    # Serialize ranked_candidates explicitly to guarantee the enriched shape
    # (name, confidence, signal_scores, evidence[], slot_idx) is present even
    # if the RunResult was populated by an older code path.
    serialized_candidates = []
    for c in result.ranked_candidates:
        if isinstance(c, dict):
            serialized_candidates.append({
                "name": c.get("name", ""),
                "confidence": c.get("confidence", 0.0),
                "signal_scores": c.get("signal_scores", {}),
                "evidence": c.get("evidence", []),
                "slot_idx": c.get("slot_idx", 0),
            })

    # Serialize ach_matrix if present on the RunResult
    serialized_ach_matrix = None
    if result.ach_matrix is not None:
        try:
            serialized_ach_matrix = ach_matrix_to_dict(result.ach_matrix)
        except Exception as exc:
            log.warning("engine_v2: ach_matrix serialization failed (non-fatal): %s", exc)

    run_complete_payload: dict = {
        "type": "is.run_complete",
        "run_id": run_id,
        "job_id": run_id,
        "status": result.status,
        "ranked_candidates": serialized_candidates,
        "ru_consumed": sum_consumed_ru,
        "ru_released": remaining_ru,
    }
    if serialized_ach_matrix is not None:
        run_complete_payload["ach_matrix"] = serialized_ach_matrix
    # If the run halted at an ask_user gate, surface the question text so the
    # chat panel can render it. Without this the run is shown as "ask_user"
    # in the right-rail but the user has nothing to answer. Emit a
    # `brain.question` event for AgentChat in addition to the question on
    # the run_complete payload so existing consumers keep working.
    if result.status == "ask_user" and getattr(result, "user_question", None):
        run_complete_payload["user_question"] = result.user_question
        await _emit(event_emit, {
            "type": "brain.question",
            "run_id": run_id,
            "job_id": run_id,
            "question": result.user_question,
            "options": [],
        })

    await _emit(event_emit, run_complete_payload)

    # Pre-warm entity-profile cache for the top candidates so the user gets
    # an instant evidence modal. Fire-and-forget — never blocks completion,
    # never raises. Skipped for runs with <2 candidates (no comparison view).
    if result.status == "completed" and len(result.ranked_candidates) >= 2:
        try:
            from app.services.entity_enrichment import build_profile
            from app.routers.v3.db import execute as _execute, fetch_one as _fetch_one
            import hashlib as _hashlib
            import json as _json
            ctx_hash = _hashlib.sha256(
                (query or "").strip().lower().encode("utf-8"),
            ).hexdigest()[:32]

            async def _prefetch(cand_name: str, evidence_urls: list[str]) -> None:
                try:
                    if _fetch_one(
                        "SELECT 1 FROM entity_profiles WHERE name = %s AND context_hash = %s",
                        (cand_name, ctx_hash),
                    ):
                        return
                    payload = await build_profile(
                        name=cand_name, context=query, evidence_urls=evidence_urls,
                    )
                    _execute(
                        """INSERT INTO entity_profiles (name, context_hash, entity_type, payload)
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT (name, context_hash) DO NOTHING""",
                        (cand_name, ctx_hash, payload.get("entity_type"), _json.dumps(payload)),
                    )
                except Exception as exc:
                    log.debug("prefetch entity-profile for %s failed: %s", cand_name, exc)

            for c in result.ranked_candidates[:3]:
                if not isinstance(c, dict):
                    continue
                name = (c.get("name") or "").strip()
                if not name:
                    continue
                evidence_urls = [
                    e.get("source_url") for e in (c.get("evidence") or [])
                    if isinstance(e, dict) and e.get("source_url")
                ][:6]
                asyncio.create_task(_prefetch(name, evidence_urls))
        except Exception as exc:  # pragma: no cover
            log.debug("prefetch dispatch failed: %s", exc)

    log.info(
        "engine_v2: run_id=%s finished status=%s consumed=%d released=%d",
        run_id, result.status, sum_consumed_ru, remaining_ru,
    )
    return result


# ---------------------------------------------------------------------------
# Research trail writer
# ---------------------------------------------------------------------------

def _write_research_trail(
    run_id: str,
    user_id: str,
    query: str,
    result: RunResult,
) -> None:
    """Insert a research_trail row compatible with the existing schema.

    branches is a list of per-tactician outputs, one entry per phase×slot.
    This structure supports the M9 gate checks (distinct_candidate_names,
    source_class diversity).
    """
    from app.routers.v3.db import execute, fetch_one

    branches: list[dict] = []
    for phase_output in result.phases:
        for i, finding in enumerate(phase_output.aggregated_findings):
            branches.append({
                "phase_id": phase_output.phase_id,
                "slot_idx": finding.get("hypothesis_slot", i),
                "candidate_name": finding.get("candidate_name") or finding.get("candidate", ""),
                "source_class": finding.get("source_class", ""),
                "confidence": finding.get("confidence", 0.0),
                "source_url": finding.get("source_url"),
                "evidence_summary": finding.get("evidence_summary") or finding.get("evidence_snippet", ""),
                "is_disconfirm": finding.get("is_disconfirm", False),
            })

    # Rich phase metadata for replay reconstruction
    phases_full: list[dict] = []
    for p in result.phases:
        phases_full.append({
            "phase_id": p.phase_id,
            "status": "passed",  # only completed phases reach this point
            "distinct_candidate_names": p.distinct_candidate_names,
            "metadata": p.metadata,
        })

    # ACH matrix (P5) — serialize if present
    ach: dict | None = None
    if result.ach_matrix is not None:
        from app.pipeline.ach import ach_matrix_to_dict
        try:
            ach = ach_matrix_to_dict(result.ach_matrix)
        except Exception:
            ach = None

    trail_id = str(_uuid_mod.uuid4())
    execute("DELETE FROM research_trails WHERE run_id = %s", (run_id,))
    execute(
        """INSERT INTO research_trails
            (id, user_id, run_id, query, entity_type, trail, findings, tool_calls, suggested_pipeline)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            trail_id,
            user_id,
            run_id,
            query,
            "media",
            json.dumps({
                "branches": branches,
                "phases": [p.phase_id for p in result.phases],
                "phases_full": phases_full,
                "status": result.status,
                "ranked_candidates": result.ranked_candidates,
                "ach_matrix": ach,
                "terminate_reason": result.terminate_reason,
            }),
            json.dumps([f for p in result.phases for f in p.aggregated_findings]),
            len(branches),
            None,
        ),
    )
