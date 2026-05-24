"""Node execution endpoint — allows MCP server (and other callers) to run individual pipeline nodes."""
from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app.deps import require_api_key
from app.observability.tracker import tracker
from app.pipeline.nodes import NodeRegistry
from app.pipeline.nodes.base import RunContext
from app.routers.v3.stream import push_event

router = APIRouter(prefix="/v3/nodes", tags=["v3-nodes"])
log = logging.getLogger(__name__)

# Per-item target fields that ad-hoc / MCP callers pass at the top level of an
# /execute payload instead of inside an explicit `inputs` list. When one of
# these is present and no `inputs` were given, the payload is wrapped as a
# single upstream item so nodes that read these fields per-item receive their
# target. Pure config keys (research_goal, criteria, instructions, ...) are
# intentionally absent so config-only nodes keep their empty-inputs behaviour.
_INPUT_TARGET_FIELDS = frozenset(
    {
        "query",
        "domain",
        "url",
        "urls",
        "website",
        "company_name",
        "company",
        "full_name",
        "name",
        "username",
        "title",
        "email",
        "phone",
    }
)


def _wrap_payload_as_input(inputs: list[dict], body: dict) -> list[dict]:
    """Wrap an ad-hoc /execute payload as a single upstream item when needed.

    Ad-hoc callers (the MCP server, manual API calls) pass the node's target as
    top-level fields rather than an explicit ``inputs`` list — e.g.
    ``{"query": ...}`` for search nodes, ``{"domain": ...}`` for whois,
    ``{"urls": [...]}`` for web_crawl. Nodes read their target from each upstream
    item (``item["query"]``, ``item["domain"]``, ``item["url"]``, ...), so when
    no explicit inputs are given but the payload carries a recognised target
    field, the payload is wrapped as a single upstream item. ``body`` is still
    passed through as config; nodes read only the keys they need from each side.

    Without this, enrich nodes such as whois_lookup iterate an empty inputs list
    and return zero items while the endpoint still reports ``status: success``
    (see issue #111).

    The allowlist is deliberately limited to per-item target fields. Pure config
    keys (``research_goal``, ``criteria``, ``instructions``, ...) are excluded so
    config-only nodes that synthesise their own input when ``inputs`` is empty
    (intelligent_search, ai_scoring, summarizer) keep working unchanged.
    """
    if not inputs and any(k in body for k in _INPUT_TARGET_FIELDS):
        return [dict(body)]
    return inputs


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
    request: Request,
    _key: str = Depends(require_api_key),
) -> dict:
    """Execute a pipeline node ad-hoc.

    The request body is used as the node's config. Any ``inputs`` key in the
    body is extracted and passed as the upstream items list; everything else
    becomes the config dict.
    """
    caller_identity: str = request.headers.get("X-Caller-Identity", "unknown")
    session_id: str | None = request.headers.get("X-Session-Id")
    call_id = str(uuid.uuid4())

    node = _get_node(node_type)

    # Allow caller to pass inputs alongside config in the same payload.
    inputs: list[dict] = body.pop("inputs", [])

    inputs = _wrap_payload_as_input(inputs, body)

    ctx = RunContext(
        user_id="mcp-system",
        run_id="mcp-adhoc",
        node_id="mcp-adhoc",
    )

    # --- observability: record call start (non-fatal) ---
    try:
        # Ensure session exists (auto-create if header provided)
        effective_session = session_id or call_id
        await tracker.start_session(
            caller_identity=caller_identity,
            session_type="mcp_tool_call",
            session_id=effective_session,
        )
        await tracker.log_call_start(
            session_id=effective_session,
            tool_name=node_type,
            node_type=node_type,
            call_id=call_id,
            caller_identity=caller_identity,
            input_params=body,
        )
        await push_event(
            "__admin__",
            {
                "type": "mcp.tool_call.start",
                "call_id": call_id,
                "node_type": node_type,
                "caller_identity": caller_identity,
                "session_id": session_id,
            },
        )
    except Exception:
        log.debug("observability log_call_start failed", exc_info=True)

    t0 = time.monotonic_ns()

    try:
        result = await node.execute(body, inputs, ctx)
    except Exception as exc:
        duration_ms = (time.monotonic_ns() - t0) // 1_000_000
        log.exception("Node %s execution failed", node_type)

        # --- observability: record failure (non-fatal) ---
        try:
            await tracker.log_call_complete(
                call_id=call_id,
                status="failed",
                duration_ms=duration_ms,
                error_message=str(exc),
            )
            await push_event(
                "__admin__",
                {
                    "type": "mcp.tool_call.complete",
                    "call_id": call_id,
                    "node_type": node_type,
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "error_message": str(exc),
                },
            )
        except Exception:
            log.debug("observability log_call_complete (failed) failed", exc_info=True)

        raise HTTPException(status_code=500, detail=str(exc)) from exc

    duration_ms = (time.monotonic_ns() - t0) // 1_000_000

    # --- observability: record success (non-fatal) ---
    try:
        await tracker.log_call_complete(
            call_id=call_id,
            status="succeeded",
            result_preview=json.dumps(result[:3]) if result else None,
            result_count=len(result),
            duration_ms=duration_ms,
        )
        await push_event(
            "__admin__",
            {
                "type": "mcp.tool_call.complete",
                "call_id": call_id,
                "node_type": node_type,
                "status": "succeeded",
                "result_count": len(result),
                "duration_ms": duration_ms,
            },
        )
    except Exception:
        log.debug("observability log_call_complete (succeeded) failed", exc_info=True)

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
