"""IS Loop Run Temporal workflow — Path B (orchestrated multi-turn brain).

Parallel workflow alongside ISRunWorkflow. Selected by IS_USE_LOOP=true (read
in the agent dispatcher, not here). Each turn = one Temporal activity =
`run_brain_turn`. The workflow body owns phase transitions and termination —
the LLM does NOT decide when the run ends.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.preflight import (
        PreflightInput, PreflightResult, MarkAwaitingInput,
        preflight_validation, mark_awaiting_input,
    )
    from app.temporal.activities.conflict_check import (
        ConflictCheckInput, ConflictCheckResult, conflict_check,
    )
    from app.temporal.activities.budget import (
        ReserveBudgetInput, ReservationResult, AbortInput,
        reserve_budget, release_budget_and_mark_failed,
    )
    from app.temporal.activities.brain_turn import (
        BrainTurnInput, BrainTurnOutput, InitWorkingMemoryInput,
        init_working_memory, run_brain_turn,
    )
    from app.temporal.activities.post_process import PostProcessInput, post_process
    from app.pipeline.runners.working_memory import (
        MAX_TURNS_DEFAULT, WorkingMemory,
        compute_next_phase, should_terminate,
        pick_target_hypothesis, is_stagnant_in_test, abandon_open_hypotheses,
    )

log = logging.getLogger(__name__)

_STANDARD_RETRY = RetryPolicy(
    maximum_attempts=3, initial_interval=timedelta(seconds=2), backoff_coefficient=2.0,
)
_TURN_RETRY = RetryPolicy(
    maximum_attempts=2, initial_interval=timedelta(seconds=5), backoff_coefficient=2.0,
)
_NO_RETRY = RetryPolicy(maximum_attempts=1)


@dataclass
class ISLoopRunInput:
    run_id: str
    user_id: str
    org_id: str
    query: str
    pipeline_id: str
    session_id: str | None = None
    session_context: str = ""
    past_research: list[dict] = field(default_factory=list)
    budget: dict = field(default_factory=dict)
    callback_url: str | None = None
    preflight_prior_slots: dict = field(default_factory=dict)
    max_turns: int = MAX_TURNS_DEFAULT
    mode_id: str = "general"


@workflow.defn(name="IsLoopRunWorkflow")
class IsLoopRunWorkflow:
    """Orchestrated multi-turn IS brain loop with explicit phase machine."""

    def __init__(self) -> None:
        self._brain_answer: str | None = None
        self._cancelled: bool = False
        self._phase: str = "init"
        self._turn: int = 0

    @workflow.signal
    async def brain_answer(self, answer: str) -> None:
        self._brain_answer = answer

    @workflow.signal
    async def cancel_run(self) -> None:
        self._cancelled = True

    @workflow.query
    def get_run_status(self) -> str:
        return f"{self._phase}:turn={self._turn}"

    @workflow.run
    async def run(self, inp: ISLoopRunInput) -> str:
        workflow.logger.info("IsLoopRunWorkflow starting run_id=%s", inp.run_id)
        self._phase = "preflight"

        # 1. PreFlight
        preflight: PreflightResult = await workflow.execute_activity(
            preflight_validation,
            PreflightInput(query=inp.query, prior_slots=inp.preflight_prior_slots or None),
            schedule_to_close_timeout=timedelta(seconds=60),
            retry_policy=_STANDARD_RETRY,
        )

        if preflight.blocking:
            self._phase = "awaiting_input"
            await workflow.execute_activity(
                mark_awaiting_input,
                MarkAwaitingInput(
                    run_id=inp.run_id,
                    question=preflight.first_question or "",
                    options=preflight.first_question_options,
                ),
                schedule_to_close_timeout=timedelta(seconds=30),
                retry_policy=_STANDARD_RETRY,
            )
            await workflow.wait_condition(
                lambda: self._brain_answer is not None or self._cancelled,
                timeout=timedelta(minutes=10),
            )
            if self._cancelled:
                await self._abort(inp, "cancelled_by_user")
                return "cancelled"
            inp.query = f"{inp.query}\n\nClarification: {self._brain_answer}"
            self._brain_answer = None  # reset for any future ask_user pauses

        # 1.5 Pre-research conflict-detection gate (Tier 1 priority #2).
        # One Gemini call asks "is the query unambiguous about which entity/
        # scope/time?" If not, block with a clarification question BEFORE
        # spending any research budget. Fail-open if no LLM available.
        self._phase = "conflict_check"
        try:
            cc: ConflictCheckResult = await workflow.execute_activity(
                conflict_check,
                ConflictCheckInput(query=inp.query),
                schedule_to_close_timeout=timedelta(seconds=30),
                retry_policy=_NO_RETRY,
            )
        except Exception as exc:
            workflow.logger.warning("conflict_check activity errored (fail-open): %s", exc)
            cc = ConflictCheckResult(ambiguous=False)

        if cc.ambiguous and cc.clarification_question:
            self._phase = "awaiting_input"
            await workflow.execute_activity(
                mark_awaiting_input,
                MarkAwaitingInput(
                    run_id=inp.run_id,
                    question=f"[Pre-research check — {cc.ambiguity_kind}] {cc.clarification_question}",
                    options=cc.options or None,
                ),
                schedule_to_close_timeout=timedelta(seconds=30),
                retry_policy=_STANDARD_RETRY,
            )
            await workflow.wait_condition(
                lambda: self._brain_answer is not None or self._cancelled,
                timeout=timedelta(minutes=10),
            )
            if self._cancelled:
                await self._abort(inp, "cancelled_by_user")
                return "cancelled"
            inp.query = f"{inp.query}\n\nDisambiguation: {self._brain_answer}"
            self._brain_answer = None

        # 2. Reserve budget — multiplied estimate to cover N turns
        self._phase = "budget"
        # The reserve activity reads inp.budget; pre-multiply daily/per_run there.
        loop_budget = dict(inp.budget or {})
        for key in ("per_run_ru", "per_run_max_ru"):
            if key in loop_budget and isinstance(loop_budget[key], (int, float)):
                loop_budget[key] = int(loop_budget[key] * inp.max_turns)
        reservation: ReservationResult = await workflow.execute_activity(
            reserve_budget,
            ReserveBudgetInput(
                run_id=inp.run_id, user_id=inp.user_id, org_id=inp.org_id,
                budget=loop_budget,
            ),
            schedule_to_close_timeout=timedelta(seconds=30),
            retry_policy=_STANDARD_RETRY,
        )
        if not reservation.ok:
            await self._abort(inp, f"insufficient_budget: {reservation.reason}")
            return "failed"
        if self._cancelled:
            await self._abort(inp, "cancelled_by_user")
            return "cancelled"

        # 3. Initialize working memory (seeds A-graded facts from past_research)
        self._phase = "init_wm"
        wm_json: str = await workflow.execute_activity(
            init_working_memory,
            InitWorkingMemoryInput(
                run_id=inp.run_id, user_id=inp.user_id,
                query=inp.query, past_research=inp.past_research or [],
                mode_id=inp.mode_id,
            ),
            schedule_to_close_timeout=timedelta(seconds=60),
            retry_policy=_STANDARD_RETRY,
        )

        # 4. The loop — workflow-owned phase machine + termination
        self._phase = "running"
        terminate_reason = ""
        while True:
            self._turn += 1
            try:
                turn_out: BrainTurnOutput = await workflow.execute_activity(
                    run_brain_turn,
                    BrainTurnInput(
                        run_id=inp.run_id, user_id=inp.user_id,
                        working_memory_json=wm_json,
                        past_research=inp.past_research or [],
                    ),
                    schedule_to_close_timeout=timedelta(minutes=4),
                    heartbeat_timeout=timedelta(minutes=2),
                    retry_policy=_TURN_RETRY,
                )
            except Exception as exc:
                workflow.logger.error("turn %s failed: %s", self._turn, exc)
                terminate_reason = f"turn_error: {exc}"
                break

            wm_json = turn_out.working_memory_json
            wm = WorkingMemory.model_validate_json(wm_json)

            # Phase transitions — pure function, workflow-owned (not LLM-owned).
            next_phase = compute_next_phase(wm)
            if next_phase != wm.phase:
                wm = wm.model_copy(update={
                    "phase": next_phase, "phase_entered_at_turn": wm.turn,
                })

            # Stagnation: if we've been in TEST for STAGNATION_TURNS without
            # resolving anything, abandon remaining opens and force synthesize.
            if is_stagnant_in_test(wm):
                workflow.logger.info(
                    "stagnant in test phase, force-synthesizing (turn=%s last_resolved=%s)",
                    wm.turn, wm.last_resolved_at_turn,
                )
                wm = abandon_open_hypotheses(
                    wm, reason="stagnant_in_test_phase",
                )
                wm = wm.model_copy(update={
                    "phase": "synthesize", "phase_entered_at_turn": wm.turn,
                })

            # In TEST phase, pick a focus target if we don't have one.
            if wm.phase == "test" and wm.current_target_hypothesis_id is None:
                target = pick_target_hypothesis(wm)
                if target is not None:
                    wm = wm.model_copy(update={"current_target_hypothesis_id": target})

            wm_json = wm.model_dump_json()

            reason = should_terminate(wm, inp.max_turns, self._cancelled)
            if reason is not None:
                terminate_reason = reason
                break

        # 5. Post-process — convert final WM to legacy result shape
        self._phase = "post_process"
        final_wm = WorkingMemory.model_validate_json(wm_json)
        legacy_result = final_wm.to_legacy_brain_result()
        legacy_result["_loop_meta"]["terminate_reason"] = terminate_reason

        # Honesty: status column is binary (succeeded/failed/cancelled) and we
        # don't add a new "partial" status here. Instead, when the loop did NOT
        # reach synthesize, prepend a clear gap so the result surface reflects
        # incompleteness even though status=succeeded.
        if terminate_reason != "synthesized":
            unresolved = sum(1 for h in final_wm.hypotheses if h.status == "open")
            legacy_result["gaps"].insert(
                0,
                f"Loop terminated early ({terminate_reason}) — "
                f"{unresolved}/{len(final_wm.hypotheses)} hypotheses still open. "
                f"Final phase: {final_wm.phase}.",
            )

        try:
            await workflow.execute_activity(
                post_process,
                PostProcessInput(
                    run_id=inp.run_id, user_id=inp.user_id,
                    session_id=inp.session_id,
                    brain_result={**legacy_result, "query": inp.query},
                    callback_url=inp.callback_url,
                ),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=_STANDARD_RETRY,
            )
        except Exception as exc:
            workflow.logger.error("post_process failed: %s", exc)
            await self._abort(inp, f"post_process_error: {exc}")
            return "failed"

        if terminate_reason == "cancelled_by_user":
            self._phase = "cancelled"
            return "cancelled"
        if terminate_reason.startswith("turn_error"):
            self._phase = "failed"
            return "failed"

        self._phase = "succeeded"
        workflow.logger.info(
            "IsLoopRunWorkflow completed run_id=%s turns=%s reason=%s",
            inp.run_id, final_wm.turn, terminate_reason,
        )
        return "succeeded"

    async def _abort(self, inp: ISLoopRunInput, reason: str) -> None:
        self._phase = "failed"
        try:
            await workflow.execute_activity(
                release_budget_and_mark_failed,
                AbortInput(
                    run_id=inp.run_id, user_id=inp.user_id, org_id=inp.org_id,
                    reason=reason, callback_url=inp.callback_url,
                ),
                schedule_to_close_timeout=timedelta(seconds=30),
                retry_policy=_STANDARD_RETRY,
            )
        except Exception as exc:
            workflow.logger.error("_abort activity failed: %s", exc)
