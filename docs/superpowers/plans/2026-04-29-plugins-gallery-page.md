# Plugins Gallery Page

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Create a dedicated Plugins page (own nav item) that shows a curated gallery of plugin cards — each with title, description, tags, and an enable/disable toggle — replacing the plugins section in Settings; clicking a plugin card opens that plugin's full page (e.g. LinkedIn Scraper opens the existing LinkedIn page).

**Architecture:** A static front-end plugin registry defines the curated list (LinkedIn Scraper as a full-page app plugin; the 4 pipeline nodes as toggle-only plugins). The Plugins page is a new route `/plugins`. The backend gains two endpoints (`GET/PUT /v3/pipelines/nodes/types/{node_type}/enabled`) that persist enabled state in `core_settings`. IconRail gains a Plugins icon and loses the LinkedIn shortcut (users reach LinkedIn Scraper through Plugins). Settings loses its PLUGINS sidebar section.

**Tech Stack:** React 18, TypeScript, React Router v6, React Query, FastAPI, psycopg2.

**Prerequisite:** The pipeline save-fix plan (`2026-04-29-pipeline-save-fix-and-node-toggles.md` Task 1) fixes an independent bug and can be executed before or after this plan.

---

## Task 1: Backend — Pipeline Node Enable/Disable Endpoints

Store per-node-type enabled state in `core_settings` (`key = pipeline_node.{node_type}.enabled`, `value = "true"/"false"`, default `true` if absent). Add two endpoints and filter `list_node_types` to respect enabled state.

**Files:**
- Modify: `app/routers/v3/pipelines.py`

---

- [ ] **Step 1: Add helpers and filter `list_node_types` in pipelines.py**

Open `app/routers/v3/pipelines.py`. Add these three helpers immediately after the import block (before the router definition):

```python
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
```

Then update `list_node_types` to filter by enabled state:

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

- [ ] **Step 2: Add enable/disable endpoints**

In `app/routers/v3/pipelines.py`, add these two endpoints immediately after `list_node_types` (before the `GET /runs/{run_id}` endpoint — keep all `/nodes/` routes before parametric `/{pipeline_id}` routes):

```python
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
    user: dict = Depends(get_current_user),
):
    from app.pipeline.nodes import NodeRegistry
    NodeRegistry.auto_discover()
    valid = {n.node_type for n in NodeRegistry.all()}
    if node_type not in valid:
        raise HTTPException(status_code=404, detail=f"Unknown node type: {node_type!r}")
    _set_node_enabled(node_type, bool(body.get("enabled", True)))
```

- [ ] **Step 3: Rebuild API and verify**

```bash
docker compose up --build -d info-broker-api
sleep 5

TOKEN=$(curl -s -X POST http://localhost:8000/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# All 4 enabled by default
curl -s http://localhost:8000/v3/pipelines/nodes/types \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print([n['node_type'] for n in d])"
# Expected: ['ddg_search', 'qdrant_search', 'rss_monitor', 'apify_actor']

# Disable rss_monitor
curl -s -X PUT http://localhost:8000/v3/pipelines/nodes/types/rss_monitor/enabled \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# Only 3 returned now
curl -s http://localhost:8000/v3/pipelines/nodes/types \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d)==3, d; print('OK:', [n['node_type'] for n in d])"
# Expected: OK: ['ddg_search', 'qdrant_search', 'apify_actor']

# Re-enable
curl -s -X PUT http://localhost:8000/v3/pipelines/nodes/types/rss_monitor/enabled \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

- [ ] **Step 4: Commit**

```bash
git add app/routers/v3/pipelines.py
git commit -m "feat(plugins): pipeline node enable/disable via core_settings, filter list_node_types"
```

---

## Task 2: Frontend API — Plugin Enable/Disable Functions

Add two typed functions to the frontend API client.

**Files:**
- Modify: `frontend/src/api/v3.ts`

---

- [ ] **Step 1: Add functions to v3.ts**

At the end of `frontend/src/api/v3.ts`, append:

```typescript
export const getPipelineNodeEnabled = (
  nodeType: string,
): Promise<{ node_type: string; enabled: boolean }> =>
  api.get(`/v3/pipelines/nodes/types/${nodeType}/enabled`).then(r => r.data)

