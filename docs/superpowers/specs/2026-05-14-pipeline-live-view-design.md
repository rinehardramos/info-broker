# Design: Live Run Split-Pane Results, Streaming Cards & Brain Intent System

**Status:** Approved (visual mockup confirmed + dynamic node injection added)
**Date:** 2026-05-14
**Scope:** `frontend/` (primary) · `app/services/` and `app/routers/v3/` (additive backend)

---

## 0. Non-negotiable constraints

- WebSocket is a singleton (`useWebSocket.ts`). All event-driven UI subscribes via `useWebSocket(handler)`. No per-component socket connections.
- State lives in Zustand stores under `frontend/src/stores/`. Persisted state uses the `persist` middleware.
- DAGs are pure SVG: `ResearchFlow.tsx` (IS, live) and `DagPreview.tsx` (pipeline). No graph library introduced.
- Resizing uses `react-resizable-panels` — already present via `ResizableSplit.tsx`. No second resize library.
- UI primitives: Radix via wrappers in `frontend/src/components/ui/`. New primitives (Dialog) only if absent.
- `ResultsPanel.tsx` refactored by extraction, not rewrite. Tab routing logic is untouched.

---

## A. Component Architecture

### A.1 New components (all under `frontend/src/components/results/`)

| Component | Responsibility |
|---|---|
| `RunResultsView.tsx` | Top-level container for an active/completed run. Owns the split-pane layout. Selects `DagPreview` vs `ResearchFlow` by run kind. Replaces the inner body of the `run:<id>` tab branch in `ResultsPanel.tsx`. |
| `StreamingCardList.tsx` | Top pane. Subscribes to `useRunStreamStore` for the active run. Renders brain suggestion banners above, then `NodeResultCard` list in arrival order with mount animations. |
| `NodeResultCard.tsx` | One card per node. Header: name, status badge, elapsed. Body: streaming or completed preview. Footer: source tags. Clickable → `NodeResultDetailModal`. Presentational only. |
| `NodeResultDetailModal.tsx` | Centered Dialog (not Sheet). Tabs: Raw / Formatted / Sources. IS variant adds confidence bar + Branch tab. |
| `FlowMiniPreview.tsx` | Bottom pane. Scaled wrapper rendering `<DagPreview compact>` or `<ResearchFlow compact>`. Click → toggle fullscreen overlay. |
| `FlowFullscreenOverlay.tsx` | Fullscreen view of the live DAG. Toggle gesture: clicking the diagram body OR the Collapse button returns to split-pane. Clicking the mini preview from the split view opens fullscreen again. Escape also closes. |
| `BrainSuggestionBanner.tsx` | Dismissable banner. Variants: `enrichment` (pre-run, in chat), `next-step` (post-run, in results pane), `strategy`. Primary CTA + dismiss `×`. |
| `RunningTabBadge.tsx` | Pulsing-dot + run label used in the tab bar for any `run:<id>` with status `running`. |

### A.2 Existing components — modifications

| File | Change |
|---|---|
| `ResultsPanel.tsx` | Replace `run:<id>` tab body with `<RunResultsView runId={id} />`. Replace run-tab title with `<RunningTabBadge />`. No other behavioral change. |
| `ResearchFlow.tsx` | Add `compact?: boolean` prop: scales SVG viewBox, hides labels at small size, disables interactivity. |
| `DagPreview.tsx` | Same `compact?: boolean` prop, same semantics. |
| `AgentChat.tsx` | Render `BrainSuggestionBanner` of kind `enrichment` inline under the user message where a `brain.enrichment` event targets it. Render mirrored suggestion messages as `Message` rows with `type:'plan'`. |
| `useWebSocket.ts` | Add a central dispatch block (parallel to the existing fast/thorough switch) routing `pipeline.step.update`, `pipeline.step.stream`, `pipeline.run.complete`, `is.finding`, `brain.*` events into `useRunStreamStore` and `chatStore`. No component subscribes to WS for these directly. |

### A.3 Component hierarchy (active run tab)

```
ResultsPanel
└── RunResultsView (runId)
    └── PanelGroup (vertical, react-resizable-panels)
        ├── Panel (top, default 65%, min 30%)
        │   └── StreamingCardList
        │       ├── BrainSuggestionBanner × N
        │       └── NodeResultCard × N  → click → NodeResultDetailModal
        ├── PanelResizeHandle
        └── Panel (bottom, default 35%, min 15%, max 60%)
            └── FlowMiniPreview  → click → FlowFullscreenOverlay (toggle)
```

### A.4 Data flow

WebSocket → `useWebSocket.ts` central dispatch → `useRunStreamStore` actions → React subscribers.

