"""IS Run Temporal workflow — Phase 0 stub."""
from __future__ import annotations
from dataclasses import dataclass, field
from temporalio import workflow


@dataclass
class ISRunInput:
    run_id: str
    user_id: str
    org_id: str
    query: str
    pipeline_id: str
    session_id: str | None = None
    preflight_prior_slots: dict = field(default_factory=dict)


@workflow.defn(name="ISRunWorkflow")
class ISRunWorkflow:
    """Intelligent Search run as a Temporal workflow.

    Phase 0: stub — connects and registers, no activities executed yet.
    Phase 1: full IS brain execution with activities.
    """

    @workflow.run
    async def run(self, inp: ISRunInput) -> str:
        # Phase 0 stub — will be replaced in Phase 1
        workflow.logger.info("ISRunWorkflow Phase 0 stub — run_id=%s", inp.run_id)
        return "stub"

    @workflow.signal
    async def brain_answer(self, answer: str) -> None:
        """Signal from user answering a PreFlight clarification question."""
        pass  # Phase 1

    @workflow.signal
    async def cancel_run(self) -> None:
        """Signal to cancel the IS run."""
        pass  # Phase 1

    @workflow.query
    def get_run_status(self) -> str:
        return "stub"
