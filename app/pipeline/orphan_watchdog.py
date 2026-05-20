"""Periodic reconciliation of pipeline_runs against Temporal workflow state.

The HTTP path may write a `queued` row and then fail to dispatch (Temporal
down, bug, etc.). The metrics-fetch sweeper is an opportunistic safety net;
this watchdog is the authoritative path: every few minutes it asks Temporal
about each in-flight workflow_id and reconciles the DB row.

Spawned at FastAPI startup via `asyncio.create_task(start_orphan_watchdog())`.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

_INTERVAL_SECONDS    = int(os.getenv("ORPHAN_WATCHDOG_INTERVAL_SEC", "300"))
_STALE_AFTER_MINUTES = int(os.getenv("ORPHAN_STALE_AFTER_MIN", "15"))
_BATCH_SIZE          = 50


async def _temporal_client():
    """Return a connected Temporal client, or None if unreachable."""
    try:
        from temporalio.client import Client
        host = os.getenv("TEMPORAL_HOST", "localhost")
        port = int(os.getenv("TEMPORAL_PORT", "7233"))
        return await asyncio.wait_for(Client.connect(f"{host}:{port}"), timeout=4)
    except Exception as exc:
        log.debug("orphan_watchdog: temporal connect failed: %s", exc)
        return None


async def _reconcile_one(client: Any, row: dict) -> str:
    """Reconcile a single stale row. Returns the action taken (for logging)."""
    from app.routers.v3.db import execute
    workflow_id = row.get("temporal_workflow_id")
    run_id      = row["id"]

    if not workflow_id:
        # No workflow was ever registered for this row — it was dropped before
        # dispatch reached Temporal. Mark failed: orphaned.
        execute(
            """UPDATE pipeline_runs
                  SET status = 'failed', finished_at = now(),
                      error_message = COALESCE(error_message, 'orphaned: no workflow')
                WHERE id = %s AND status IN ('queued', 'running')""",
            (run_id,),
        )
        return "orphaned-no-workflow"

    try:
        handle = client.get_workflow_handle(workflow_id)
        desc = await asyncio.wait_for(handle.describe(), timeout=4)
        status_name = (
            desc.status.name if hasattr(desc.status, "name")
            else str(desc.status)
        ).upper()
    except Exception as exc:
        # Workflow not found in Temporal — orphan.
        msg = str(exc)
        if "WorkflowNotFound" in type(exc).__name__ or "not found" in msg.lower():
            execute(
                """UPDATE pipeline_runs
                      SET status = 'failed', finished_at = now(),
                          error_message = COALESCE(error_message, 'orphaned: workflow not found in temporal')
                    WHERE id = %s AND status IN ('queued', 'running')""",
                (run_id,),
            )
            return "orphaned-workflow-missing"
        log.debug("describe %s failed: %s", workflow_id, exc)
        return "describe-error"

    if "RUNNING" in status_name:
        return "still-running"

    if "COMPLETED" in status_name:
        execute(
            """UPDATE pipeline_runs
                  SET status = 'succeeded', finished_at = COALESCE(finished_at, now())
                WHERE id = %s AND status IN ('queued', 'running')""",
            (run_id,),
        )
        return "reconciled-succeeded"

    if "FAILED" in status_name or "TERMINATED" in status_name or "CANCEL" in status_name:
        execute(
            """UPDATE pipeline_runs
                  SET status = 'failed', finished_at = COALESCE(finished_at, now()),
                      error_message = COALESCE(error_message, %s)
                WHERE id = %s AND status IN ('queued', 'running')""",
            (f"reconciled from temporal: {status_name.lower()}", run_id),
        )
        return f"reconciled-{status_name.lower()}"

    return f"unknown-status-{status_name}"


async def _tick() -> dict[str, int]:
    """One reconciliation pass. Returns counts per action for log/metrics."""
    from app.routers.v3.db import fetch_all
    rows = fetch_all(
        """SELECT id, temporal_workflow_id, status, started_at
             FROM pipeline_runs
            WHERE status IN ('queued', 'running')
              AND started_at < now() - (%s * INTERVAL '1 minute')
            ORDER BY started_at ASC
            LIMIT %s""",
        (_STALE_AFTER_MINUTES, _BATCH_SIZE),
    ) or []
    if not rows:
        return {"checked": 0}
    client = await _temporal_client()
    if client is None:
        log.warning(
            "orphan_watchdog: %d stale rows but temporal unreachable; skipping",
            len(rows),
        )
        return {"checked": 0, "temporal_unreachable": 1, "stale_pending": len(rows)}
    actions: dict[str, int] = {}
    for row in rows:
        try:
            action = await _reconcile_one(client, dict(row))
        except Exception as exc:
            log.exception("orphan_watchdog: row %s reconcile crashed: %s", row.get("id"), exc)
            action = "exception"
        actions[action] = actions.get(action, 0) + 1
    return {"checked": len(rows), **actions}


async def _watchdog_loop() -> None:
    while True:
        try:
            stats = await _tick()
            if stats.get("checked", 0) > 0:
                log.info("orphan_watchdog: %s", stats)
        except Exception as exc:
            log.exception("orphan_watchdog tick crashed: %s", exc)
        await asyncio.sleep(_INTERVAL_SECONDS)


async def start_orphan_watchdog() -> asyncio.Task:
    """Launch the watchdog loop. Idempotent — safe to call from startup."""
    log.info("orphan_watchdog: starting (interval=%ss, stale_after=%smin)",
             _INTERVAL_SECONDS, _STALE_AFTER_MINUTES)
    return asyncio.create_task(_watchdog_loop())
