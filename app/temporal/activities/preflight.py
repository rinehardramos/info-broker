"""PreFlight validation activity."""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from temporalio import activity

log = logging.getLogger(__name__)


@dataclass
class PreflightInput:
    query: str
    prior_slots: dict | None = None


@dataclass
class PreflightResult:
    tier: int
    blocking: bool
    first_question: str | None
    first_question_options: list[str] | None
    disclaimer: str | None
    raw_result: dict | None = field(default=None, repr=False)


@dataclass
class MarkAwaitingInput:
    run_id: str
    question: str
    options: list[str] | None


@activity.defn(name="preflight_validation")
async def preflight_validation(inp: PreflightInput) -> PreflightResult:
    """Run 3-layer PreFlight validation. Non-fatal — returns tier=3 on failure."""
    try:
        from app.pipeline.preflight import validate
        result = validate(inp.query, prior_slots=inp.prior_slots)
        return PreflightResult(
            tier=result.tier if hasattr(result.tier, '__int__') else int(result.tier),
            blocking=result.blocking,
            first_question=result.first_question,
            first_question_options=result.first_question_options,
            disclaimer=getattr(result, "disclaimer", None),
            raw_result=None,
        )
    except Exception as exc:
        log.warning("PreFlight failed (non-fatal): %s", exc)
        return PreflightResult(tier=3, blocking=False, first_question=None,
                               first_question_options=None, disclaimer=None)


@activity.defn(name="mark_awaiting_input")
async def mark_awaiting_input(inp: MarkAwaitingInput) -> None:
    """Mark run as awaiting_input and push WS event with question."""
    from app.routers.v3.db import execute
    from app.routers.v3.stream import push_event
    import asyncio
    execute(
        "UPDATE pipeline_runs SET status = 'awaiting_input' WHERE id = %s",
        (inp.run_id,),
    )
    asyncio.create_task(push_event(inp.run_id, {
        "type": "brain.question", "run_id": inp.run_id, "job_id": inp.run_id,
        "question": inp.question, "options": inp.options or [],
        "preflight": True,
    }))
