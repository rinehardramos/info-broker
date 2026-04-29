# Pipeline Runs in LiveStream + Results Panel

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Show running and completed pipeline runs in the Research page LiveStream (right column); clicking a completed run opens a step-by-step results view in the ResultsPanel (left column), with live updates via WebSocket while the run is active.

**Architecture:** (1) A new backend endpoint `GET /v3/pipelines/runs/all` returns all pipeline runs for the user with pipeline name included. (2) `col1Content` in Zustand sessionStore gains a second content type: `{ type: 'pipeline_run'; runId: string }`. (3) LiveStream gains a "Pipelines" section that polls the new endpoint and listens to `pipeline.step.update` / `pipeline.run.complete` WebSocket events. (4) ResultsPanel branches on `col1Content.type` — when `pipeline_run`, it fetches `getPipelineRun(runId)` and renders a step-by-step breakdown with status dots, item counts, and error messages. Polling stops when the run reaches a terminal status.

**Tech Stack:** Python 3.11, FastAPI, psycopg2, React 18, TypeScript, React Query, Zustand.

---

## Task 1: Backend — `GET /v3/pipelines/runs/all` Endpoint

Returns all pipeline runs for the authenticated user across all pipelines, newest first. Joins `pipelines` table to include the pipeline name (needed for the LiveStream display).

**Files:**
- Modify: `app/routers/v3/pipelines.py`
- Modify: `app/routers/v3/models.py`

---

- [ ] **Step 1: Add `PipelineRunSummaryOut` model to models.py**

In `app/routers/v3/models.py`, add this model after `PipelineRunOut`:

```python
class PipelineRunSummaryOut(BaseModel):
    id: UUID
    pipeline_id: UUID
    pipeline_name: str
    status: str
    trigger_type: str
    started_at: datetime
    finished_at: datetime | None
    step_count: int
    steps_done: int
```

- [ ] **Step 2: Add the endpoint to pipelines.py**

In `app/routers/v3/pipelines.py`, add this endpoint **before** the `GET /runs/{run_id}` route (keep it in the non-parametric section):

```python
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
```

Also add the import of `PipelineRunSummaryOut` in the models import block at the top of `pipelines.py`:

```python
from app.routers.v3.models import (
    NodeTypeOut,
    PipelineDetailOut,
    PipelineEdgeOut,
    PipelineIn,
    PipelineNodeOut,
    PipelineOut,
    PipelineRunDetailOut,
    PipelineRunOut,
    PipelineRunSummaryOut,   # add this
    PipelineStepRunOut,
)
```

- [ ] **Step 3: Rebuild and verify**

```bash
docker compose up --build -d info-broker-api
sleep 5

TOKEN=$(curl -s -X POST http://localhost:8000/v3/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:8000/v3/pipelines/runs/all \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK, runs:', len(d))"
```

Expected: `OK, runs: <N>` (0 or more, no error).

- [ ] **Step 4: Commit**

```bash
git add app/routers/v3/models.py app/routers/v3/pipelines.py
git commit -m "feat(pipeline): add GET /v3/pipelines/runs/all endpoint with pipeline name and step counts"
```

---

## Task 2: Frontend API — `listAllPipelineRuns` Function

**Files:**
- Modify: `frontend/src/api/pipelines.ts`

---

- [ ] **Step 1: Add `PipelineRunSummary` type and API function**

In `frontend/src/api/pipelines.ts`, add the type and function:

```typescript
export interface PipelineRunSummary {
  id: string
  pipeline_id: string
  pipeline_name: string
  status: string
  trigger_type: string
  started_at: string
  finished_at: string | null
  step_count: number
  steps_done: number
}

export const listAllPipelineRuns = (): Promise<PipelineRunSummary[]> =>
  api.get('/v3/pipelines/runs/all').then(r => r.data)
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/pipelines.ts
git commit -m "feat(pipeline): add listAllPipelineRuns API function"
```

