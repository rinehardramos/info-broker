# UI/UX Design Spec — Info-Broker Non-Admin Surface

**Date:** 2026-05-13
**Status:** Approved for implementation
**Audience:** Frontend engineers (Sonnet coding agent + humans)
**Scope:** All routes accessible to `analyst` and `viewer` roles. Admin-only surfaces (`AdminUsersPage`, admin sections of Settings) are out of scope.

---

## 1. Design Foundation

### 1.1 Framework

- **Component library:** shadcn/ui (copy-paste components into `frontend/src/components/ui/`).
- **Styling:** existing Tailwind + CSS variables. Do not introduce a new CSS runtime.
- **Icons:** `lucide-react` (already a shadcn dep).
- **State:** existing Zustand stores; one new store for the Result Drawer (see §4.1).
- **Forms:** native `<form>` + `useState` for the few forms in scope. No new form library.

### 1.2 Theming

- Reuse current CSS variables (`--background`, `--foreground`, `--primary`, etc.). When `shadcn init` asks, choose:
  - Style: `default`
  - Base color: `slate`
  - CSS variables: yes
  - `app/globals.css` location: `frontend/src/index.css`
  - Components alias: `@/components`
  - Utils alias: `@/lib/utils`

### 1.3 Install command

Run from `frontend/`:

```
npx shadcn@latest init
npx shadcn@latest add card badge table sheet dropdown-menu tabs dialog input button select toast separator tooltip
```

Generated files land in `frontend/src/components/ui/{card,badge,table,sheet,dropdown-menu,tabs,dialog,input,button,select,toast,separator,tooltip}.tsx`. Do **not** hand-edit these — extend via composition in `frontend/src/components/`.

### 1.4 Layout (unchanged)

- Existing right-side `IconRail` (`frontend/src/components/layout/IconRail.tsx`) remains the primary navigation. Order is updated (see §5).
- Existing `ThreeColumnLayout.tsx` continues to back the Research page only. All new pages use a single-column main with optional drawer.

### 1.5 Role enforcement

| Role | Read | Write (run / upload / pin) | Admin (users, secrets) |
|---|---|---|---|
| `viewer` | yes | no | no |
| `analyst` | yes | yes | no |
| `admin` | yes | yes | yes |

Frontend gating uses a `useRole()` hook reading from the auth store; backend remains source of truth (`require_analyst`, `require_admin` decorators). Buttons that would 403 must be **hidden** for `viewer`, not just disabled, except in Settings where "Change password" is always visible.

---

## 2. Routes

All routes mount inside `AuthGuard`. Default route after login is `/dashboard`.

| Path | Page component (new/existing) | Min role |
|---|---|---|
| `/login` | `pages/Login.tsx` (existing) | public |
| `/dashboard` | `pages/Dashboard.tsx` (new) | viewer |
| `/research` | `pages/Research.tsx` (existing) | viewer (read), analyst (run) |
| `/jobs` | `pages/Jobs.tsx` (existing) | viewer |
| `/history` | `pages/History.tsx` (rewrite stub) | viewer |
| `/logs` | `pages/Logs.tsx` (new) | viewer |
| `/reports` | `pages/Reports.tsx` (new) | viewer (read), analyst (generate) |
| `/performance` | `pages/PerformanceDashboardPage.tsx` (enhance) | viewer |
| `/assets` | `pages/Assets.tsx` (new) | viewer (read), analyst (upload / pin) |
| `/review` | `pages/Review.tsx` (new) | viewer |
| `/pipelines` | `pages/PipelinePage.tsx` (existing, light reskin) | viewer (read), analyst (write) |
| `/settings` | `pages/Settings.tsx` (enhance) | viewer (own profile) |

Update `frontend/src/App.tsx` router declarations accordingly. Remove the `Research` landing redirect; default authenticated landing is `/dashboard`.

---

## 3. Page specs

### 3.1 Login / Logout

**File:** `frontend/src/pages/Login.tsx` (existing — minor additions).

- Keep current email + password form, JWT exchange via `POST /v3/auth/login`.
- Add a disabled "Forgot password?" link under the submit button with `title="Coming soon"`. Tracked as future work; do not implement reset-email backend in this spec.
- Logout is triggered by the avatar dropdown in `IconRail` (bottom). Action: clear JWT from `localStorage.jwt`, clear auth store, `navigate('/login', { replace: true })`.

