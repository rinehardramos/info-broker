from __future__ import annotations

import json
import logging
import os
import time
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user, require_admin
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.tenancy import user_org_id, org_scope_clause
from app.routers.v3.models import (
    NodeTypeOut,
    PipelineDetailOut,
    PipelineEdgeOut,
    PipelineIn,
    PipelineNodeOut,
    PipelineOut,
    PipelineRunDetailOut,
    PipelineRunOut,
    PipelineRunSummaryOut,
    PipelineStepRunOut,
    PluginRequestOut,
    PluginRequestStatusIn,
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

_TIMEOUT_SCHEMA = {
    "timeout_seconds": {
        "type": "integer",
        "title": "Timeout (seconds)",
        "default": 60,
        "minimum": 5,
        "maximum": 3600,
    }
}


def _with_timeout(schema: dict) -> dict:
    """Inject timeout_seconds into a node's config schema."""
    import copy
    s = copy.deepcopy(schema)
    s.setdefault("properties", {})
    s["properties"].update(_TIMEOUT_SCHEMA)
    return s


# Node types that are internal orchestrators — never exposed in the Pipeline Builder
_HIDDEN_NODE_TYPES = {"intelligent_search"}


@router.get("/nodes/types", response_model=list[NodeTypeOut])
def list_node_types(user: dict = Depends(get_current_user)):
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()
    return [
        NodeTypeOut(
            node_type=n.node_type,
            display_name=n.display_name,
            category=n.category,
            config_schema=_with_timeout(n.config_schema),
        )
        for n in NodeRegistry.all()
        if _is_node_enabled(n.node_type) and n.node_type not in _HIDDEN_NODE_TYPES
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
    user: dict = Depends(require_admin),
):
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()
    valid = {n.node_type for n in NodeRegistry.all()}
    if node_type not in valid:
        raise HTTPException(status_code=404, detail=f"Unknown node type: {node_type!r}")
    _set_node_enabled(node_type, bool(body.get("enabled", True)))


# ---------------------------------------------------------------------------
# Node health check (must come BEFORE parametric routes)
# ---------------------------------------------------------------------------

# Simple in-process TTL cache: { node_type: (timestamp, HealthStatus) }
_health_cache: dict[str, tuple[float, dict]] = {}
_HEALTH_CACHE_TTL = 300  # seconds


@router.get("/nodes/types/health")
async def get_nodes_health(user: dict = Depends(get_current_user)):
    """Check health status of all pipeline nodes."""
    import asyncio
    from app.pipeline.nodes import NodeRegistry
    from app.pipeline.nodes.base import HealthStatus
    NodeRegistry.auto_discover()

    results = []
    pending_checks: list[tuple] = []  # (node, node_type)
    now = time.time()

    for node in NodeRegistry.all():
        nt = node.node_type

        # Check cache first
        if nt in _health_cache:
            cached_time, cached_status = _health_cache[nt]
            if now - cached_time < _HEALTH_CACHE_TTL:
                results.append({"node_type": nt, "display_name": node.display_name, **cached_status})
                continue

        # No health_check method = always healthy
        if not hasattr(node, "health_check"):
            status: dict = HealthStatus(
                healthy=True, error=None, requires_key=None, setup_url=None, setup_instructions=None
            )
            _health_cache[nt] = (now, status)
            results.append({"node_type": nt, "display_name": node.display_name, **status})
        else:
            pending_checks.append((node, nt))

    # Run health checks in parallel with 10s timeout per check
    async def _check(node, nt):
        try:
            return nt, await asyncio.wait_for(node.health_check(), timeout=10)
        except asyncio.TimeoutError:
            return nt, HealthStatus(
                healthy=False, error="Health check timed out",
                requires_key=None, setup_url=None, setup_instructions=None,
            )
        except Exception as exc:
            return nt, HealthStatus(
                healthy=False, error=str(exc),
                requires_key=None, setup_url=None, setup_instructions=None,
            )

    if pending_checks:
        check_results = await asyncio.gather(
            *[_check(node, nt) for node, nt in pending_checks]
        )
        for nt, status in check_results:
            _health_cache[nt] = (now, status)
            node = next(n for n in NodeRegistry.all() if n.node_type == nt)
            results.append({"node_type": nt, "display_name": node.display_name, **status})

    return results


# ---------------------------------------------------------------------------
# get_healthy_nodes — helper for IS brain
# ---------------------------------------------------------------------------

async def get_healthy_nodes() -> list[dict]:
    """Return node metadata for only healthy + enabled nodes. Used by IS brain."""
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()

    healthy = []
    now = time.time()

    for node in NodeRegistry.all():
        nt = node.node_type
        if nt in ("agent_input", "intelligent_search"):
            continue
        if not _is_node_enabled(nt):
            continue

        # Check health
        if hasattr(node, "health_check"):
            if nt in _health_cache:
                cached_time, cached_status = _health_cache[nt]
                if now - cached_time < _HEALTH_CACHE_TTL:
                    if not cached_status["healthy"]:
                        continue
                else:
                    try:
                        status = await node.health_check()
                        _health_cache[nt] = (now, status)
                        if not status["healthy"]:
                            continue
                    except Exception:
                        continue
            else:
                try:
                    status = await node.health_check()
                    _health_cache[nt] = (now, status)
                    if not status["healthy"]:
                        continue
                except Exception:
                    continue

        # Build tool info for IS prompt
        tool_name = f"run_{nt}"
        params = ", ".join(node.config_schema.get("properties", {}).keys()) if hasattr(node, "config_schema") else ""
        healthy.append({
            "node_type": nt,
            "mcp_tool_name": tool_name,
            "display_name": node.display_name,
            "params": params,
            "description": node.display_name,
        })

    return healthy


# ---------------------------------------------------------------------------
# Run detail (must come BEFORE parametric routes)
# ---------------------------------------------------------------------------

@router.get("/runs/all", response_model=list[PipelineRunSummaryOut])
def list_all_pipeline_runs(user: dict = Depends(get_current_user)):
    rows = fetch_all(
        """
        SELECT
            pr.id,
            pr.pipeline_id,
            p.name            AS pipeline_name,
            pr.status,
            pr.trigger_type,
            pr.started_at,
            pr.finished_at,
            pr.error_message,
            pr.query,
            COUNT(psr.id)                                          AS step_count,
            COUNT(CASE WHEN psr.status IN ('succeeded','failed') THEN 1 END) AS steps_done
        FROM pipeline_runs pr
        JOIN pipelines p ON p.id = pr.pipeline_id
        LEFT JOIN pipeline_step_runs psr ON psr.run_id = pr.id
        WHERE pr.user_id = %s
        GROUP BY pr.id, p.name
        ORDER BY pr.started_at DESC
        LIMIT 50
        """,
        (str(user["id"]),),
    )
    return [PipelineRunSummaryOut(**dict(r)) for r in rows]


@router.post("/runs/{run_id}/cancel", status_code=204)
async def cancel_pipeline_run(run_id: str, user: dict = Depends(get_current_user)):
    try:
        uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="run_id must be a valid UUID")
    from temporalio.client import Client
    run = fetch_one(
        "SELECT * FROM pipeline_runs WHERE id = %s AND user_id = %s",
        (run_id, str(user["id"])),
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] not in ("queued", "running"):
        raise HTTPException(status_code=400, detail=f"Run is not active (status: {run['status']})")
    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = int(os.getenv("TEMPORAL_PORT", "7233"))
    try:
        client = await Client.connect(f"{host}:{port}")
        handle = client.get_workflow_handle(str(run["temporal_workflow_id"]))
        await handle.cancel()
    except Exception as exc:
        log.warning("Temporal cancel failed for run %s: %s", run_id, exc)
    execute(
        "UPDATE pipeline_runs SET status = 'paused', finished_at = now() WHERE id = %s",
        (run_id,),
    )


