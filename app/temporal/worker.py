"""Temporal worker for IS runs - separate from pipeline-tasks worker.

Run with: python -m app.temporal.worker
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger(__name__)

IS_QUEUE_NAME = "is-run-tasks"


async def run_is_worker() -> None:
    from temporalio.client import Client
    from temporalio.worker import Worker
    from app.temporal.workflows.is_run import ISRunWorkflow
    from app.temporal.workflows.is_loop_run import IsLoopRunWorkflow
    from app.temporal.activities.brain import run_is_brain
    from app.temporal.activities.brain_turn import init_working_memory, run_brain_turn
    from app.temporal.activities.budget import reserve_budget, release_budget_and_mark_failed
    from app.temporal.activities.post_process import post_process
    from app.temporal.activities.preflight import preflight_validation, mark_awaiting_input
    from app.temporal.activities.conflict_check import conflict_check

    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = int(os.getenv("TEMPORAL_PORT", "7233"))

    client = await Client.connect(f"{host}:{port}")
    queue_name = IS_QUEUE_NAME
    worker = Worker(
        client,
        task_queue=queue_name,
        workflows=[ISRunWorkflow, IsLoopRunWorkflow],
        activities=[
            run_is_brain,
            init_working_memory,
            run_brain_turn,
            reserve_budget,
            release_budget_and_mark_failed,
            post_process,
            preflight_validation,
            mark_awaiting_input,
            conflict_check,
        ],
    )
    log.info("IS Temporal worker starting on queue %s", queue_name)
    await worker.run()


# Backwards compat alias for any importer that referenced the original name.
IS_TASK_QUEUE = IS_QUEUE_NAME


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_is_worker())