### 3.2 Dashboard — `/dashboard`

**File:** `frontend/src/pages/Dashboard.tsx` (new).

**Layout:** single column, `max-w-7xl mx-auto p-6 space-y-6`.

**Section A — Stat cards row** (4 × shadcn `Card`, grid `grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4`):

| Card | Value | Sub-label | Source |
|---|---|---|---|
| Runs Today | integer | "since 00:00 local" | `GET /v3/metrics/summary?window=today` |
| Success Rate | percent | "last 7 days" | same endpoint, key `success_rate_7d` |
| Live | integer | "currently running" | same endpoint, key `live_runs` |
| Errors | integer (red number when > 0) | "last 24 h" | same endpoint, key `errors_24h` |

Polling: SWR / `useEffect` `setInterval` every 30 s. Pause when tab is hidden (`document.visibilityState`).

**Section B — Recent runs** (shadcn `Table`):

- Source: `GET /v3/runs?limit=20&order=started_at.desc`.
- Columns: Query (truncate w/ tooltip), Type (`badge`: IS / pipeline), Status (`StatusBadge`, see §4.3), Started (relative time + absolute tooltip), Duration (`hh:mm:ss`), Actions.
- Actions cell: `[Show] [Download dropdown]` (see §4.1, §4.2). Hidden if user is viewer and the row is owned by another tenant — backend filters already, just render what API returns.
- Empty state: centered illustration text "No runs yet — start one from Research."

**Architecture hint:** Extract `<StatCard title value sub variant />` to `components/dashboard/StatCard.tsx`. Extract `<RunListTable rows actions />` to `components/runs/RunListTable.tsx` — reused by `/history`.

### 3.3 Logs — `/logs`

**File:** `frontend/src/pages/Logs.tsx` (new).

**Layout:** filter bar (sticky top), table below, paginated.

**Tabs** (shadcn `Tabs`): `All` (default) and `Errors`. The `Errors` tab pins `level=ERROR` in the query.

**Filter bar:**
- Date range (two `<input type="date">` wrapped in shadcn `Input`).
- Level multi-select (`Select`): INFO / WARN / ERROR. Disabled on Errors tab.
- Free-text search (`Input`, debounced 300 ms) — matches against `message`.

**Table columns:** Timestamp (ISO + local tooltip), Level (color-coded `Badge`), Message (truncate, expand on click), Run ID (link, opens Result Drawer for that run), Source (node name / activity).

**Pagination:** 100 rows / page, cursor-based via `?cursor=<id>`.

**Error badge (icon rail):** small red dot on the Logs icon. Counter sourced from `GET /v3/logs/unread_errors_count` (see §6) and cleared by writing `localStorage.logs_last_seen = <ISO>` on visit to `/logs`. The badge re-appears when the API returns errors with `created_at > logs_last_seen`.

**Backend requirement (new):**

```
GET /v3/logs
  query: from, to, level (csv), q, cursor, limit (default 100)
  returns { items: LogRow[], next_cursor: string|null }

GET /v3/logs/unread_errors_count?since=<iso>
  returns { count: int }

type LogRow = {
  id: string
  ts: string                // ISO 8601 UTC
  level: 'INFO'|'WARN'|'ERROR'
  message: string
  run_id: string | null
  source: string            // e.g. "node:linkedin_lookup" / "activity:export"
}
```

### 3.4 Pipelines — `/pipelines`, `/pipelines/:id`

**File:** `frontend/src/pages/PipelinePage.tsx` (existing, minimal change).

- Wrap primitive buttons / inputs in shadcn equivalents where it is a 1:1 swap; do not refactor logic.
- Add a top-of-page banner if `useRole() === 'viewer'`: "Read-only — request analyst access to edit." Hide all `Create / Edit / Delete` buttons for viewer.
- Backend already enforces `require_analyst` on mutating endpoints; the FE change is purely visual.

### 3.5 Reports — `/reports`

**File:** `frontend/src/pages/Reports.tsx` (new).

**Layout:** action bar (`Generate report` button right-aligned), then table.

**Table columns:** Run query (link, opens drawer), Format (`Badge`: CSV / XLSX / PDF), Generated at, File size (humanized), Download (button, calls `GET /v3/exports/:id/download`, browser handles file save).

