# Loading UX Layer + Scale-Out Path

Companion to `system-design-decisions.md`. Re-anchors the design on **2–3 concurrent users** as the steady-state target (matching hardware + subscription capacity), then specifies the loading-UI patterns that let the product *feel* responsive even when individual operations are slow, and sketches the K8s scale-out path for when 2–3 concurrent stops being enough.

---

## 1. The new anchor — 2–3 concurrent users

The earlier 10-user analysis remains valid as a *worst-case* document for what would have to change. The design center is now **2–3 concurrent runs**, which has these consequences:

- **Hardware fits without juggling.** Legion 5 hosts 2 brain workers comfortably (5–6 GB of the ~11 GB WSL2 budget).
- **Subscription quota fits without throttling.** Pro plan tolerates 2–3 concurrent reliably; no API-key acrobatics.
- **No async-only UX required.** A user starting a run can *watch it progress live* instead of being told to leave and come back. This is qualitatively different from the 10-user world.
- **Queueing is exceptional, not normal.** At 2-slot capacity with 2–3 active users, queue depth is 0 almost always. A user *occasionally* sees "queued for 5 min." That's fine.
- **Caching still matters** — but for *latency* and *cost*, not for stretching capacity.

**Scale-out happens when:** sustained queue depth >2 for >1 hour, OR consistent 4+ active users. Path is K8s (Section 8). Until then, hardware is enough.

---

## 2. Loading-UX principles (the rules)

Five rules, in order of precedence. Earlier ones beat later ones when they conflict.

1. **Never show a blank canvas.** Every screen has a structural shell from t=0. Data slots in.
2. **Don't flash.** A loading state shown for <250 ms is a bug, not a feature. Use a 200 ms debounce before showing any spinner/skeleton.
3. **Preserve what you have.** Stale-while-revalidate by default. The previous answer stays on screen while the new one fetches.
4. **Show structure, then content, then polish.** Layout → skeleton → real text → animations. Never the reverse.
5. **Make slow operations narratable.** If something takes >2 s, tell the user *what* is happening, not just *that* it's happening.

The rest of the doc operationalizes these.

---

## 3. The five loading patterns

Pick by what you know about the data shape and arrival time. **There is no universal loading component;** the right answer depends on whether you know the shape of what's coming.

### 3.1 Skeleton screens
**Use when:** the data has a known shape (list of N rows, card grid, table), and you don't yet have the data.

**Properties:**
- Renders the *layout* of the eventual content (right number of rows, right column widths, right card sizes).
- Uses subtle pulse animation; not a spinner.
- Prevents cumulative layout shift (CLS) when real data arrives.
- Replaceable item-by-item if items stream in.

**Implementation note:** Library-of-record is `shadcn/ui` `<Skeleton />`. Wrap it in domain components — `<FindingRowSkeleton />`, `<HypothesisCardSkeleton />` — so the shapes match real components exactly.

### 3.2 Optimistic UI
**Use when:** the user-initiated action's expected result is predictable (annotation save, hypothesis status flip, mode change).

**Properties:**
- Apply the change to local UI state *before* the server responds.
- React Query mutation `onMutate` writes the cache; `onError` rolls back.
- Show a subtle "saving…" indicator (not a blocking modal).
- On failure, show inline error + retry button at the affected element.

**Implementation:** React Query's `useMutation` with `onMutate` + `onSettled`. Already partially in use in `ResultDrawer.tsx` for annotations.

### 3.3 Progressive disclosure
**Use when:** different parts of a screen come from different queries with different latencies.

**Properties:**
- Each section has its own loading state.
- Fast sections render immediately with real data; slow sections render skeleton; very slow sections render lazy/on-demand.
- No global page spinner.

**Example: Dashboard.**
- History list (fast, indexed): <100 ms — renders real data
- G cost aggregate (medium, cached): <300 ms — renders real data, no skeleton
- B entity knowledge (slow, depends on query): show skeleton + search hint until user types
- H open-questions (medium): skeleton while loading, then real list
- Active run indicator (live): WebSocket-driven, always fresh

### 3.4 Streaming UI
**Use when:** the result arrives in pieces — turn-by-turn brain output, LLM-generated headlines, run progress.

**Properties:**
- Output appears as it arrives (token-by-token for LLM text, item-by-item for lists).
- A phase indicator shows *what step* is in progress.
- The shell is rendered immediately; content fills in.
- A persistent permalink exists from the first render — the user can close the tab and come back to the same URL.

