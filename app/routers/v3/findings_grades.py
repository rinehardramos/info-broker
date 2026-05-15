"""Findings grading endpoints — POST/GET grade per finding, GET all grades for a run."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one

router = APIRouter(tags=["findings-grades"])

_ALLOWED_GRADES = {"A", "B", "C", "D"}


class GradeIn(BaseModel):
    grade: str
    note: str | None = None
    run_id: str

    @field_validator("grade")
    @classmethod
    def grade_must_be_valid(cls, v: str) -> str:
        if v not in _ALLOWED_GRADES:
            raise ValueError(f"grade must be one of {sorted(_ALLOWED_GRADES)}, got '{v}'")
        return v


@router.post("/v3/findings/{finding_id}/grade")
def post_grade(
    finding_id: str,
    body: GradeIn,
    user: dict = Depends(get_current_user),
) -> dict:
    """UPSERT a grade for a finding. Re-grading replaces the prior grade."""
    execute(
        """
        INSERT INTO findings_grades (finding_id, run_id, user_id, grade, note, graded_at)
        VALUES (%s, %s::uuid, %s::uuid, %s, %s, now())
        ON CONFLICT (user_id, finding_id)
        DO UPDATE SET
            grade     = EXCLUDED.grade,
            note      = EXCLUDED.note,
            run_id    = EXCLUDED.run_id,
            graded_at = now()
        """,
        (finding_id, body.run_id, str(user["id"]), body.grade, body.note),
    )
    row = fetch_one(
        """
        SELECT id::text, finding_id, run_id::text, user_id::text, grade, note, graded_at::text
        FROM findings_grades
        WHERE finding_id = %s AND user_id = %s::uuid
        """,
        (finding_id, str(user["id"])),
    )
    return row  # type: ignore[return-value]


@router.get("/v3/findings/{finding_id}/grade")
def get_grade(
    finding_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return the current user's grade (or null) plus aggregate counts for the finding."""
    my_row = fetch_one(
        """
        SELECT grade, note, graded_at::text
        FROM findings_grades
        WHERE finding_id = %s AND user_id = %s::uuid
        """,
        (finding_id, str(user["id"])),
    )
    agg_row = fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE grade = 'A') AS a_count,
            COUNT(*) FILTER (WHERE grade = 'B') AS b_count,
            COUNT(*) FILTER (WHERE grade = 'C') AS c_count,
            COUNT(*) FILTER (WHERE grade = 'D') AS d_count,
            COUNT(*) AS total_graders
        FROM findings_grades
        WHERE finding_id = %s
        """,
        (finding_id,),
    )
    return {
        "my_grade": my_row,
        "aggregate": agg_row,
    }


@router.get("/v3/runs/{run_id}/grades")
def get_run_grades(
    run_id: str,
    user: dict = Depends(get_current_user),
) -> list[dict]:
    """Return all grades submitted by the current user for findings in this run."""
    rows = fetch_all(
        """
        SELECT id::text, finding_id, run_id::text, user_id::text, grade, note, graded_at::text
        FROM findings_grades
        WHERE run_id = %s::uuid AND user_id = %s::uuid
        ORDER BY graded_at DESC
        """,
        (run_id, str(user["id"])),
    )
    return rows
