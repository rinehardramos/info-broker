from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import JobOut, ResultGradeIn

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
    job = fetch_one(
        "SELECT id FROM v3_jobs WHERE id = %s AND user_id = %s",
        (job_id, str(user["id"])),
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    rows = fetch_all(
        """
        SELECT r.id::text, r.source, r.title, r.url, r.snippet, r.created_at,
               g.grade
        FROM v3_job_results r
        LEFT JOIN v3_result_grades g
               ON g.result_id = r.id AND g.user_id = %s
        WHERE r.job_id = %s
        ORDER BY r.created_at
        """,
        (str(user["id"]), job_id),
    )
    return rows


@router.post("/{job_id}/results/{result_id}/grade")
def grade_result(
    job_id: str,
    result_id: str,
    body: ResultGradeIn,
    user: dict = Depends(get_current_user),
):
    # Verify result belongs to a job owned by this user
    row = fetch_one(
        """
        SELECT r.id FROM v3_job_results r
        JOIN v3_jobs j ON j.id = r.job_id
        WHERE r.id = %s AND j.id = %s AND j.user_id = %s
        """,
        (result_id, job_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Result not found")
    execute(
        """
        INSERT INTO v3_result_grades (result_id, user_id, grade)
        VALUES (%s, %s, %s)
        ON CONFLICT (result_id, user_id)
        DO UPDATE SET grade = EXCLUDED.grade, updated_at = now()
        """,
        (result_id, str(user["id"]), body.grade),
    )
    return {"ok": True}


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
