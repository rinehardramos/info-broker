from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_one
from app.pipeline.runners import injection_queue
from app.routers.v3.stream import push_event

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v3/brain", tags=["brain"])
runs_router = APIRouter(prefix="/v3/runs", tags=["runs"])


class AggregateRequest(BaseModel):
    run_id: str


class ReportRequest(BaseModel):
    run_id: str
    format: str = "md"


class PresentationRequest(BaseModel):
    run_id: str


class SaveAsPipelineRequest(BaseModel):
    run_id: str
    name: str


class InjectNodeRequest(BaseModel):
    node_spec: dict | None = None
    instruction: str | None = None
    after_node_id: str | None = None


@router.post("/aggregate")
async def aggregate(req: AggregateRequest, current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/report")
async def report(req: ReportRequest, current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/presentation")
async def presentation(req: PresentationRequest, current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/save-as-pipeline")
async def save_as_pipeline(req: SaveAsPipelineRequest, current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet")


@runs_router.post("/{run_id}/inject")
async def inject_node(
    run_id: str,
    req: InjectNodeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Inject a mid-run user instruction into the running research brain.

    Ownership-checks the run, persists the message to the session's
    conversation_thread, enqueues the instruction for the running Strategist,
    and emits a WS event so the live view notes it.

    NOTE: in-memory injection only works because agent-triggered runs execute
    in the same API process (asyncio.create_task).  Out-of-process Temporal
    workers are NOT bridged by this mechanism.
    """
    # 1. Fetch run — 404 if missing
    run = fetch_one(
        "SELECT user_id, session_id FROM pipeline_runs WHERE id = %s",
        (run_id,),
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # 2. Ownership check
    if str(run["user_id"]) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Forbidden")

    # 3. Extract instruction (may be None if only node_spec provided — still enqueue)
    instruction = req.instruction or ""

    # 4. Enqueue for the running brain
    if instruction:
        injection_queue.enqueue(run_id, instruction)

    # 5. Persist to session conversation_thread (skip if no session_id or no instruction)
    session_id = run.get("session_id")
    if session_id and instruction:
        try:
            now = datetime.now(timezone.utc).isoformat()
            msg = json.dumps([{
                "role": "user",
                "content": instruction,
                "type": "injection",
                "ts": now,
            }])
            execute(
                "UPDATE agent_sessions SET conversation_thread = conversation_thread || %s::jsonb WHERE id = %s",
                (msg, str(session_id)),
            )
        except Exception as exc:
            # Non-fatal: enqueue already succeeded; log and continue
            log.warning("inject_node: failed to persist to conversation_thread: %s", exc)

    # 6. Emit WS event so the live view notes the injection
    try:
        await push_event(str(current_user["id"]), {
            "type": "is.node_injected",
            "run_id": run_id,
            "instruction": instruction,
        })
    except Exception as exc:
        log.warning("inject_node: push_event failed (non-fatal): %s", exc)

    node_id = str(uuid.uuid4())
    return {"node_id": node_id, "status": "queued"}