---

## Task 3: Extend SessionStore — Pipeline Run Content Type

**Files:**
- Modify: `frontend/src/stores/sessionStore.ts`

---

- [ ] **Step 1: Extend `col1Content` union type**

In `frontend/src/stores/sessionStore.ts`, update `col1Content` to support pipeline runs:

```typescript
interface SessionState {
  accessToken: string | null
  username: string | null
  userId: string | null
  activeJobId: string | null
  col1Content:
    | { type: 'job'; jobId: string }
    | { type: 'pipeline_run'; runId: string }
    | null

  setTokens: (access: string, refresh: string) => void
  setUser: (id: string, username: string) => void
  setActiveJobId: (id: string | null) => void
  setCol1Content: (content: SessionState['col1Content']) => void
  logout: () => void
}
```

The store implementation body (the `create` call) does not need to change — `setCol1Content` already accepts the full union.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/sessionStore.ts
git commit -m "feat(pipeline): extend col1Content union type with pipeline_run variant"
```

---

## Task 4: Create PipelineRunItem Component

A clickable item for the LiveStream panel. Shows pipeline name, status dot, and step progress. Completed/failed runs are clickable and set `col1Content`.

**Files:**
- Create: `frontend/src/components/live/PipelineRunItem.tsx`

---

- [ ] **Step 1: Create the component**

```tsx
import { useSessionStore } from '../../stores/sessionStore'
import type { PipelineRunSummary } from '../../api/pipelines'

const STATUS_COLOR: Record<string, string> = {
  queued:    'var(--muted)',
  running:   'var(--accent)',
  succeeded: '#4ade80',
  failed:    '#ef4444',
}

interface Props {
  run: PipelineRunSummary
}

