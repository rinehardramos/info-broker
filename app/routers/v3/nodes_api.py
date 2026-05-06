"""Node execution endpoint — allows MCP server (and other callers) to run individual pipeline nodes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_api_key
from app.pipeline.nodes import NodeRegistry
from app.pipeline.nodes.base import RunContext

router = APIRouter(prefix="/v3/nodes", tags=["v3-nodes"])
log = logging.getLogger(__name__)


def _get_node(node_type: str):
    NodeRegistry.auto_discover()
    try:
        return NodeRegistry.get(node_type)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown node type: {node_type!r}")


@router.post("/{node_type}/execute")
async def execute_node(
    node_type: str,
    body: dict,
    _key: str = Depends(require_api_key),
) -> dict:
    """Execute a pipeline node ad-hoc.

    The request body is used as the node's config. Any ``inputs`` key in the
    body is extracted and passed as the upstream items list; everything else
    becomes the config dict.
    """
    node = _get_node(node_type)

    # Allow caller to pass inputs alongside config in the same payload.
    inputs: list[dict] = body.pop("inputs", [])

    # For source/search nodes that accept a bare `query`, wrap it as an input
    # item so the node can iterate over it.
    if not inputs and "query" in body:
        inputs = [{"query": body["query"]}]

    ctx = RunContext(
        user_id="mcp-system",
        run_id="mcp-adhoc",
        node_id="mcp-adhoc",
    )

    try:
        result = await node.execute(body, inputs, ctx)
    except Exception as exc:
        log.exception("Node %s execution failed", node_type)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "success", "items": result, "count": len(result)}


@router.post("/{node_type}/tool-invoke")
async def tool_invoke_node(
    node_type: str,
    body: dict,
    _key: str = Depends(require_api_key),
) -> dict:
    """Invoke a ToolCallable node directly with LLM-provided params.

    Only nodes that implement the ``ToolCallable`` protocol (datastores such as
    obsidian_vault and local_files) support this endpoint.
    """
    node = _get_node(node_type)

    if not hasattr(node, "tool_invoke"):
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_type!r} does not support tool_invoke",
        )

    ctx = RunContext(
        user_id="mcp-system",
        run_id="mcp-adhoc",
        node_id="mcp-adhoc",
    )

    try:
        result = await node.tool_invoke(body, ctx)
    except Exception as exc:
        log.exception("Node %s tool_invoke failed", node_type)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "success", "items": result, "count": len(result)}
