"""Metrics and performance summary endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one

log = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])

# Runs stuck in queued/running this long are auto-failed on the next read.
# No worker / orchestrator picks orphaned runs up today, so without this
# they'd sit in the user's "Live" count forever.
_STALE_RUN_MINUTES = 30


def _fail_stale_runs(user_id: str) -> int:
    """Mark queued/running rows older than _STALE_RUN_MINUTES as failed.

    Lazy sweeper — runs on metrics fetch so the dashboard self-heals. Cheap
    UPDATE on a small set; safe to run on every request.
    """
    try:
        execute(
            """UPDATE pipeline_runs
                  SET status = 'failed',
                      finished_at = now(),
                      error_message = COALESCE(error_message,
                          'auto-failed: run stuck in ' || status || ' for >' || %s || ' minutes')
                WHERE user_id = %s
                  AND status IN ('queued', 'running')
                  AND started_at < now() - (%s * INTERVAL '1 minute')""",
            (_STALE_RUN_MINUTES, user_id, _STALE_RUN_MINUTES),
        )
    except Exception as exc:
        log.warning("stale-run sweep failed for user %s: %s", user_id, exc)
    return 0


@router.get("/summary")
def get_metrics_summary(
    days: int = 30,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return performance metrics for the last N days.

    Scoped by `user_id` alone (matching `/v3/pipelines/runs/all`). Earlier
    versions added `AND org_id = %s` which silently dropped historical rows
    that had NULL org_id, making the dashboard show 0 even when the user
    had visible runs.
    """
    uid = str(user["id"])
    _fail_stale_runs(uid)

    # Run stats — total, succeeded, failed, budget_exhausted, today, live
    run_stats = fetch_one(
        """SELECT
             COUNT(*) as total_runs,
             COUNT(*) FILTER (WHERE status = 'succeeded') as succeeded,
             COUNT(*) FILTER (WHERE status = 'failed') as failed,
             COUNT(*) FILTER (WHERE status = 'budget_exhausted') as budget_exhausted,
             COUNT(*) FILTER (WHERE status IN ('running', 'queued')) as live_runs,
             COUNT(*) FILTER (WHERE started_at > NOW() - INTERVAL '1 day') as runs_today,
             AVG(EXTRACT(EPOCH FROM (finished_at - started_at)))
               FILTER (WHERE status = 'succeeded' AND finished_at IS NOT NULL) as avg_latency_seconds,
             PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)))
               FILTER (WHERE status = 'succeeded' AND finished_at IS NOT NULL) as p50_latency_seconds,
             PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)))
               FILTER (WHERE status = 'succeeded' AND finished_at IS NOT NULL) as p95_latency_seconds
           FROM pipeline_runs
           WHERE user_id = %s
             AND started_at > NOW() - (%s * INTERVAL '1 day')""",
        (uid, days),
    ) or {}

    # Step stats — per node_type success/fail rates
    step_stats = fetch_all(
        """SELECT
             pn.node_type,
             COUNT(*) as total,
             COUNT(*) FILTER (WHERE psr.status = 'succeeded') as succeeded,
             AVG(psr.item_count) FILTER (WHERE psr.status = 'succeeded') as avg_items
           FROM pipeline_step_runs psr
           JOIN pipeline_nodes pn ON psr.node_id = pn.id
           JOIN pipeline_runs pr ON psr.run_id = pr.id
           WHERE pr.user_id = %s
             AND pr.started_at > NOW() - (%s * INTERVAL '1 day')
           GROUP BY pn.node_type
           ORDER BY total DESC
           LIMIT 20""",
        (uid, days),
    )

    # Strategy usage from research_trails scorecard
    strategy_stats = fetch_all(
        """SELECT
             scorecard->>'strategy' as strategy,
             COUNT(*) as uses,
             AVG((scorecard->>'score')::float) FILTER (WHERE scorecard->>'score' ~ '^[0-9.]+$') as avg_score
           FROM research_trails
           WHERE user_id = %s
             AND created_at > NOW() - (%s * INTERVAL '1 day')
             AND scorecard IS NOT NULL AND scorecard->>'strategy' IS NOT NULL
           GROUP BY scorecard->>'strategy'
           ORDER BY uses DESC
           LIMIT 10""",
        (uid, days),
    )

    total = run_stats.get("total_runs") or 0
    succeeded = run_stats.get("succeeded") or 0
    failed = run_stats.get("failed") or 0
    return {
        # Flat fields for Dashboard stat cards
        "total_runs":           total,
        "runs_today":           run_stats.get("runs_today") or 0,
        "succeeded":            succeeded,
        "failed":               failed,
        "live_runs":            run_stats.get("live_runs") or 0,
        "error_count":          failed,
        "avg_latency_seconds":  round(float(run_stats.get("avg_latency_seconds") or 0), 1),
        # Nested shape retained for Performance Dashboard
        "period_days": days,
        "runs": {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "budget_exhausted": run_stats.get("budget_exhausted") or 0,
            "success_rate": round(succeeded / max(total, 1) * 100, 1),
        },
        "latency": {
            "avg_seconds": round(float(run_stats.get("avg_latency_seconds") or 0), 1),
            "p50_seconds": round(float(run_stats.get("p50_latency_seconds") or 0), 1),
            "p95_seconds": round(float(run_stats.get("p95_latency_seconds") or 0), 1),
        },
        "steps": [dict(r) for r in step_stats],
        "strategies": [dict(r) for r in strategy_stats],
    }


@router.get("/runs")
def get_run_history(
    limit: int = 50,
    user: dict = Depends(get_current_user),
) -> list[dict]:
    """Return recent run history with latency and status. user-scoped."""
    rows = fetch_all(
        """SELECT id, status, trigger_type, query,
             started_at, finished_at,
             EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_seconds,
             error_message
           FROM pipeline_runs
           WHERE user_id = %s
             AND started_at IS NOT NULL
           ORDER BY started_at DESC
           LIMIT %s""",
        (str(user["id"]), limit),
    )
    return [dict(r) for r in rows]