**Generate report modal (shadcn `Dialog`):**
- Field 1 — Run picker (`Select`, options = last 100 completed runs, search-as-you-type using `GET /v3/runs?status=succeeded&q=`).
- Field 2 — Format picker (`Select`: CSV, XLSX, PDF). PDF is `analyst` only — hidden for viewer.
- Submit calls `POST /v3/exports` body `{ run_id, format }`. On 202 response, close modal, push toast "Generating…", refresh the list every 5 s until the export's `status === 'ready'`.

**Backend requirements (new):**

```
GET /v3/exports?limit=&cursor=
  returns { items: Export[], next_cursor: string|null }

POST /v3/exports
  body: { run_id: string, format: 'csv'|'xlsx'|'pdf' }
  returns 202 { id, status: 'pending' }

GET /v3/exports/:id
  returns Export

GET /v3/exports/:id/download
  returns binary stream + Content-Disposition

type Export = {
  id: string
  run_id: string
  run_query: string         // denormalized for list rendering
  format: 'csv'|'xlsx'|'pdf'
  status: 'pending'|'ready'|'failed'
  size_bytes: number | null
  created_at: string
  ready_at: string | null
  error: string | null
}
```

### 3.6 Metrics — `/performance`

**File:** `frontend/src/pages/PerformanceDashboardPage.tsx` + `frontend/src/components/metrics/PerformanceDashboard.tsx` (enhance).

**Sections (vertical stack):**

1. **Date range filter row** — two date inputs + "Last 7d / 30d / 90d" preset buttons (shadcn `Button` variant `outline`). Selection persists in URL `?from=&to=`.
2. **Export button** (top-right) — opens dropdown: "Export CSV", "Export XLSX". Calls `POST /v3/exports` with `kind: 'performance'` body `{ from, to, format }`. New backend kind required.
3. **Strategy Summary** — shadcn `Table`. Columns: Strategy, Runs, Avg grade (1–5, color-coded), Last used. Source: `GET /v3/metrics/strategies?from=&to=`.
4. **Tactic Summary** — same shape, source `GET /v3/metrics/tactics`. Sortable by usage and grade.
5. **Technique Summary** — same shape, source `GET /v3/metrics/techniques`. Add a "drill in" expand row that lists last 5 example run IDs (link, opens drawer).

If any of those `/v3/metrics/{strategies,tactics,techniques}` endpoints don't yet exist, add them — list as a backend requirement. Response shape:

```
type MetricRow = {
  name: string
  runs: number
  avg_grade: number          // 0–5, two decimals
  last_used: string | null   // ISO
  sample_run_ids: string[]   // only on techniques endpoint, length <= 5
}
```

### 3.7 Assets — `/assets`

**File:** `frontend/src/pages/Assets.tsx` (new).

**Layout:** Tabs (shadcn `Tabs`): `Uploaded files` (default) and `Saved outputs`.

**Tab A — Uploaded files:**

- Action bar: `Upload new file` button (`analyst` only). Clicking opens existing `FileUploadZone` (`frontend/src/components/chat/FileUploadZone.tsx`) inside a `Dialog`.
- Table columns: Filename, Type (csv/pdf/xlsx/txt), Size, Uploaded at, Indexing status (`Badge`: queued / indexing / ready / failed), Delete (`analyst` only, confirmation in `Dialog`).
- Source: `GET /v3/sources` (existing). Delete: `DELETE /v3/sources/:id`.

**Tab B — Saved outputs:**

- Table columns: Title (editable inline for analyst — click to edit), Source run (link, opens drawer), Pinned at, View (button, opens drawer for that run, jumped to the pinned finding).
- Source: `GET /v3/results/pinned`. Unpin button at row end (`analyst` only) calls `DELETE /v3/results/:run_id/pins/:finding_id`.

**Backend requirements (new):**

```
POST /v3/results/:run_id/pin
  body: { finding_id: string, title?: string }
  returns Pin

GET /v3/results/pinned?limit=&cursor=
  returns { items: Pin[], next_cursor: string|null }

DELETE /v3/results/:run_id/pins/:finding_id
  returns 204

PATCH /v3/results/:run_id/pins/:finding_id
  body: { title: string }
  returns Pin

type Pin = {
  run_id: string
  finding_id: string
  title: string
  run_query: string
  pinned_at: string
  pinned_by: string
}
```

### 3.8 History — `/history`

**File:** `frontend/src/pages/History.tsx` (rewrite stub).