**Implementation:** Server-Sent Events from FastAPI for run progress (already partially supported via Temporal queries). WebSocket for bidirectional needs (mostly: queue position).

### 3.5 Suspense boundaries
**Use when:** a section can't render without specific data, and that data is critical to the screen's purpose.

**Properties:**
- React Suspense wraps the section.
- Fallback is a skeleton (Rule 1) — never a spinner or text.
- Boundaries are at the *section* level, not the page level.

**Example:** the Turns tab in the Run drawer is wrapped in Suspense; its fallback is `<TurnsTabSkeleton />`. The drawer itself is *not* Suspense-wrapped — it opens immediately with header and tab strip visible.

---

## 4. The status states (in addition to loading)

A loading state is one of *five* states every data view should handle. Designs that only think about loading vs loaded ship empty-page bugs.

| State | When | What to show |
|---|---|---|
| **Loading** | Initial fetch, no previous data | Skeleton matching the eventual shape |
| **Refreshing** | Refetch in background, have previous data | Previous data + subtle pulse on whatever's updating |
| **Empty** | Query succeeded, returned zero items | Informative empty state with a hint ("No annotations yet — add one from the Turns tab") |
| **Partial** | Some queries on the page succeeded, others failed or timed out | Show what worked; small inline error in the failed section |
| **Error** | Critical fetch failed | Specific error + retry button. Never a generic "Something went wrong." |

The two most-missed states are **Empty** (designers test with real data and forget the first-use case) and **Partial** (engineers test happy path and never test "G timed out while H loaded fine").

---

## 5. Surface-by-surface plan

What changes on each significant surface, in priority order.

### 5.1 Dashboard
Currently: most widgets render with React Query, some show "loading…" text.

| Widget | Current | Target |
|---|---|---|
| History list | basic | Skeleton row grid (6 rows × 4 cols), stale-while-revalidate |
| G — cost aggregate (7d) | renders or empty | Skeleton card → real numbers; empty state for new users ("No runs yet — start one →") |
| H — open questions | renders or empty | Skeleton list (3 items) → real; empty: "No open questions across recent runs" |
| B — entity knowledge | live-typed | Search input is always interactive; results below show skeleton on type, empty state ("Search for an entity") on focus, results when ready |
| Active run banner | conditional | Always-mounted slot. Renders nothing if no active run. Renders progress card the moment a run starts (no flash). |

### 5.2 Research submit screen
The single most important loading surface. The user is about to commit cost; the UI must justify it confidently.

```
┌────────────────────────────────────────────────┐
│  Subject: [____________________________________│
│  Mode:    [▼ KYC / EDD                       ] │
│                                                │
│  Cost estimate:    ▒▒▒▒▒  →  $1.20             │
│  Duration:         ▒▒▒▒▒  →  ~12 min           │
│  Queue position:   ▒▒▒    →  #1 (no wait)      │
│                                                │
│  [ Submit ]   [ Cancel ]                       │
└────────────────────────────────────────────────┘
```

- Estimate fields are skeleton until the cost-preview API returns (typically <500 ms).
- Submit button is disabled while estimates are loading.
- If estimate fetch fails, fields render "—" with a small inline retry.

### 5.3 Run in progress (the streaming surface)

This is where the new anchor pays off. At 2–3 concurrent, the user *watches* the run.

```
┌────────────────────────────────────────────────┐
│  ⏱  Running · Phase: EXPLORE · Turn 3 of ~6   │
│  ─────────────────────────────────────────────│
│  ✓ Turn 1: Decomposed question (4s)            │
│  ✓ Turn 2: 3 candidate hypotheses formed (18s) │
│  ▸ Turn 3: Testing hypothesis A...             │
│     • run_sec_lookup ✓                         │
│     • run_world_check ✓                        │
│     • run_news_search · running                │
│  ▒  Turn 4: queued                             │
│  ▒  Turn 5: queued                             │
│                                                │
│  Open this in background ▸                     │
└────────────────────────────────────────────────┘
```

- SSE stream from `/v3/runs/{id}/events` pushes turn events.
- Each turn renders as it starts (skeleton) then fills in tool calls live.
- Phase indicator updates on phase transition.
- "Open in background" button drops to dashboard; run continues; notification fires on completion.

### 5.4 Run drawer
Currently: tabs load on click; some tabs have visible "loading" text.

