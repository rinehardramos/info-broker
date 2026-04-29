from __future__ import annotations

import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import (
    NodeTypeOut,
    PipelineDetailOut,
    PipelineEdgeOut,
    PipelineIn,
    PipelineNodeOut,
    PipelineOut,
    PipelineRunDetailOut,
    PipelineRunOut,
    PipelineStepRunOut,
)

router = APIRouter(prefix="/v3/pipelines", tags=["v3-pipelines"])
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node type enable/disable helpers
# ---------------------------------------------------------------------------

def _node_enabled_key(node_type: str) -> str:
    return f"pipeline_node.{node_type}.enabled"


def _is_node_enabled(node_type: str) -> bool:
    row = fetch_one(
        "SELECT value FROM core_settings WHERE key = %s",
        (_node_enabled_key(node_type),),
    )
    return row["value"].lower() == "true" if row else True  # default: enabled


def _set_node_enabled(node_type: str, enabled: bool) -> None:
    execute(
        """
        INSERT INTO core_settings (key, value, is_secret)
        VALUES (%s, %s, false)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (_node_enabled_key(node_type), "true" if enabled else "false"),
    )


# ---------------------------------------------------------------------------
# Node types (must come BEFORE parametric routes)
# ---------------------------------------------------------------------------

@router.get("/nodes/types", response_model=list[NodeTypeOut])
def list_node_types(user: dict = Depends(get_current_user)):
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()
    return [
        NodeTypeOut(
            node_type=n.node_type,
            display_name=n.display_name,
            category=n.category,
            config_schema=n.config_schema,
        )
        for n in NodeRegistry.all()
        if _is_node_enabled(n.node_type)
    ]


@router.get("/nodes/types/{node_type}/enabled")
def get_node_type_enabled(node_type: str, user: dict = Depends(get_current_user)):
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()
    valid = {n.node_type for n in NodeRegistry.all()}
    if node_type not in valid:
        raise HTTPException(status_code=404, detail=f"Unknown node type: {node_type!r}")
    return {"node_type": node_type, "enabled": _is_node_enabled(node_type)}


@router.put("/nodes/types/{node_type}/enabled", status_code=204)
def set_node_type_enabled(
    node_type: str,
    body: dict,
    user: dict = Depends(get_current_user),
):
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()
    valid = {n.node_type for n in NodeRegistry.all()}
    if node_type not in valid:
        raise HTTPException(status_code=404, detail=f"Unknown node type: {node_type!r}")
    _set_node_enabled(node_type, bool(body.get("enabled", True)))


# ---------------------------------------------------------------------------
# Run detail (must come BEFORE parametric routes)
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}", response_model=PipelineRunDetailOut)
def get_run(run_id: str, user: dict = Depends(get_current_user)):
    run = fetch_one(
        "SELECT * FROM pipeline_runs WHERE id = %s AND user_id = %s",
        (run_id, str(user["id"])),
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    steps = fetch_all(
        "SELECT * FROM pipeline_step_runs WHERE run_id = %s ORDER BY started_at",
        (run_id,),
    )
    return PipelineRunDetailOut(
        **dict(run),
        steps=[PipelineStepRunOut(**dict(s)) for s in steps],
    )


# ---------------------------------------------------------------------------
# Pipeline CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=PipelineOut, status_code=201)
def create_pipeline(body: PipelineIn, user: dict = Depends(get_current_user)):
    pipeline_id = str(uuid.uuid4())
    row = fetch_one(
        """
        INSERT INTO pipelines (id, user_id, name, description)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (pipeline_id, str(user["id"]), body.name, body.description),
    )
    _upsert_nodes_edges(pipeline_id, body)
    return PipelineOut(**dict(row))


@router.get("", response_model=list[PipelineOut])
def list_pipelines(user: dict = Depends(get_current_user)):
    rows = fetch_all(
        "SELECT * FROM pipelines WHERE user_id = %s ORDER BY created_at DESC",
        (str(user["id"]),),
    )
    return [PipelineOut(**dict(r)) for r in rows]


