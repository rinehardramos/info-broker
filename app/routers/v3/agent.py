from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_one
from app.routers.v3.models import AgentMessageIn, AgentMessageOut
from app.routers.v3.stream import push_event

router = APIRouter(prefix="/v3/agent", tags=["v3-agent"])
log = logging.getLogger(__name__)


async def _run_research(job_id: str, user_id: str, message: str) -> None:
    """Background task: run a DDG search and push events over WebSocket."""
    try:
        execute(
            "UPDATE v3_jobs SET status = 'running' WHERE id = %s",
            (job_id,),
        )
        await push_event(user_id, {
            "type": "job.update",
            "job_id": job_id,
            "status": "running",
            "message": f"Starting research: {message}",
        })

        from app.search_engine.plugins.ddg import DdgPlugin
        plugin = DdgPlugin()
        results = await plugin.search(message, max_results=10)

        result_count = len(results)
        execute(
            "UPDATE v3_jobs SET status = 'completed', completed_at = now() WHERE id = %s",
            (job_id,),
        )
        await push_event(user_id, {
            "type": "job.completed",
            "job_id": job_id,
            "status": "completed",
            "result_count": result_count,
            "message": f"Research complete — {result_count} results",
        })
    except Exception as exc:
        log.error("Research job %s failed: %s", job_id, exc)
        execute("UPDATE v3_jobs SET status = 'failed' WHERE id = %s", (job_id,))
        await push_event(user_id, {
            "type": "job.failed",
            "job_id": job_id,
            "status": "failed",
            "message": str(exc),
        })


@router.post("/message", response_model=AgentMessageOut, status_code=202)
async def send_message(
    body: AgentMessageIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    job_id = str(uuid.uuid4())
    user_id = str(user["id"])

    execute(
        "INSERT INTO v3_jobs (id, user_id, query, status) VALUES (%s, %s, %s, 'pending')",
        (job_id, user_id, body.message),
    )

    background_tasks.add_task(_run_research, job_id, user_id, body.message)
    return AgentMessageOut(job_id=job_id)
