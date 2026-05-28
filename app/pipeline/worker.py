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


async def _init_observability() -> None:
    """Initialise UsageEmitter and PricingResolver in this worker process.

    Mirrors the lifespan logic in app/main.py so that telemetry hooks in
    app/pipeline/workflow.py (emit_step_run) and app/pipeline/nodes/ have a
    live emitter and resolver — without these, _emitter_ref._emitter stays None
    and all usage events are silently dropped.
    """
    try:
        import redis.asyncio as aioredis
        _mon_redis_url = os.getenv("MONITORING_REDIS_URL", "redis://monitoring-redis:6379/0")
        _mon_redis = aioredis.from_url(_mon_redis_url)

        from platform_monitoring.usage.emitter import UsageEmitter
        _emitter = UsageEmitter(_mon_redis)
        import app.observability.usage_emitter_ref as _emitter_ref
        _emitter_ref._emitter = _emitter
        log.info("UsageEmitter registered in temporal-worker (stream=mon:usage, redis=%s)", _mon_redis_url)
    except Exception:
        log.warning("UsageEmitter init failed in temporal-worker — telemetry disabled", exc_info=True)

    try:
        from app.observability.pricing import PricingResolver
        import app.observability.pricing_ref as _pricing_ref
        _pr_dsn = os.getenv("DATABASE_URL", "")
        if _pr_dsn:
            _resolver = PricingResolver(_pr_dsn)
            _pricing_ref._resolver = _resolver
            log.info("PricingResolver registered in temporal-worker")
        else:
            log.warning("PricingResolver not initialised in temporal-worker: DATABASE_URL not set")
    except Exception:
        log.warning("PricingResolver init failed in temporal-worker — cost estimation disabled", exc_info=True)


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

    # Initialise observability (best-effort — worker keeps running even if this fails)
    await _init_observability()

    log.info("Starting worker on queue %s", TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
