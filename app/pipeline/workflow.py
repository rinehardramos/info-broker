from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

log = logging.getLogger(__name__)

TASK_QUEUE = "pipeline-tasks"


# ---------------------------------------------------------------------------
# Dataclasses for workflow/activity I/O
# ---------------------------------------------------------------------------

@dataclass
class NodeSpec:
    node_id: str
    node_type: str
    label: str
    config: dict = field(default_factory=dict)


@dataclass
class EdgeSpec:
    source_node_id: str
    target_node_id: str
    edge_type: str = "results"


@dataclass
class PipelineRunInput:
    run_id: str
    user_id: str
    pipeline_id: str
    nodes: list[NodeSpec] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)


@dataclass
class ActivityInput:
    run_id: str
    user_id: str
    node: NodeSpec
    inputs: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

@activity.defn(name="execute_node")
async def execute_node(inp: ActivityInput) -> list[dict]:
    from app.pipeline.nodes import NodeRegistry
    from app.routers.v3.db import execute as db_execute
    from app.pipeline.nodes.base import RunContext

    NodeRegistry.auto_discover()

    # Mark step as running
    db_execute(
        "UPDATE pipeline_step_runs SET status = 'running', started_at = now() WHERE run_id = %s AND node_id = %s",
        (inp.run_id, inp.node.node_id),
    )

    # Best-effort WebSocket push
    try:
        from app.routers.v3.stream import push_event
        asyncio.create_task(push_event(inp.user_id, {
            "type": "pipeline.step.update",
            "run_id": inp.run_id,
            "node_id": inp.node.node_id,
            "status": "running",
            "item_count": 0,
        }))
    except Exception:
        pass

    async def _push(event: dict) -> None:
        try:
            from app.routers.v3.stream import push_event
            await push_event(inp.user_id, event)
        except Exception:
            pass

    try:
        node = NodeRegistry.get(inp.node.node_type)
        ctx = RunContext(user_id=inp.user_id, run_id=inp.run_id, node_id=inp.node.node_id, push_event=_push)
        timeout = int(inp.node.config.get("timeout_seconds", 60))
        try:
            result = await asyncio.wait_for(
                node.execute(inp.node.config, inp.inputs, ctx),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(f"Timed out after {timeout}s")
        item_count = len(result) if isinstance(result, list) else 0

        db_execute(
            "UPDATE pipeline_step_runs SET status = 'succeeded', item_count = %s, finished_at = now() WHERE run_id = %s AND node_id = %s",
            (item_count, inp.run_id, inp.node.node_id),
        )

        try:
            from app.routers.v3.stream import push_event
            asyncio.create_task(push_event(inp.user_id, {
                "type": "pipeline.step.update",
                "run_id": inp.run_id,
                "node_id": inp.node.node_id,
                "status": "succeeded",
                "item_count": item_count,
            }))
        except Exception:
            pass

        return result

    except Exception as exc:
        error_msg = str(exc)
        log.error("execute_node failed for node %s: %s", inp.node.node_id, exc)
        db_execute(
            "UPDATE pipeline_step_runs SET status = 'failed', error_message = %s, finished_at = now() WHERE run_id = %s AND node_id = %s",
            (error_msg, inp.run_id, inp.node.node_id),
        )
        try:
            from app.routers.v3.stream import push_event
            asyncio.create_task(push_event(inp.user_id, {
                "type": "pipeline.step.update",
                "run_id": inp.run_id,
                "node_id": inp.node.node_id,
                "status": "failed",
                "item_count": 0,
            }))
        except Exception:
            pass
        raise


# ---------------------------------------------------------------------------
# Topological sort helper
# ---------------------------------------------------------------------------

def _topo_sort(nodes: list[NodeSpec], edges: list[EdgeSpec]) -> list[list[NodeSpec]]:
    """Return layers of nodes in topological order (parallel nodes in same layer)."""
    # Only "results" edges drive execution order; "tool" edges are config-only
    result_edges = [e for e in edges if e.edge_type != "tool"]
    node_map = {n.node_id: n for n in nodes}
    deps: dict[str, set[str]] = {n.node_id: set() for n in nodes}
    for edge in result_edges:
        if edge.target_node_id in deps:
            deps[edge.target_node_id].add(edge.source_node_id)

    layers: list[list[NodeSpec]] = []
    resolved: set[str] = set()

    while len(resolved) < len(nodes):
        layer_ids = [
            nid for nid, d in deps.items()
            if nid not in resolved and d.issubset(resolved)
        ]
        if not layer_ids:
            # Cycle or unreachable nodes — add remaining as final layer
            remaining = [n for n in nodes if n.node_id not in resolved]
            if remaining:
                layers.append(remaining)
            break
        layer = [node_map[nid] for nid in layer_ids]
        layers.append(layer)
        resolved.update(layer_ids)

    return layers


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

@workflow.defn(name="PipelineWorkflow")
class PipelineWorkflow:

    @workflow.run
    async def run(self, inp: PipelineRunInput) -> str:
        from app.routers.v3.db import execute as db_execute

        db_execute(
            "UPDATE pipeline_runs SET status = 'running' WHERE id = %s",
            (inp.run_id,),
        )

        # Separate tool edges from execution edges
        tool_edges = [e for e in inp.edges if e.edge_type == "tool"]
        result_edges = [e for e in inp.edges if e.edge_type != "tool"]
        tool_target_ids = {e.target_node_id for e in tool_edges}

        # Build tool lookup: source_node_id → [{node_type, node_id, config}]
        node_map = {n.node_id: n for n in inp.nodes}
        tool_lookup: dict[str, list[dict]] = {}
        for te in tool_edges:
            target = node_map.get(te.target_node_id)
            if target:
                tool_lookup.setdefault(te.source_node_id, []).append({
                    "node_type": target.node_type,
                    "node_id": target.node_id,
                    "config": target.config,
                })

        # Inject _tool_nodes into config of nodes that have outgoing tool edges
        for node in inp.nodes:
            if node.node_id in tool_lookup:
                node.config["_tool_nodes"] = tool_lookup[node.node_id]

        # Exclude tool-target nodes (datastores) from execution
        executable_nodes = [n for n in inp.nodes if n.node_id not in tool_target_ids]
        layers = _topo_sort(executable_nodes, result_edges)

        # Build edge lookup: target_node_id → list of source_node_ids (results only)
        edge_lookup: dict[str, list[str]] = {}
        for edge in result_edges:
            edge_lookup.setdefault(edge.target_node_id, []).append(edge.source_node_id)

        # node_id → output items
        outputs: dict[str, list[dict]] = {}

        try:
            for layer in layers:
                # Execute all nodes in this layer in parallel
                activity_coros = []
                for node in layer:
                    upstream_ids = edge_lookup.get(node.node_id, [])
                    merged_inputs: list[dict] = []
                    for uid in upstream_ids:
                        merged_inputs.extend(outputs.get(uid, []))

                    activity_coros.append(
                        workflow.execute_activity(
                            execute_node,
                            ActivityInput(
                                run_id=inp.run_id,
                                user_id=inp.user_id,
                                node=node,
                                inputs=merged_inputs,
                            ),
                            start_to_close_timeout=timedelta(minutes=15),
                            retry_policy=RetryPolicy(maximum_attempts=1),
                        )
                    )

                results = await asyncio.gather(*activity_coros, return_exceptions=True)

                for node, result in zip(layer, results):
                    if isinstance(result, Exception):
                        raise result
                    outputs[node.node_id] = result  # type: ignore[assignment]

            db_execute(
                "UPDATE pipeline_runs SET status = 'succeeded', finished_at = now() WHERE id = %s",
                (inp.run_id,),
            )
            return "succeeded"

        except Exception as exc:
            log.error("PipelineWorkflow %s failed: %s", inp.run_id, exc)
            db_execute(
                "UPDATE pipeline_runs SET status = 'failed', finished_at = now() WHERE id = %s",
                (inp.run_id,),
            )
            raise
