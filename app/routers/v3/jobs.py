from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import JobOut

router = APIRouter(prefix="/v3/jobs", tags=["v3-jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(user: dict = Depends(get_current_user)):
    rows = fetch_all(
        "SELECT id::text, status, query, created_at, completed_at, COALESCE(result_count,0) AS result_count FROM v3_jobs WHERE user_id = %s ORDER BY created_at DESC LIMIT 50",
        (str(user["id"]),),
    )
    return [JobOut(**r) for r in rows]


@router.get("/{job_id}/results")
def get_job_results(job_id: str, user: dict = Depends(get_current_user)):
    # Verify ownership
    job = fetch_one(
        "SELECT id FROM v3_jobs WHERE id = %s AND user_id = %s",
        (job_id, str(user["id"])),
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    rows = fetch_all(
        "SELECT id::text, source, title, url, snippet, created_at FROM v3_job_results WHERE job_id = %s ORDER BY created_at",
        (job_id,),
    )
    return rows


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT id::text, status, query, created_at, completed_at, COALESCE(result_count,0) AS result_count FROM v3_jobs WHERE id = %s AND user_id = %s",
        (job_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut(**row)


@router.delete("/{job_id}", status_code=204)
def cancel_job(job_id: str, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT id FROM v3_jobs WHERE id = %s AND user_id = %s AND status = 'running'",
        (job_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Running job not found")
    execute("UPDATE v3_jobs SET status = 'cancelled' WHERE id = %s", (job_id,))
