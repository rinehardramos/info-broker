# Agent System Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a system-level default pipeline for the Agent chat interface with `agent_input → ddg_search → manual_scoring`, wire agent message execution to Temporal pipeline runs, and let users override the pipeline in Settings.

**Architecture:** A single `is_system` flag + nullable `user_id` on `pipelines` extends the existing schema. A new shared `app/pipeline/runner.py` helper launches Temporal workflows so agent.py and pipelines.py share zero logic. User preference is stored as `agent_pipeline_id` in `ui_preferences`. The frontend pipeline builder locks the `agent_input` node and hides source-add for agent pipelines.

**Tech Stack:** FastAPI, PostgreSQL (psycopg2), Temporalio, React + TypeScript, TanStack Query, Playwright (headed Chrome)

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app/routers/v3/db.py` | Modify | Add ALTER TABLE migrations + system pipeline seed |
| `app/routers/v3/models.py` | Modify | Add `is_system` to `PipelineOut`, `agent_pipeline_id` to preferences, new `AgentPipelineOut` |
| `app/routers/v3/pipelines.py` | Modify | List system pipelines, 403 guards on delete/update |
| `app/pipeline/runner.py` | Create | Shared Temporal launch helper |
| `app/routers/v3/agent.py` | Modify | New GET/PUT /pipeline endpoints, rewrite message execution |
| `tests/v3/test_pipelines.py` | Modify | System pipeline 403 tests, agent pipeline constraint tests |
| `frontend/src/api/pipelines.ts` | Modify | Add `is_system` to `Pipeline` type |
| `frontend/src/api/v3.ts` | Modify | Add `getAgentPipeline`, `setAgentPipeline` API calls |
| `frontend/src/components/pipeline/StepList.tsx` | Modify | Add `lockedNodeIds` prop to lock individual nodes |
| `frontend/src/components/pipeline/PipelineBuilder.tsx` | Modify | System pipeline read-only badge + delete guard; agent_input lock |
| `frontend/src/pages/Settings.tsx` | Modify | Add Agent section with pipeline selector |
| `frontend/src/components/agent/AgentChat.tsx` | Modify | Show active pipeline name in header |
| `frontend/e2e/agent-pipeline.spec.ts` | Create | E2E tests (Playwright, headed Chrome) |

---

## Task 1: DB Migration — system pipeline schema

**Files:**
- Modify: `app/routers/v3/db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/v3/test_pipelines.py — add to top of file after imports
def test_pipelines_table_has_is_system_column():
    """Schema migration adds is_system and nullable user_id."""
    from app.routers.v3.db import fetch_one
    row = fetch_one(
        "SELECT column_name, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'pipelines' AND column_name IN ('is_system', 'user_id') "
        "ORDER BY column_name"
    )
    # At minimum is_system column must exist
    assert row is not None, "is_system column not found in pipelines table"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/rinehardramos/Projects/info-broker
docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/test_pipelines.py::test_pipelines_table_has_is_system_column -v 2>&1 | tail -20
```

Expected: FAIL — column `is_system` does not exist yet.

- [ ] **Step 3: Add ALTER TABLE statements to `_MIGRATION` in `app/routers/v3/db.py`**

Append these statements to the end of the `_MIGRATION` string, just before the closing `"""`. Place them after the existing `CREATE TABLE IF NOT EXISTS pipeline_step_runs` block:

```python
# In db.py, inside _MIGRATION string, append before closing """:

ALTER TABLE pipelines ALTER COLUMN user_id DROP NOT NULL;

ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE pipelines DROP CONSTRAINT IF EXISTS ck_pipeline_owner;

ALTER TABLE pipelines ADD CONSTRAINT ck_pipeline_owner CHECK ((user_id IS NOT NULL) OR (is_system = true));

