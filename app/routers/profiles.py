"""Profile read endpoints (list, detail, raw)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_db_conn, require_api_key
from app.schemas import ProfileDetail, ProfileRaw, ProfileSummary

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileSummary])
def list_profiles(
    limit: int = 50,
    offset: int = 0,
    _: str = Depends(require_api_key),
    conn=Depends(get_db_conn),
):
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    cur = conn.cursor()
    cur.execute(
        "SELECT id, first_name, last_name, headline "
        "FROM linkedin_profiles ORDER BY id LIMIT %s OFFSET %s",
        (limit, offset),
    )
    rows = cur.fetchall()
    cur.close()
    return [
        ProfileSummary(id=r[0], first_name=r[1], last_name=r[2], headline=r[3])
        for r in rows
    ]


@router.get("/{profile_id}", response_model=ProfileDetail)
def get_profile(
    profile_id: str,
    _: str = Depends(require_api_key),
    conn=Depends(get_db_conn),
):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, first_name, last_name, headline, about, research_status, "
        "is_smb, research_summary, system_confidence_score, user_grade "
        "FROM linkedin_profiles WHERE id = %s",
        (profile_id,),
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        raise HTTPException(status_code=404, detail="profile not found")
    return ProfileDetail(
        id=row[0],
        first_name=row[1],
        last_name=row[2],
        headline=row[3],
        about=row[4],
        research_status=row[5],
        is_smb=row[6],
        research_summary=row[7],
        system_confidence_score=row[8],
        user_grade=row[9],
    )


@router.get("/{profile_id}/raw", response_model=ProfileRaw)
def get_profile_raw(
    profile_id: str,
    _: str = Depends(require_api_key),
    conn=Depends(get_db_conn),
):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, raw_data FROM linkedin_profiles WHERE id = %s",
        (profile_id,),
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        raise HTTPException(status_code=404, detail="profile not found")
    return ProfileRaw(id=row[0], raw_data=row[1])
