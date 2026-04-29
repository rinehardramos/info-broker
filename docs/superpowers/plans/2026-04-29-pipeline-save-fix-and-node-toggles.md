# Pipeline Save Fix + Node Type Enable/Disable

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Fix the broken Pipeline Save (FK constraint bug on edge insertion) and add per-node-type enable/disable toggles in the Settings page so only enabled node types appear in the Pipeline builder.

**Architecture:** Two independent fixes. (1) The save bug is a UUID mapping error in `_upsert_nodes_edges` — the backend generates new node UUIDs but then inserts edges using frontend UUIDs that don't match; fix by passing frontend UUIDs through as DB node IDs. (2) Node type enabled state is stored in the existing `core_settings` table with key `pipeline_node.{node_type}.enabled`; the `list_node_types` endpoint filters by this; the Settings page gains a "Pipeline Nodes" section with toggles.

**Tech Stack:** Python 3.11, FastAPI, psycopg2, React 18, TypeScript, Tailwind CSS.

---

## Task 1: Fix Pipeline Save — Edge UUID Mapping Bug

**Root cause:** `_upsert_nodes_edges` in `app/routers/v3/pipelines.py` inserts each node with a newly generated UUID (`nid = str(uuid.uuid4())`), but then inserts edges using `edge.source_node_id` / `edge.target_node_id` — which are the **frontend-generated** UUIDs, not the DB UUIDs just created. This causes a FK constraint violation on `pipeline_edges.source_node_id → pipeline_nodes.id`.

**Fix:** Accept the frontend node `id` in `PipelineNodeIn`. Use it directly as the DB node ID. The edges reference those same frontend UUIDs, so they now match exactly.

**Files:**
- Modify: `app/routers/v3/models.py`
- Modify: `app/routers/v3/pipelines.py`
- Modify: `frontend/src/api/pipelines.ts`
- Modify: `frontend/src/components/pipeline/PipelineBuilder.tsx`

---

- [ ] **Step 1: Add optional `id` to `PipelineNodeIn` in models.py**

In `app/routers/v3/models.py`, find `class PipelineNodeIn` and add `id: UUID | None = None` as the first field:

```python
class PipelineNodeIn(BaseModel):
    id: UUID | None = None      # frontend-generated UUID; used as DB node ID
    node_type: str
    label: str
    config: dict = {}
    position_x: int = 0
    position_y: int = 0
```

- [ ] **Step 2: Fix `_upsert_nodes_edges` in pipelines.py**

Replace the entire `_upsert_nodes_edges` function in `app/routers/v3/pipelines.py`:

```python
def _upsert_nodes_edges(pipeline_id: str, body: PipelineIn) -> None:
    """Insert nodes and edges. Nodes use frontend-provided UUIDs as DB IDs."""
    import json

    # Build map: frontend_uuid → db_uuid (use frontend UUID directly)
    node_id_map: dict[str, str] = {}
    for node in body.nodes:
        nid = str(node.id) if node.id else str(uuid.uuid4())
        node_id_map[str(node.id) if node.id else ""] = nid
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
```

Also remove the `import json` inside the old function (it used `__import__("json")`). Add `import json` at the top of `pipelines.py` with the other imports.

- [ ] **Step 3: Update frontend `PipelineNodeIn` type to include `id`**

In `frontend/src/api/pipelines.ts`, update `PipelineNodeIn`:

```typescript
export interface PipelineNodeIn {
  id?: string                      // frontend UUID — sent to backend to use as DB node ID
  node_type: string
  label: string
  config: Record<string, unknown>
  position_x?: number
  position_y?: number
}
```

- [ ] **Step 4: Include `id` in `handleSave` node mapping**

In `frontend/src/components/pipeline/PipelineBuilder.tsx`, in `handleSave`, update the nodes mapping:

```typescript
const handleSave = () => {
  const body = {
    name: localName,
    description: localDesc || null,
    nodes: localNodes.map(n => ({
      id: n.id,                   // pass frontend UUID through
      node_type: n.node_type,
      label: n.label,
      config: n.config,
      position_x: n.position_x,
      position_y: n.position_y,
    })),
    edges: localEdges.map(e => ({
      source_node_id: e.source_node_id,
      target_node_id: e.target_node_id,
      edge_type: e.edge_type,
    })),
  }
  if (selectedPipelineId) {
    updateMutation.mutate({ id: selectedPipelineId, body })
  } else {
    createMutation.mutate(body)
  }
}
```

- [ ] **Step 5: Verify fix — rebuild API and test**

```bash
docker compose up --build -d info-broker-api
sleep 5

# Get auth token
TOKEN=$(curl -s -X POST http://localhost:8000/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create pipeline with nodes and edges
curl -s -X POST http://localhost:8000/v3/pipelines \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Save Test",
    "nodes": [
      {"id": "aaa-111", "node_type": "ddg_search", "label": "DDG", "config": {"query": "test"}, "position_x": 0, "position_y": 0},
      {"id": "bbb-222", "node_type": "qdrant_search", "label": "Qdrant", "config": {}, "position_x": 200, "position_y": 0}
    ],
    "edges": [
      {"source_node_id": "aaa-111", "target_node_id": "bbb-222", "edge_type": "results"}
    ]
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK:', d.get('id')) if 'id' in d else print('FAIL:', d)"
```

Expected: `OK: <uuid>` — no FK error.

- [ ] **Step 6: Commit**

```bash
git add app/routers/v3/models.py app/routers/v3/pipelines.py frontend/src/api/pipelines.ts frontend/src/components/pipeline/PipelineBuilder.tsx
git commit -m "fix(pipeline): pass frontend node UUIDs to backend to fix edge FK constraint on save"
```

---

## Task 2: Backend — Node Type Enable/Disable via core_settings

Store enabled/disabled state in the existing `core_settings` table.
- Key pattern: `pipeline_node.{node_type}.enabled`
- Value: `"true"` or `"false"`
- Default (key absent): `true` (all node types enabled by default)

**Files:**
- Modify: `app/routers/v3/pipelines.py`

---

- [ ] **Step 1: Add helper functions for node enabled state**

In `app/routers/v3/pipelines.py`, add these helpers after the imports:

```python
def _node_enabled_key(node_type: str) -> str:
    return f"pipeline_node.{node_type}.enabled"


def _is_node_enabled(node_type: str) -> bool:
    row = fetch_one(
        "SELECT value FROM core_settings WHERE key = %s",
        (_node_enabled_key(node_type),),
    )
    if row is None:
        return True  # default: enabled
    return row["value"].lower() == "true"


def _set_node_enabled(node_type: str, enabled: bool) -> None:
    execute(
        """
        INSERT INTO core_settings (key, value, is_secret)
        VALUES (%s, %s, false)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (_node_enabled_key(node_type), "true" if enabled else "false"),
    )
```

- [ ] **Step 2: Filter `list_node_types` to only return enabled types**

Update the `list_node_types` endpoint in `app/routers/v3/pipelines.py`:

```python
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
```

- [ ] **Step 3: Add enable/disable endpoints**

Add two new endpoints in `app/routers/v3/pipelines.py` — place them BEFORE the parametric `/{pipeline_id}` routes. They must be added right after `list_node_types`:

```python
@router.put("/nodes/types/{node_type}/enabled", status_code=204)
def set_node_type_enabled(
    node_type: str,
    body: dict,
    user: dict = Depends(get_current_user),
):
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()
    valid_types = {n.node_type for n in NodeRegistry.all()}
    if node_type not in valid_types:
        raise HTTPException(status_code=404, detail=f"Unknown node type: {node_type!r}")
    enabled = bool(body.get("enabled", True))
    _set_node_enabled(node_type, enabled)


@router.get("/nodes/types/{node_type}/enabled")
def get_node_type_enabled(node_type: str, user: dict = Depends(get_current_user)):
    return {"node_type": node_type, "enabled": _is_node_enabled(node_type)}
```