ALTER TABLE ui_preferences ADD COLUMN IF NOT EXISTS agent_pipeline_id UUID REFERENCES pipelines(id) ON DELETE SET NULL;
```

- [ ] **Step 4: Add system pipeline seed to `_SEED` in `app/routers/v3/db.py`**

Append to the end of the `_SEED` string (before closing `"""`):

```python
INSERT INTO pipelines (id, user_id, name, description, is_system)
VALUES (
    '10000000-0000-4000-8000-000000000001',
    NULL,
    'Agent Default',
    'Default pipeline for Agent chat: agent_input → ddg_search → manual_scoring',
    true
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO pipeline_nodes (id, pipeline_id, node_type, label, config, position_x, position_y)
VALUES
    ('10000000-0000-4000-8000-000000000011', '10000000-0000-4000-8000-000000000001', 'agent_input',    'Agent CLI',       '{}', 0, 0),
    ('10000000-0000-4000-8000-000000000012', '10000000-0000-4000-8000-000000000001', 'ddg_search',     'DDG Search',      '{}', 0, 1),
    ('10000000-0000-4000-8000-000000000013', '10000000-0000-4000-8000-000000000001', 'manual_scoring', 'Manual Scoring',  '{}', 0, 2)
ON CONFLICT (id) DO NOTHING;

INSERT INTO pipeline_edges (id, pipeline_id, source_node_id, target_node_id, edge_type)
VALUES
    ('10000000-0000-4000-8000-000000000021', '10000000-0000-4000-8000-000000000001',
     '10000000-0000-4000-8000-000000000011', '10000000-0000-4000-8000-000000000012', 'results'),
    ('10000000-0000-4000-8000-000000000022', '10000000-0000-4000-8000-000000000001',
     '10000000-0000-4000-8000-000000000012', '10000000-0000-4000-8000-000000000013', 'results')
ON CONFLICT (id) DO NOTHING;
```

- [ ] **Step 5: Restart API to apply migrations**

```bash
docker compose restart info-broker-api
sleep 5
curl -s http://localhost:8000/healthz
```

Expected: `{"status": "ok"}`

- [ ] **Step 6: Run test to verify it passes**

```bash
docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/test_pipelines.py::test_pipelines_table_has_is_system_column -v 2>&1 | tail -10
```

Expected: PASS

- [ ] **Step 7: Verify seed data**

```bash
docker exec info-broker-postgres-1 psql -U user -d info_broker -c \
  "SELECT id, name, is_system, user_id FROM pipelines WHERE is_system = true;"
```

Expected: 1 row with name `Agent Default`, `is_system = true`, `user_id = NULL`.

- [ ] **Step 8: Commit**

```bash
git add app/routers/v3/db.py
git commit -m "feat(db): add is_system to pipelines, agent_pipeline_id to preferences, seed Agent Default pipeline"
```

---

## Task 2: Update Python models

**Files:**
- Modify: `app/routers/v3/models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/v3/test_pipelines.py — add this test
def test_pipeline_list_includes_is_system_field():
    headers = _auth("model_test_user")
    r = client.get("/v3/pipelines", headers=headers)
    assert r.status_code == 200
    pipelines = r.json()
    # System pipeline should appear
    system = next((p for p in pipelines if p.get("is_system")), None)
    assert system is not None, "No system pipeline in list"
    assert "is_system" in system
```

Run: `docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/test_pipelines.py::test_pipeline_list_includes_is_system_field -v 2>&1 | tail -10`

Expected: FAIL — `PipelineOut` has no `is_system` field.

- [ ] **Step 2: Add `is_system` to `PipelineOut` in `app/routers/v3/models.py`**

Find the `PipelineOut` class (currently ~line 239) and add `is_system`:

```python
class PipelineOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_system: bool = False
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 3: Add `agent_pipeline_id` to preferences models in `app/routers/v3/models.py`**

Find `PreferencesIn` and `PreferencesOut` (currently ~line 30) and add the field:

```python
class PreferencesIn(BaseModel):
    theme: str | None = None
    column_layout: dict | None = None
    agent_pipeline_id: str | None = None


class PreferencesOut(BaseModel):
    theme: str
    column_layout: dict
    agent_pipeline_id: str | None = None
```

- [ ] **Step 4: Add `AgentPipelineOut` model to `app/routers/v3/models.py`**

Add after `AgentMessageOut`:

```python
class AgentPipelineOut(BaseModel):
    pipeline_id: str
    pipeline_name: str
    is_system: bool
```

- [ ] **Step 5: Run test to verify it passes**

```bash
docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/test_pipelines.py::test_pipeline_list_includes_is_system_field -v 2>&1 | tail -10
```

Expected: FAIL still — `list_pipelines` doesn't return system pipelines yet. That's Task 3.

- [ ] **Step 6: Commit**

```bash
git add app/routers/v3/models.py
git commit -m "feat(models): add is_system to PipelineOut, agent_pipeline_id to preferences, AgentPipelineOut"
```

---

## Task 3: Pipeline API — system pipeline guards

**Files:**
- Modify: `app/routers/v3/pipelines.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/v3/test_pipelines.py — add these tests

SYSTEM_PIPELINE_ID = "10000000-0000-4000-8000-000000000001"

def test_list_pipelines_includes_system():
    headers = _auth("list_test_user")
    r = client.get("/v3/pipelines", headers=headers)
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert SYSTEM_PIPELINE_ID in ids

def test_delete_system_pipeline_returns_403():
    headers = _auth("delete_test_user")
    r = client.delete(f"/v3/pipelines/{SYSTEM_PIPELINE_ID}", headers=headers)
    assert r.status_code == 403

def test_update_system_pipeline_returns_403():
    headers = _auth("update_test_user")
    r = client.put(
        f"/v3/pipelines/{SYSTEM_PIPELINE_ID}",
        json={"name": "Hacked", "description": "", "nodes": [], "edges": []},
        headers=headers,
    )
    assert r.status_code == 403
```

Run:
```bash
docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/test_pipelines.py::test_list_pipelines_includes_system tests/v3/test_pipelines.py::test_delete_system_pipeline_returns_403 tests/v3/test_pipelines.py::test_update_system_pipeline_returns_403 -v 2>&1 | tail -20
```

Expected: All FAIL.

- [ ] **Step 2: Update `list_pipelines` to include system pipelines**

Replace the `list_pipelines` function body in `app/routers/v3/pipelines.py`:

```python
@router.get("", response_model=list[PipelineOut])
def list_pipelines(user: dict = Depends(get_current_user)):
    rows = fetch_all(
        """
        SELECT * FROM pipelines
        WHERE user_id = %s OR is_system = true
        ORDER BY is_system DESC, created_at DESC
        """,
        (str(user["id"]),),
    )
    return [PipelineOut(**dict(r)) for r in rows]
```

- [ ] **Step 3: Update `get_pipeline` to allow access to system pipelines**

Replace the `get_pipeline` fetch query:

```python
@router.get("/{pipeline_id}", response_model=PipelineDetailOut)
def get_pipeline(pipeline_id: str, user: dict = Depends(get_current_user)):
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
        nodes=[PipelineNodeOut(**dict(n)) for n in nodes],
        edges=[PipelineEdgeOut(**dict(e)) for e in edges],
    )
```

- [ ] **Step 4: Add 403 guard to `update_pipeline`**

At the top of the `update_pipeline` function body, before the UPDATE query, add:

```python
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
    existing = fetch_all(
        "SELECT id FROM pipeline_nodes WHERE pipeline_id = %s", (pipeline_id,)
    )
    incoming_ids = {str(n.id) for n in body.nodes if n.id}
    for removed in existing:
        if str(removed["id"]) not in incoming_ids:
            execute("DELETE FROM pipeline_nodes WHERE id = %s", (str(removed["id"]),))
    execute("DELETE FROM pipeline_edges WHERE pipeline_id = %s", (pipeline_id,))
    _upsert_nodes_edges(pipeline_id, body)
    return PipelineOut(**dict(row))
```

- [ ] **Step 5: Add 403 guard to `delete_pipeline`**

Replace `delete_pipeline`:

```python
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
```

- [ ] **Step 6: Run all three tests**

```bash
docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/test_pipelines.py::test_list_pipelines_includes_system tests/v3/test_pipelines.py::test_delete_system_pipeline_returns_403 tests/v3/test_pipelines.py::test_update_system_pipeline_returns_403 -v 2>&1 | tail -15
```

Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add app/routers/v3/pipelines.py tests/v3/test_pipelines.py
git commit -m "feat(pipelines): include system pipelines in list, 403 on delete/update of system pipelines"
```

---

## Task 4: Shared pipeline runner helper

**Files:**
- Create: `app/pipeline/runner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/v3/test_pipelines.py — add
def test_runner_raises_on_temporal_unavailable():
    """runner.launch_pipeline_run raises HTTPException 503 when Temporal is unreachable."""
    import asyncio
    from app.pipeline.runner import launch_pipeline_run
    from app.pipeline.workflow import NodeSpec, EdgeSpec
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            launch_pipeline_run(
                run_id="test-run",
                user_id="test-user",
                pipeline_id="test-pipeline",
                nodes=[NodeSpec(node_id="n1", node_type="agent_input", label="A", config={})],
                edges=[],
                temporal_host="localhost",
                temporal_port=19999,  # nothing listening here
            )
        )
    assert exc_info.value.status_code == 503
```

Run: `docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/test_pipelines.py::test_runner_raises_on_temporal_unavailable -v 2>&1 | tail -10`

Expected: FAIL — module `app.pipeline.runner` does not exist.

- [ ] **Step 2: Create `app/pipeline/runner.py`**

```python
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
```

- [ ] **Step 3: Run test to verify it passes**

```bash
docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/test_pipelines.py::test_runner_raises_on_temporal_unavailable -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 4: Refactor `start_pipeline_run` in `pipelines.py` to use the runner**

In `app/routers/v3/pipelines.py`, replace the Temporal try/except block inside `start_pipeline_run` with a call to `launch_pipeline_run`. Add the import at the top of the function (not at module level — avoids circular imports):

```python
# Inside start_pipeline_run, replace the try/except Temporal block:
from app.pipeline.runner import launch_pipeline_run
import os

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
        "UPDATE pipeline_runs SET status = 'failed', finished_at = now() WHERE id = %s",
        (run_id,),
    )
    raise
```

Also add `from fastapi import APIRouter, Body, Depends, HTTPException` — `HTTPException` is already imported, so no change needed.

- [ ] **Step 5: Run existing pipeline run tests to confirm no regression**

```bash
docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/test_pipelines.py -v 2>&1 | tail -20
```

Expected: All previously passing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add app/pipeline/runner.py app/routers/v3/pipelines.py tests/v3/test_pipelines.py
git commit -m "feat(pipeline): extract Temporal launch into shared runner helper"
```

---

## Task 5: Agent pipeline endpoints + new execution

**Files:**
- Modify: `app/routers/v3/agent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/v3/test_pipelines.py — add these tests

SYSTEM_PIPELINE_ID = "10000000-0000-4000-8000-000000000001"

def test_get_agent_pipeline_returns_system_default():
    headers = _auth("agent_pipeline_user")
    r = client.get("/v3/agent/pipeline", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["pipeline_id"] == SYSTEM_PIPELINE_ID
    assert data["is_system"] is True

def test_put_agent_pipeline_rejects_no_agent_input():
    headers = _auth("agent_pipeline_user2")
    # Create a pipeline without agent_input as source
    p = client.post(
        "/v3/pipelines",
        json={"name": "No agent input", "nodes": [
            {"id": str(uuid.uuid4()), "node_type": "ddg_search", "label": "DDG", "config": {}, "position_x": 0, "position_y": 0},
        ], "edges": []},
        headers=headers,
    ).json()
    r = client.put("/v3/agent/pipeline", json={"pipeline_id": p["id"]}, headers=headers)
    assert r.status_code == 422

def test_put_agent_pipeline_accepts_valid_pipeline():
    headers = _auth("agent_pipeline_user3")
    node_id = str(uuid.uuid4())
    p = client.post(
        "/v3/pipelines",
        json={"name": "My Agent Pipeline", "nodes": [
            {"id": node_id, "node_type": "agent_input", "label": "CLI", "config": {}, "position_x": 0, "position_y": 0},
        ], "edges": []},
        headers=headers,
    ).json()
    r = client.put("/v3/agent/pipeline", json={"pipeline_id": p["id"]}, headers=headers)
    assert r.status_code == 200
    assert r.json()["pipeline_id"] == p["id"]
```

Run:
```bash
docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/test_pipelines.py::test_get_agent_pipeline_returns_system_default tests/v3/test_pipelines.py::test_put_agent_pipeline_rejects_no_agent_input tests/v3/test_pipelines.py::test_put_agent_pipeline_accepts_valid_pipeline -v 2>&1 | tail -20
```

Expected: All FAIL — endpoints don't exist yet.

- [ ] **Step 2: Rewrite `app/routers/v3/agent.py`**

Replace the entire file with:

```python
from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from pydantic import BaseModel

from app.routers.v3.auth import get_current_user
from app.routers.v3.db import execute, fetch_all, fetch_one
from app.routers.v3.models import AgentMessageIn, AgentMessageOut, AgentPipelineOut

router = APIRouter(prefix="/v3/agent", tags=["v3-agent"])
log = logging.getLogger(__name__)

SYSTEM_PIPELINE_ID = "10000000-0000-4000-8000-000000000001"


# ---------------------------------------------------------------------------
# Agent pipeline preference
# ---------------------------------------------------------------------------

def _get_active_pipeline(user_id: str) -> dict:
    """Return the active pipeline row for this user (preference → system default)."""
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

    # Fall back to system default
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

    # Validate: exactly 1 source, must be agent_input at position_y=0
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
# Agent message — triggers pipeline run via Temporal
# ---------------------------------------------------------------------------

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

    nodes_rows = fetch_all(
        "SELECT * FROM pipeline_nodes WHERE pipeline_id = %s ORDER BY position_y, position_x",
        (pipeline_id,),
    )
    edges_rows = fetch_all(
        "SELECT * FROM pipeline_edges WHERE pipeline_id = %s",
        (pipeline_id,),
    )

    run_id = str(uuid.uuid4())
    workflow_id = f"pipeline-{run_id}"

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

    # Inject message into agent_input node config
    def _node_config(node: dict) -> dict:
        cfg = dict(node["config"] or {})
        if node["node_type"] == "agent_input":
            cfg["message"] = body.message
        return cfg

    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = int(os.getenv("TEMPORAL_PORT", "7233"))

    try:
        await launch_pipeline_run(
            run_id=run_id,
            user_id=uid,
            pipeline_id=pipeline_id,
            nodes=[
                NodeSpec(
                    node_id=str(n["id"]),
                    node_type=n["node_type"],
                    label=n["label"],
                    config=_node_config(n),
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
            "UPDATE pipeline_runs SET status = 'failed', finished_at = now() WHERE id = %s",
            (run_id,),
        )
        raise

    return AgentMessageOut(job_id=run_id)
```

- [ ] **Step 3: Run the three new tests**

```bash
docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/test_pipelines.py::test_get_agent_pipeline_returns_system_default tests/v3/test_pipelines.py::test_put_agent_pipeline_rejects_no_agent_input tests/v3/test_pipelines.py::test_put_agent_pipeline_accepts_valid_pipeline -v 2>&1 | tail -20
```

Expected: All PASS.

- [ ] **Step 4: Run full test suite to check for regressions**

```bash
docker exec info-broker-info-broker-api-1 python -m pytest tests/v3/ -v 2>&1 | tail -30
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/v3/agent.py tests/v3/test_pipelines.py
git commit -m "feat(agent): GET/PUT /pipeline endpoints, wire message execution to Temporal pipeline run"
```

---

## Task 6: Frontend — API types and client functions

**Files:**
- Modify: `frontend/src/api/pipelines.ts`
- Modify: `frontend/src/api/v3.ts`

- [ ] **Step 1: Add `is_system` to `Pipeline` type in `frontend/src/api/pipelines.ts`**

Find the `Pipeline` interface and add `is_system`:

```typescript
export interface Pipeline {
  id: string
  name: string
  description: string | null
  is_system: boolean
  created_at: string
  updated_at: string
}
```

- [ ] **Step 2: Add agent pipeline API functions to `frontend/src/api/v3.ts`**

Add after the existing agent section (after `sendMessage`):

```typescript
export interface AgentPipelineOut {
  pipeline_id: string
  pipeline_name: string
  is_system: boolean
}

export const getAgentPipeline = (): Promise<AgentPipelineOut> =>
  api.get('/v3/agent/pipeline').then(r => r.data)

export const setAgentPipeline = (pipeline_id: string): Promise<AgentPipelineOut> =>
  api.put('/v3/agent/pipeline', { pipeline_id }).then(r => r.data)
```

- [ ] **Step 3: Update `PreferencesOut` type in `frontend/src/api/v3.ts`**

Find the `PreferencesOut` interface (it may be named `Preferences` or similar) and add `agent_pipeline_id`:

```typescript
export interface PreferencesOut {
  theme: string
  column_layout: Record<string, unknown>
  agent_pipeline_id: string | null
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/pipelines.ts frontend/src/api/v3.ts
git commit -m "feat(frontend/api): add is_system to Pipeline type, getAgentPipeline/setAgentPipeline"
```

---

## Task 7: Pipeline Builder — system pipeline read-only

**Files:**
- Modify: `frontend/src/components/pipeline/PipelineBuilder.tsx`

- [ ] **Step 1: Add system pipeline detection and read-only guard**

In `PipelineBuilder.tsx`, find where `pipelineDetail` is used to set local state (the `useEffect` around line 118). Add a derived boolean:

```typescript
// After the existing state declarations, add:
const isSystemPipeline = pipelineDetail?.is_system ?? false
```

- [ ] **Step 2: Hide delete button for system pipelines**

Find the delete button / `confirmDelete` block (around line 440). Wrap it so it only renders when `!isSystemPipeline`:

```typescript
{!isSystemPipeline && (
  // existing delete button / confirmDelete block
)}
```

- [ ] **Step 3: Show read-only badge for system pipelines**

Find where the pipeline name is displayed in the header area. Add a badge next to the name:

```typescript
{isSystemPipeline && (
  <span
    style={{
      fontSize: 9,
      padding: '1px 5px',
      borderRadius: 3,
      background: '#1e3a5f',
      color: '#60a5fa',
      border: '1px solid #2d5a8f',
      fontWeight: 600,
      marginLeft: 4,
    }}
  >
    DEFAULT
  </span>
)}
```

- [ ] **Step 4: Pass `readOnly` to `StepList` for system pipelines**

In the `<StepList>` usage, update the `readOnly` prop:

```typescript
readOnly={isRunning || isSystemPipeline}
```

- [ ] **Step 5: Disable save button for system pipelines**

Find the Save button. Add `disabled={!dirty || updateMutation.isPending || isSystemPipeline}` to it.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/pipeline/PipelineBuilder.tsx
git commit -m "feat(pipeline-builder): system pipelines show DEFAULT badge, read-only, no delete"
```

---

## Task 8: Pipeline Builder — lock agent_input node

**Files:**
- Modify: `frontend/src/components/pipeline/StepList.tsx`
- Modify: `frontend/src/components/pipeline/PipelineBuilder.tsx`

- [ ] **Step 1: Add `lockedNodeIds` prop to `StepList`**

In `frontend/src/components/pipeline/StepList.tsx`, update the `Props` interface:

```typescript
interface Props {
  nodes: PipelineNodeOut[]
  stepRuns?: PipelineStepRun[]
  nodeTypes?: NodeType[]
  selectedNodeId?: string | null
  invalidNodeIds?: Set<string>
  lockedNodeIds?: Set<string>     // add this
  onSelect?: (nodeId: string) => void
  onRemove?: (nodeId: string) => void
  onMoveUp?: (nodeId: string) => void
  onMoveDown?: (nodeId: string) => void
  onAdd?: (nodeType: string) => void
  readOnly?: boolean
}
```

Add `lockedNodeIds = new Set()` to the destructure:

```typescript
export function StepList({
  nodes,
  stepRuns = [],
  nodeTypes = [],
  selectedNodeId,
  invalidNodeIds = new Set(),
  lockedNodeIds = new Set(),
  onSelect,
  onRemove,
  onMoveUp,
  onMoveDown,
  onAdd,
  readOnly = false,
}: Props) {
```

- [ ] **Step 2: Use `lockedNodeIds` to hide move/delete for locked nodes**

Inside the `nodes.map(...)`, find where `!readOnly` controls the controls div. Update it:

```typescript
{!readOnly && !lockedNodeIds.has(node.id) && (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    {/* existing ▲ ▼ × buttons — unchanged */}
  </div>
)}
{lockedNodeIds.has(node.id) && (
  <span
    title="This node is required and cannot be moved or removed"
    style={{ fontSize: 9, color: '#60a5fa', padding: '0 4px' }}
  >
    🔒
  </span>
)}
```

- [ ] **Step 3: Hide source category from "Add step" dropdown for agent pipelines**

In `StepList`, the `<select>` at the bottom iterates `orderedCategories`. Add a `hiddenCategories` prop:

```typescript
interface Props {
  // ... existing props
  hiddenCategories?: Set<string>
}
```

Add `hiddenCategories = new Set()` to the destructure. In the `orderedCategories.map(...)` that renders option groups:

```typescript
{orderedCategories
  .filter(c => !hiddenCategories.has(c))
  .map(category => (
    // existing optgroup rendering
  ))
}
```

- [ ] **Step 4: Wire locked node and hidden categories in `PipelineBuilder`**

In `PipelineBuilder.tsx`, compute derived values below the `isSystemPipeline` declaration:

```typescript
const isAgentPipeline = localNodes.some(n => n.node_type === 'agent_input')
const agentInputNode = localNodes.find(n => n.node_type === 'agent_input')
const lockedNodeIds = isAgentPipeline && agentInputNode
  ? new Set([agentInputNode.id])
  : new Set<string>()
const hiddenCategories = isAgentPipeline ? new Set(['source']) : new Set<string>()
```

Pass them to `<StepList>`:

```typescript
<StepList
  nodes={localNodes}
  stepRuns={stepRuns}
  nodeTypes={nodeTypes}
  selectedNodeId={editingNodeId}
  invalidNodeIds={invalidNodeIds}
  lockedNodeIds={lockedNodeIds}
  hiddenCategories={hiddenCategories}
  onSelect={setEditingNodeId}
  onRemove={handleRemoveNode}
  onMoveUp={id => handleMoveNode(id, 'up')}
  onMoveDown={id => handleMoveNode(id, 'down')}
  onAdd={handleAddNode}
  readOnly={isRunning || isSystemPipeline}
/>
```

- [ ] **Step 5: Guard `handleRemoveNode` to block removing locked nodes**

Find `handleRemoveNode` in `PipelineBuilder.tsx` and add a guard at the top:

```typescript
const handleRemoveNode = (nodeId: string) => {
  if (lockedNodeIds.has(nodeId)) return   // add this guard
  // ... existing logic
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/pipeline/StepList.tsx frontend/src/components/pipeline/PipelineBuilder.tsx
git commit -m "feat(pipeline-builder): lock agent_input node, hide source add for agent pipelines"
```

---

## Task 9: Settings — Agent pipeline section

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Add `AgentSettingsForm` component to `frontend/src/pages/Settings.tsx`**

Add before the `export default function Settings()`:

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listPipelines } from '../api/pipelines'
import { getAgentPipeline, setAgentPipeline } from '../api/v3'

function AgentSettingsForm() {
  const qc = useQueryClient()
  const { data: pipelines = [] } = useQuery({ queryKey: ['pipelines'], queryFn: listPipelines })
  const { data: activePipeline } = useQuery({ queryKey: ['agentPipeline'], queryFn: getAgentPipeline })

  const save = useMutation({
    mutationFn: (id: string) => setAgentPipeline(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agentPipeline'] }),
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label className="text-[11px]" style={{ color: 'var(--subtext)' }}>
          Active Agent Pipeline
        </label>
        <select
          value={activePipeline?.pipeline_id ?? ''}
          onChange={e => save.mutate(e.target.value)}
          disabled={save.isPending}
          className="px-2 py-1 rounded text-xs outline-none"
          style={{
            background: 'var(--panel)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
            cursor: 'pointer',
          }}
        >
          {pipelines.map(p => (
            <option key={p.id} value={p.id}>
              {p.name}{p.is_system ? ' [Default]' : ''}
            </option>
          ))}
        </select>
        <p className="text-[10px] mt-1" style={{ color: 'var(--muted)' }}>
          The pipeline used when you send a message in the Agent chat.
          Must have an Agent CLI source node.
        </p>
      </div>
      {save.isError && (
        <span className="text-[11px]" style={{ color: '#f87171' }}>
          {(save.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to save'}
        </span>
      )}
      {save.isSuccess && (
        <span className="text-[11px]" style={{ color: '#4ade80' }}>Saved</span>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Add "Agent" section to the Settings sidebar**

In the `Settings` component, update the `section` state type and add the new section button:

```typescript
const [section, setSection] = useState<'core' | 'plugins' | 'agent'>('core')
```

In the sidebar, add after the PLUGINS section:

```typescript
<div className="text-[10px] font-semibold mb-2 mt-3 px-1" style={{ color: 'var(--muted)' }}>AGENT</div>
<button
  onClick={() => setSection('agent')}
  className="w-full text-left px-2 py-1 rounded text-xs mb-1"
  style={{
    background: section === 'agent' ? 'var(--panel2)' : 'transparent',
    color: section === 'agent' ? 'var(--accent)' : 'var(--text)',
    border: 'none', cursor: 'pointer',
  }}
>
  Agent
</button>
```

- [ ] **Step 3: Add Agent section render to the content area**

In the content `<div>`, update the section title and add the form:

```typescript
<h2 className="text-sm font-bold mb-4 capitalize" style={{ color: 'var(--accent)' }}>
  {section === 'core' ? 'Core Settings' : section === 'agent' ? 'Agent Settings' : 'Plugin Settings'}
</h2>
{section === 'core' && <CoreSettingsForm />}
{section === 'plugins' && <PluginSettingsForm />}
{section === 'agent' && <AgentSettingsForm />}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Settings.tsx
git commit -m "feat(settings): add Agent section with active pipeline selector"
```

---

## Task 10: AgentChat — show active pipeline name

**Files:**
- Modify: `frontend/src/components/agent/AgentChat.tsx`

- [ ] **Step 1: Add pipeline query and display to `AgentChat.tsx`**

Add `useQuery` import and `getAgentPipeline` import, then add a query and update the header:

```typescript
import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import MessageBubble from './MessageBubble'
import { sendMessage, getAgentPipeline } from '../../api/v3'
import { useWebSocket, type WsEvent } from '../../hooks/useWebSocket'
import { useSessionStore } from '../../stores/sessionStore'
```

Inside the `AgentChat` component, add:

```typescript
const { data: activePipeline } = useQuery({
  queryKey: ['agentPipeline'],
  queryFn: getAgentPipeline,
})
```

Update the header div (the one showing "Agent"):

```typescript
<div
  className="px-3 py-2 text-[11px] font-semibold flex items-center justify-between"
  style={{ color: 'var(--accent)', borderBottom: '1px solid var(--border)' }}
>
  <span>Agent</span>
  {activePipeline && (
    <span
      style={{ fontSize: 9, color: 'var(--muted)', fontWeight: 400 }}
      title="Active pipeline — change in Settings"
    >
      {activePipeline.pipeline_name}
      {activePipeline.is_system && (
        <span style={{ color: '#60a5fa', marginLeft: 3 }}>[Default]</span>
      )}
    </span>
  )}
</div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/agent/AgentChat.tsx
git commit -m "feat(agent-chat): show active pipeline name in header"
```

---

## Task 11: E2E tests

**Files:**
- Create: `frontend/e2e/agent-pipeline.spec.ts`

- [ ] **Step 1: Ensure the stack is running**

```bash
docker compose up -d
sleep 5
curl -s http://localhost:8000/healthz
```

Expected: `{"status": "ok"}`

- [ ] **Step 2: Create `frontend/e2e/agent-pipeline.spec.ts`**

```typescript
/**
 * Agent System Pipeline E2E tests.
 *
 * Run (headed Chrome):
 *   cd frontend && npx playwright test e2e/agent-pipeline.spec.ts --headed --project=chromium
 *
 * Prerequisites: docker compose up -d (full stack running on localhost:5173 + :8000)
 */
import { test, expect, Page } from '@playwright/test'

const SYSTEM_PIPELINE_ID = '10000000-0000-4000-8000-000000000001'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder(/username/i).fill('admin')
  await page.getByPlaceholder(/password/i).fill('admin')
  await page.getByRole('button', { name: /login|sign in/i }).click()
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 10_000 })
}

test.describe('Agent Settings — pipeline selector', () => {
  test.beforeEach(async ({ page }) => { await login(page) })

  test('Settings > Agent shows system default pipeline with [Default] label', async ({ page }) => {
    await page.goto('/settings')
    // Click the Agent sidebar item
    await page.getByRole('button', { name: /^agent$/i }).click()
    await expect(page.getByText(/agent settings/i)).toBeVisible()
    // The dropdown should contain the system pipeline with [Default]
    const option = page.locator('select option').filter({ hasText: '[Default]' })
    await expect(option).toBeVisible()
    await expect(option).toContainText('Agent Default')
  })
})

test.describe('AgentChat — pipeline name in header', () => {
  test.beforeEach(async ({ page }) => { await login(page) })

  test('Agent header shows active pipeline name', async ({ page }) => {
    await page.goto('/')
    // The agent header shows [Default] badge for the system pipeline
    await expect(page.getByText(/\[Default\]/)).toBeVisible({ timeout: 8_000 })
  })
})

test.describe('Agent message — creates pipeline run', () => {
  test.beforeEach(async ({ page }) => { await login(page) })

  test('sending a message creates a pipeline run and shows status', async ({ page }) => {
    await page.goto('/')
    const textarea = page.getByPlaceholder(/ask info-broker/i)
    await textarea.fill('test query for e2e')
    await textarea.press('Enter')
    // Agent shows "Research started…" bubble
    await expect(page.getByText(/research started/i)).toBeVisible({ timeout: 8_000 })
  })
})

test.describe('Pipeline Builder — system pipeline constraints', () => {
  test.beforeEach(async ({ page }) => { await login(page) })

  test('system pipeline shows DEFAULT badge and has no delete button', async ({ page }) => {
    await page.goto('/pipelines')
    // Find the Agent Default pipeline in the list and click it
    await page.getByText('Agent Default').first().click()
    // DEFAULT badge should appear
    await expect(page.getByText('DEFAULT')).toBeVisible({ timeout: 5_000 })
    // Delete button should not be visible
    const deleteBtn = page.getByRole('button', { name: /delete/i })
    await expect(deleteBtn).not.toBeVisible()
  })

  test('agent_input node shows lock icon and has no remove button', async ({ page }) => {
    await page.goto('/pipelines')
    await page.getByText('Agent Default').first().click()
    // The agent_input step card should be visible
    await expect(page.locator('[data-testid="step-card-agent_input"]')).toBeVisible({ timeout: 5_000 })
    // Lock icon present
    await expect(page.getByTitle(/required and cannot be moved/i)).toBeVisible()
  })
})

test.describe('Settings — set custom agent pipeline', () => {
  test.beforeEach(async ({ page }) => { await login(page) })

  test('can set a user pipeline as active agent pipeline', async ({ page }) => {
    // First create a pipeline with agent_input via API using fetch
    const loginRes = await page.request.post('/api/v3/auth/login', {
      data: { username: 'admin', password: 'admin' },
    })
    const { access_token } = await loginRes.json()

    const nodeId = crypto.randomUUID()
    const createRes = await page.request.post('/api/v3/pipelines', {
      data: {
        name: 'E2E Agent Override',
        nodes: [{ id: nodeId, node_type: 'agent_input', label: 'CLI', config: {}, position_x: 0, position_y: 0 }],
        edges: [],
      },
      headers: { Authorization: `Bearer ${access_token}` },
    })
    expect(createRes.ok()).toBeTruthy()
    const created = await createRes.json()

    // Now go to Settings > Agent and select it
    await page.goto('/settings')
    await page.getByRole('button', { name: /^agent$/i }).click()
    await page.selectOption('select', created.id)

    // Verify the "Saved" confirmation appears
    await expect(page.getByText('Saved')).toBeVisible({ timeout: 5_000 })

    // Verify agent header now shows the new pipeline name
    await page.goto('/')
    await expect(page.getByText('E2E Agent Override')).toBeVisible({ timeout: 8_000 })
  })
})
```

- [ ] **Step 3: Run E2E tests**

```bash
cd /Users/rinehardramos/Projects/info-broker/frontend
npx playwright test e2e/agent-pipeline.spec.ts --headed --project=chromium 2>&1 | tail -40
```

Expected: All 5 tests pass with Chrome browser visible.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/agent-pipeline.spec.ts
git commit -m "test(e2e): agent system pipeline — settings selector, builder constraints, message run"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** DB schema ✓ | System pipeline seed ✓ | List/get/delete/update guards ✓ | GET/PUT /agent/pipeline ✓ | Message execution via Temporal ✓ | Pipeline builder read-only ✓ | agent_input lock ✓ | Settings section ✓ | AgentChat header ✓ | E2E tests ✓
- [x] **No placeholders:** All code blocks are complete
- [x] **Type consistency:** `AgentPipelineOut` defined in Task 2 (models.py), used in Tasks 5, 6 — consistent field names `pipeline_id`, `pipeline_name`, `is_system` throughout
- [x] **SYSTEM_PIPELINE_ID** constant defined once in `agent.py` and used in tests as a literal — consistent
- [x] **`lockedNodeIds` prop** introduced in Task 8 Step 1 (StepList) and consumed in Step 4 (PipelineBuilder) — consistent
- [x] **`hiddenCategories` prop** introduced in Task 8 Step 3 and consumed in Step 4 — consistent
