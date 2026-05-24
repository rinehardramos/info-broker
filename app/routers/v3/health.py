"""Worker health endpoint — surfaces Temporal connectivity + queue depth.

The dashboard renders a small pill from this so a worker outage is visible
without digging into logs. Non-admins see only their own queue depth;
admins see global totals.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_one

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v3/health", tags=["v3-health"])


async def _temporal_status() -> str:
    try:
        from temporalio.client import Client
        host = os.getenv("TEMPORAL_HOST", "localhost")
        port = int(os.getenv("TEMPORAL_PORT", "7233"))
        client = await asyncio.wait_for(Client.connect(f"{host}:{port}"), timeout=3)
        # connect succeeded; a deeper liveness check would list workflows,
        # but connect alone is enough to distinguish "down" from "up".
        del client
        return "ok"
    except Exception as exc:
        log.debug("temporal health probe failed: %s", exc)
        return "unreachable"


@router.get("/workers")
async def workers_health(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    is_admin = bool(user.get("is_admin"))
    user_filter = ""
    params: tuple = ()
    if not is_admin:
        user_filter = "AND user_id = %s"
        params = (str(user["id"]),)

    counts = fetch_one(
        f"""SELECT
              COUNT(*) FILTER (WHERE status = 'queued')  AS queued_count,
              COUNT(*) FILTER (WHERE status = 'running') AS running_count,
              EXTRACT(EPOCH FROM (now() - MIN(started_at) FILTER (WHERE status = 'queued')))  AS oldest_queued_age_seconds,
              EXTRACT(EPOCH FROM (now() - MIN(started_at) FILTER (WHERE status = 'running'))) AS oldest_running_age_seconds
            FROM pipeline_runs
            WHERE status IN ('queued', 'running') {user_filter}""",  # noqa: S608 - user_filter is a constant fragment; value parameterized
        params,
    ) or {}

    temporal = await _temporal_status()
    return {
        "temporal":                    temporal,
        "scope":                       "global" if is_admin else "user",
        "queued_count":                int(counts.get("queued_count") or 0),
        "running_count":               int(counts.get("running_count") or 0),
        "oldest_queued_age_seconds":   _round_or_none(counts.get("oldest_queued_age_seconds")),
        "oldest_running_age_seconds":  _round_or_none(counts.get("oldest_running_age_seconds")),
    }


def _round_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None
