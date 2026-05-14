from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user

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
    # TODO: verify run_id belongs to current_user before mutating
    # TODO: emit WS event to notify pipeline live-view of the injected node
    node_id = str(uuid.uuid4())
    return {"node_id": node_id, "status": "queued"}