**Layout:** filter bar then table. Same `RunListTable` component as Dashboard, just with full pagination and filters.

**Filter bar:**
- Date range (from/to).
- Status multi-select (running, succeeded, failed, queued).
- Type select (All / IS / Pipeline).
- Free-text search on query.

**Table columns:** Query, Type, Status, Started, Duration, Actions (`Show`, `Download dropdown`).

**Pagination:** 50 / page, cursor-based.

**Source:** `GET /v3/runs?from=&to=&status=&type=&q=&cursor=&limit=50`. The endpoint exists; verify it accepts all listed filters and extend if not.

### 3.9 Review — Datastore — `/review`

**File:** `frontend/src/pages/Review.tsx` (new).

**Layout:** two-pane (Tailwind `grid grid-cols-[280px_1fr] gap-4`).

**Left — Source list:**
- shadcn `Table` or scrollable list with each row = file. Click selects, highlights with `bg-accent`.
- Search box at top.
- Source: `GET /v3/sources`.

**Right — Data preview:**
- Header: filename, indexing status, row/chunk count, "Re-index" button (`analyst`, calls `POST /v3/sources/:id/reindex`).
- Body: paginated table of indexed rows/chunks via `POST /v3/sources/query` with `{ source_id, limit, offset, q? }`. Columns are derived from `result.columns` (datastore returns column metadata; if missing, fall back to `id`, `chunk_text`).
- Pagination: 25 rows / page.

If `POST /v3/sources/query` does not return pagination metadata today, extend it: response must include `{ rows, columns, total, limit, offset }`.

### 3.10 Settings — `/settings`

**File:** `frontend/src/pages/Settings.tsx` (enhance).

Sections (vertical, each in its own `Card`):

1. **Profile** — read-only email, role, tenant.
2. **Change password** (SOC 2 Type 2 compliant):
   - Current password (`Input type=password`, required).
   - New password (`Input type=password`) + strength indicator. Bar component derived from zxcvbn score 0–4 (install `zxcvbn-ts`). Reject submit if score < 3.
   - Confirm new password (`Input type=password`). Must match.
   - Submit calls existing `POST /v3/auth/change_password` body `{ current_password, new_password }`. On success: toast "Password updated", clear fields.
3. **Reset password** — single button "Send reset link" with `disabled` + tooltip "Coming soon". Tracked separately; do not wire backend.
4. **Theme** — existing toggle, keep.
5. **Plugin config** — existing, keep.

---

## 4. Cross-cutting components

### 4.1 Result Drawer

**File:** `frontend/src/components/runs/ResultDrawer.tsx` (new).

- Built on shadcn `Sheet`, `side="right"`. Width: `sm:max-w-[640px] lg:max-w-[50vw]`. Full-screen on `< sm` via `Sheet` defaults.
- Driven by a small Zustand store `frontend/src/stores/resultDrawerStore.ts`:

```ts
type ResultDrawerState = {
  runId: string | null
  initialTab: 'findings'|'trail'|'scorecard'|'raw'
  initialFindingId?: string
  open: (runId: string, opts?: { tab?, findingId? }) => void
  close: () => void
}
```

- Mount once in `App.tsx` so any page can open it via `useResultDrawer().open(runId)`.
- Header: run query (truncate, tooltip), `StatusBadge`, started/duration, close (`X`).
- Tabs (shadcn `Tabs`):
  - **Findings** — `GET /v3/runs/:id/findings`. Renders a card list. Each finding shows a `Pin` button (analyst only).
  - **Trail** — `GET /v3/runs/:id/trail`. Step-by-step list with timestamps and node names. Each step expandable to show inputs/outputs.
  - **Scorecard** — only present when `run.type === 'IS'`. `GET /v3/runs/:id/scorecard`.
  - **Raw** — toggle pretty/minified JSON of the full run document. `GET /v3/runs/:id?include=raw`.
- Footer: `DownloadMenu` (see §4.2).

### 4.2 Download menu

**File:** `frontend/src/components/runs/DownloadMenu.tsx` (new).

- Built on shadcn `DropdownMenu`. Trigger label: "Download" with chevron.
- Items: "Export as CSV", "Export as XLSX".
- On click: `POST /v3/exports { run_id, format }`. Show toast "Generating…". Poll `GET /v3/exports/:id` every 2 s until `status === 'ready'`, then auto-trigger download by setting `window.location.href = '/v3/exports/:id/download'`. On `failed`, toast error with the `error` message.
- Component used by: Dashboard rows, History rows, Reports rows (label "Re-download" there), Result Drawer footer.

