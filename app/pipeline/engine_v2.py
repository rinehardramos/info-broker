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

def _classify_query_stub(query: str) -> dict[str, Any]:
    """MVP stub: always returns celebrity_identification task_type."""
    return {"task_type": "celebrity_identification"}


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
    from app.pipeline.runners.scoped_brain import scoped_brain_runner

    def _make_tactic_runner_fn(phase: PhaseSpec, slot_idx: int):
        """Return a synchronous wrapper that the tactician expects.

        tactician.execute_tactician calls: tactic_runner_fn(prompt, model) -> list[dict]
        But our scoped_brain_runner is async and needs more context.
        We capture phase/slot in closure and run the coroutine synchronously.
        """
        def _tactic_runner_fn(prompt: str, model: str) -> list[dict]:
            # Retrieve tactic from the prompt to pass to scoped_brain_runner.
            # The tactician already selected the tactic and built the prompt;
            # we need the tactic object.  Look it up from prompt prefix.
            # MVP: tactic selection is deterministic — re-derive from slot_idx and tactics.
            from app.pipeline.tactician import _select_tactic
            tactic = _select_tactic(slot_idx, {}, tactics, phase)
            if tactic is None:
                return []

            # Run the async scoped_brain_runner in the current event loop
            loop = asyncio.get_event_loop()
            # unit_of_work is embedded in the prompt string; we pass {} as a
            # lightweight stand-in since the prompt already encodes it.
            coro = scoped_brain_runner(
                tactic=tactic,
                unit_of_work={"briefing": prompt},
                capability_tier=envelope.capability,
                budget_ru=hold_amount_ru,
                event_emit=event_emit,
                run_id=run_id,
                slot_idx=slot_idx,
            )
            # Within an async context we can't use loop.run_until_complete.
            # Use asyncio.ensure_future + a manual wait via a Future.
            import concurrent.futures
            future: concurrent.futures.Future = concurrent.futures.Future()

            async def _run():
                try:
                    result = await coro
                    future.set_result(result)
                except Exception as exc:
                    future.set_exception(exc)

            asyncio.ensure_future(_run())
            # Spin the event loop until the future resolves.
            # NOTE: this blocks the calling coroutine's thread — acceptable for
            # MVP where each tactician slot runs in the same asyncio task.
            # Post-MVP: refactor tactician to accept async tactic_runner_fn.
            while not future.done():
                loop.run_until_complete(asyncio.sleep(0.05))

            try:
                return future.result()
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
        })

        tactic_runner_fn = _make_tactic_runner_fn(phase, slot_idx)

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

        # Return the shape strategist._aggregate() expects.
        # slot_idx is included so _aggregate can tag findings with hypothesis_slot.
        return {
            "slot_idx": slot_idx,
            "findings": output.findings,
            "metadata": {
                **output.metadata,
                "hypotheses_explored": 1,
                "primary_signals_count": len(output.findings),
                "disconfirm_count": output.metadata.get("disconfirm_count", 0),
                "surviving_hypothesis_count": 1 if output.candidate_names else 0,
                "actual_ru": output.metadata.get("ru_spent", 1),
            },
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
    # 10. Write to research_trails
    # ------------------------------------------------------------------
    try:
        _write_research_trail(run_id, user_id, query, result)
    except Exception as exc:
        log.warning("engine_v2: research_trail write failed (non-fatal): %s", exc)

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

    await _emit(event_emit, {
        "type": "is.run_complete",
        "run_id": run_id,
        "job_id": run_id,
        "status": result.status,
        "ranked_candidates": serialized_candidates,
        "ru_consumed": sum_consumed_ru,
        "ru_released": remaining_ru,
    })

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
                "slot_idx": i,
                "candidate_name": finding.get("candidate_name") or finding.get("candidate", ""),
                "source_class": finding.get("source_class", ""),
                "confidence": finding.get("confidence", 0.0),
                "evidence_summary": finding.get("evidence_summary", ""),
            })

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
                "status": result.status,
                "ranked_candidates": result.ranked_candidates,
            }),
            json.dumps([f for p in result.phases for f in p.aggregated_findings]),
            len(branches),
            None,
        ),
    )