@router.get("/runs/{run_id}/gate-detail")
def get_run_gate_detail(
    run_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return the GateResult for the most recent failing phase of `run_id`.

    Admin-only — returns 403 for non-admin users regardless of run ownership,
    because gate detail may include strategy internals not appropriate for end users.
    Spec: docs/superpowers/specs/2026-05-22-gather-ask-user-diagnostic-design.md.
    """
    is_admin = bool(current_user.get("is_admin", False)) or current_user.get("role", "") == "admin"
    if not is_admin:
        raise HTTPException(status_code=403, detail="admin-only resource")

    row = fetch_one(
        "SELECT trail FROM research_trails WHERE run_id = %s ORDER BY created_at DESC LIMIT 1",
        (run_id,),
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"no trail for run_id={run_id}")

    raw_trail = row["trail"] if isinstance(row["trail"], dict) else json.loads(row["trail"])
    phases_full = raw_trail.get("phases_full") or []
    failing = next(
        (p for p in reversed(phases_full) if (p.get("gate_result") or {}).get("passed") is False),
        phases_full[-1] if phases_full else None,
    )
    if failing is None:
        raise HTTPException(status_code=404, detail="no phases in trail")

    return {
        "run_id": run_id,
        "phase_id": failing.get("phase_id"),
        "gate_result": failing.get("gate_result"),  # may be None for pre-spec rows
    }


@router.get("/runs/{run_id}", response_model=PipelineRunDetailOut)
def get_run(run_id: str, user: dict = Depends(get_current_user)):
    from app.routers.v3.models import ResearchTrailOut

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

    research = None
    if run["trigger_type"] == "agent_is":
        _clause, _cparams = org_scope_clause(user)
        _trail_sql = (
            "SELECT rt.query, rt.entity_type, rt.findings, rt.trail, "  # noqa: S608 - clause is a constant org-scope fragment; values parameterized
            "rt.tool_calls, rt.suggested_pipeline, rt.analysis "
            "FROM research_trails rt "
            "JOIN pipeline_runs pr ON pr.id = rt.run_id "
            f"WHERE rt.run_id = %s {_clause.replace('AND org_id', 'AND pr.org_id')}"
        )
        trail_row = fetch_one(_trail_sql, tuple([run_id, *_cparams]))
        if trail_row:
            research = ResearchTrailOut(**dict(trail_row))

    return PipelineRunDetailOut(
        **dict(run),
        steps=[PipelineStepRunOut(**dict(s)) for s in steps],
        research=research,
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
    # The `pipelines` table is scoped by user_id, not org_id.
    # System pipelines (is_system=TRUE) are shared across all users.
    rows = fetch_all(
        """
        SELECT * FROM pipelines
        WHERE (user_id = %s OR is_system = TRUE)
        ORDER BY is_system DESC, created_at DESC
        """,  # noqa: S608 - user_id is parameterized
        (str(user["id"]),),
    )
    return [PipelineOut(**dict(r)) for r in rows]


def _enrich_node_category(node_row: dict) -> dict:
    """Add category from NodeRegistry to a pipeline node row."""
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()
    category_map = {n.node_type: n.category for n in NodeRegistry.all()}
    d = dict(node_row)
    d["category"] = category_map.get(d.get("node_type", ""), "source")
    return d


# ---------------------------------------------------------------------------
# Plugin scaffold helpers — shared by scaffold endpoint and create-all/create
# ---------------------------------------------------------------------------

def _make_node_type_slug(name: str) -> str:
    """Convert a plugin name to a safe node_type slug (lowercase, underscores)."""
    return name.lower().replace("-", "_").replace(" ", "_")


def _generate_stub(node_type: str, spec: dict) -> tuple[str, str]:
    """Write an auto-generated stub node file and register it dynamically.

    Returns (file_path, class_name).
    """
    import importlib.util as _il

    auto_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "../../pipeline/nodes/auto",
    )
    os.makedirs(auto_dir, exist_ok=True)

    name = spec.get("name", node_type)
    class_name = "".join(w.capitalize() for w in node_type.split("_")) + "Node"
    display = name.replace("-", " ").replace("_", " ").title()
    description = spec.get("description", "")
    category = spec.get("category", "source")

    # Build config_schema from optional config_fields list
    config_fields = spec.get("config_fields", [])
    props: dict = {"query": {"type": "string"}}
    required: list = ["query"]
    for field in config_fields:
        fname = field.get("name", "")
        if not fname:
            continue
        props[fname] = {
            "type": field.get("type", "string"),
            "title": field.get("description", fname),
        }
        if field.get("required"):
            required.append(fname)

    props_json = json.dumps(props)
    required_json = json.dumps(required)

    stub = (
        f'"""Auto-generated stub: {name}\n\n{description}\n"""\n'
        f"from __future__ import annotations\n\n\n"
        f"class {class_name}:\n"
        f'    node_type = "{node_type}"\n'
        f'    display_name = "{display}"\n'
        f'    category = "{category}"\n'
        f"    generated = True\n"
        f"    config_schema = {{"
        f'"type": "object", "properties": {props_json}, "required": {required_json}'
        f"}}\n\n"
        f"    async def execute(self, config: dict, inputs: list, context) -> list:\n"
        f"        return []\n"
    )

    file_path = os.path.join(auto_dir, f"{node_type}.py")
    with open(file_path, "w") as fh:
        fh.write(stub)

    # Dynamically load and register
    from app.pipeline.nodes import NodeRegistry
    mod_spec = _il.spec_from_file_location(f"app.pipeline.nodes.auto.{node_type}", file_path)
    mod = _il.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    node_cls = getattr(mod, class_name)
    NodeRegistry.register(node_cls())
    _set_node_enabled(node_type, True)

    return file_path, class_name


# Plugin requests — MUST be before /{pipeline_id} to avoid route shadowing
@router.get("/plugin-requests", response_model=list[PluginRequestOut])
def list_plugin_requests(user: dict = Depends(get_current_user)):
    rows = fetch_all(
        "SELECT * FROM plugin_requests WHERE user_id = %s ORDER BY created_at DESC",
        (str(user["id"]),),
    )
    return [PluginRequestOut(**dict(r)) for r in rows]


@router.put("/plugin-requests/{request_id}/status")
def update_plugin_request_status(
    request_id: str,
    body: PluginRequestStatusIn,
    user: dict = Depends(get_current_user),
):
    execute(
        "UPDATE plugin_requests SET status = %s, reviewed_at = now() WHERE id = %s AND user_id = %s",
        (body.status, request_id, str(user["id"])),
    )
    return {"status": "updated"}


@router.post("/plugin-requests/scaffold", status_code=201)
def scaffold_plugin(
    body: dict,
    user: dict = Depends(require_admin),
):
    """Generate a stub pipeline node from a plugin spec and register it immediately.

    Body: { name, description, category, config_fields: [{name, type, description, required}] }
    Returns: { node_type, file_path, registered: bool }
    """
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="'name' is required")

    node_type = _make_node_type_slug(name)

    try:
        file_path, _ = _generate_stub(node_type, body)
        registered = True
    except Exception as exc:
        log.warning("scaffold_plugin failed for %s: %s", node_type, exc)
        registered = False
        file_path = ""

    return {"node_type": node_type, "file_path": file_path, "registered": registered}


@router.post("/plugin-requests/create-all")
def create_all_plugin_requests(user: dict = Depends(get_current_user)):
    """Deduplicate pending plugin requests by name and create/enable each unique plugin."""
    rows = fetch_all(
        "SELECT * FROM plugin_requests WHERE user_id = %s AND status = 'pending' ORDER BY created_at ASC",
        (str(user["id"]),),
    )

    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()
    existing = {n.node_type for n in NodeRegistry.all()}

    seen_names: dict[str, str] = {}  # normalized_name -> first request_id (kept)
    created = []
    dismissed = []

    import json as _json
    for row in rows:
        raw_spec = row.get("spec") or {}
        spec = _json.loads(raw_spec) if isinstance(raw_spec, str) else (raw_spec or {})
        name = spec.get("name", "")
        node_type = _make_node_type_slug(name)
        rid = str(row["id"])

        if node_type in seen_names:
            # Duplicate — dismiss it
            execute(
                "UPDATE plugin_requests SET status = 'dismissed', reviewed_at = now() WHERE id = %s",
                (rid,),
            )
            dismissed.append(rid)
            continue

        seen_names[node_type] = rid

        # Enable node if it exists
        enabled = False
        actual_type = node_type
        if node_type in existing:
            _set_node_enabled(node_type, True)
            enabled = True
        else:
            for et in existing:
                if node_type in et or et in node_type:
                    _set_node_enabled(et, True)
                    enabled = True
                    actual_type = et
                    break

        # If no existing node found, generate a stub in auto/ and register it dynamically
        if not enabled:
            try:
                _generate_stub(node_type, spec)
                enabled = True
                actual_type = node_type
            except Exception as _exc:
                log.warning("Auto-node generation failed for %s: %s", node_type, _exc)

        execute(
            "UPDATE plugin_requests SET status = 'approved', reviewed_at = now() WHERE id = %s",
            (rid,),
        )
        created.append({"request_id": rid, "node_type": actual_type, "node_enabled": enabled})

    return {"created": created, "dismissed_duplicates": dismissed}


@router.post("/plugin-requests/{request_id}/create")
def create_plugin_from_request(request_id: str, user: dict = Depends(get_current_user)):
    """Mark a suggested plugin as approved and enable the node if it already exists."""
    row = fetch_one(
        "SELECT * FROM plugin_requests WHERE id = %s AND user_id = %s",
        (request_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Plugin request not found")

    import json as _json
    raw_spec = row.get("spec") or {}
    spec = _json.loads(raw_spec) if isinstance(raw_spec, str) else (raw_spec or {})
    name = spec.get("name", "")
    node_type = _make_node_type_slug(name)

    # Enable node if it already exists in the registry
    enabled = False
    try:
        from app.pipeline.nodes import NodeRegistry
        NodeRegistry.auto_discover()
        existing = {n.node_type for n in NodeRegistry.all()}
        if node_type in existing:
            _set_node_enabled(node_type, True)
            enabled = True
        else:
            for et in existing:
                if node_type in et or et in node_type:
                    _set_node_enabled(et, True)
                    enabled = True
                    node_type = et
                    break
    except Exception:
        pass

    # If no existing node found, generate a stub in auto/ and register it dynamically
    if not enabled:
        try:
            _generate_stub(node_type, spec)
            enabled = True
        except Exception as _exc:
            log.warning("Auto-node generation failed for %s: %s", node_type, _exc)

    execute(
        "UPDATE plugin_requests SET status = 'approved', reviewed_at = now() WHERE id = %s AND user_id = %s",
        (request_id, str(user["id"])),
    )
    return {"status": "approved", "node_type": node_type, "node_enabled": enabled}


@router.get("/{pipeline_id}", response_model=PipelineDetailOut)
def get_pipeline(pipeline_id: str, user: dict = Depends(get_current_user)):
    try:
        uuid.UUID(pipeline_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="pipeline_id must be a valid UUID")
    row = fetch_one(
        "SELECT * FROM pipelines WHERE id = %s AND (user_id = %s OR is_system = true)",
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
        nodes=[PipelineNodeOut(**_enrich_node_category(n)) for n in nodes],
        edges=[PipelineEdgeOut(**dict(e)) for e in edges],
    )


@router.put("/{pipeline_id}", response_model=PipelineOut)
def update_pipeline(pipeline_id: str, body: PipelineIn, user: dict = Depends(get_current_user)):
    guard = fetch_one(
        "SELECT is_system FROM pipelines WHERE id = %s AND (user_id = %s OR is_system = true)",
        (pipeline_id, str(user["id"])),
    )
    if not guard:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if guard.get("is_system"):
        raise HTTPException(status_code=403, detail="System pipelines are read-only")
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
    # Only delete nodes that were removed — preserves pipeline_step_runs for kept nodes.
    # Edges have no dependent run data so delete-all-then-reinsert is safe.
    incoming_ids = {str(n.id) for n in body.nodes if n.id}
    existing = fetch_all(
        "SELECT id FROM pipeline_nodes WHERE pipeline_id = %s", (pipeline_id,)
    )
    for removed in existing:
        if str(removed["id"]) not in incoming_ids:
            execute("DELETE FROM pipeline_nodes WHERE id = %s", (str(removed["id"]),))
    execute("DELETE FROM pipeline_edges WHERE pipeline_id = %s", (pipeline_id,))
    _upsert_nodes_edges(pipeline_id, body)
    return PipelineOut(**dict(row))


@router.delete("/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str, user: dict = Depends(get_current_user)):
    guard = fetch_one(
        "SELECT is_system FROM pipelines WHERE id = %s AND (user_id = %s OR is_system = true)",
        (pipeline_id, str(user["id"])),
    )
    if not guard:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if guard.get("is_system"):
        raise HTTPException(status_code=403, detail="System pipelines cannot be deleted")
    row = fetch_one(
        "DELETE FROM pipelines WHERE id = %s AND user_id = %s RETURNING id",
        (pipeline_id, str(user["id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")


# ---------------------------------------------------------------------------
# Pipeline runs
# ---------------------------------------------------------------------------

class RunVariables(BaseModel):
    variables: dict[str, str] = {}


def _substitute_variables(config: dict, variables: dict[str, str]) -> dict:
    """Replace {{var}} placeholders in string config values."""
    result = {}
    for k, v in config.items():
        if isinstance(v, str):
            for var_name, var_value in variables.items():
                v = v.replace(f"{{{{{var_name}}}}}", var_value)
        result[k] = v
    return result


@router.post("/{pipeline_id}/run", response_model=PipelineRunOut, status_code=202)
async def start_pipeline_run(
    pipeline_id: str,
    body: RunVariables = Body(default_factory=RunVariables),
    user: dict = Depends(get_current_user),
):
    from app.pipeline.workflow import NodeSpec, EdgeSpec
    from app.pipeline.runner import launch_pipeline_run

    pipeline = fetch_one(
        "SELECT * FROM pipelines WHERE id = %s AND (user_id = %s OR is_system = true)",
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

    # Validate source node rules
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()
    node_category = {n.node_type: n.category for n in NodeRegistry.all()}
    node_types_in_pipeline = [str(row["node_type"]) for row in nodes_rows]
    # Datastore nodes are tool-only; exclude from source/aggregator validation
    source_count = sum(1 for nt in node_types_in_pipeline if node_category.get(nt) == "source" and nt != "aggregator")
    aggregator_count = sum(1 for nt in node_types_in_pipeline if nt == "aggregator")
    if source_count == 0:
        raise HTTPException(status_code=422, detail="Pipeline has no source node")
    if source_count > 1 and aggregator_count != 1:
        raise HTTPException(status_code=422, detail="Multiple sources require exactly one Aggregator node")

    run_id = str(uuid.uuid4())
    workflow_id = f"pipeline-{run_id}"

    run_row = fetch_one(
        """
        INSERT INTO pipeline_runs (id, pipeline_id, user_id, org_id, temporal_workflow_id, status, trigger_type)
        VALUES (%s, %s, %s, %s, %s, 'queued', 'manual')
        RETURNING *
        """,
        (run_id, pipeline_id, str(user["id"]), user_org_id(user), workflow_id),
    )

    # Create step_run rows for each node (skip tool-target datastores — they never execute)
    tool_target_ids = {
        str(e["target_node_id"]) for e in edges_rows if e.get("edge_type") == "tool"
    }
    for node in nodes_rows:
        if str(node["id"]) not in tool_target_ids:
            execute(
                "INSERT INTO pipeline_step_runs (id, run_id, node_id, status) VALUES (%s, %s, %s, 'pending')",
                (str(uuid.uuid4()), run_id, str(node["id"])),
            )

    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = int(os.getenv("TEMPORAL_PORT", "7233"))

    try:
        await launch_pipeline_run(
            run_id=run_id,
            user_id=str(user["id"]),
            pipeline_id=pipeline_id,
            nodes=[
                NodeSpec(
                    node_id=str(n["id"]),
                    node_type=n["node_type"],
                    label=n["label"],
                    config=_substitute_variables(n["config"] or {}, body.variables),
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
            temporal_host=host,
            temporal_port=port,
        )
    except HTTPException:
        execute(
            "UPDATE pipeline_runs SET status = 'failed', finished_at = now(),"
            " error_message = COALESCE(error_message, 'dispatch failed') WHERE id = %s",
            (run_id,),
        )
        raise
    except Exception as exc:
        # Temporal unreachable / start_workflow crash. Don't leave the row
        # in queued — caller needs to know dispatch failed so they can retry.
        execute(
            "UPDATE pipeline_runs SET status = 'failed', finished_at = now(),"
            " error_message = %s WHERE id = %s",
            (f"dispatch failed: {type(exc).__name__}: {str(exc)[:160]}", run_id),
        )
        log.exception("pipeline dispatch failed for run %s: %s", run_id, exc)
        raise HTTPException(status_code=503, detail="Pipeline worker unavailable. Try again shortly.")
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
            ON CONFLICT (id) DO UPDATE SET
                node_type  = EXCLUDED.node_type,
                label      = EXCLUDED.label,
                config     = EXCLUDED.config,
                position_x = EXCLUDED.position_x,
                position_y = EXCLUDED.position_y
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