TanStack Query remains authoritative for persisted run records (History, reload, completed runs). The stream store is the live overlay. On `pipeline.run.complete`, `['pipeline-run', runId]` is invalidated and the store sets `hydratedFromServer = true`. Conflicts (same nodeId in both) resolved in favor of server record after hydration.

---

## B. State Management

### B.1 New store: `frontend/src/stores/runStreamStore.ts`

Not persisted (live-only).

```typescript
type NodeCard = {
  nodeId: string
  nodeName: string
  pluginOrTool?: string
  status: 'pending' | 'running' | 'streaming' | 'succeeded' | 'failed' | 'canceled'
  startedAt?: number      // ms epoch
  finishedAt?: number
  preview: string         // accumulating text during streaming
  output?: unknown        // final structured payload
  sources?: Array<{ url?: string; label?: string }>
  // IS-specific:
  confidence?: number
  branchId?: string
  pir?: string
}

type BrainSuggestion = {
  id: string
  kind: 'enrichment' | 'next-step' | 'strategy'
  action?: 'aggregate' | 'report' | 'presentation' | 'save-as-pipeline' | 'rerun-enriched'
  title: string
  body?: string
  payload?: Record<string, unknown>
  createdAt: number
}

type RunStream = {
  kind: 'pipeline' | 'is'
  status: 'running' | 'succeeded' | 'failed' | 'canceled'
  startedAt: number
  cardOrder: string[]                      // nodeIds in arrival order
  cards: Record<string, NodeCard>
  suggestions: BrainSuggestion[]
  dismissedSuggestionIds: Set<string>
  hydratedFromServer: boolean
}

// Store shape:
{ runsById: Record<string, RunStream> }

// Actions:
upsertCard(runId, partial: Partial<NodeCard> & { nodeId })
appendStreamChunk(runId, nodeId, chunk: string, seq: number)
setRunStatus(runId, status)
addSuggestion(runId, BrainSuggestion)
dismissSuggestion(runId, id)
hydrateFromServer(runId, serverRun)
clearRun(runId)          // called on tab close
```

### B.2 Streaming accumulation rules

- `pipeline.step.update` with `status:'running'` → `upsertCard({status:'running', startedAt})`
- `pipeline.step.stream` with `chunk` → `appendStreamChunk`; set status to `'streaming'`
- `pipeline.step.update` with terminal status → `upsertCard({status, finishedAt, output, sources})`
- Unknown `nodeId` → card created lazily; order is first-seen, never resorted
- Stream chunks coalesced via `requestAnimationFrame` batching to prevent re-render storms at 50+ tok/s

### B.3 Suggestion state

- Suggestions live in `runsById[runId].suggestions`, ordered by `createdAt`
- Dismissed ids are in-session only (not localStorage)
- `chatStore.appendBrainSuggestionAsMessage(suggestion)` mirrors each suggestion as an `assistant` Message with `type:'plan'` into `AgentChat`

### B.4 Split-pane size persistence

`layoutStore.ts` gains `runSplit: { top: number; bottom: number }` defaulting to `{ top: 65, bottom: 35 }`. One global value, not per-run.

---

## C. WebSocket Events

### C.1 Existing events leveraged (no backend change required)

| Event | Mapped action |
|---|---|
| `pipeline.step.update` | `upsertCard` lifecycle for pipeline runs |
| `pipeline.run.complete` | `setRunStatus`; invalidate TanStack Query |
| `intelligent_search.*` | IS card lifecycle (card nodeId = `call_id`) |
| `is.cycle` / `is.finding` | Per-cycle cards with confidence, pir, branchId |
| `research.fast.completed` | Emit synthetic `next-step` suggestion ("Fast results ready") |

### C.2 New backend events (proposed, additive)

| Event | Payload | Purpose |
|---|---|---|
| `pipeline.step.stream` | `{ run_id, node_id, chunk: string, seq: number }` | Token-level streaming for LLM nodes. Optional — UI degrades gracefully. |
| `brain.intent` | `{ session_id, query, intent, confidence, rationale? }` | Intent classification result. Emitted once per user query. |
| `brain.enrichment` | `{ session_id, query, suggestions: BrainSuggestion[] }` | Optional query enrichment proposals. Non-blocking. |
| `brain.suggestion` | `{ session_id, run_id, suggestion: BrainSuggestion }` | Mid- or post-run next-step suggestions. |

All new events are additive — frontend renders nothing if they don't arrive.

---

## D. Split-Pane UX

