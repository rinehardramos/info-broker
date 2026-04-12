"""FastAPI router for /v2/ search-engine endpoints."""

import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.search_engine import db
from app.search_engine.auth import create_token, require_jwt
from app.search_engine.executor import AsyncioSearchExecutor
from app.search_engine.feedback import save_feedback, validate_feedback_ownership
from app.search_engine.qdrant import get_results_payloads
from app.search_engine.schemas import (
    SearchFeedbackRequest,
    SearchFeedbackResponse,
    SearchHistoryItem,
    SearchHistoryResponse,
    SearchJobResponse,
    SearchJobStatus,
    SearchRequest,
    SearchResultItem,
    SearchResultsResponse,
    SearchSubmitResponse,
    TokenRequest,
    TokenResponse,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2", tags=["search-engine"])

_executor = AsyncioSearchExecutor()

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@router.post("/auth/token", response_model=TokenResponse)
async def auth_token(req: TokenRequest):
    expiry_hours = float(os.environ.get("JWT_EXPIRY_HOURS", "24"))
    token = create_token(username=req.username, expiry_hours=expiry_hours)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=int(expiry_hours * 3600),
    )


# ---------------------------------------------------------------------------
# Search submit
# ---------------------------------------------------------------------------


@router.post(
    "/search",
    response_model=SearchSubmitResponse,
    status_code=202,
)
async def submit_search(req: SearchRequest, payload: dict = Depends(require_jwt)):
    username = payload.get("username", "unknown")
    user_id = await db.ensure_user(username)
    config = {
        "deep_search": req.deep_search,
        "max_parallel": req.max_parallel,
        "max_budget": req.max_budget,
        "plugins": req.plugins,
        "callback_url": req.callback_url,
    }
    job_id = await _executor.submit(query=req.query, config=config, user_id=user_id)
    return SearchSubmitResponse(
        job_id=job_id,
        status=SearchJobStatus.PENDING,
        status_url=f"/v2/search/{job_id}/status",
        results_url=f"/v2/search/{job_id}/results",
    )


# ---------------------------------------------------------------------------
# History -- MUST be before {job_id} routes to avoid "history" matching as UUID
# ---------------------------------------------------------------------------


@router.get("/search/history", response_model=SearchHistoryResponse)
async def search_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    payload: dict = Depends(require_jwt),
):
    username = payload.get("username", "unknown")
    user_id = await db.ensure_user(username)
    jobs, total = await db.get_user_jobs(user_id, page=page, per_page=per_page)
    items = [
        SearchHistoryItem(
            job_id=j["id"],
            query=j["query"],
            status=SearchJobStatus(j["status"]),
            total_results=j.get("total_results"),
            aggregate_confidence=j.get("aggregate_confidence"),
            created_at=j["created_at"],
        )
        for j in jobs
    ]
    return SearchHistoryResponse(jobs=items, total=total, page=page, per_page=per_page)


# ---------------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------------


@router.get("/search/{job_id}/status", response_model=SearchJobResponse)
async def get_job_status(job_id: uuid.UUID, payload: dict = Depends(require_jwt)):
    job = await db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    # Ownership check
    username = payload.get("username", "unknown")
    user_id = await db.ensure_user(username)
    if job["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your job")
    count = await db.get_job_result_count(job_id)
    return SearchJobResponse(
        job_id=job["id"],
        status=SearchJobStatus(job["status"]),
        query=job["query"],
        total_results=count,
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        error=job.get("error"),
    )


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@router.get("/search/{job_id}/results", response_model=SearchResultsResponse)
async def get_results(job_id: uuid.UUID, payload: dict = Depends(require_jwt)):
    job = await db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    username = payload.get("username", "unknown")
    user_id = await db.ensure_user(username)
    if job["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your job")

    rows = await db.get_results_for_job(job_id)
    result_ids = [r["id"] for r in rows]

    # Hydrate snippets from Qdrant
    try:
        qdrant_payloads = get_results_payloads(result_ids)
    except Exception as exc:
        log.warning("Qdrant hydration failed: %s", exc)
        qdrant_payloads = {}

    items: list[SearchResultItem] = []
    for r in rows:
        rid = r["id"]
        scores = r.get("heuristic_scores", {})
        if isinstance(scores, str):
            scores = json.loads(scores)

        # Get snippet from Qdrant payload or fallback
        qdrant_payload = qdrant_payloads.get(str(rid), {})
        snippet = qdrant_payload.get("snippet", r.get("title", ""))

        # Get feedback
        feedback_rows = await db.get_feedback_for_result(rid)
        feedback = feedback_rows[0] if feedback_rows else None

        items.append(
            SearchResultItem(
                id=rid,
                plugin=r["plugin"],
                title=r["title"],
                url=r.get("url"),
                snippet=snippet,
                published_at=r.get("published_at"),
                is_deep_child=r.get("is_deep_child", False),
                scores=scores,
                feedback=feedback,
            )
        )

    return SearchResultsResponse(
        job_id=job_id,
        query=job["query"],
        status=SearchJobStatus(job["status"]),
        total_results=len(items),
        results=items,
        aggregate_confidence=job.get("aggregate_confidence"),
    )


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@router.post("/search/{job_id}/cancel")
async def cancel_job(job_id: uuid.UUID, payload: dict = Depends(require_jwt)):
    job = await db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    username = payload.get("username", "unknown")
    user_id = await db.ensure_user(username)
    if job["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your job")
    cancelled = await _executor.cancel(job_id)
    return {"job_id": str(job_id), "cancelled": cancelled}


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


@router.post(
    "/search/{job_id}/results/{result_id}/feedback",
    response_model=SearchFeedbackResponse,
)
async def submit_feedback(
    job_id: uuid.UUID,
    result_id: uuid.UUID,
    body: SearchFeedbackRequest,
    payload: dict = Depends(require_jwt),
):
    username = payload.get("username", "unknown")
    user_id = await db.ensure_user(username)
    owns = await validate_feedback_ownership(result_id=result_id, user_id=user_id)
    if not owns:
        raise HTTPException(status_code=403, detail="Not your result")
    fb_id = await save_feedback(
        result_id=result_id,
        user_id=user_id,
        interest=body.interest,
        relevance=body.relevance,
        usefulness=body.usefulness,
        comment=body.comment,
    )
    return SearchFeedbackResponse(id=fb_id, result_id=result_id, saved=True)
