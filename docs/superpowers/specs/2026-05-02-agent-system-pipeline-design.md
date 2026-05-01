# Agent System Pipeline Design

**Date:** 2026-05-02
**Status:** Approved

## Summary

Add a default system-level pipeline for the Agent chat interface. The pipeline has `agent_input` as a fixed, immovable source node, `ddg_search` as the enrichment step, and `manual_scoring` for scoring. Users can configure their own override pipeline in Settings; the system pipeline is the read-only fallback. The Agent chat executes the active pipeline via Temporal instead of its current hardcoded flow.

---

## 1. Database

### Schema changes

```sql
ALTER TABLE pipelines
  ALTER COLUMN user_id DROP NOT NULL,
  ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE pipelines
  ADD CONSTRAINT ck_pipeline_owner
  CHECK ((user_id IS NOT NULL) OR (is_system = true));
```

- `user_id` is NULL for system pipelines.
- `is_system = true` pipelines cannot be deleted or updated by any user.

### Seed migration (idempotent)

Runs at app startup via the existing `_SCHEMA_MIGRATION` block. Uses a fixed UUID so it is safe to run multiple times.

**Default system pipeline:** `"Agent Default"`

| # | node_type | label | position_y |
|---|-----------|-------|-----------|
| 1 | `agent_input` | Agent CLI | 0 |
| 2 | `ddg_search` | DDG Search | 1 |
| 3 | `manual_scoring` | Manual Scoring | 2 |

Edges: node1→node2 (`results`), node2→node3 (`results`).

### User preference

Stored in the existing `ui_preferences` table as key `agent.pipeline_id`, value = pipeline UUID. No new table.

Active pipeline resolution order:
1. `ui_preferences` row for the current user with key `agent.pipeline_id`
2. System default pipeline (`is_system = true`, seeded at startup)
3. 503 if neither exists (migration hasn't run)

---

## 2. API

### Modified endpoints

| Method | Path | Change |
|--------|------|--------|
| `GET /v3/pipelines` | Returns user pipelines + all system pipelines. Adds `is_system: bool` to `PipelineOut`. |
| `DELETE /v3/pipelines/{id}` | Returns 403 if `is_system = true`. |
| `PUT /v3/pipelines/{id}` | Returns 403 if `is_system = true`. |

### New endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET /v3/agent/pipeline` | Returns active pipeline for current user (preference → system default fallback). |
| `PUT /v3/agent/pipeline` | Sets user's preferred agent pipeline. Validates constraints (see below). |

### Agent pipeline constraints (enforced on `PUT /v3/agent/pipeline`)

- Pipeline must have exactly 1 source node.
- That source node must be `agent_input`.
- `agent_input` must be at `position_y = 0`.
- No other source-category nodes are permitted.

### `POST /v3/agent/message` — new execution flow

1. Load active pipeline for current user (preference → system default).
2. Create `pipeline_run` row with `trigger_type = 'agent'`.
3. Inject message text into `agent_input` node config as `{ "message": "<user text>" }`.
4. Start Temporal workflow with the full pipeline spec.
5. Return `{ job_id: run_id, status: "pending" }` — same response shape as today.

If no active pipeline resolves, return 503 with `{ "detail": "No agent pipeline configured" }`.

---

## 3. Pipeline Builder — agent_input constraints

When a pipeline's source node is `agent_input`:

- The `agent_input` node is rendered as **locked**:
  - Delete handle hidden.
  - Drag disabled (position fixed).
- "Add node" is restricted to `enrich` and `score` categories — source category hidden.

Enforced in `PipelineBuilder.tsx` and `NodeConfigForm.tsx` via an `isAgentPipeline` flag derived from the presence of `agent_input` as the sole source.

---

## 4. Settings Page

New "Agent" section in Settings:

- Pipeline dropdown — lists all pipelines from `GET /v3/pipelines`.
  - System pipelines shown with a `[Default]` badge.
  - User's current selection highlighted.
- On change: `PUT /v3/agent/pipeline` with selected `pipeline_id`.
- Validation error shown inline if the selected pipeline fails the `agent_input` constraint.

---

## 5. AgentChat

- On mount: `GET /v3/agent/pipeline` → displays active pipeline name in the header next to "Agent" label.
- Header shows a small link/icon to navigate to Settings for pipeline configuration.
- No in-chat pipeline selector.

---

## 6. E2E Tests

**File:** `frontend/e2e/agent-pipeline.spec.ts`
**Runner:** Playwright, Chrome, headed (`--headed --project=chromium`)

| # | Scenario |
|---|----------|
| 1 | Login → Settings shows system default pipeline labeled `[Default]` in agent dropdown |
| 2 | Send agent message → pipeline run created, WebSocket delivers status updates |
| 3 | Pipeline Builder: open system default → `agent_input` has no delete handle, cannot be dragged |
| 4 | Create user pipeline with `agent_input` source → set in Settings → send agent message → correct pipeline runs |
| 5 | Attempt to delete system pipeline via UI → blocked (403 shown) |

---

## 7. Out of Scope

- Multiple agent pipelines active simultaneously (always exactly one)
- Admin UI for managing system pipelines
- Adding sources other than `agent_input` to agent pipelines (future)
