# Pipeline Engine -- Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add an internal pipeline system that lets users chain source plugins (Apify, DDG, Qdrant, RSS) into multi-step DAGs executed via Temporal, with per-step tracking and a hybrid step-list plus DAG preview UI.

**Architecture:** Pipeline definitions stored in Postgres (nodes, edges, runs, step_runs). Execution via Temporal workflows -- each node is a Temporal activity wrapping a PipelineNode.execute() call. Frontend is a reusable PipelineBuilder component with resizable split panels (step list editor plus SVG DAG preview), integrated as a Pipelines tab in source pages.

**Tech Stack:** Python 3.11, FastAPI, psycopg2, Temporal (temporalio SDK), React 18, TypeScript, react-resizable-panels, tanstack/react-query, Zustand, Tailwind CSS plus CSS custom properties.

**Spec:** docs/superpowers/specs/2026-04-29-pipeline-engine-design.md

---

## Task 1: Add temporalio Dependency

Modify: pyproject.toml -- add "temporalio>=1.9.0" to dependencies. Run uv lock. Verify with uv run python -c "import temporalio". Commit.

---

## Task 2: DB Migration -- Pipeline Tables

Modify: app/routers/v3/db.py -- append to _MIGRATION string.

Tables: pipelines (id, user_id, name, description, timestamps), pipeline_nodes (id, pipeline_id, node_type, label, config JSONB, position_x, position_y), pipeline_edges (id, pipeline_id, source_node_id, target_node_id, edge_type), pipeline_runs (id, pipeline_id, user_id, temporal_workflow_id, status, trigger_type, timestamps), pipeline_step_runs (id, run_id, node_id, status, item_count, error_message, timestamps). All with CASCADE deletes. Rebuild API container to verify. Commit.

---

## Task 3: Pydantic Models for Pipelines

Modify: app/routers/v3/models.py -- append models.

PipelineNodeIn (node_type, label, config, position_x, position_y), PipelineNodeOut (adds id UUID), PipelineEdgeIn (source_node_id, target_node_id, edge_type), PipelineEdgeOut (adds id), PipelineIn (name, description, nodes list, edges list), PipelineOut (id, name, description, timestamps), PipelineDetailOut (extends with nodes+edges), PipelineStepRunOut (id, node_id, status, item_count, error_message, timestamps), PipelineRunOut (id, pipeline_id, status, trigger_type, timestamps), PipelineRunDetailOut (extends with steps list), NodeTypeOut (node_type, display_name, category, config_schema). Commit.

---

## Task 4: Pipeline Node Interface plus Registry

Create: app/pipeline/__init__.py (empty), app/pipeline/nodes/base.py, app/pipeline/nodes/__init__.py.

base.py: RunContext dataclass (user_id, run_id, node_id). PipelineNode protocol with node_type, display_name, category, config_schema, async execute(config, inputs, context) returning list of dicts.

__init__.py: NodeRegistry class with register(), get(), all(), auto_discover() that imports and registers all 4 node types. Commit.

---

## Task 5: DDG Search Node

Create: app/pipeline/nodes/ddg_search.py. Category source. Config schema: query (string, required), max_results (int, default 10). Execute wraps DdgPlugin.search(), returns list of title/url/snippet/source dicts. Commit.

---

## Task 6: Qdrant Search Node

Create: app/pipeline/nodes/qdrant_search.py. Category enrich. Config: collection (enum search_results or linkedin_profiles), limit (int, default 20). Execute: for each input item, embed title+snippet, search Qdrant, append qdrant_matches to item. Commit.

---

## Task 7: RSS Monitor Node

Create: app/pipeline/nodes/rss_monitor.py. Category source. Config: feed_url (required uri), max_items (int, default 20). Execute: GET feed, parse RSS 2.0 or Atom, return title/url/snippet/published_at/source dicts. Use run_in_executor for sync requests call. Commit.

---

## Task 8: Apify Actor Node

Create: app/pipeline/nodes/apify_actor.py. Category source. Follow exact same pattern as app/routers/v3/apify.py _run_and_ingest: read API key from core_settings, POST to start actor run, poll for status, fetch dataset items. Config schema: actor_id (required), currentJobTitles, locations, maxItems, scraperMode, segmentation fields, recently changed/posted booleans. Output: profile dicts with id, first_name, last_name, headline, about, source. Use run_in_executor for sync HTTP calls. Commit.

---

## Task 9: Temporal Workflow plus Activities

Create: app/pipeline/workflow.py.

Dataclasses: NodeSpec, EdgeSpec, PipelineRunInput, ActivityInput. Constant TASK_QUEUE = "pipeline-tasks".

Activity execute_node: instantiate NodeRegistry, find node by type, update step_run to running, call node.execute(), update step_run to succeeded with item_count. On failure update to failed with error_message. Push WebSocket events via push_event (best-effort).

Helper _topo_sort(nodes, edges): topological sort returning layers of parallel nodes (nodes with no unresolved deps form a layer).

Workflow PipelineWorkflow: update run to running, iterate topo layers, execute activities in parallel per layer via workflow.execute_activity with 15min timeout, pass upstream outputs to downstream nodes based on edge_lookup, update run to succeeded or failed. Commit.

---

## Task 10: Temporal Worker Entrypoint

Create: app/pipeline/worker.py. Connect to Temporal (TEMPORAL_HOST:TEMPORAL_PORT env vars), create Worker on TASK_QUEUE with PipelineWorkflow and execute_node. Entry: python -m app.pipeline.worker. Commit.