- Vertical `PanelGroup` from `react-resizable-panels`. Default: top 65 / bottom 35.
- Constraints: top min 30%, bottom min 15%, bottom max 60%.
- Drag handle: 6px, `cursor: row-resize`, hover shows accent-colored line.
- Size persists in `layoutStore.runSplit`.
- **Responsive (≤ 768px):** stacked layout — cards above, diagram in a collapsed accordion below. No `PanelGroup` on mobile.
- Keyboard: focus handle + arrow keys adjusts ±5% (built into `react-resizable-panels`).

---

## E. Flow Diagram Toggle Interaction

**Mini preview (bottom pane):** click → opens fullscreen overlay.

**Fullscreen overlay:**
- Click the diagram body → returns to split-pane (collapses overlay).
- Click "⊡ Collapse" button in header → same.
- Press Escape → same.
- The gesture is a **toggle**: mini preview click = expand; any click in fullscreen = collapse.
- Visual cue: `cursor: zoom-out` on the fullscreen diagram body; tooltip "Click to return to split view".
- The fullscreen overlay is implemented as a Radix Dialog (not Sheet, not a page transition) so it layers over the entire app without disrupting URL or tab state.
- The mini preview continues to receive live WS updates while the fullscreen is open (same data source — no duplication).

---

## F. Intent Analysis + Brain Suggestions

### F.1 Where classification runs

Backend only (`app/services/brain_intent.py`). Frontend has an 800ms heuristic fallback: if `brain.intent` doesn't arrive, show a neutral "Analyzing…" chip and proceed without blocking the pipeline.

### F.2 Intent taxonomy (frozen contract between backend and frontend)

| Intent | Trigger patterns | Default strategy |
|---|---|---|
| `list` | "list X", "who are all", "what are all" | Wide breadth, parallel sources, aggregate at end |
| `lookup` | "what is", "find", "look up" | Single high-quality source, fast path |
| `comparison` | "X vs Y", "differences between" | Parallel lookups + structured diff |
| `deep` | "investigate", "research thoroughly" | Full IS brain cycle |
| `monitoring` | "track", "alert when", "watch" | Create monitor + initial baseline |

New intents require updating both `brain_intent.py` and `BrainSuggestionBanner.tsx`.

### F.3 Rendering

- Suggestions render as `BrainSuggestionBanner` at the top of `StreamingCardList`, above the first card.
- Banner has a primary CTA and `×` dismiss button.
- Dismissal is per-run, in-session.
- Each suggestion is mirrored to `AgentChat` as an `assistant` message (`type:'plan'`).

### F.4 Backend endpoints (new, under `/v3/brain/`)

- `POST /v3/brain/aggregate` — body `{ run_id }` → merged ranked summary
- `POST /v3/brain/report` — body `{ run_id, format: 'md' | 'docx' }` → document
- `POST /v3/brain/presentation` — body `{ run_id }` → slide structure JSON
- `POST /v3/brain/save-as-pipeline` — body `{ run_id, name }` → reusable pipeline

---

## G. Query Enrichment Flow

1. User submits query in `AgentChat`.
2. Backend emits `brain.intent` → frontend shows intent chip on the user's message bubble.
3. Backend emits `brain.enrichment` (optional) → `BrainSuggestionBanner` of kind `enrichment` renders inline in `AgentChat` below the user message (not in the results pane).
4. Banner: "Did you mean: '<enriched query>'?" with `Use enriched` / `Keep original` / `Dismiss`.
5. `Use enriched` → `POST /v3/chat/send` with `{ query: enrichedQuery, supersedes: messageId }`, cancels original run.
6. `Keep original` or no action within 4s → pipeline proceeds with original query unchanged.

Enrichment is strictly non-blocking. The pipeline never waits for the user to decide.

---

## H. Result Detail Modal

- Component: `NodeResultDetailModal.tsx` using Radix Dialog (centered, not Sheet).
- Rationale: existing right-side `ResultDrawer.tsx` already occupies the Sheet slot for whole-run drilldown.
- If `Dialog` wrapper missing from `components/ui/`, add `dialog.tsx` mirroring `sheet.tsx` patterns.

### Tab structure

| Tab | Content |
|---|---|
| Raw Output | Pretty-printed JSON of `output`. Copy button. |
| Formatted | Markdown render for text; table for tabular; JSON fallback. |
| Sources | `sources[]` list: favicon, label, URL, copy per row. |

### IS vs non-IS differences

- IS findings: header shows `confidence` (0–1 as colored bar via `GradeBar.tsx`), `pir`, `branchId`. Branch tab added between Formatted and Sources showing parent cycle → current cycle lineage.
- Non-IS: no confidence/branch tabs.
- Gate: `card.confidence !== undefined || card.pir` → IS variant.

---

## I. Dynamic Node Injection

