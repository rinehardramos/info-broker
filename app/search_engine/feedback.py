from __future__ import annotations

"""Feedback storage for search results.
MVP: stores feedback in Postgres. Post-MVP: triggers domain score
updates and episodic memory injection.
"""
import uuid

from app.search_engine import db


async def validate_feedback_ownership(*, result_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT j.user_id
               FROM search_results r
               JOIN search_jobs j ON j.id = r.job_id
               WHERE r.id = $1""",
            result_id,
        )
        if not row:
            return False
        return row["user_id"] == user_id


async def save_feedback(
    *,
    result_id: uuid.UUID,
    user_id: uuid.UUID,
    interest: int,
    relevance: int,
    usefulness: int,
    comment: str | None = None,
) -> uuid.UUID:
    return await db.insert_feedback(
        result_id=result_id,
        user_id=user_id,
        interest=interest,
        relevance=relevance,
        usefulness=usefulness,
        comment=comment,
    )
