"""Temporal worker entrypoint.

Run with: python -m app.pipeline.worker
"""
from __future__ import annotations

import asyncio
import logging
import os

# Load secrets BEFORE any other app imports — must run outside Temporal sandbox.
from app.secrets import load_secrets
load_secrets("info-broker")

from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from app.pipeline.workflow import TASK_QUEUE, PipelineWorkflow, execute_node

log = logging.getLogger(__name__)


async def main() -> None:
    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = int(os.getenv("TEMPORAL_PORT", "7233"))
    target = f"{host}:{port}"

    log.info("Connecting to Temporal at %s", target)
    client = await Client.connect(target)

    # Allow our DB/secrets modules through Temporal's workflow sandbox --
    # they use os.getenv() which the sandbox restricts by default.
    sandbox_runner = SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions.default.with_passthrough_modules(
            "app.routers.v3.db",
            "app.secrets",
        )
    )

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[PipelineWorkflow],
        activities=[execute_node],
        workflow_runner=sandbox_runner,
    )

    log.info("Starting worker on queue %s", TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