---

## Task 11: Docker Compose -- Temporal Services

Modify: docker-compose.yml.

Add 3 services: (1) temporal -- temporalio/auto-setup image, DB postgres12, connects to existing postgres, port 7233. (2) temporal-ui -- temporalio/ui image, port 8233 mapped to 8080, TEMPORAL_ADDRESS temporal:7233. (3) temporal-worker -- same build as info-broker-api, command python -m app.pipeline.worker, same env vars as info-broker-api plus TEMPORAL_HOST/PORT.

Add TEMPORAL_HOST and TEMPORAL_PORT env vars to info-broker-api service. Match the existing env var pattern (same as QDRANT_HOST etc). Verify with docker compose config --quiet. Commit.

---

## Task 12: Pipeline Router -- CRUD plus Run Endpoints

Create: app/routers/v3/pipelines.py. Modify: app/main.py.

Endpoints following existing patterns from apify.py and jobs.py:
- POST /v3/pipelines -- create with nodes and edges
- GET /v3/pipelines -- list user pipelines
- GET /v3/pipelines/nodes/types -- list available node types (define BEFORE parametric routes)
- GET /v3/pipelines/runs/{run_id} -- run detail with steps (define BEFORE parametric routes)
- GET /v3/pipelines/{pipeline_id} -- pipeline with nodes plus edges
- PUT /v3/pipelines/{pipeline_id} -- update (delete+recreate nodes/edges)
- DELETE /v3/pipelines/{pipeline_id} -- cascade delete
- POST /v3/pipelines/{pipeline_id}/run -- async, starts Temporal workflow
- GET /v3/pipelines/{pipeline_id}/runs -- list runs

Run endpoint: create pipeline_runs + pipeline_step_runs rows, connect to Temporal via Client.connect(), start PipelineWorkflow on TASK_QUEUE with PipelineRunInput.

Register router in app/main.py after v3_apify_router. Commit.

---

## Task 13: Frontend API Client

Create: frontend/src/api/pipelines.ts.

Types: PipelineNodeIn/Out, PipelineEdgeIn/Out, PipelineIn, Pipeline, PipelineDetail, PipelineStepRun, PipelineRun, PipelineRunDetail, NodeType.

Functions: createPipeline, listPipelines, getPipeline, updatePipeline, deletePipeline, startPipelineRun, listPipelineRuns, getPipelineRun, listNodeTypes. All use api from ./client. Commit.

---

## Task 14: ResizableSplit Component

Create: frontend/src/components/pipeline/ResizableSplit.tsx. Wraps react-resizable-panels PanelGroup with left (default 40%, min 20%, max 60%) and right (min 30%) panels. 4px drag handle styled with var(--border). Commit.

---

## Task 15: DagPreview Component

Create: frontend/src/components/pipeline/DagPreview.tsx. SVG DAG renderer.

Auto-layout: topological layer assignment, nodes at same depth are stacked vertically. Constants NODE_W=160, NODE_H=60, GAP_X=80, GAP_Y=30. Dot grid background via SVG pattern. Bezier curve edges (C path) colored by status. Nodes are rounded rects color-coded by category (source blue, enrich purple, score green). Status indicators: checkmark/pulse/X during runs. Item count text. Empty state message. Commit.

---

## Task 16: StepList Component

Create: frontend/src/components/pipeline/StepList.tsx.

Vertical step list. Each step: numbered circle (color by category or status), card with label, category badge, config summary. Status badges + item counts during runs. Add Step button with grouped dropdown by category. Remove button per node. onClick selects node for config editing. readOnly prop disables editing during active runs. Commit.

---

## Task 17: NodeConfigForm Component

Create: frontend/src/components/pipeline/NodeConfigForm.tsx.

Slide-over panel generated from JSON Schema. Supports: string inputs, number inputs with min/max, boolean checkboxes, enum selects, array inputs (comma-separated). Required field markers. onChange callback updates node config in parent. Done button to close. Commit.

---

## Task 18: PipelineBuilder Main Component

Create: frontend/src/components/pipeline/PipelineBuilder.tsx.

Layout: saved pipelines sidebar (160px) | main area with header (name input, Save/Run/Delete buttons) | ResizableSplit with StepList left and DagPreview right.

State: selectedPipelineId, localNodes/Edges/Name/Desc, editingNodeId, activeRunId, dirty flag. Queries: listPipelines, getPipeline, listNodeTypes, listPipelineRuns (poll 5s), getPipelineRun (poll 3s when active). Mutations: create, save (update), run (start), delete.

handleAddNode: create node with crypto.randomUUID(), auto-connect edge to last node. handleRemoveNode: filter nodes and edges. NodeConfigForm overlays StepList when editing. Auto-select latest active run for live tracking. Commit.

---

## Task 19: Integrate Pipelines Tab into LinkedInPage

Modify: frontend/src/pages/LinkedInPage.tsx.

Import PipelineBuilder. Extend tab state type to include 'pipelines'. Add tabBtn for Pipelines. Add content block: tab === 'pipelines' renders PipelineBuilder. Commit.

---

## Task 20: End-to-End Verification

Rebuild all: docker compose up --build -d. Check Temporal UI at localhost:8233. Check temporal-worker logs for "Starting worker on queue pipeline-tasks". Check info-broker-api startup. Test node types endpoint with auth. Open LinkedIn page Pipelines tab. Verify empty state and New Pipeline button.
