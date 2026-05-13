"""IS Run Temporal workflow — Phase 1."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.preflight import (
        PreflightInput,
        PreflightResult,
        MarkAwaitingInput,
        preflight_validation,
        mark_awaiting_input,
    )
    from app.temporal.activities.budget import (
        ReserveBudgetInput,
        ReservationResult,
        AbortInput,
        reserve_budget,
        release_budget_and_mark_failed,
    )
    from app.temporal.activities.brain import RunISBrainInput, BrainResult, run_is_brain
    from app.temporal.activities.post_process import PostProcessInput, post_process

log = logging.getLogger(__name__)

# Retry policies
_STANDARD_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
)
_NO_RETRY = RetryPolicy(maximum_attempts=1)


@dataclass
class ISRunInput:
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


@workflow.defn(name="ISRunWorkflow")
class ISRunWorkflow:
    """Intelligent Search run as a Temporal workflow.

    Phase 1: full IS brain execution with activities.
    Signals: brain_answer (PreFlight clarification), cancel_run
    Query: get_run_status
    """

    def __init__(self) -> None:
        self._brain_answer: str | None = None
        self._cancelled: bool = False
        self._phase: str = "init"
        self._cycle_count: int = 0

    @workflow.signal
    async def brain_answer(self, answer: str) -> None:
        """Signal from user answering a PreFlight clarification question."""
        self._brain_answer = answer

    @workflow.signal
    async def cancel_run(self) -> None:
        """Signal to cancel the IS run."""
        self._cancelled = True

    @workflow.query
    def get_run_status(self) -> str:
        return self._phase

    @workflow.run
    async def run(self, inp: ISRunInput) -> str:
        workflow.logger.info("ISRunWorkflow starting run_id=%s", inp.run_id)
        self._phase = "preflight"

        # 1. PreFlight validation
        preflight: PreflightResult = await workflow.execute_activity(
            preflight_validation,
            PreflightInput(query=inp.query, prior_slots=inp.preflight_prior_slots or None),
            schedule_to_close_timeout=timedelta(seconds=60),
            retry_policy=_STANDARD_RETRY,
        )

        # 2. If blocking, wait for user's answer before proceeding
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
            # Wait up to 10 minutes for the user answer signal
            await workflow.wait_condition(
                lambda: self._brain_answer is not None or self._cancelled,
                timeout=timedelta(minutes=10),
            )
            if self._cancelled:
                await self._abort(inp, "cancelled_by_user")
                return "cancelled"
            # Enrich query with clarification answer
            inp = ISRunInput(
                run_id=inp.run_id,
                user_id=inp.user_id,
                org_id=inp.org_id,
                query=f"{inp.query}\n\nClarification: {self._brain_answer}",
                pipeline_id=inp.pipeline_id,
                session_id=inp.session_id,
                session_context=inp.session_context,
                past_research=inp.past_research,
                budget=inp.budget,
                callback_url=inp.callback_url,
                preflight_prior_slots=inp.preflight_prior_slots,
            )

        # 3. Reserve budget
        self._phase = "budget"
        reservation: ReservationResult = await workflow.execute_activity(
            reserve_budget,
            ReserveBudgetInput(
                run_id=inp.run_id,
                user_id=inp.user_id,
                org_id=inp.org_id,
                budget=inp.budget,
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

        # 4. Run IS brain
        self._phase = "running"
        try:
            brain_result: BrainResult = await workflow.execute_activity(
                run_is_brain,
                RunISBrainInput(
                    run_id=inp.run_id,
                    user_id=inp.user_id,
                    query=inp.query,
                    session_id=inp.session_id,
                    session_context=inp.session_context,
                    past_research=inp.past_research or [],
                    preflight_tier=preflight.tier,
                    preflight_disclaimer=preflight.disclaimer,
                ),
                schedule_to_close_timeout=timedelta(minutes=15),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=_NO_RETRY,
            )
        except Exception as exc:
            workflow.logger.error("run_is_brain failed: %s", exc)
            await self._abort(inp, f"brain_error: {exc}")
            return "failed"

        # 5. Post-process
        self._phase = "post_process"
        await workflow.execute_activity(
            post_process,
            PostProcessInput(
                run_id=inp.run_id,
                user_id=inp.user_id,
                session_id=inp.session_id,
                brain_result={**brain_result.raw, "query": inp.query},
                callback_url=inp.callback_url,
            ),
            schedule_to_close_timeout=timedelta(minutes=2),
            retry_policy=_STANDARD_RETRY,
        )

        self._phase = "succeeded"
        workflow.logger.info("ISRunWorkflow completed run_id=%s", inp.run_id)
        return "succeeded"

    async def _abort(self, inp: ISRunInput, reason: str) -> None:
        """Release budget and mark run failed."""
        self._phase = "failed"
        try:
            await workflow.execute_activity(
                release_budget_and_mark_failed,
                AbortInput(
                    run_id=inp.run_id,
                    user_id=inp.user_id,
                    org_id=inp.org_id,
                    reason=reason,
                    callback_url=inp.callback_url,
                ),
                schedule_to_close_timeout=timedelta(seconds=30),
                retry_policy=_STANDARD_RETRY,
            )
        except Exception as exc:
            workflow.logger.error("_abort activity failed: %s", exc)