- [ ] **Step 4: Verify endpoints — rebuild and test**

```bash
docker compose up --build -d info-broker-api
sleep 5

TOKEN=$(curl -s -X POST http://localhost:8000/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# All 4 should appear initially
curl -s http://localhost:8000/v3/pipelines/nodes/types \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print([n['node_type'] for n in json.load(sys.stdin)])"

# Disable ddg_search
curl -s -X PUT http://localhost:8000/v3/pipelines/nodes/types/ddg_search/enabled \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# Now only 3 should appear
curl -s http://localhost:8000/v3/pipelines/nodes/types \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d); assert len(d)==3"

# Re-enable ddg_search
curl -s -X PUT http://localhost:8000/v3/pipelines/nodes/types/ddg_search/enabled \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

Expected output line 2: `['ddg_search', 'qdrant_search', 'rss_monitor', 'apify_actor']`
Expected output line 3 (after disable): list of 3 without `ddg_search`

- [ ] **Step 5: Commit**

```bash
git add app/routers/v3/pipelines.py
git commit -m "feat(pipeline): enable/disable node types via core_settings, filter list_node_types"
```

---

## Task 3: Frontend — Node Type Toggles in Settings Page

Add a "Pipeline Nodes" section to the Settings page sidebar. Each node type shows an enable/disable toggle. When a node is disabled it disappears from the Pipeline builder's "Add Step" dropdown (which already fetches from `list_node_types` and will now get the filtered list).

**Files:**
- Modify: `frontend/src/api/v3.ts` (add API functions)
- Modify: `frontend/src/pages/Settings.tsx` (add Pipeline Nodes section)

---

- [ ] **Step 1: Add API functions to frontend/src/api/v3.ts**

At the end of `frontend/src/api/v3.ts`, add:

```typescript
export const getPipelineNodeEnabled = (nodeType: string): Promise<{ node_type: string; enabled: boolean }> =>
  api.get(`/v3/pipelines/nodes/types/${nodeType}/enabled`).then(r => r.data)

export const setPipelineNodeEnabled = (nodeType: string, enabled: boolean): Promise<void> =>
  api.put(`/v3/pipelines/nodes/types/${nodeType}/enabled`, { enabled }).then(() => undefined)
```

- [ ] **Step 2: Add NodeTypeToggle component inside Settings.tsx**

In `frontend/src/pages/Settings.tsx`, add this component before the `Settings` default export:

```tsx
const ALL_NODE_TYPES = [
  { node_type: 'ddg_search', display_name: 'DDG Search', category: 'source' },
  { node_type: 'qdrant_search', display_name: 'Qdrant Search', category: 'enrich' },
  { node_type: 'rss_monitor', display_name: 'RSS Monitor', category: 'source' },
  { node_type: 'apify_actor', display_name: 'Apify Actor', category: 'source' },
]

const CATEGORY_COLORS: Record<string, string> = {
  source: '#60a5fa',
  enrich: '#a78bfa',
  score: '#4ade80',
}