| Tab | Target |
|---|---|
| Findings | Skeleton list (5 rows) → real; empty: "No findings — run still in progress" |
| Hypotheses | Skeleton cards → real; status-grouped (open/supported/refuted) |
| Turns | Skeleton turn rows → real; expand-on-click loads full turn detail with own skeleton |
| Working Memory | Skeleton JSON tree → real; not lazy-loaded — small enough to ship in initial fetch |
| Annotations | Skeleton 2 rows → real; empty: input + "Add the first annotation" hint |
| ACH Matrix | Skeleton grid → real; empty: "No competing hypotheses" |
| Audit (when shipped) | Skeleton verdict cards → real; empty: "Audit pending" |

### 5.5 B / PKG entity view (when v2 ships)
This view is the single most performance-sensitive surface — users will hit it constantly.

- Search input mounted instantly; debounced 250 ms; no skeleton until query length ≥2.
- Below input: when results loading, skeleton with the right number of fact rows (pulled from a count query that returns in <50 ms).
- Each fact row: source class badge, confidence bar, temporal range. Skeletons preserve these slots so layout doesn't shift.
- Time-travel selector (date picker) mounts immediately; defaults to "now"; switching dates re-fetches with stale-while-revalidate (previous date stays visible, pulses while next loads).

### 5.6 Modes picker
- 4-card grid with Mode name, short description, icon.
- Loaded from `/v3/modes` (cached in localStorage; refetch on app load).
- Skeleton 4 cards on first ever visit; immediate render on subsequent visits.
- Selecting a Mode applies optimistically; reverts on error with toast.

### 5.7 Settings (BYOK + notifications + budget)
- Per-field skeletons during fetch.
- Optimistic save on each field change with 1 s debounce.
- Inline validation; no full-form submit.

---

## 6. Anti-patterns to ban

Audit existing code against these. Each is a real failure mode in shipped products.

1. **The page-level spinner.** Replaces the entire screen with a centered loader. Hides what's already loaded; blocks all interaction. Replace with section-level skeletons.
2. **The 50 ms spinner flash.** Spinner appears, immediately disappears. Looks like the page is glitching. Fix with 200 ms debounce.
3. **Layout shift on data arrival.** Skeleton row is 40 px; real row is 60 px. Page jumps when data loads. Fix by measuring real components and matching skeleton heights exactly.
4. **The "Loading…" text label.** Tells nothing. Worse than a skeleton. Banned.
5. **Empty state = blank.** Query returned [] and we render nothing. User thinks the app is broken. Always render an empty state with a hint.
6. **Generic error.** "Something went wrong" with no recovery. Errors must name what failed and provide retry.
7. **Skeleton that doesn't match the real component.** Skeleton shows 3 columns; real component has 4. Pure noise. Fix by deriving skeletons from real components, not approximating.
8. **Blocking spinner on optimistic actions.** Annotation save spins for 800 ms before the new annotation appears. Use optimistic UI instead.
9. **Cancelled requests still showing loading.** User navigates away mid-fetch; React Query keeps showing loading on the next visit. Use proper query keys + `staleTime`.
10. **Loading state for a 50 ms cache hit.** Always shows skeleton even when data is fresh in cache. Use `keepPreviousData` + `staleTime` so cache hits render instantly.

---

## 7. Tech recipes

Concrete code shapes that pair with the patterns. Stack assumptions: React + Vite + React Query + shadcn/ui.

### 7.1 Stale-while-revalidate as default
Global React Query config:

```ts
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,          // 30 s — most queries can be a little stale
      gcTime: 5 * 60_000,         // 5 min before unmounted queries gc'd
      refetchOnWindowFocus: false,
      retry: (failureCount, err) => {
        // Don't retry 4xx, do retry transient 5xx up to 2 times
        if (err.status >= 400 && err.status < 500) return false
        return failureCount < 2
      },
    },
  },
})
```

### 7.2 Debounced loading state hook
Prevents <250 ms flashes:

```ts
export function useDebouncedLoading(isLoading: boolean, delay = 250) {
  const [show, setShow] = useState(false)
  useEffect(() => {
    if (!isLoading) { setShow(false); return }
    const t = setTimeout(() => setShow(true), delay)
    return () => clearTimeout(t)
  }, [isLoading, delay])
  return show
}
```

Usage:
```tsx
const { data, isLoading } = useQuery(...)
const showSkeleton = useDebouncedLoading(isLoading)
return showSkeleton ? <FindingRowsSkeleton /> : <FindingRows data={data} />
```

### 7.3 Domain skeleton components
Pair each real component with a skeleton sibling in the same file:

```tsx
// findings/FindingRow.tsx
export function FindingRow({ finding }: { finding: Finding }) { … }

export function FindingRowSkeleton() {
  return (
    <div className="flex gap-2 py-2 h-[60px]">   {/* match real height */}
      <Skeleton className="w-12 h-4" />
      <Skeleton className="flex-1 h-4" />
      <Skeleton className="w-16 h-4" />
    </div>
  )
}
```

Pin the height to the real component's height. Use Storybook or a visual diff to verify.

### 7.4 Optimistic mutation pattern
```ts
const annotationMutation = useMutation({
  mutationFn: upsertAnnotation,
  onMutate: async (next) => {
    await queryClient.cancelQueries(['annotations', runId])
    const previous = queryClient.getQueryData(['annotations', runId])
    queryClient.setQueryData(['annotations', runId], (old) => [...old, next])
    return { previous }
  },
  onError: (err, _next, ctx) => {
    queryClient.setQueryData(['annotations', runId], ctx.previous)
    toast.error(`Save failed: ${err.message}`)
  },
  onSettled: () => queryClient.invalidateQueries(['annotations', runId]),
})
```

### 7.5 SSE for run progress
```ts
export function useRunEvents(runId: string) {
  const [events, setEvents] = useState<RunEvent[]>([])
  useEffect(() => {
    const es = new EventSource(`/v3/runs/${runId}/events`)
    es.onmessage = (e) => setEvents(prev => [...prev, JSON.parse(e.data)])
    es.onerror = () => es.close()
    return () => es.close()
  }, [runId])
  return events
}
```

Backend: FastAPI streaming response from a Temporal workflow query, polled at 500 ms.

### 7.6 Suspense boundary for a tab
```tsx
<Tabs.Content value="turns">
  <Suspense fallback={<TurnsTabSkeleton />}>
    <TurnsTab runId={runId} />
  </Suspense>
</Tabs.Content>
```

`TurnsTab` uses React Query's `useSuspenseQuery` so Suspense suspends until data resolves.

### 7.7 Empty state component
A single reusable shape:

```tsx
<EmptyState
  icon={<FileQuestion />}
  title="No findings yet"
  hint="The brain is still working. Findings appear here as they're produced."
  action={null}
/>
```

Forces every empty state to have a title and hint. Action optional.

---

## 8. Scale-out path — K8s when 2–3 concurrent stops being enough

Serverless ruled out for the brain worker (long-running subprocess + persistent OAuth state). The scale-out target is **K8s** when capacity demands it. Sketch — not a build-now plan.

### 8.1 When K8s is justified
- Sustained queue depth >2 for >1 hour
- Concurrent active users consistently ≥4
- A second tenant arrives (multi-tenant isolation requirement)
- Compliance ask requires audited managed infra

Until then: home + (optional) Hetzner CX22 are sufficient and cheaper than K8s management overhead.

### 8.2 Target shape