export const setPipelineNodeEnabled = (
  nodeType: string,
  enabled: boolean,
): Promise<void> =>
  api.put(`/v3/pipelines/nodes/types/${nodeType}/enabled`, { enabled }).then(() => undefined)
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/v3.ts
git commit -m "feat(plugins): add getPipelineNodeEnabled / setPipelineNodeEnabled API functions"
```

---

## Task 3: Create PluginsPage Component

A gallery page showing all curated plugins as cards. Plugin types:

- **`app`** — has a full detail page; clicking navigates to it (e.g. LinkedIn Scraper → `/linkedin`)
- **`pipeline_node`** — pipeline-only; card shows enable/disable toggle; no separate config page yet

Each card shows: title, description, tags as colored badges, enabled/disabled state, and a clickable area.

**Files:**
- Create: `frontend/src/pages/PluginsPage.tsx`

---

- [ ] **Step 1: Create PluginsPage.tsx**

Create `frontend/src/pages/PluginsPage.tsx` with the full content below:

```tsx
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import IconRail from '../components/layout/IconRail'
import { getPipelineNodeEnabled, setPipelineNodeEnabled } from '../api/v3'

// ─── Static plugin registry ──────────────────────────────────────────────────

type AppPlugin = {
  kind: 'app'
  id: string
  title: string
  description: string
  tags: string[]
  route: string
}

type NodePlugin = {
  kind: 'node'
  id: string
  title: string
  description: string
  tags: string[]
  node_type: string
}

type PluginDef = AppPlugin | NodePlugin

const PLUGINS: PluginDef[] = [
  {
    kind: 'app',
    id: 'linkedin-scraper',
    title: 'LinkedIn Scraper',
    description: 'Harvest LinkedIn profiles using Apify actor runs. Configure targeting, run scraper jobs, view ingested profiles, and build automated pipelines.',
    tags: ['SRC'],
    route: '/linkedin',
  },
  {
    kind: 'node',
    id: 'ddg-search',
    title: 'DDG Search',
    description: 'Search the web using DuckDuckGo. Use as a source node in pipelines to pull search results for a given query.',
    tags: ['SRC', 'PIPELINE'],
    node_type: 'ddg_search',
  },
  {
    kind: 'node',
    id: 'qdrant-search',
    title: 'Qdrant Semantic Search',
    description: 'Enrich pipeline results with semantic vector search against your Qdrant collections.',
    tags: ['ENRICH', 'PIPELINE'],
    node_type: 'qdrant_search',
  },
  {
    kind: 'node',
    id: 'rss-monitor',
    title: 'RSS Monitor',
    description: 'Fetch and parse RSS 2.0 and Atom feeds. Use as a source node to pull news or blog posts into a pipeline.',
    tags: ['SRC', 'PIPELINE'],
    node_type: 'rss_monitor',
  },
  {
    kind: 'node',
    id: 'apify-actor',
    title: 'Apify Actor',
    description: 'Run any Apify actor and ingest the resulting dataset as pipeline items.',
    tags: ['SRC', 'PIPELINE'],
    node_type: 'apify_actor',
  },
]

// ─── Tag colors ───────────────────────────────────────────────────────────────

const TAG_COLORS: Record<string, { bg: string; text: string }> = {
  SRC:      { bg: '#1e3a5f', text: '#60a5fa' },
  ENRICH:   { bg: '#2d1f4e', text: '#a78bfa' },
  SCORE:    { bg: '#1a3a2a', text: '#4ade80' },
  PIPELINE: { bg: '#1a2a1a', text: '#86efac' },
  FILTER:   { bg: '#3a2a1a', text: '#fb923c' },
}

