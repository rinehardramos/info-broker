from __future__ import annotations
import uuid
from fastapi import APIRouter
from pydantic import BaseModel

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
async def aggregate(req: AggregateRequest):
    return {"summary": f"Aggregated summary for run {req.run_id} (implementation pending)"}


@router.post("/report")
async def report(req: ReportRequest):
    return {"content": f"# Report for {req.run_id}\n\n(implementation pending)", "format": req.format}


@router.post("/presentation")
async def presentation(req: PresentationRequest):
    return {"slides": [{"title": f"Results: {req.run_id}", "bullets": []}]}


@router.post("/save-as-pipeline")
async def save_as_pipeline(req: SaveAsPipelineRequest):
    return {"pipeline_id": f"saved-{req.run_id}"}


@runs_router.post("/{run_id}/inject")
async def inject_node(run_id: str, req: InjectNodeRequest):
    node_id = str(uuid.uuid4())
    return {"node_id": node_id, "status": "queued"}