function PipelineNodesPanel() {
  const qc = useQueryClient()
  const { data: plugins = [] } = useQuery({
    queryKey: ['pipeline-node-enabled'],
    queryFn: async () => {
      const results = await Promise.all(
        ALL_NODE_TYPES.map(n => getPipelineNodeEnabled(n.node_type).then(r => r).catch(() => ({ node_type: n.node_type, enabled: true })))
      )
      return Object.fromEntries(results.map(r => [r.node_type, r.enabled]))
    },
  })

  const toggle = async (nodeType: string, current: boolean) => {
    await setPipelineNodeEnabled(nodeType, !current)
    qc.invalidateQueries({ queryKey: ['pipeline-node-enabled'] })
    qc.invalidateQueries({ queryKey: ['nodeTypes'] })
  }

  return (
    <div>
      <p className="text-xs mb-4" style={{ color: 'var(--muted)' }}>
        Enable or disable pipeline node types. Disabled nodes won't appear in the Pipeline builder.
      </p>
      <div className="flex flex-col gap-3">
        {ALL_NODE_TYPES.map(n => {
          const enabled = plugins[n.node_type] !== false
          return (
            <div
              key={n.node_type}
              className="flex items-center justify-between px-3 py-2 rounded"
              style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
            >
              <div>
                <div className="text-xs font-semibold" style={{ color: 'var(--text)' }}>
                  {n.display_name}
                  <span
                    className="ml-2 text-[9px] font-normal"
                    style={{ color: CATEGORY_COLORS[n.category] ?? 'var(--muted)' }}
                  >
                    {n.category.toUpperCase()}
                  </span>
                </div>
                <div className="text-[10px]" style={{ color: 'var(--muted)' }}>{n.node_type}</div>
              </div>
              <button
                onClick={() => toggle(n.node_type, enabled)}
                className="text-xs px-2 py-1 rounded"
                style={{
                  background: enabled ? '#22c55e22' : '#ef444422',
                  border: `1px solid ${enabled ? '#22c55e' : '#ef4444'}`,
                  color: enabled ? '#22c55e' : '#ef4444',
                  cursor: 'pointer',
                  minWidth: 60,
                }}
              >
                {enabled ? 'Enabled' : 'Disabled'}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Add imports to Settings.tsx**

At the top of `frontend/src/pages/Settings.tsx`, add the import for the new API functions and `useQueryClient`:

```typescript
import { useQueryClient } from '@tanstack/react-query'
import { getCoreSettings, updateCoreSettings, listPlugins, getPipelineNodeEnabled, setPipelineNodeEnabled, type PluginInfo } from '../api/v3'
```

- [ ] **Step 4: Add "Pipeline Nodes" to the Settings sidebar and routing**

In `frontend/src/pages/Settings.tsx`, find where `setSection` type is defined and extend it. The section state currently holds `'core' | string`. Add `'pipeline-nodes'` to the sidebar:

After the `{plugins.map(...)}` block in the sidebar, add:

```tsx
<div className="text-[10px] font-semibold mb-2 mt-3 px-1" style={{ color: 'var(--muted)' }}>PIPELINE</div>
<button
  onClick={() => setSection('pipeline-nodes')}
  className="w-full text-left px-2 py-1 rounded text-xs mb-1"
  style={{
    background: section === 'pipeline-nodes' ? 'var(--panel2)' : 'transparent',
    color: section === 'pipeline-nodes' ? 'var(--accent)' : 'var(--text)',
    border: 'none', cursor: 'pointer',
  }}
>
  Node Types
</button>
```

In the right panel content area, add the `pipeline-nodes` case:

```tsx
{section === 'core' ? (
  <CoreSettingsForm />
) : section === 'pipeline-nodes' ? (
  <PipelineNodesPanel />
) : (
  <PluginConfigPage pluginName={section} />
)}
```

And update the section header:

```tsx
{section === 'core' ? 'Core Settings' : section === 'pipeline-nodes' ? 'Pipeline Node Types' : `${section} Plugin`}
```

- [ ] **Step 5: Rebuild frontend and verify**

```bash
docker compose up --build -d frontend
```

Open http://localhost:5173, navigate to Settings → Pipeline → Node Types. Verify:
- All 4 node types appear with Enabled/Disabled toggle buttons
- Clicking "Enabled" on `ddg_search` turns it Disabled
- Navigate to LinkedIn → Pipelines tab → click "+ Add Step" — DDG Search should not appear in the dropdown
- Toggle back to Enabled — DDG Search reappears

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/v3.ts frontend/src/pages/Settings.tsx
git commit -m "feat(pipeline): add Pipeline Node Types section in Settings with enable/disable toggles"
```