function TagBadge({ tag }: { tag: string }) {
  const colors = TAG_COLORS[tag] ?? { bg: '#1e293b', text: '#94a3b8' }
  return (
    <span
      style={{
        fontSize: 9,
        fontWeight: 700,
        padding: '2px 6px',
        borderRadius: 4,
        background: colors.bg,
        color: colors.text,
        letterSpacing: '0.05em',
      }}
    >
      {tag}
    </span>
  )
}

// ─── Node plugin card (with enable/disable) ───────────────────────────────────

function NodePluginCard({ plugin }: { plugin: NodePlugin }) {
  const qc = useQueryClient()

  const { data } = useQuery({
    queryKey: ['plugin-enabled', plugin.node_type],
    queryFn: () => getPipelineNodeEnabled(plugin.node_type).catch(() => ({ node_type: plugin.node_type, enabled: true })),
  })

  const enabled = data?.enabled !== false

  const toggleMutation = useMutation({
    mutationFn: (next: boolean) => setPipelineNodeEnabled(plugin.node_type, next),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plugin-enabled', plugin.node_type] })
      qc.invalidateQueries({ queryKey: ['nodeTypes'] })
    },
  })

  return (
    <div
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        opacity: enabled ? 1 : 0.55,
        transition: 'opacity 0.15s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{plugin.title}</span>
        <button
          onClick={() => toggleMutation.mutate(!enabled)}
          disabled={toggleMutation.isPending}
          style={{
            fontSize: 10,
            fontWeight: 600,
            padding: '3px 10px',
            borderRadius: 20,
            border: `1px solid ${enabled ? '#22c55e' : '#475569'}`,
            background: enabled ? '#14532d33' : 'transparent',
            color: enabled ? '#22c55e' : '#64748b',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          {enabled ? 'Enabled' : 'Disabled'}
        </button>
      </div>

      <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0, lineHeight: 1.5 }}>
        {plugin.description}
      </p>

      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {plugin.tags.map(t => <TagBadge key={t} tag={t} />)}
      </div>
    </div>
  )
}

// ─── App plugin card (navigates to full page) ─────────────────────────────────

function AppPluginCard({ plugin }: { plugin: AppPlugin }) {
  const navigate = useNavigate()

  return (
    <div
      onClick={() => navigate(plugin.route)}
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        cursor: 'pointer',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--accent)')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{plugin.title}</span>
        <span style={{ fontSize: 10, color: 'var(--accent)', fontWeight: 600 }}>Open →</span>
      </div>

      <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0, lineHeight: 1.5 }}>
        {plugin.description}
      </p>

      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {plugin.tags.map(t => <TagBadge key={t} tag={t} />)}
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PluginsPage() {
  const appPlugins = PLUGINS.filter((p): p is AppPlugin => p.kind === 'app')
  const nodePlugins = PLUGINS.filter((p): p is NodePlugin => p.kind === 'node')

  return (
    <div className="flex h-screen" style={{ background: 'var(--bg)', color: 'var(--text)' }}>
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div
          style={{
            padding: '14px 20px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <h1 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>Plugins</h1>
            <p style={{ fontSize: 11, color: 'var(--muted)', margin: '2px 0 0' }}>
              Curated integrations and pipeline nodes
            </p>
          </div>
          {/* Search stub — future feature */}
          <input
            disabled
            placeholder="Search plugins (coming soon)"
            style={{
              padding: '6px 12px',
              fontSize: 11,
              background: 'var(--panel)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              color: 'var(--muted)',
              width: 220,
              cursor: 'not-allowed',
            }}
          />
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto" style={{ padding: 20 }}>
          {/* App plugins */}
          <section style={{ marginBottom: 28 }}>
            <h2
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.08em',
                color: 'var(--muted)',
                margin: '0 0 12px',
              }}
            >
              INTEGRATIONS
            </h2>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: 12,
              }}
            >
              {appPlugins.map(p => <AppPluginCard key={p.id} plugin={p} />)}
            </div>
          </section>

          {/* Pipeline node plugins */}
          <section>
            <h2
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.08em',
                color: 'var(--muted)',
                margin: '0 0 12px',
              }}
            >
              PIPELINE NODES
            </h2>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: 12,
              }}
            >
              {nodePlugins.map(p => <NodePluginCard key={p.id} plugin={p} />)}
            </div>
          </section>
        </div>
      </div>
      <IconRail />
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/PluginsPage.tsx
git commit -m "feat(plugins): create PluginsPage gallery with app and node plugin cards"
```

---

## Task 4: Add /plugins Route to App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

---

- [ ] **Step 1: Add lazy import and route**

In `frontend/src/App.tsx`, add the lazy import for PluginsPage alongside the other lazy imports:

```typescript
const PluginsPage = React.lazy(() => import('./pages/PluginsPage'))
```

Then add the route inside the `<Routes>` block (inside `<AuthGuard>`) alongside existing routes:

```tsx
<Route path="/plugins" element={<PluginsPage />} />
```

- [ ] **Step 2: Verify app compiles**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: build succeeds with no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(plugins): add /plugins route"
```