### 4.3 Status badge

**File:** `frontend/src/components/runs/StatusBadge.tsx` (new).

- Wraps shadcn `Badge`. Variant chosen by status:
  - `running` -> amber, with a `Loader2` spin icon.
  - `succeeded` -> green, `Check`.
  - `failed` -> red, `X`.
  - `queued` -> grey, `Clock`.

### 4.4 Error badge (icon rail)

- `IconRail` gains a `useUnreadErrors()` hook (polls `GET /v3/logs/unread_errors_count?since=<localStorage.logs_last_seen>` every 60 s).
- When `count > 0`, render an 8 px red dot in the top-right of the Logs icon's tile, with `aria-label="N unread errors"`.
- Visiting `/logs` writes `localStorage.logs_last_seen = new Date().toISOString()` and immediately re-polls.

### 4.5 Role hook

**File:** `frontend/src/hooks/useRole.ts` (new if missing).

```ts
export function useRole(): 'admin'|'analyst'|'viewer' { ... }
export function useCan(action: 'run'|'upload'|'pin'|'edit_pipeline'|'generate_pdf'|'change_password'): boolean { ... }
```

Mapping:

| Action | viewer | analyst | admin |
|---|---|---|---|
| run | no | yes | yes |
| upload | no | yes | yes |
| pin | no | yes | yes |
| edit_pipeline | no | yes | yes |
| generate_pdf | no | yes | yes |
| change_password | yes | yes | yes |

---

## 5. Icon rail layout

**File:** `frontend/src/components/layout/IconRail.tsx` (modify).

Top to bottom:

| Slot | Icon (lucide) | Label / route | Notes |
|---|---|---|---|
| 0 | `BarChart2` | Dashboard `/dashboard` | new default landing |
| 1 | `Sparkles` (existing) | Research `/research` | |
| 2 | `Briefcase` (existing) | Jobs `/jobs` | |
| 3 | `FileText` | History `/history` | |
| 4 | `FileDown` | Reports `/reports` | |
| 5 | `Database` | Assets `/assets` | |
| 6 | `Search` | Review `/review` | |
| 7 | `Activity` | Metrics `/performance` | reuse existing if present |
| 8 | `GitBranch` | Pipelines `/pipelines` | reuse existing if present |
| — flex spacer — | | | |
| bottom-3 | `AlertCircle` | Logs `/logs` | red dot badge when unread errors |
| bottom-2 | `Settings` (existing) | Settings `/settings` | |
| bottom-1 | avatar | menu (Profile, Logout) | |

Each item is a `<NavLink>` with `aria-label`, tooltip on hover (shadcn `Tooltip`), and `data-active` styling when route matches.

---

## 6. Backend requirements (summary)

Endpoints flagged as new or extended in the page specs above. Owner: backend team. Required before shipping the corresponding FE page.

| Endpoint | Method | Status | Used by |
|---|---|---|---|
| `/v3/metrics/summary` | GET | new | Dashboard |
| `/v3/runs` filter set | GET | extend | Dashboard, History |
| `/v3/logs` | GET | new | Logs |
| `/v3/logs/unread_errors_count` | GET | new | IconRail, Logs |
| `/v3/exports` | GET/POST | new | Reports, DownloadMenu, Metrics export |
| `/v3/exports/:id` | GET | new | DownloadMenu polling |
| `/v3/exports/:id/download` | GET | new | DownloadMenu, Reports |
| `/v3/metrics/{strategies,tactics,techniques}` | GET | new if missing | Metrics |
| `/v3/results/pinned` | GET | new | Assets |
| `/v3/results/:run_id/pin` | POST | new | ResultDrawer (Findings tab) |
| `/v3/results/:run_id/pins/:finding_id` | PATCH/DELETE | new | Assets |
| `/v3/sources/:id/reindex` | POST | new if missing | Review |
| `/v3/sources/query` pagination | POST | extend | Review |
| `/v3/runs/:id/{findings,trail,scorecard}` | GET | confirm exists | ResultDrawer |

All endpoints inherit existing JWT auth + tenant scoping. Mutating ones use `require_analyst`.