| Component | K8s mapping |
|---|---|
| FastAPI | `Deployment`, 2 replicas, `HorizontalPodAutoscaler` on CPU |
| Brain workers | `Deployment` per Mode, `HorizontalPodAutoscaler` on Temporal queue depth (via custom metrics adapter) |
| Postgres | `CloudNativePG` operator OR managed (Cloud SQL / Neon) |
| Qdrant | `StatefulSet` with PVCs OR Qdrant Cloud |
| Temporal | Temporal Cloud (don't self-host at this scale) |
| Redis | `Deployment`, single replica, persistent volume |
| MCP server | Sidecar in brain pod (per-pod lifecycle) |
| Frontend | Cloudflare Pages (unchanged) |
| Tunnel | `cloudflared` `Deployment` with 2 replicas for HA |
| Secrets | External Secrets Operator → Cloudflare or GCP Secret Manager |
| Observability | Prometheus + Grafana + Loki on the cluster, OR Grafana Cloud |

### 8.3 Cluster options (in cost order)

| Option | Cost (low) | Cost (10-user load) | Operational burden |
|---|---:|---:|---|
| k3s on a single 32 GB VPS (Hetzner CCX23, Vultr, etc.) | $30/mo | $30/mo | Medium — single node, no HA |
| Hetzner Cloud + k3s multi-node | $50–100/mo | $50–100/mo | Medium-high |
| **GKE Autopilot** | ~$200/mo idle | $400–600/mo at load | Low — fully managed |
| EKS Fargate | $300/mo + per-pod | $600–800/mo | Medium |
| DigitalOcean Kubernetes | $100/mo | $200–400/mo | Low-medium |

**Honest recommendation at scale-out trigger:**

1. **First step out of home: k3s on a single Hetzner CCX23 (8 vCPU / 32 GB, ~$30/mo).** Multi-node when one box isn't enough. Maintain via `k3sup`. ~1 day of setup; runs the whole stack except managed Postgres (Neon $19/mo) and Temporal Cloud ($100/mo). Total ~$150/mo for materially better capacity than home.
2. **Promote to GKE Autopilot** only when reliability becomes a customer-facing SLO or compliance demands managed infra.

### 8.4 What needs to be K8s-ready in the app

- **All config from env.** Already mostly true; audit before move.
- **No local-filesystem state** outside of clearly persistent volumes. Brain worker writes nothing important to local disk; verify.
- **Graceful shutdown.** SIGTERM → drain current turn → exit. Already in the plan.
- **Health endpoints.** `/healthz` (liveness) + `/readyz` (readiness, checks DB connection). API + workers both.
- **Structured logs to stdout.** Already true.
- **Image build per service.** Multi-stage Dockerfiles. Already true.
- **Helm chart or Kustomize overlay.** When the move happens, the artifact.

This is ~2 days of cleanup, not a refactor. Worth doing *whenever* a Cloud migration becomes likely.

---

## 9. Build sequence for the loading-UX work

Sequenced so each step delivers visible improvement on its own.

### Phase 1 — Foundations (~1 day)
1. Add `useDebouncedLoading` hook + default React Query config.
2. Define a `<Skeleton>` design system primitive (already present via shadcn).
3. Define `<EmptyState>` and `<InlineError>` shared components.
4. Adopt the five-state pattern (Loading / Refreshing / Empty / Partial / Error) in a coding-standard doc.

### Phase 2 — Dashboard surfaces (~1 day)
5. Skeleton each dashboard widget; ensure layout matches real component.
6. Empty states for G, H, B widgets.
7. Stale-while-revalidate verified on each (no flash on cache hits).

### Phase 3 — Research + Run progress (~1.5 days)
8. Cost-preview skeleton on submit screen.
9. SSE endpoint + `useRunEvents` hook.
10. Run-in-progress live UI (phase, turns, tool calls streaming in).
11. Permalink + "open in background" affordance.

### Phase 4 — Run drawer + PKG (~1 day)
12. Per-tab skeletons in `ResultDrawer.tsx`; Suspense boundaries where appropriate.
13. PKG entity view skeleton when B v2 ships (overlap with that work).

### Phase 5 — Polish (~0.5 day)
14. Audit every existing query for the five states.
15. Audit every form for optimistic mutation pattern.
16. Audit for spinner flashes <250 ms.

**Total ~4 engineer-days** for the full loading-UX layer. Independently shippable per phase.

---

## 10. Open decisions

1. **SSE vs WebSocket for run progress.** SSE is one-way + auto-reconnect + simpler; WebSocket is bidirectional but rarely needed for runs. *My pick: SSE for runs, WebSocket reserved for queue position + future collab features.*
2. **Skeleton style — pulsing vs shimmering vs static gray.** *My pick: subtle pulse, matches shadcn default.*
3. **Should completed-run notifications work via in-app toast only, or default to email too?** *My pick: email default, opt-out in settings, since users will close the tab during a 10-min run.*
4. **Permalink format for in-progress runs.** `/runs/{id}` with status changing live, or `/runs/{id}/live` separate from `/runs/{id}`? *My pick: single URL; status changes are state, not routes.*
5. **Empty-state copy ownership.** Engineering writes or product writes? *My pick: engineering ships scaffolding with placeholder copy; product reviews monthly.*
6. **Phase 5 timing — interleave with feature work or as a dedicated polish sprint?** *My pick: dedicated 1-day pass after PKG ships, since PKG will introduce new states that need patterns applied.*

---

## 11. The 30-second summary

At 2–3 concurrent users the architecture can deliver real-time UX, not async-only. The job of the loading-UX layer is to make every operation *feel* responsive even when individual fetches are slow. Five patterns (skeleton, optimistic, progressive, streaming, Suspense) cover every surface in the app; five states (loading, refreshing, empty, partial, error) must be handled per query. Banned anti-patterns: page-level spinners, sub-250 ms flashes, layout shift on data arrival, generic errors, blank empty states. Stack already supports all of this via React Query + Suspense + shadcn; ~4 engineer-days to roll out across all surfaces. The K8s scale-out path stays sketched, not built — promoted only when sustained load demands it, and the first step is k3s on a single $30/mo Hetzner box, not a hyperscaler.