---

## Task 5: Update IconRail — Add Plugins, Remove LinkedIn Shortcut

The LinkedIn Scraper is now accessed through the Plugins page. Remove its direct nav item from IconRail and add a Plugins icon.

**Files:**
- Modify: `frontend/src/components/layout/IconRail.tsx`

---

- [ ] **Step 1: Read the current IconRail NAV array**

Read `frontend/src/components/layout/IconRail.tsx` to see the exact format of the NAV entries. The NAV array looks like:

```typescript
const NAV = [
  { icon: '⬡', label: 'Research', path: '/' },
  { icon: '◉', label: 'Jobs', path: '/jobs' },
  { icon: '◈', label: 'Monitors', path: '/monitors' },
  { icon: '▤', label: 'History', path: '/history' },
  { icon: '⊞', label: 'LinkedIn', path: '/linkedin' },
  { icon: '⚙', label: 'Settings', path: '/settings' },
]
```

- [ ] **Step 2: Replace the LinkedIn entry with Plugins**

In `frontend/src/components/layout/IconRail.tsx`, replace the LinkedIn nav entry with a Plugins entry. Use `⊟` or `⊞` or `❖` as the icon — pick whichever reads best as "Plugins/Extensions". Use `❖` for Plugins:

Remove:
```typescript
  { icon: '⊞', label: 'LinkedIn', path: '/linkedin' },
```

Add in its place:
```typescript
  { icon: '❖', label: 'Plugins', path: '/plugins' },
```

- [ ] **Step 3: Rebuild frontend and verify nav**

```bash
docker compose up --build -d frontend
```

Open http://localhost:5173. Verify:
- IconRail shows the Plugins icon where LinkedIn used to be
- Clicking it navigates to `/plugins`
- The Plugins page renders with two sections: INTEGRATIONS and PIPELINE NODES
- LinkedIn Scraper card appears under INTEGRATIONS and clicking it navigates to `/linkedin`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/layout/IconRail.tsx
git commit -m "feat(plugins): replace LinkedIn nav with Plugins in IconRail"
```

---

## Task 6: Clean Up Settings Page — Remove Plugins Section

The plugins section in Settings is now superseded by the dedicated Plugins page. Remove it from Settings and leave Settings as a pure system configuration page.

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`

---

- [ ] **Step 1: Remove plugin-related state and queries from Settings.tsx**

In `frontend/src/pages/Settings.tsx`:

