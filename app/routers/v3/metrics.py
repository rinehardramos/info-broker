"""Metrics and performance summary endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import fetch_all, fetch_one
from app.routers.v3.tenancy import user_org_id

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/summary")
def get_metrics_summary(
    days: int = 30,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return performance metrics for the last N days."""
    org = user_org_id(user)
    uid = str(user["id"])

    # Run stats — total, succeeded, failed, budget_exhausted
    run_stats = fetch_one(
        """SELECT
             COUNT(*) as total_runs,
             COUNT(*) FILTER (WHERE status = 'succeeded') as succeeded,
             COUNT(*) FILTER (WHERE status = 'failed') as failed,
             COUNT(*) FILTER (WHERE status = 'budget_exhausted') as budget_exhausted,
             AVG(EXTRACT(EPOCH FROM (finished_at - started_at)))
               FILTER (WHERE status = 'succeeded' AND finished_at IS NOT NULL) as avg_latency_seconds,
             PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)))
               FILTER (WHERE status = 'succeeded' AND finished_at IS NOT NULL) as p50_latency_seconds,
             PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)))
               FILTER (WHERE status = 'succeeded' AND finished_at IS NOT NULL) as p95_latency_seconds
           FROM pipeline_runs
           WHERE user_id = %s AND org_id = %s
             AND started_at > NOW() - (%s * INTERVAL '1 day')""",
        (uid, org, days),
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
           WHERE pr.user_id = %s AND pr.org_id = %s
             AND pr.started_at > NOW() - (%s * INTERVAL '1 day')
           GROUP BY pn.node_type
           ORDER BY total DESC
           LIMIT 20""",
        (uid, org, days),
    )

    # Strategy usage from research_trails scorecard
    strategy_stats = fetch_all(
        """SELECT
             scorecard->>'strategy' as strategy,
             COUNT(*) as uses,
             AVG((scorecard->>'score')::float) FILTER (WHERE scorecard->>'score' ~ '^[0-9.]+$') as avg_score
           FROM research_trails
           WHERE user_id = %s AND org_id = %s
             AND created_at > NOW() - (%s * INTERVAL '1 day')
             AND scorecard IS NOT NULL AND scorecard->>'strategy' IS NOT NULL
           GROUP BY scorecard->>'strategy'
           ORDER BY uses DESC
           LIMIT 10""",
        (uid, org, days),
    )

    return {
        "period_days": days,
        "runs": {
            "total": run_stats.get("total_runs") or 0,
            "succeeded": run_stats.get("succeeded") or 0,
            "failed": run_stats.get("failed") or 0,
            "budget_exhausted": run_stats.get("budget_exhausted") or 0,
            "success_rate": round(
                (run_stats.get("succeeded") or 0)
                / max((run_stats.get("total_runs") or 1), 1)
                * 100,
                1,
            ),
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
    """Return recent run history with latency and status."""
    rows = fetch_all(
        """SELECT id, status, trigger_type, query,
             started_at, finished_at,
             EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_seconds,
             error_message
           FROM pipeline_runs
           WHERE user_id = %s AND org_id = %s
             AND started_at IS NOT NULL
           ORDER BY started_at DESC
           LIMIT %s""",
        (str(user["id"]), user_org_id(user), limit),
    )
    return [dict(r) for r in rows]