The pipeline graph is **live and open-ended**. While a run is active, new nodes can be injected by two entry points:

### I.1 Sources of injection

**1. Chat input during a run**
The chat input in `AgentChat` remains active while a run is in progress. A new user message sent while a run is running is treated as an **instruction injection**: the backend spawns additional nodes (or a sub-pipeline) connected to the in-progress run, emitting a `pipeline.node.injected` event. The frontend receives this and appends the new card to `cardOrder` with status `pending`. The DAG updates to show the new node wired in.

**2. Brain suggestion click**
Brain suggestions rendered in `BrainSuggestionBanner` that have an `action` of type `inject` carry a `payload.nodeSpec` describing the node to add. Clicking the primary CTA fires `POST /v3/runs/{runId}/inject` with the nodeSpec. The backend wires the node into the running graph and emits `pipeline.node.injected`. The banner transitions to a "queued" visual state (dimmed, spinner) until the new node's first `pipeline.step.update` event arrives.

### I.2 New WebSocket events

| Event | Payload | Meaning |
|---|---|---|
| `pipeline.node.injected` | `{ run_id, node_id, node_name, injected_by: 'chat'\|'suggestion', after_node_id?: string }` | A new node has been wired into the running graph. Frontend appends a `pending` card and re-renders the DAG edge set. |
| `pipeline.node.injection_failed` | `{ run_id, node_id, reason }` | Injection was rejected (e.g., run already completed). Frontend shows an inline error on the banner. |

### I.3 DAG updates on injection

`DagPreview` and `ResearchFlow` currently render a static edge set derived from `PipelineEdgeOut[]`. For dynamic runs, the edge set must be reactive:

- `runStreamStore` gains an `edges: Array<{ from: string; to: string; kind: 'result'|'injected' }>` field per run.
- On `pipeline.node.injected`, append the new edge(s). Injected edges are rendered with a **dashed violet stroke** to distinguish them from the original pipeline edges.
- Both `DagPreview` and `ResearchFlow` accept `extraEdges?: Edge[]` prop used only in compact/fullscreen modes driven by live run state. Static (builder) usage is unaffected.

### I.4 Chat input state during injection

- The chat input shows a subtle indicator while a run is active: a small pulsing border or "Pipeline running — your message will inject a node" tooltip.
- Submitting a message during a run does **not** cancel the run — it appends to it.
- If the user explicitly wants to cancel and restart, they use the existing cancel button in the run tab header (unchanged behavior).
- Multiple injections are queued server-side; `cardOrder` grows in arrival order.

### I.5 Suggestion banner state transitions

```
[active]  → user clicks CTA            → [queued: spinner]
[queued]  → pipeline.node.injected     → [banner disappears, card appears in results pane]
[queued]  → pipeline.node.injection_failed → [banner shows inline error, retry CTA]
[active]  → user dismisses             → [gone for this session]
```

### I.6 Backend injection endpoint

`POST /v3/runs/{runId}/inject`
Body: `{ node_spec: { type, config }, instruction?: string, after_node_id?: string }`
- `node_spec`: a pipeline node definition (same schema as `PipelineNodeOut`)
- `instruction`: free-text instruction from chat, used when the source is a chat message
- `after_node_id`: optional — if absent, backend decides where to wire it

Returns: `{ node_id, status: 'queued' }` immediately; result streams via WS.

---

## J. Performance & Edge Cases

| Scenario | Handling |
|---|---|
| 50+ node results | Simple "show last 30 + collapsed older section" — no premature virtualization. Cards are `React.memo` with `(nodeId, status, preview.length)` comparator. |
| Injected nodes on reconnect | `GET /v3/pipelines/runs/{runId}` backfill includes injected nodes and edges; `hydratedFromServer = true` reconciles store. |
| Very fast run (all events before mount) | Central dispatcher populates store before `RunResultsView` mounts. First render shows complete state. |
| Injection while run completes | If `pipeline.run.complete` arrives before `pipeline.node.injected`, injection is rejected server-side; frontend shows error on queued banner. |
| Multiple simultaneous injections | Each gets its own `node_id`. `cardOrder` appends in arrival order. |
| Cancellation mid-stream | `pipeline.run.complete` with `status:'canceled'` → all `running`/`streaming`/`pending` injected cards → gray `canceled` variant. |
| Node failure (injected or original) | `pipeline.step.update` with `status:'failed'` → red border card, error in modal Raw tab. |
| Empty runs | Single placeholder card "No node events received" + static DAG in mini preview. |
| Tab close | `clearRun(runId)` called in existing tab-close handler in `ResultsPanel.tsx`. |
| Memory | `clearRun` prevents unbounded store growth. |
