from __future__ import annotations

import json
import logging
import os
import uuid

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import AgentMessageIn, AgentMessageOut, AgentPipelineOut

router = APIRouter(prefix="/v3/agent", tags=["v3-agent"])
log = logging.getLogger(__name__)

SYSTEM_PIPELINE_ID = "00000000-0000-4000-8000-000000000001"


# ---------------------------------------------------------------------------
# Agent pipeline preference
# ---------------------------------------------------------------------------

def _get_active_pipeline(user_id: str) -> dict:
    """Return active pipeline row for this user (preference -> system default)."""
    prefs = fetch_one(
        "SELECT agent_pipeline_id FROM ui_preferences WHERE user_id = %s",
        (user_id,),
    )
    preferred_id = prefs["agent_pipeline_id"] if prefs else None

    if preferred_id:
        row = fetch_one(
            "SELECT id, name, is_system FROM pipelines WHERE id = %s AND (user_id = %s OR is_system = true)",
            (str(preferred_id), user_id),
        )
        if row:
            return row

    row = fetch_one(
        "SELECT id, name, is_system FROM pipelines WHERE id = %s",
        (SYSTEM_PIPELINE_ID,),
    )
    if not row:
        raise HTTPException(status_code=503, detail="No agent pipeline configured")
    return row


@router.get("/pipeline", response_model=AgentPipelineOut)
def get_agent_pipeline(user: dict = Depends(get_current_user)):
    row = _get_active_pipeline(str(user["id"]))
    return AgentPipelineOut(
        pipeline_id=str(row["id"]),
        pipeline_name=row["name"],
        is_system=row["is_system"],
    )


class AgentPipelineIn(BaseModel):
    pipeline_id: str


@router.put("/pipeline", response_model=AgentPipelineOut)
def set_agent_pipeline(body: AgentPipelineIn, user: dict = Depends(get_current_user)):
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()

    uid = str(user["id"])
    pipeline = fetch_one(
        "SELECT * FROM pipelines WHERE id = %s AND (user_id = %s OR is_system = true)",
        (body.pipeline_id, uid),
    )
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    nodes = fetch_all(
        "SELECT node_type, position_y FROM pipeline_nodes WHERE pipeline_id = %s",
        (body.pipeline_id,),
    )
    node_meta = {n.node_type: n.category for n in NodeRegistry.all()}
    sources = [n for n in nodes if node_meta.get(n["node_type"]) == "source" and n["node_type"] != "aggregator"]

    if len(sources) != 1:
        raise HTTPException(status_code=422, detail="Agent pipeline must have exactly one source node")
    if sources[0]["node_type"] != "agent_input":
        raise HTTPException(status_code=422, detail="Agent pipeline source must be agent_input")
    if sources[0]["position_y"] != 0:
        raise HTTPException(status_code=422, detail="agent_input must be the first node (position_y=0)")

    execute(
        """
        INSERT INTO ui_preferences (user_id, agent_pipeline_id)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET agent_pipeline_id = EXCLUDED.agent_pipeline_id, updated_at = now()
        """,
        (uid, body.pipeline_id),
    )
    return AgentPipelineOut(
        pipeline_id=body.pipeline_id,
        pipeline_name=pipeline["name"],
        is_system=pipeline["is_system"],
    )


# ---------------------------------------------------------------------------
# Intelligent search — Claude Code brain (no Temporal, no pipeline nodes)
# ---------------------------------------------------------------------------


@router.get("/brain/status")
async def get_brain_status(user: dict = Depends(get_current_user)):
    """Check if the IS brain (Claude Code) is authenticated and ready."""
    from app.is_brain import check_auth

    auth = await check_auth()
    has_api_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    return {
        "ready": auth.get("loggedIn", False) or has_api_key,
        "auth_method": "api_key" if has_api_key else auth.get("authMethod", "none"),
        "logged_in": auth.get("loggedIn", False),
        "has_api_key": has_api_key,
        "email": auth.get("email"),
        "error": auth.get("error"),
    }


# ---------------------------------------------------------------------------
# Agent message — triggers pipeline run via Temporal
# ---------------------------------------------------------------------------

