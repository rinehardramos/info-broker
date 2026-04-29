# Pipeline Engine — Phase 1 Design

## Goal

Add an internal pipeline system to info-broker that lets users chain source plugins (Apify, DDG, Qdrant, RSS) into multi-step DAGs with per-step tracking. Pipelines are saved, manually triggered, and executed via Temporal workflows.

## Scope — Phase 1

- Pipeline CRUD (create, edit, delete, list)
- DAG execution via Temporal (sequential + parallel fan-out)
- 4 node types: Apify Actor, DDG Search, Qdrant Search, RSS Monitor
- Hybrid UI: step-list editor + resizable DAG preview
- Run tracking with status badges + metrics per step
- Manual trigger only (scheduled + event-driven deferred to Phase 2)
- Multi-user (user_id scoping on all tables)

## Out of Scope (Phase 2+)

- Scheduled and event-driven triggers
- RBAC / permissions
- Agentic deep research (LangGraph/LangChain)
- Additional node types (Shodan, Google, OSINT, dark web, etc.)
- Pipeline templates / marketplace

---

## Architecture

### Temporal Workflow

Each pipeline run maps to one Temporal workflow execution:

1. `POST /v3/pipelines/{id}/run` reads the pipeline definition, inserts a `pipeline_runs` row, and starts a `PipelineWorkflow` on the `pipeline-tasks` task queue.
2. `PipelineWorkflow` topologically sorts the DAG from `pipeline_edges`. Nodes at the same depth with no inter-dependencies run as parallel activities.
3. Each activity wraps a `PipelineNode.execute()` call. Before execution, the activity updates `pipeline_step_runs.status = 'running'` and pushes a WebSocket event. On completion, it writes `status = 'succeeded'`, `item_count`, and duration.
4. Output from upstream activities is passed as `inputs` to downstream activities based on `pipeline_edges.edge_type`:
   - `results`: upstream output list is forwarded directly
   - `query`: the pipeline's original query string is forwarded
5. On workflow completion (all activities done), `pipeline_runs.status` is set to `succeeded` or `failed`.

### Docker Services

Added to `docker-compose.yml`:

- **temporal**: `temporalio/auto-setup` image, uses its own internal PostgreSQL (or connects to the existing one via env vars). Exposes gRPC on port 7233.
- **temporal-ui**: `temporalio/ui` image, port 8233. Optional — for debugging workflows.
- **temporal-worker**: Same Docker image as `info-broker-api`, but with entrypoint `python temporal_worker.py`. Registers `PipelineWorkflow` and all node activities. Connects to Temporal on `temporal:7233`.

---

## Data Model

### `pipelines`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| user_id | UUID FK → ui_users | |
| name | VARCHAR(255) | |
| description | TEXT | nullable |
| created_at | TIMESTAMPTZ | default now() |
| updated_at | TIMESTAMPTZ | default now() |

### `pipeline_nodes`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| pipeline_id | UUID FK → pipelines | ON DELETE CASCADE |
| node_type | VARCHAR(64) | `apify_actor`, `ddg_search`, `qdrant_search`, `rss_monitor` |
| label | VARCHAR(255) | user-facing name |
| config | JSONB | node-type-specific settings |
| position_x | INT | for DAG layout |
| position_y | INT | for DAG layout |

### `pipeline_edges`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| pipeline_id | UUID FK → pipelines | ON DELETE CASCADE |
| source_node_id | UUID FK → pipeline_nodes | |
| target_node_id | UUID FK → pipeline_nodes | |
| edge_type | VARCHAR(16) | `results` or `query` |

### `pipeline_runs`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| pipeline_id | UUID FK → pipelines | |
| user_id | UUID FK → ui_users | |
| temporal_workflow_id | TEXT | Temporal workflow execution ID |
| status | VARCHAR(20) | `queued`, `running`, `succeeded`, `failed` |
| trigger_type | VARCHAR(16) | `manual` (Phase 1 only) |
| started_at | TIMESTAMPTZ | default now() |
| finished_at | TIMESTAMPTZ | nullable |

### `pipeline_step_runs`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| run_id | UUID FK → pipeline_runs | ON DELETE CASCADE |
| node_id | UUID FK → pipeline_nodes | |
| status | VARCHAR(20) | `pending`, `running`, `succeeded`, `failed` |
| item_count | INT | default 0 |
| error_message | TEXT | nullable |
| started_at | TIMESTAMPTZ | nullable |
| finished_at | TIMESTAMPTZ | nullable |

---

## Node Plugin Interface

```python
class PipelineNode(Protocol):
    node_type: str           # e.g. "apify_actor"
    display_name: str        # e.g. "Apify Actor"
    category: str            # "source" | "enrich" | "score" | "filter"
    config_schema: dict      # JSON Schema for the node's config JSONB

    async def execute(
        self,
        config: dict,              # from pipeline_nodes.config
        inputs: list[dict],        # results from upstream nodes (empty for sources)
        context: RunContext,       # user_id, run_id, node_id
    ) -> list[dict]:               # output passed to downstream nodes
        ...
```

