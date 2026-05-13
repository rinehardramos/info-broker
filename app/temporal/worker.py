"""Temporal worker for IS runs — separate from pipeline-tasks worker.

Run with: python -m app.temporal.worker
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger(__name__)

IS_TASK_QUEUE = "is-run-tasks"


async def run_is_worker() -> None:
    from temporalio.client import Client
    from temporalio.worker import Worker
    from app.temporal.workflows.is_run import ISRunWorkflow
    from app.temporal.activities.brain import run_is_brain
    from app.temporal.activities.budget import reserve_budget, release_budget_and_mark_failed
    from app.temporal.activities.post_process import post_process
    from app.temporal.activities.preflight import preflight_validation, mark_awaiting_input

    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = int(os.getenv("TEMPORAL_PORT", "7233"))

    client = await Client.connect(f"{host}:{port}")
    worker = Worker(
        client,
        IS_TASK_QUEUE,
        workflows=[ISRunWorkflow],
        activities=[
            run_is_brain,
            reserve_budget,
            release_budget_and_mark_failed,
            post_process,
            preflight_validation,
            mark_awaiting_input,
        ],
    )
    log.info("IS Temporal worker starting on queue %s", IS_TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_is_worker())