async def _run_is_research(
    run_id: str, uid: str, pipeline_id: str, query: str,
    past_research: list[dict] | None = None,
) -> None:
    """Background task: run IS brain and push WS events."""
    from app.routers.v3.stream import push_event

    await push_event(uid, {
        "type": "job.update", "job_id": run_id, "status": "running",
        "run_id": run_id, "message": query,
    })

    try:
        from app.is_brain import run_research

        async def _on_tool_event(ev: dict) -> None:
            # Strip MCP prefix: mcp__info-broker-mcp__run_ddg_search -> run_ddg_search
            raw_tool = ev.get("tool", "") or ""
            clean_tool = raw_tool.split("__")[-1] if "__" in raw_tool else raw_tool

            if ev.get("type") == "tool_result":
                await push_event(uid, {
                    "type": "is.tool_result",
                    "job_id": run_id, "run_id": run_id,
                    "call_id": ev.get("tool_use_id", ""),
                    "preview": ev.get("preview", ""),
                })
            else:
                await push_event(uid, {
                    "type": "is.tool_call",
                    "job_id": run_id, "run_id": run_id,
                    "tool": clean_tool,
                    "status": ev.get("status", ""),
                    "call_id": ev.get("id", ""),
                })

        # Only advertise healthy+enabled tools to the brain
        from app.routers.v3.pipelines import get_healthy_nodes
        healthy_nodes = await get_healthy_nodes()

        result = await run_research(
            query=query, user_id=uid, past_research=past_research,
            on_event=_on_tool_event,
            available_nodes=healthy_nodes,
        )

        # Check if IS brain returned an error result (no findings, error summary)
        is_error = (
            not result.get("findings")
            and result.get("summary", "").startswith("Research failed:")
        )
        if is_error:
            raise RuntimeError(result["summary"])

        suggested_pipeline = result.get("pipeline")
        execute(
            """INSERT INTO research_trails
                (id, user_id, run_id, query, entity_type, trail, findings, tool_calls, suggested_pipeline)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (str(uuid.uuid4()), uid, run_id, query,
             result.get("entity_type", "unknown"),
             json.dumps(result.get("tree", {})),
             json.dumps(result.get("findings", [])),
             result.get("tree", {}).get("total_branches", 0),
             json.dumps(suggested_pipeline) if suggested_pipeline else None),
        )

        # Deduplicate plugin suggestions against existing nodes
        from app.pipeline.nodes import NodeRegistry
        NodeRegistry.auto_discover()
        existing_types = {n.node_type for n in NodeRegistry.all()}

        for plugin in result.get("suggested_plugins", []):
            pname = (plugin.get("name") or "").lower().replace("-", "_").replace(" ", "_")
            reason = plugin.get("reason", "")
            is_enhancement = reason.startswith("ENHANCE:") or pname in existing_types
            if not is_enhancement:
                for et in existing_types:
                    if pname in et or et in pname:
                        is_enhancement = True
                        plugin["reason"] = f"ENHANCE ({et}): {reason}"
                        break
            plugin["is_enhancement"] = is_enhancement
            status = "enhancement" if is_enhancement else "pending"
            execute(
                "INSERT INTO plugin_requests (id, user_id, spec, status) VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()), uid, json.dumps(plugin), status),
            )

        execute(
            "UPDATE pipeline_runs SET status = 'succeeded', finished_at = now() WHERE id = %s",
            (run_id,),
        )

        summary = result.get("summary", "Research complete.")
        findings_count = len(result.get("findings", []))
        await push_event(uid, {
            "type": "job.completed", "job_id": run_id, "status": "succeeded",
            "run_id": run_id,
            "message": f"{summary[:200]}{'...' if len(summary) > 200 else ''} ({findings_count} findings)",
        })
        # Also notify Live panel's pipeline section
        await push_event(uid, {
            "type": "pipeline.run.complete", "run_id": run_id, "status": "succeeded",
        })
    except Exception as exc:
        log.error("IS Brain failed: %s", exc)
        execute(
            "UPDATE pipeline_runs SET status = 'failed', finished_at = now() WHERE id = %s",
            (run_id,),
        )
        await push_event(uid, {
            "type": "job.failed", "job_id": run_id, "status": "failed",
            "run_id": run_id,
            "message": f"Research failed: {str(exc)[:200]}",
        })
        await push_event(uid, {
            "type": "pipeline.run.complete", "run_id": run_id, "status": "failed",
        })


@router.post("/message", response_model=AgentMessageOut, status_code=202)
async def send_message(
    body: AgentMessageIn,
    user: dict = Depends(get_current_user),
):
    from app.pipeline.workflow import NodeSpec, EdgeSpec
    from app.pipeline.runner import launch_pipeline_run

    uid = str(user["id"])
    pipeline_row = _get_active_pipeline(uid)
    pipeline_id = str(pipeline_row["id"])

    run_id = str(uuid.uuid4())
    workflow_id = f"pipeline-{run_id}"

    if body.use_intelligent_search:
        # IS bypasses the pipeline entirely — runs Claude Code as a subprocess brain.
        # A pipeline_run record is created for UI tracking; research runs in background.
        fetch_one(
            """
            INSERT INTO pipeline_runs (id, pipeline_id, user_id, temporal_workflow_id, status, trigger_type)
            VALUES (%s, %s, %s, %s, 'queued', 'agent_is')
            RETURNING *
            """,
            (run_id, pipeline_id, uid, workflow_id),
        )

        # Fetch parent research trail for "Go Deeper" context
        past_research = None
        if body.parent_run_id:
            parent_trail = fetch_one(
                "SELECT query, entity_type, findings, trail FROM research_trails WHERE run_id = %s",
                (body.parent_run_id,),
            )
            if parent_trail:
                trail_data = parent_trail["trail"] if isinstance(parent_trail["trail"], dict) else {}
                past_research = [{
                    "query": parent_trail["query"],
                    "entity_type": parent_trail["entity_type"],
                    "findings": parent_trail["findings"] if isinstance(parent_trail["findings"], list) else [],
                    "summary": "",
                    "deeper_leads": trail_data.get("deeper_leads", []),
                }]

        # Fire and forget — research runs async, pushes WS events when done.
        task = asyncio.create_task(
            _run_is_research(run_id, uid, pipeline_id, body.message, past_research=past_research)
        )
        task.add_done_callback(lambda t: log.error("IS research task failed: %s", t.exception()) if t.exception() else None)

        return AgentMessageOut(job_id=run_id)

    else:
        nodes_rows = fetch_all(
            "SELECT * FROM pipeline_nodes WHERE pipeline_id = %s ORDER BY position_y, position_x",
            (pipeline_id,),
        )
        edges_rows = fetch_all(
            "SELECT * FROM pipeline_edges WHERE pipeline_id = %s",
            (pipeline_id,),
        )

        fetch_one(
            """
            INSERT INTO pipeline_runs (id, pipeline_id, user_id, temporal_workflow_id, status, trigger_type)
            VALUES (%s, %s, %s, %s, 'queued', 'agent')
            RETURNING *
            """,
            (run_id, pipeline_id, uid, workflow_id),
        )
        for node in nodes_rows:
            execute(
                "INSERT INTO pipeline_step_runs (id, run_id, node_id, status) VALUES (%s, %s, %s, 'pending')",
                (str(uuid.uuid4()), run_id, str(node["id"])),
            )

        def _node_config(node: dict) -> dict:
            cfg = dict(node["config"] or {})
            if node["node_type"] == "agent_input":
                cfg["message"] = body.message
            return cfg

        nodes = [
            NodeSpec(
                node_id=str(n["id"]),
                node_type=n["node_type"],
                label=n["label"],
                config=_node_config(n),
            )
            for n in nodes_rows
        ]
        edges = [
            EdgeSpec(
                source_node_id=str(e["source_node_id"]),
                target_node_id=str(e["target_node_id"]),
                edge_type=e["edge_type"],
            )
            for e in edges_rows
        ]

    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = int(os.getenv("TEMPORAL_PORT", "7233"))

    try:
        await launch_pipeline_run(
            run_id=run_id,
            user_id=uid,
            pipeline_id=pipeline_id,
            nodes=nodes,
            edges=edges,
            temporal_host=host,
            temporal_port=port,
        )
    except HTTPException:
        execute(
            "UPDATE pipeline_runs SET status = 'failed', finished_at = now() WHERE id = %s",
            (run_id,),
        )
        raise

    return AgentMessageOut(job_id=run_id)
