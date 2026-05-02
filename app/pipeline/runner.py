from __future__ import annotations

import logging
from fastapi import HTTPException
from app.pipeline.workflow import TASK_QUEUE, PipelineRunInput, NodeSpec, EdgeSpec, PipelineWorkflow

log = logging.getLogger(__name__)


async def launch_pipeline_run(
    run_id: str,
    user_id: str,
    pipeline_id: str,
    nodes: list[NodeSpec],
    edges: list[EdgeSpec],
    temporal_host: str = "localhost",
    temporal_port: int = 7233,
) -> None:
    """Start a Temporal pipeline workflow. Raises HTTPException 503 on connection failure."""
    from temporalio.client import Client

    workflow_id = f"pipeline-{run_id}"
    try:
        client = await Client.connect(f"{temporal_host}:{temporal_port}")
        await client.start_workflow(
            PipelineWorkflow.run,
            PipelineRunInput(
                run_id=run_id,
                user_id=user_id,
                pipeline_id=pipeline_id,
                nodes=nodes,
                edges=edges,
            ),
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )
    except Exception as exc:
        log.error("Failed to start Temporal workflow for run %s: %s", run_id, exc)
        raise HTTPException(status_code=503, detail=f"Temporal unavailable: {exc}")
