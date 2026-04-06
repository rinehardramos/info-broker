"""Research and grading endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_api_key
from app.schemas import (
    GradeRequest,
    GradeResponse,
    IngestRequest,
    IngestResponse,
    ResearchRequest,
    ResearchResponse,
)

router = APIRouter(tags=["research"])


@router.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest, _: str = Depends(require_api_key)):
    from ingest import ingest_data

    counts = ingest_data(overwrite=req.overwrite)
    return IngestResponse(**counts)


@router.post("/research", response_model=ResearchResponse)
def research(req: ResearchRequest, _: str = Depends(require_api_key)):
    from research_agent import run_research_batch

    counts = run_research_batch(limit=req.limit)
    return ResearchResponse(**counts)


@router.post("/profiles/{profile_id}/grade", response_model=GradeResponse)
def grade_profile(
    profile_id: str,
    req: GradeRequest,
    _: str = Depends(require_api_key),
):
    from research_agent import save_grade

    try:
        result = save_grade(profile_id, req.grade, req.feedback or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not result.get("saved"):
        raise HTTPException(status_code=404, detail="profile not found")
    return GradeResponse(**result)