### `RunContext`

```python
@dataclass
class RunContext:
    user_id: str
    run_id: str
    node_id: str
    push_event: Callable       # WebSocket push for real-time updates
```

### Launch Node Types

**`apify_actor`** (category: source)
- Config: `actor_id`, `api_key_setting`, `job_titles`, `locations`, `max_items`, `scraper_mode`, segmentation fields
- Execute: POST to Apify actor runs API, poll until done, fetch dataset items
- Output: list of profile dicts

**`ddg_search`** (category: source)
- Config: `query`, `max_results`
- Execute: calls existing `DdgPlugin.search()`
- Output: list of `{title, url, snippet, source_name}` dicts

**`qdrant_search`** (category: enrich)
- Config: `collection`, `limit`
- Execute: for each input item, runs `semantic_search()` against Qdrant
- Output: input items enriched with matched results

**`rss_monitor`** (category: source)
- Config: `feed_url`, `max_items`
- Execute: fetches and parses RSS feed
- Output: list of `{title, url, snippet, published_at}` dicts

---

## API Endpoints

All endpoints scoped to authenticated user.

### Pipeline CRUD

```
POST   /v3/pipelines                    → create pipeline (name, description)
GET    /v3/pipelines                    → list user's pipelines
GET    /v3/pipelines/{id}               → pipeline + nodes + edges
PUT    /v3/pipelines/{id}               → update (name, description, nodes, edges)
DELETE /v3/pipelines/{id}               → delete pipeline + cascade
```

### Pipeline Runs

```
POST   /v3/pipelines/{id}/run           → start Temporal workflow, return run_id
GET    /v3/pipelines/{id}/runs          → list runs for pipeline
GET    /v3/pipelines/runs/{run_id}      → run detail + step statuses + metrics
```

### Node Registry

```
GET    /v3/pipeline-nodes/types         → list available node types with config schemas
```

---

## Frontend

### Pipeline Builder Component (`PipelineBuilder.tsx`)

Reusable component integrated as a "Pipelines" tab in source pages (LinkedIn, Research).

**Layout**: Two resizable panels separated by a draggable divider.

- **Steps panel** (left, ~40% default): Vertical step list. Each step shows node type, category badge, and config summary. Parallel nodes share the same step number. Click a node to open config editor (form generated from `config_schema`). "+ Add Step" button at the bottom.
- **Graph panel** (right, ~60% default): Read-only SVG DAG. Auto-laid out from step list topology. Dot-grid background. Nodes are rounded rectangles color-coded by category (blue=source, purple=enrich, green=score). Bezier curve edges with endpoint dots. Parallel bracket indicator.

**Saved pipelines sidebar**: Left-most narrow column listing saved pipelines with name, step count, and trigger type. "+ New Pipeline" button.

### Pipeline Run View (`PipelineRunView.tsx`)

Same layout but read-only, showing live execution:

- Steps panel: each step shows status badge (pending/running/succeeded/failed), item count, and duration
- Graph panel: active node highlighted with pulse animation, completed nodes show checkmark, edges colored by completion status
- Real-time updates via existing WebSocket stream (`pipeline.step.update` events)

### WebSocket Events

```jsonc
// Step status change
{"type": "pipeline.step.update", "run_id": "...", "node_id": "...", "status": "running", "item_count": 0}
{"type": "pipeline.step.update", "run_id": "...", "node_id": "...", "status": "succeeded", "item_count": 142}

// Run completion
{"type": "pipeline.run.complete", "run_id": "...", "status": "succeeded"}
```

### Frontend API Client (`frontend/src/api/pipelines.ts`)

```typescript
// CRUD
createPipeline(body): Promise<Pipeline>
listPipelines(): Promise<Pipeline[]>
getPipeline(id): Promise<PipelineDetail>
updatePipeline(id, body): Promise<Pipeline>
deletePipeline(id): Promise<void>

// Runs
startPipelineRun(id): Promise<PipelineRun>
listPipelineRuns(id): Promise<PipelineRun[]>
getPipelineRun(runId): Promise<PipelineRunDetail>

// Node types
listNodeTypes(): Promise<NodeType[]>
```

---

## File Structure

```
app/
  pipeline/
    __init__.py
    nodes/
      __init__.py          # NodeRegistry
      base.py              # PipelineNode protocol, RunContext
      apify_actor.py
      ddg_search.py
      qdrant_search.py
      rss_monitor.py
    workflow.py             # PipelineWorkflow + activities
    worker.py               # Temporal worker entrypoint
  routers/v3/
    pipelines.py            # CRUD + run endpoints

frontend/src/
  api/pipelines.ts
  components/pipeline/
    PipelineBuilder.tsx     # step list + DAG editor
    PipelineRunView.tsx     # live run tracking
    StepList.tsx            # step list panel
    DagPreview.tsx          # SVG DAG renderer
    NodeConfigForm.tsx      # config editor (from JSON Schema)
    ResizableSplit.tsx       # draggable divider
```
