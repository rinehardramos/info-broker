"""IS brain activity — wraps run_research() with heartbeating."""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from temporalio import activity

log = logging.getLogger(__name__)


@dataclass
class RunISBrainInput:
    run_id: str
    user_id: str
    query: str
    session_id: str | None
    session_context: str
    past_research: list[dict] | None = field(default_factory=list)
    preflight_tier: int = 1
    preflight_disclaimer: str | None = None
    preflight_question: str | None = None


@dataclass
class BrainResult:
    findings: list[dict] = field(default_factory=list)
    summary: str = ""
    raw: dict = field(default_factory=dict)


@activity.defn(name="run_is_brain")
async def run_is_brain(inp: RunISBrainInput) -> BrainResult:
    """Run the IS brain subprocess. Heartbeats every 30s."""
    from app.is_brain import run_research
    from app.routers.v3.db import execute, fetch_one
    from app.routers.v3.stream import push_event

    execute(
        "UPDATE pipeline_runs SET status = 'running' WHERE id = %s",
        (inp.run_id,),
    )
    await push_event(inp.user_id, {
        "type": "job.update", "job_id": inp.run_id, "status": "running",
        "run_id": inp.run_id, "message": inp.query,
    })

    # Heartbeat task — keeps Temporal informed every 30s
    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    async def _on_event(ev: dict) -> None:
        try:
            await push_event(inp.user_id, {**ev, "job_id": inp.run_id, "run_id": inp.run_id})
        except Exception:
            pass

    try:
        # Fetch pipeline run info for depth/branch params
        row = fetch_one(
            "SELECT max_depth, max_branches FROM pipeline_runs WHERE id = %s",
            (inp.run_id,),
        ) or {}
        result = await run_research(
            query=inp.query,
            user_id=inp.user_id,
            past_research=inp.past_research or [],
            max_depth=row.get("max_depth") or 3,
            max_branches=row.get("max_branches") or 10,
            on_event=_on_event,
            session_context=inp.session_context,
        )
        return BrainResult(
            findings=result.get("findings", []),
            summary=result.get("summary", ""),
            raw=result,
        )
    except Exception as exc:
        log.error("run_is_brain failed: %s", exc)
        raise
    finally:
        heartbeat_task.cancel()


async def _heartbeat_loop() -> None:
    while True:
        await asyncio.sleep(30)
        try:
            activity.heartbeat("IS brain running")
        except Exception:
            break