1. Remove the import of `listPlugins` and `PluginInfo` from `../api/v3`
2. Remove the import of `PluginConfigPage` from `../components/plugins/PluginConfigPage`
3. Remove the `useQuery` call for `listPlugins`:
   ```typescript
   // Remove this:
   const { data: plugins = [] } = useQuery({ queryKey: ['plugins'], queryFn: listPlugins })
   ```
4. Remove the PLUGINS section from the sidebar (the `<div>` with "PLUGINS" label and the `{plugins.map(...)}` block)
5. Remove the `PluginConfigPage` branch from the content area:
   ```tsx
   // Before:
   {section === 'core' ? <CoreSettingsForm /> : <PluginConfigPage pluginName={section} />}

   // After:
   <CoreSettingsForm />
   ```
6. Simplify the section header: change `{section === 'core' ? 'Core Settings' : \`${section} Plugin\`}` to just `Core Settings`
7. Set the initial section state to always be `'core'` (remove the `params.name` fallback since plugin routing no longer goes through Settings)

The Settings page sidebar becomes just the "SYSTEM" section with "Core Settings".

- [ ] **Step 2: Verify Settings page still works**

Open http://localhost:5173/settings. Verify:
- Settings page shows only "Core Settings" in the sidebar
- Core settings form renders correctly
- No broken imports or TypeScript errors

Check browser console for errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Settings.tsx
git commit -m "refactor(settings): remove plugins section, Settings is now core-only"
```

---

## Task 7: Add "← Plugins" Breadcrumb to LinkedInPage

Users now navigate to the LinkedIn Scraper from the Plugins page. Add a back link so they can return.

**Files:**
- Modify: `frontend/src/pages/LinkedInPage.tsx`

---

- [ ] **Step 1: Add breadcrumb to the top of the left config panel**

In `frontend/src/pages/LinkedInPage.tsx`, add the `useNavigate` import:

```typescript
import { useNavigate } from 'react-router-dom'
```

Then in the `LinkedInPage` component's left column (the config panel), add a breadcrumb above the "LinkedIn Harvester" title. Find the left column's title element and prepend:

```tsx
const navigate = useNavigate()
// ...
// At the top of the left column:
<button
  onClick={() => navigate('/plugins')}
  style={{
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    fontSize: 10,
    color: 'var(--muted)',
    background: 'transparent',
    border: 'none',
    cursor: 'pointer',
    padding: '0 0 8px',
  }}
>
  ← Plugins
</button>
```

- [ ] **Step 2: Verify**

Open http://localhost:5173/plugins, click LinkedIn Scraper → verify it opens the LinkedIn page with "← Plugins" breadcrumb at the top-left. Click breadcrumb → returns to /plugins.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/LinkedInPage.tsx
git commit -m "feat(plugins): add ← Plugins breadcrumb to LinkedInPage"
```

---

## Task 8: Final Verification

- [ ] **End-to-end check**

1. **Nav**: IconRail shows ❖ Plugins. Clicking opens `/plugins`.
2. **Gallery**: Two sections visible — INTEGRATIONS (LinkedIn Scraper) and PIPELINE NODES (4 cards).
3. **App plugin**: Clicking LinkedIn Scraper card navigates to `/linkedin` with "← Plugins" breadcrumb.
4. **Node toggle**: Click "Enabled" on DDG Search card → button shows "Disabled", card dims. Navigate to LinkedIn → Pipelines tab → Add Step dropdown → DDG Search not listed.
5. **Re-enable**: Toggle DDG Search back to Enabled → reappears in Pipelines dropdown.
6. **Settings**: `/settings` shows only Core Settings, no Plugins section.
7. **Tag badges**: SRC, ENRICH, PIPELINE badges render with correct colors on each card.
8. **Search stub**: Search input is visible but disabled with placeholder text.

- [ ] **Commit if any last fixes needed, then done**

```bash
git add -A
git commit -m "fix(plugins): any final adjustments from e2e check"
```