export default function PipelineRunItem({ run }: Props) {
  const setCol1Content = useSessionStore(s => s.setCol1Content)
  const isTerminal = run.status === 'succeeded' || run.status === 'failed'

  const handleClick = () => {
    if (isTerminal) {
      setCol1Content({ type: 'pipeline_run', runId: run.id })
    }
  }

  const progress =
    run.step_count > 0
      ? `${run.steps_done}/${run.step_count} steps`
      : 'no steps'

  return (
    <div
      onClick={handleClick}
      className="px-3 py-2 mb-1 rounded text-xs transition-colors"
      style={{
        background: 'var(--panel2)',
        border: '1px solid var(--border)',
        cursor: isTerminal ? 'pointer' : 'default',
        opacity: run.status === 'queued' ? 0.6 : 1,
      }}
    >
      <div className="flex items-center gap-1 mb-1">
        <span style={{ color: STATUS_COLOR[run.status] ?? 'var(--muted)', fontSize: 8 }}>◆</span>
        <span style={{ color: 'var(--subtext)', fontSize: 10 }}>{run.status}</span>
        <span className="ml-auto" style={{ color: 'var(--muted)', fontSize: 9 }}>{progress}</span>
      </div>
      <div className="truncate" style={{ color: 'var(--text)' }}>
        {run.pipeline_name}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/live/PipelineRunItem.tsx
git commit -m "feat(pipeline): create PipelineRunItem component for LiveStream"
```

---

## Task 5: Update LiveStream — Add Pipeline Runs Section

Poll `listAllPipelineRuns` and listen for `pipeline.step.update` / `pipeline.run.complete` WebSocket events to update pipeline run status in real-time. Show pipeline runs in a separate "Pipelines" section below the existing jobs.

**Files:**
- Modify: `frontend/src/components/live/LiveStream.tsx`

---

- [ ] **Step 1: Rewrite LiveStream.tsx**

Replace the entire content of `frontend/src/components/live/LiveStream.tsx`:

```tsx
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listJobs, type JobOut } from '../../api/v3'
import { listAllPipelineRuns, type PipelineRunSummary } from '../../api/pipelines'
import { useWebSocket, type WsEvent } from '../../hooks/useWebSocket'
import JobItem from './JobItem'
import PipelineRunItem from './PipelineRunItem'

export default function LiveStream() {
  const qc = useQueryClient()
  const { data: jobs = [] } = useQuery({ queryKey: ['jobs'], queryFn: listJobs, refetchInterval: 30_000 })
  const { data: pipelineRuns = [] } = useQuery({
    queryKey: ['pipeline-runs-all'],
    queryFn: listAllPipelineRuns,
    refetchInterval: 10_000,
  })
  const [liveEvents, setLiveEvents] = useState<JobOut[]>([])
  const [livePipelineEvents, setLivePipelineEvents] = useState<Partial<PipelineRunSummary> & { id: string }[]>([])

  useWebSocket((event: WsEvent) => {
    // Job events
    if (['job.update', 'job.completed', 'job.failed'].includes(event.type) && event.job_id) {
      setLiveEvents(prev => {
        const exists = prev.find(j => j.id === event.job_id)
        const updated: JobOut = exists
          ? { ...exists, status: event.status ?? exists.status, result_count: event.result_count ?? exists.result_count }
          : {
              id: event.job_id!,
              status: event.status ?? 'running',
              query: event.message ?? '…',
              created_at: new Date().toISOString(),
              completed_at: null,
              result_count: event.result_count ?? 0,
            }
        return exists ? prev.map(j => j.id === event.job_id ? updated : j) : [updated, ...prev]
      })
      if (event.type === 'job.completed') {
        qc.invalidateQueries({ queryKey: ['jobs'] })
      }
    }

    // Pipeline events
    if (event.type === 'pipeline.step.update' && event.run_id) {
      setLivePipelineEvents(prev => {
        const exists = prev.find(r => r.id === event.run_id)
        if (exists) {
          // Increment steps_done when a step reaches a terminal state
          const isTerminalStep = event.status === 'succeeded' || event.status === 'failed'
          return prev.map(r =>
            r.id === event.run_id
              ? { ...r, status: 'running', steps_done: isTerminalStep ? (r.steps_done ?? 0) + 1 : r.steps_done }
              : r,
          )
        }
        return [{ id: event.run_id!, status: 'running', steps_done: 0, step_count: 0 }, ...prev]
      })
    }

    if (event.type === 'pipeline.run.complete' && event.run_id) {
      setLivePipelineEvents(prev =>
        prev.map(r =>
          r.id === event.run_id
            ? { ...r, status: event.status ?? 'succeeded' }
            : r,
        ),
      )
      qc.invalidateQueries({ queryKey: ['pipeline-runs-all'] })
    }
  })

  const mergedJobs: JobOut[] = [
    ...liveEvents,
    ...jobs.filter(j => !liveEvents.find(l => l.id === j.id)),
  ].slice(0, 30)

  // Merge live pipeline events with fetched runs
  const mergedPipelineRuns: PipelineRunSummary[] = pipelineRuns
    .map(r => {
      const live = livePipelineEvents.find(l => l.id === r.id)
      return live ? { ...r, ...live } as PipelineRunSummary : r
    })
    .slice(0, 20)

  return (
    <div className="flex flex-col h-full">
      <div
        className="px-3 py-2 text-[11px] font-semibold"
        style={{ color: 'var(--accent)', borderBottom: '1px solid var(--border)' }}
      >
        Live
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {/* Research jobs */}
        {mergedJobs.length > 0 && (
          <>
            <div
              className="px-1 pb-1 text-[9px] font-semibold tracking-widest"
              style={{ color: 'var(--muted)' }}
            >
              RESEARCH
            </div>
            {mergedJobs.map(job => <JobItem key={job.id} job={job} />)}
          </>
        )}

        {/* Pipeline runs */}
        {mergedPipelineRuns.length > 0 && (
          <div className={mergedJobs.length > 0 ? 'mt-3' : ''}>
            <div
              className="px-1 pb-1 text-[9px] font-semibold tracking-widest"
              style={{ color: 'var(--muted)' }}
            >
              PIPELINES
            </div>
            {mergedPipelineRuns.map(run => <PipelineRunItem key={run.id} run={run} />)}
          </div>
        )}

        {mergedJobs.length === 0 && mergedPipelineRuns.length === 0 && (
          <p className="text-[10px] text-center mt-6" style={{ color: 'var(--muted)' }}>
            No active jobs
          </p>
        )}
      </div>
    </div>
  )
}
```

Note: The `WsEvent` type may need `run_id` and `status` fields added. Check `hooks/useWebSocket.ts` — if `WsEvent` doesn't have `run_id`, add it.

- [ ] **Step 2: Check and patch WsEvent type if needed**

Read `frontend/src/hooks/useWebSocket.ts`. If `WsEvent` does not have `run_id?: string`, add it:

```typescript
export interface WsEvent {
  type: string
  job_id?: string
  run_id?: string       // add if missing — pipeline run ID
  node_id?: string      // add if missing — pipeline node ID
  status?: string
  message?: string
  result_count?: number
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/live/LiveStream.tsx frontend/src/hooks/useWebSocket.ts
git commit -m "feat(pipeline): add pipeline runs section to LiveStream with real-time WebSocket updates"
```

---

## Task 6: Update ResultsPanel — Pipeline Run Results View

When `col1Content.type === 'pipeline_run'`, show the pipeline run's step-by-step results. While the run is active, poll every 3 seconds. When terminal, stop polling and show final state.

**Files:**
- Modify: `frontend/src/components/results/ResultsPanel.tsx`

---

- [ ] **Step 1: Add pipeline run branch to ResultsPanel.tsx**

Replace the entire `ResultsPanel.tsx` content:

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSessionStore } from '../../stores/sessionStore'
import { getJob, getJobResults, gradeResult } from '../../api/v3'
import { getPipelineRun } from '../../api/pipelines'
import NewsCard from './NewsCard'
import GradeBar from './GradeBar'

type Tab = 'Profiles' | 'News' | 'Social' | 'Summary'
const TABS: Tab[] = ['Profiles', 'News', 'Social', 'Summary']

const STEP_STATUS_COLOR: Record<string, string> = {
  pending:   'var(--muted)',
  running:   'var(--accent)',
  succeeded: '#4ade80',
  failed:    '#ef4444',
}

function PipelineRunResults({ runId }: { runId: string }) {
  const { data: run, isLoading } = useQuery({
    queryKey: ['pipeline-run', runId],
    queryFn: () => getPipelineRun(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'running' || status === 'queued' ? 3000 : false
    },
  })

  if (isLoading) {
    return <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>Loading…</p>
  }

  if (!run) {
    return <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>Run not found.</p>
  }

  const totalItems = run.steps.reduce((sum, s) => sum + s.item_count, 0)

  return (
    <div className="p-3">
      {/* Run header */}
      <div
        className="rounded p-3 mb-4 text-xs"
        style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span
            style={{
              fontSize: 8,
              color: STEP_STATUS_COLOR[run.status] ?? 'var(--muted)',
            }}
          >
            ◆
          </span>
          <span style={{ color: STEP_STATUS_COLOR[run.status] ?? 'var(--muted)', fontWeight: 600 }}>
            {run.status}
          </span>
          <span className="ml-auto" style={{ color: 'var(--muted)' }}>
            {totalItems > 0 ? `${totalItems} items collected` : ''}
          </span>
        </div>
        {run.status === 'running' && (
          <p style={{ color: 'var(--muted)', fontSize: 10, marginTop: 4 }}>
            ⟳ Pipeline in progress…
          </p>
        )}
      </div>

      {/* Steps */}
      <div className="text-[10px] font-semibold mb-2 tracking-widest" style={{ color: 'var(--muted)' }}>
        STEPS
      </div>
      <div className="flex flex-col gap-2">
        {run.steps.length === 0 && (
          <p className="text-xs" style={{ color: 'var(--muted)' }}>No steps recorded.</p>
        )}
        {run.steps.map((step, idx) => (
          <div
            key={step.id}
            className="rounded p-3 text-xs"
            style={{
              background: 'var(--panel2)',
              border: `1px solid ${step.status === 'failed' ? '#ef444433' : 'var(--border)'}`,
            }}
          >
            <div className="flex items-center gap-2 mb-1">
              <span style={{ color: STEP_STATUS_COLOR[step.status] ?? 'var(--muted)', fontSize: 8 }}>●</span>
              <span style={{ color: 'var(--subtext)', fontWeight: 600 }}>Step {idx + 1}</span>
              <span style={{ color: 'var(--muted)' }}>·</span>
              <span style={{ color: STEP_STATUS_COLOR[step.status] ?? 'var(--muted)' }}>
                {step.status}
              </span>
              {step.item_count > 0 && (
                <span className="ml-auto" style={{ color: '#4ade80' }}>
                  {step.item_count} items
                </span>
              )}
            </div>
            {step.error_message && (
              <div
                className="mt-1 rounded px-2 py-1 text-[10px]"
                style={{ background: '#ef444411', color: '#f87171' }}
              >
                {step.error_message}
              </div>
            )}
            {step.started_at && step.finished_at && (
              <div className="mt-1 text-[9px]" style={{ color: 'var(--muted)' }}>
                {Math.round(
                  (new Date(step.finished_at).getTime() - new Date(step.started_at).getTime()) / 1000,
                )}s
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ResultsPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('News')
  const col1Content = useSessionStore(s => s.col1Content)

  const { data: job } = useQuery({
    queryKey: ['job', col1Content?.type === 'job' ? col1Content.jobId : null],
    queryFn: () => getJob((col1Content as { type: 'job'; jobId: string }).jobId),
    enabled: col1Content?.type === 'job' && !!col1Content?.jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'running' || status === 'pending' ? 3000 : false
    },
  })

  const { data: results = [] } = useQuery({
    queryKey: ['job-results', col1Content?.type === 'job' ? col1Content.jobId : null],
    queryFn: () => getJobResults((col1Content as { type: 'job'; jobId: string }).jobId),
    enabled: col1Content?.type === 'job' && !!col1Content?.jobId && job?.status === 'completed',
  })

  // Pipeline run view — renders without tabs
  if (col1Content?.type === 'pipeline_run') {
    return (
      <div className="flex flex-col h-full">
        <div
          className="px-3 py-2 text-[11px] font-semibold"
          style={{ color: 'var(--accent)', borderBottom: '1px solid var(--border)' }}
        >
          Pipeline Run
        </div>
        <div className="flex-1 overflow-y-auto">
          <PipelineRunResults runId={col1Content.runId} />
        </div>
      </div>
    )
  }

  // Job / empty view — original tabs UI
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-3 gap-1 pt-2 pb-1" style={{ borderBottom: '1px solid var(--border)' }}>
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="px-2 py-1 rounded text-[11px] font-medium transition-colors"
            style={{
              background: activeTab === tab ? 'var(--panel2)' : 'transparent',
              color:      activeTab === tab ? 'var(--accent)' : 'var(--muted)',
              border:     activeTab === tab ? '1px solid var(--border)' : '1px solid transparent',
              cursor: 'pointer',
            }}
          >
            {tab}
          </button>
        ))}
        {job && (
          <span className="ml-auto text-[10px] truncate max-w-[40%]" style={{ color: 'var(--subtext)' }}>
            {job.query}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {!col1Content && (
          <div className="text-center mt-16">
            <p className="text-xs" style={{ color: 'var(--muted)' }}>
              Send a message to the agent or tap a job in the live stream.
            </p>
          </div>
        )}

        {col1Content?.type === 'job' && activeTab === 'News' && (
          <div>
            {job && (
              <p className="text-[10px] mb-3" style={{ color: 'var(--subtext)' }}>
                {job.status === 'running' || job.status === 'pending'
                  ? '⟳ Research in progress…'
                  : `${job.status} — ${results.length} results`}
              </p>
            )}
            {results.map(r => (
              <div key={r.id} className="mb-3">
                <NewsCard
                  item={{
                    id: r.id,
                    title: r.title,
                    url: r.url ?? undefined,
                    snippet: r.snippet ?? undefined,
                    source_name: r.source,
                  }}
                />
                <GradeBar
                  resultId={r.id}
                  jobId={col1Content.jobId}
                  initialGrade={r.grade}
                  onGrade={(resultId, grade) => {
                    gradeResult(col1Content.jobId, resultId, grade).catch(() => {})
                  }}
                />
              </div>
            ))}
            {job?.status === 'completed' && results.length === 0 && (
              <p className="text-xs text-center mt-8" style={{ color: 'var(--muted)' }}>No results found.</p>
            )}
          </div>
        )}

        {col1Content?.type === 'job' && activeTab === 'Summary' && (
          <div className="text-xs p-3 rounded" style={{ background: 'var(--panel2)', border: '1px solid var(--border)' }}>
            {job ? (
              <>
                <div className="font-semibold mb-2" style={{ color: 'var(--accent)' }}>{job.query}</div>
                <div className="mb-1" style={{ color: 'var(--subtext)' }}>Status: {job.status}</div>
                <div style={{ color: 'var(--subtext)' }}>Results: {results.length}</div>
                {results.filter(r => r.source === 'qdrant').length > 0 && (
                  <div className="mt-2 text-[10px]" style={{ color: 'var(--muted)' }}>
                    {results.filter(r => r.source === 'qdrant').length} results from Qdrant memory
                  </div>
                )}
              </>
            ) : 'Loading…'}
          </div>
        )}

        {activeTab === 'Profiles' && (
          <p className="text-[10px]" style={{ color: 'var(--muted)' }}>Profile results appear here when LinkedIn plugin is active.</p>
        )}
        {activeTab === 'Social' && (
          <p className="text-[10px]" style={{ color: 'var(--muted)' }}>Social crawl results appear here.</p>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/results/ResultsPanel.tsx
git commit -m "feat(pipeline): add PipelineRunResults view to ResultsPanel, branch on col1Content.type"
```

---

## Task 7: Final Verification

- [ ] **Rebuild frontend and end-to-end check**

```bash
docker compose up --build -d frontend
```

Open http://localhost:5173 (Research page). Verify:

1. **LiveStream shows two sections**: "RESEARCH" (existing jobs) and "PIPELINES" (pipeline runs, if any exist).
2. **Pipeline run item**: Shows pipeline name, `◆` status dot, step progress (`N/M steps`).
3. **Running run**: `◆` dot is accent color. Item is not clickable (cursor: default).
4. **Completed run**: `◆` dot is green. Item is clickable.
5. **Clicking completed run**: ResultsPanel changes to "Pipeline Run" header (no tabs). Shows run status and step list.
6. **Step cards**: Each shows status dot, item count (green if > 0), duration, and error message if failed.
7. **Polling**: While status is `running`, the run detail refetches every 3s and updates step statuses.
8. **WebSocket**: Start a pipeline run → the LiveStream PIPELINES section updates in real-time without a page refresh (steps_done increments as steps finish).
9. **Jobs still work**: Clicking a job in RESEARCH section still shows News/Summary tabs in ResultsPanel.

- [ ] **Commit any final fixes**

```bash
git add -A
git commit -m "fix(pipeline): any adjustments from e2e verification"
```