@router.get("/{pipeline_id}", response_model=PipelineDetailOut)
def get_pipeline(pipeline_id: str, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT * FROM pipelines WHERE id = %s AND user_id = %s",
        (pipeline_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    nodes = fetch_all(
        "SELECT * FROM pipeline_nodes WHERE pipeline_id = %s ORDER BY position_y, position_x",
        (pipeline_id,),
    )
    edges = fetch_all(
        "SELECT * FROM pipeline_edges WHERE pipeline_id = %s",
        (pipeline_id,),
    )
    return PipelineDetailOut(
        **dict(row),
        nodes=[PipelineNodeOut(**dict(n)) for n in nodes],
        edges=[PipelineEdgeOut(**dict(e)) for e in edges],
    )


@router.put("/{pipeline_id}", response_model=PipelineOut)
def update_pipeline(pipeline_id: str, body: PipelineIn, user: dict = Depends(get_current_user)):
    row = fetch_one(
        """
        UPDATE pipelines SET name = %s, description = %s, updated_at = now()
        WHERE id = %s AND user_id = %s
        RETURNING *
        """,
        (body.name, body.description, pipeline_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    # Delete and recreate nodes+edges
    execute("DELETE FROM pipeline_nodes WHERE pipeline_id = %s", (pipeline_id,))
    _upsert_nodes_edges(pipeline_id, body)
    return PipelineOut(**dict(row))


@router.delete("/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "DELETE FROM pipelines WHERE id = %s AND user_id = %s RETURNING id",
        (pipeline_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")


# ---------------------------------------------------------------------------
# Pipeline runs
# ---------------------------------------------------------------------------

@router.post("/{pipeline_id}/run", response_model=PipelineRunOut, status_code=202)
async def start_pipeline_run(pipeline_id: str, user: dict = Depends(get_current_user)):
    from temporalio.client import Client
    from app.pipeline.workflow import TASK_QUEUE, PipelineRunInput, NodeSpec, EdgeSpec, PipelineWorkflow

    pipeline = fetch_one(
        "SELECT * FROM pipelines WHERE id = %s AND user_id = %s",
        (pipeline_id, str(user["id"])),
    )
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    nodes_rows = fetch_all(
        "SELECT * FROM pipeline_nodes WHERE pipeline_id = %s",
        (pipeline_id,),
    )
    edges_rows = fetch_all(
        "SELECT * FROM pipeline_edges WHERE pipeline_id = %s",
        (pipeline_id,),
    )

    run_id = str(uuid.uuid4())
    workflow_id = f"pipeline-{run_id}"

    run_row = fetch_one(
        """
        INSERT INTO pipeline_runs (id, pipeline_id, user_id, temporal_workflow_id, status, trigger_type)
        VALUES (%s, %s, %s, %s, 'queued', 'manual')
        RETURNING *
        """,
        (run_id, pipeline_id, str(user["id"]), workflow_id),
    )

    # Create step_run rows for each node
    for node in nodes_rows:
        execute(
            "INSERT INTO pipeline_step_runs (id, run_id, node_id, status) VALUES (%s, %s, %s, 'pending')",
            (str(uuid.uuid4()), run_id, str(node["id"])),
        )

    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = int(os.getenv("TEMPORAL_PORT", "7233"))
    try:
        client = await Client.connect(f"{host}:{port}")
        await client.start_workflow(
            PipelineWorkflow.run,
            PipelineRunInput(
                run_id=run_id,
                user_id=str(user["id"]),
                pipeline_id=pipeline_id,
                nodes=[
                    NodeSpec(
                        node_id=str(n["id"]),
                        node_type=n["node_type"],
                        label=n["label"],
                        config=n["config"] or {},
                    )
                    for n in nodes_rows
                ],
                edges=[
                    EdgeSpec(
                        source_node_id=str(e["source_node_id"]),
                        target_node_id=str(e["target_node_id"]),
                        edge_type=e["edge_type"],
                    )
                    for e in edges_rows
                ],
            ),
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )
    except Exception as exc:
        log.error("Failed to start Temporal workflow for run %s: %s", run_id, exc)
        execute(
            "UPDATE pipeline_runs SET status = 'failed', finished_at = now() WHERE id = %s",
            (run_id,),
        )
        raise HTTPException(status_code=503, detail=f"Temporal unavailable: {exc}")

    return PipelineRunOut(**dict(run_row))


@router.get("/{pipeline_id}/runs", response_model=list[PipelineRunOut])
def list_pipeline_runs(pipeline_id: str, user: dict = Depends(get_current_user)):
    rows = fetch_all(
        "SELECT * FROM pipeline_runs WHERE pipeline_id = %s AND user_id = %s ORDER BY started_at DESC",
        (pipeline_id, str(user["id"])),
    )
    return [PipelineRunOut(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upsert_nodes_edges(pipeline_id: str, body: PipelineIn) -> None:
    """Insert nodes and edges. Nodes use frontend-provided UUIDs as DB IDs."""
    # Build map: frontend_uuid → db_uuid (use frontend UUID directly)
    node_id_map: dict[str, str] = {}
    for node in body.nodes:
        nid = str(node.id) if node.id else str(uuid.uuid4())
        if node.id:
            node_id_map[str(node.id)] = nid
        execute(
            """
            INSERT INTO pipeline_nodes (id, pipeline_id, node_type, label, config, position_x, position_y)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (nid, pipeline_id, node.node_type, node.label,
             json.dumps(node.config),
             node.position_x, node.position_y),
        )

    for edge in body.edges:
        src_id = node_id_map.get(str(edge.source_node_id), str(edge.source_node_id))
        tgt_id = node_id_map.get(str(edge.target_node_id), str(edge.target_node_id))
        execute(
            """
            INSERT INTO pipeline_edges (id, pipeline_id, source_node_id, target_node_id, edge_type)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (str(uuid.uuid4()), pipeline_id, src_id, tgt_id, edge.edge_type),
        )
