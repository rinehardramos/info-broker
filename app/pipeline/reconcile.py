from __future__ import annotations

import logging

from app.routers.v3.db import execute, fetch_all

log = logging.getLogger(__name__)


def reconcile_orphaned_runs() -> int:
    """Mark manual pipeline runs left in running/queued at startup as failed.

    Called once at server startup. Temporal workflow IDs are gone after a restart,
    so any run still in a non-terminal state will never complete.
    """
    orphans = fetch_all(
        """SELECT id FROM pipeline_runs
           WHERE status IN ('running', 'queued')
             AND trigger_type = 'manual'""",
        (),
    )
    if not orphans:
        return 0

    execute(
        """UPDATE pipeline_runs
           SET status = 'failed',
               finished_at = now(),
               error_message = 'Server restarted — Temporal workflow was killed'
           WHERE status IN ('running', 'queued')
             AND trigger_type = 'manual'""",
        (),
    )
    count = len(orphans)
    log.info("Marked %d orphaned manual pipeline runs as failed on startup", count)
    return count


def sweep_stale_runs(max_age_minutes: int = 60) -> None:
    """Periodic sweep: mark manual runs running longer than max_age_minutes as failed.

    Catches runs whose Temporal workflow completed or crashed without updating the DB.
    The Temporal activity timeout is 15 min; 60 min is a safe ceiling for any pipeline.
    """
    error_msg = f"Run exceeded maximum duration ({max_age_minutes} minutes) — killed by sweep"
    execute(
        """UPDATE pipeline_runs
           SET status = 'failed',
               finished_at = now(),
               error_message = %s
           WHERE status = 'running'
             AND trigger_type = 'manual'
             AND started_at < NOW() - (%s * INTERVAL '1 minute')""",
        (error_msg, max_age_minutes),
    )