---

## 7. Logo brief (out of scope to implement)

- **Purpose:** Replace placeholder text "info-broker" in header and favicon.
- **Style:** monochrome first; legible on dark and light. Single-color SVG, no gradients, ≤ 4 anchor groups.
- **Concepts to explore:** (1) abstract network node — three nodes connected by edges forming an arrow, (2) hexagonal grid fragment evoking data lattice, (3) stylised `ib` monogram with the dot of the `i` doubling as a "node".
- **Render targets:** 16 × 16 favicon, 32 × 32 app icon, 200 × 60 header lockup. SVG primary, PNG fallbacks generated by build.
- **Deliverable:** Figma file + exported assets in `frontend/public/brand/`. Implementation tracked in a separate ticket.

---

## 8. Architecture notes for the implementer

1. **Drop in shadcn first.** Run the init + add commands before touching pages — every new page consumes those components.
2. **Build cross-cutting components in this order:** `StatusBadge` -> `DownloadMenu` -> `ResultDrawer` (+ store) -> `RunListTable` (consumes the previous three) -> `useRole` / `useCan`. Pages that follow are thin compositions of these.
3. **Default landing.** Update `App.tsx` so `/` redirects to `/dashboard` for authenticated users (and `/login` otherwise). Remove any redirect to `/research`.
4. **Drawer over navigation.** Always prefer opening the `ResultDrawer` over navigating to a run-detail page; there is no run-detail page in this spec.
5. **Polling cadence.** Dashboard summary 30 s; error count 60 s; export status 2 s while pending. Pause all polls on `document.hidden`.
6. **Empty states.** Every table renders a centered `Text` block when `items.length === 0` — do not show an empty `<tbody>`.
7. **Accessibility.** All icon-only buttons need `aria-label`. All `Tabs`, `Sheet`, `Dialog` come a11y-correct from shadcn; do not remove `sr-only` labels.
8. **Toasts.** Single `<Toaster />` mounted in `App.tsx`. Use `toast()` from `@/components/ui/use-toast` everywhere — never `alert()`, never bespoke banner components.
9. **State stores.** New: `resultDrawerStore` (Zustand). Existing `chatStore`, auth store stay untouched.
10. **Tests.** Each new page gets a Playwright smoke test under `frontend/tests/e2e/`: load page as analyst, assert primary action visible; load as viewer, assert action hidden. Per global rule: do not mark this work done without the E2E suite green.

---

## 9. Acceptance criteria

- [ ] shadcn initialized; all listed components present under `frontend/src/components/ui/`.
- [ ] All 10 pages routable, render without console errors as both analyst and viewer.
- [ ] `IconRail` shows all 11 slots in the documented order, with badge behaviour on `/logs`.
- [ ] `ResultDrawer` opens from Dashboard, History, Reports, Logs (Run ID link), and Assets (Saved outputs view).
- [ ] `DownloadMenu` produces a working CSV and XLSX file from a succeeded run.
- [ ] Change-password flow rejects zxcvbn scores < 3 and succeeds with the existing endpoint.
- [ ] Viewer role sees no Upload/Edit/Delete/Generate-PDF buttons anywhere.
- [ ] All backend requirements in §6 have GitHub issues opened (per global lesson `feedback_create_tickets_before_fixing.md`).
- [ ] Playwright E2E suite green for every new page (per `feedback_e2e_before_done.md`).

---

## 10. Test plan

1. **Unit (Vitest):** `StatusBadge` variant mapping; `useCan` matrix; `DownloadMenu` polls + downloads on `ready`.
2. **Component (Vitest + RTL):** `RunListTable` renders columns and actions correctly per role.
3. **E2E (Playwright):**
   - Login as analyst -> land on `/dashboard` -> stat cards render.
   - Open a row's `Show` -> drawer opens with Findings tab.
   - Click `Download` -> Export as CSV -> toast -> file downloaded (assert `Content-Disposition`).
   - Visit `/logs` -> red dot on icon rail disappears; revisit Dashboard -> still no dot.
   - Login as viewer -> no Upload button on `/assets`, no Generate Report button on `/reports`, password-change form still visible.
   - Settings: weak password rejected; strong password accepted; current-password mismatch returns 401 surfaced as toast.
4. **Manual (one pass):** dark and light theme; mobile width 375 px; keyboard-only navigation across icon rail and drawer.
