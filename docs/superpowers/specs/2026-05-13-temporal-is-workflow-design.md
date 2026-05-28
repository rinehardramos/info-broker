# Temporal IS Workflow Migration Design Spec

- Author: Software Architect
- Date: 2026-05-13
- Status: Draft
- Related: `docs/superpowers/specs/2026-04-29-pipeline-engine-design.md`,
  `docs/superpowers/specs/2026-05-06-claude-code-intelligent-search-design.md`,
  `docs/superpowers/specs/2026-05-12-async-is-job-run-architecture.md`,
  `docs/superpowers/specs/2026-05-10-preflight-requirements-validation-design.md`

---

## 1. Problem Statement

Pipeline runs are already executed inside Temporal workflows (`app/pipeline/runner.py` →
`PipelineWorkflow`), but **Intelligent Search (IS) brain runs bypass Temporal entirely**.
`app/routers/v3/agent.py:1157` fires `_run_is_research` via `asyncio.create_task`, meaning
the run lives inside the FastAPI process. When the API container restarts, every in-flight
IS run is orphaned: the DB row is stuck in `running`, the budget reservation is held, no
results land, and no webhook fires. `app/pipeline/reconcile.py` papers over this on
startup by mass-failing any non-terminal `manual` run, which destroys legitimate work and
forces refunds. The asyncio path also lacks first-class cancellation, signal-based
clarification (PreFlight uses a process-local `_PREFLIGHT_PENDING` dict), retries on
transient failures (Claude API timeouts), and any form of progress checkpointing for
long-running source enrichment. Moving IS runs onto Temporal — the executor we already
operate, sandbox, and trust — unifies the run model, eliminates startup data loss, and
unlocks signals/queries/heartbeats that the asyncio approach cannot express.

---

## 2. Why Temporal (vs. asyncio)

| Concern | asyncio (today) | Temporal (proposed) |
|---|---|---|
| Process restart during run | Run orphaned; reconcile marks `failed` | Workflow resumes on any worker; activity retries from last checkpoint |
| Mid-run user clarification | Module-global `_PREFLIGHT_PENDING` dict; lost on restart | Durable workflow signal `brain_answer` |
| Cancellation | No-op (task ref not retained per-run) | Workflow signal `cancel_run` or `client.cancel()` |
| Budget refund on failure | `except` in route handler; skipped if process dies | Activity `release_budget` runs in `finally` branch of workflow |
| Retry of transient Claude/MCP failures | None | `RetryPolicy` per activity with idempotency key |
| Status visibility | DB poll only | Workflow `query`, plus DB |
| Long sources enrichment (10k-row CSV) | All-or-nothing; restart = re-do | Activity-per-batch with cursor in DB; restart resumes |
| Operational model | Two execution planes (asyncio for IS, Temporal for pipelines) | One plane, one mental model |

The cost is real: a hard dependency on the Temporal cluster for IS, sandbox passthroughs
for new modules, and additional moving parts to monitor. Section 7 covers fallback.

---

## 3. Architecture

```
                         POST /v3/agent/message (use_intelligent_search=true)
                                          │
                                          ▼
                          ┌──────────────────────────────────┐
                          │ agent.py: route handler          │
                          │  - create pipeline_runs row      │
                          │  - reserve budget (preview only) │
                          │  - launch Temporal workflow      │
                          └──────────────────┬───────────────┘
                                             │ Client.start_workflow(ISRunWorkflow, ...)
                                             ▼
                          ┌──────────────────────────────────┐
                          │      ISRunWorkflow (Temporal)    │
                          │                                  │
                          │  1. preflight_validation ────────┼─► Activity (Haiku, 5s)
                          │      │                           │
                          │      ▼ if blocking:              │
                          │  2. wait_for_signal(brain_answer)│  ◄── POST /brain-answer
                          │      │                           │      (signal payload)
                          │      ▼                           │
                          │  3. reserve_budget ──────────────┼─► Activity (DB, idempotent)
                          │  4. run_is_brain ────────────────┼─► Activity (Claude Code
                          │      │ heartbeats every 30s      │     subprocess + MCP)
                          │      ▼                           │     emits WS via push_event
                          │  5. post_process ────────────────┼─► Activity (scorecard, KG,
                          │      │                           │     session update, webhook)
                          │      ▼                           │
                          │  6. mark_succeeded / mark_failed │
                          │     release_budget on failure    │
                          │                                  │
                          │  Signals: brain_answer, cancel_run│
                          │  Queries: get_run_status         │
                          └──────────────────┬───────────────┘
                                             │
                                             ▼
                                    pipeline_runs row terminal
                                    job.completed WS event
                                    webhook delivered
```

Two task queues:
- `pipeline-tasks` — existing pipeline DAG runs (unchanged).
- `is-run-tasks` — new IS workflows. Separate queue so IS workers can be sized/scaled
  independently (Claude subprocess is heavy; pipeline activities are light).

---

## 4. Workflow Definition (pseudocode)

### 4.1 Workflow input

```python
# app/temporal/workflows/is_run.py
@dataclass
class ISRunInput:
    run_id: str
    user_id: str
    org_id: str
    pipeline_id: str
    session_id: str | None
    query: str
    past_research: list[dict] | None
    session_context: str
    budget: dict          # raw RunBudgetIn payload
    callback_url: str | None
    preflight_prior_slots: dict | None
```

### 4.2 Workflow body

```python
@workflow.defn
class ISRunWorkflow:
    def __init__(self) -> None:
        self._brain_answer: str | None = None
        self._cancelled: bool = False
        self._phase: str = "queued"
        self._cycle_count: int = 0

    @workflow.signal
    async def brain_answer(self, answer: str) -> None:
        self._brain_answer = answer

    @workflow.signal
    async def cancel_run(self, reason: str = "user") -> None:
        self._cancelled = True

    @workflow.query
    def get_run_status(self) -> dict:
        return {"phase": self._phase, "cycles": self._cycle_count,
                "cancelled": self._cancelled}

    @workflow.run
    async def run(self, inp: ISRunInput) -> dict:
        retry_short = RetryPolicy(initial_interval=timedelta(seconds=2),
                                  maximum_attempts=3)

        # 1. PreFlight
        self._phase = "preflight"
        pf = await workflow.execute_activity(
            preflight_validation,
            PreflightInput(query=inp.query, prior_slots=inp.preflight_prior_slots),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_short,
        )

        # 2. Block on user clarification, if needed
        if pf.blocking:
            self._phase = "awaiting_input"
            await workflow.execute_activity(
                mark_awaiting_input,
                MarkAwaitingInput(run_id=inp.run_id, question=pf.first_question,
                                  options=pf.first_question_options),
                start_to_close_timeout=timedelta(seconds=10),
            )
            # Durable wait — survives worker restart
            await workflow.wait_condition(
                lambda: self._brain_answer is not None or self._cancelled,
                timeout=timedelta(hours=24),
            )
            if self._cancelled:
                return await self._abort(inp, "cancelled_during_preflight")
            inp.session_context += f"\n\n[User answered preflight: {self._brain_answer}]"

        # 3. Budget gate
        self._phase = "reserving_budget"
        reservation = await workflow.execute_activity(
            reserve_budget,
            ReserveBudgetInput(run_id=inp.run_id, user_id=inp.user_id,
                               org_id=inp.org_id, budget=inp.budget),
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=retry_short,
        )
        if not reservation.ok:
            return await self._abort(inp, "insufficient_budget")

        # 4. Run the brain (long activity, heartbeats, single retry on transient)
        self._phase = "running"
        try:
            brain_result = await workflow.execute_activity(
                run_is_brain,
                RunISBrainInput(run_id=inp.run_id, user_id=inp.user_id,
                                query=inp.query, past_research=inp.past_research,
                                session_id=inp.session_id,
                                session_context=inp.session_context,
                                preflight=pf),
                start_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=10),
                    maximum_attempts=2,
                    non_retryable_error_types=["BudgetExceeded", "UserCancelled"],
                ),
            )
        except ActivityError as exc:
            return await self._abort(inp, f"brain_failed:{exc}")

        # 5. Post-process (scorecard / KG / session / webhook)
        self._phase = "post_processing"
        await workflow.execute_activity(
            post_process,
            PostProcessInput(run_id=inp.run_id, user_id=inp.user_id,
                             session_id=inp.session_id,
                             brain_result=brain_result,
                             callback_url=inp.callback_url),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_short,
        )

        self._phase = "succeeded"
        return {"run_id": inp.run_id, "status": "succeeded",
                "findings": len(brain_result.findings)}

    async def _abort(self, inp: ISRunInput, reason: str) -> dict:
        # Best-effort: release reservation, mark failed, fire failure webhook
        await workflow.execute_activity(
            release_budget_and_mark_failed,
            AbortInput(run_id=inp.run_id, user_id=inp.user_id,
                       org_id=inp.org_id, reason=reason,
                       callback_url=inp.callback_url),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )
        self._phase = "failed"
        return {"run_id": inp.run_id, "status": "failed", "reason": reason}
```

### 4.3 Activities (signatures only)

```python
# app/temporal/activities/preflight.py
@activity.defn(name="preflight_validation")
async def preflight_validation(inp: PreflightInput) -> PreflightResult: ...

# app/temporal/activities/budget.py
@activity.defn(name="reserve_budget")
async def reserve_budget(inp: ReserveBudgetInput) -> ReservationResult: ...

@activity.defn(name="release_budget_and_mark_failed")
async def release_budget_and_mark_failed(inp: AbortInput) -> None: ...

# app/temporal/activities/brain.py
@activity.defn(name="run_is_brain")
async def run_is_brain(inp: RunISBrainInput) -> BrainResult:
    """Wraps app.is_brain.run_research(); calls activity.heartbeat()
    every cycle so the workflow notices brain stalls within 2 min."""
    ...

# app/temporal/activities/post_process.py
@activity.defn(name="post_process")
async def post_process(inp: PostProcessInput) -> None:
    """Scorecard, KG write, session update, success webhook."""
    ...

@activity.defn(name="mark_awaiting_input")
async def mark_awaiting_input(inp: MarkAwaitingInput) -> None: ...
```

Idempotency: every activity that writes uses `run_id` as the natural key. `reserve_budget`
checks if `pipeline_runs.budget_status='reserved'` already and short-circuits. `post_process`
checks `pipeline_runs.status='succeeded'` and exits. This is required because Temporal will
re-execute activities on transient failure.

---

## 5. File Tree

### New

```
app/temporal/
├── __init__.py
├── client.py                # connect helper (host/port from env), reused by route handler
├── worker.py                # IS worker entrypoint (separate from pipeline worker)
├── workflows/
│   ├── __init__.py
│   └── is_run.py            # ISRunWorkflow
└── activities/
    ├── __init__.py
    ├── preflight.py         # preflight_validation, mark_awaiting_input
    ├── budget.py            # reserve_budget, release_budget_and_mark_failed
    ├── brain.py             # run_is_brain (wraps app.is_brain.run_research)
    └── post_process.py      # post_process
```

Optional Phase 3 additions:
```
app/temporal/workflows/source_enrich.py    # SourceEnrichmentWorkflow
app/temporal/activities/source_batch.py    # enrich_row_batch (cursor-based)
```

### Modified

| File | Change |
|---|---|
| `app/routers/v3/agent.py` | Replace `asyncio.create_task(_run_is_research(...))` with `client.start_workflow(ISRunWorkflow.run, ...)`. Behind feature flag `IS_USE_TEMPORAL` in Phase 0/1. Remove `_PREFLIGHT_PENDING` dict — clarification flow becomes `client.signal(workflow_id, "brain_answer", answer)`. Remove inline budget reservation (moves into activity). |
| `app/pipeline/reconcile.py` | Restrict `reconcile_orphaned_runs()` to `trigger_type='manual'` AND `temporal_workflow_id IS NULL` — once IS is on Temporal these rows no longer exist. Eventually delete the module in Phase 2. |
| `app/pipeline/worker.py` | No change (continues to serve `pipeline-tasks`). Keep separate from IS worker. |
| `app/is_brain.py` | Add `heartbeat_cb` parameter to `run_research(...)` so the activity can call `activity.heartbeat()` between cycles. No behavior change when callback is None. |
| `Dockerfile` / `docker-compose.yml` | Add `is-worker` service that runs `python -m app.temporal.worker`. |
| `app/main.py` (or wherever startup hooks live) | Gate `reconcile_orphaned_runs` behind a flag; eventually remove. |

### Deleted (Phase 2)

- `_run_is_research` function in `app/routers/v3/agent.py`
- `_PREFLIGHT_PENDING` module dict
- `app/pipeline/reconcile.py` (after the orphan class is provably empty for 2 weeks)

---

## 6. Migration Phases

### Phase 0 — Foundations (worker deployed, dark)
**Scope:** Build `app/temporal/` modules, wire up `is-worker` container, no traffic routed.
**Acceptance:**
- `is-worker` container starts, registers workflow + activities, polls `is-run-tasks`.
- Unit tests cover each activity in isolation with `WorkflowEnvironment`.
- Integration test: start workflow against ephemeral Temporal server, assert success/failure paths, signal delivery, query response.
- No production traffic touches the new code path.

### Phase 1 — Dual-write (feature flag on, opt-in users)
**Scope:** `IS_USE_TEMPORAL=true` flips the IS branch in `send_message` to use Temporal. Old in-flight asyncio runs continue to completion under the legacy code path.
**Acceptance:**
- Flag-on test users complete >50 IS runs successfully via Temporal.
- Restart `api` container mid-run; workflow continues on `is-worker`; run reaches terminal state.
- `brain_answer` signal delivered via `POST /v3/agent/brain-answer` resumes a blocked workflow within 2s.
- Cancel via `POST /v3/agent/runs/{id}/cancel` transitions a running workflow to `failed` and releases budget.
- Error rate on Temporal path ≤ asyncio baseline measured over 7 days.

### Phase 2 — Cutover (Temporal sole executor)
**Scope:** Flip `IS_USE_TEMPORAL` default to `true` for all users; remove asyncio branch and `_PREFLIGHT_PENDING`; remove `reconcile_orphaned_runs` from startup hooks.
**Acceptance:**
- One full week with zero non-Temporal IS runs created.
- All IS-related routes (`/message`, `/brain-answer`, future `/cancel`) only operate on Temporal workflow IDs.
- Documentation in `CLAUDE.md` and `tasks/agent-collab.md` updated to describe one execution model.
- `_run_is_research` and `_PREFLIGHT_PENDING` deleted; `reconcile.py` restricted to legacy `manual` pipeline runs only.

### Phase 3 — Row-level checkpointing for source enrichment
**Scope:** Tabular source uploads (CSV/XLSX with >1k rows) become their own `SourceEnrichmentWorkflow` that processes rows in batches of 200, advancing a `processed_row_offset` column on `research_sources`. Each `enrich_row_batch` activity reads `processed_row_offset`, processes the next N rows, writes findings, and atomically advances the offset.
**Acceptance:**
- 10k-row CSV upload restarts mid-process; on restart the workflow resumes at the last committed offset (verified by row-count delta).
- Failure in batch K does not lose batches 0..K-1.
- Throughput within 20% of current single-shot path for files <1k rows (no regression for small uploads — small uploads bypass the workflow and parse synchronously as today).

---

## 7. Risk Assessment & Rollback

| Risk | Severity | Mitigation |
|---|---|---|
| Temporal cluster unavailable on IS request | High | In Phase 1, route handler catches `ConnectionError` and falls back to the asyncio path with a structured log. In Phase 2, return `503 Temporal unavailable — research queue paused`; the user retries when health restores. Do NOT silently degrade once asyncio is gone. |
| Sandbox blocks new imports (`app.is_brain` pulls many modules) | Medium | Mirror the `app.pipeline.worker` `passthrough_modules` pattern for `app.is_brain`, `app.memory`, `app.pipeline.strategies`, `app.pipeline.techniques`. Validate at worker start. |
| Long Claude subprocess outlives `start_to_close_timeout` | Medium | 30 min ceiling + 2 min heartbeat. Brain emits heartbeats every cycle; if it stalls, Temporal retries (idempotent; reads `pipeline_runs` state to avoid double-billing). Hard ceiling protects against runaway cost. |
| Activity retry double-charges budget | High | `reserve_budget` activity is idempotent via `pipeline_runs.budget_status='reserved'` guard. Brain activity records a per-attempt cost in a `pipeline_run_attempts` table (new) so observability is preserved. |
| Signal arrives before workflow starts | Low | Temporal queues signals to workflow ID; signal delivery survives worker absence. Route handler asserts workflow started (returns `workflow_id` synchronously) before returning to client. |
| Loss of WebSocket events (workflow on worker, WS hub in api process) | Medium | `push_event` already uses a Redis pub/sub fan-out (see `app/routers/v3/stream.py`); activities import it and publish. Worker container has the same Redis env. Verify in Phase 0. |

**Rollback (Phase 1):** Flip `IS_USE_TEMPORAL=false`; new runs go back to asyncio. Old Temporal workflows finish normally.
**Rollback (Phase 2):** Re-introduce `_run_is_research` from git history, set `IS_USE_TEMPORAL=false`, redeploy. Workflows in flight complete; new runs go via asyncio. This window is the reason Phase 2 should not delete code until Phase 1 has run clean for ≥2 weeks.

---

## 8. Cross-cutting Decisions

1. **Separate task queue (`is-run-tasks`).** IS runs spawn a Claude subprocess that consumes memory and time on a very different profile than pipeline node activities. Mixing them on `pipeline-tasks` would let one IS run starve a fleet of cheap pipeline activities.
2. **Workflow ID format: `is-run-{run_id}`.** Mirrors `pipeline-{run_id}` from `runner.py:22`. Stored in `pipeline_runs.temporal_workflow_id` (column already exists). One unified lookup pattern for the UI and webhooks.
3. **Activities, not workflow code, call the DB.** Workflows must stay deterministic and side-effect-free. The DB is exposed only through `app.routers.v3.db` inside activities (already passthrough'd in pipeline worker — reuse).
4. **PreFlight stays a workflow signal, not a child workflow.** The preflight question is part of *this* run's narrative; modeling it as a child workflow adds visibility cost without buying anything (a child workflow can't share parent state cleanly). Signal + `wait_condition` is the boring choice and Temporal's idiomatic answer to "human in the loop."
5. **Budget reservation moves into an activity.** Today it sits inline in the route handler; if Temporal is unavailable, the handler refunds. Moving it into an activity means the workflow owns the reservation's lifecycle, and `_abort()` always runs `release_budget_and_mark_failed`. Closes the failure-mode gap from the current code.
6. **No new abstraction for "executor."** Resist building an `IExecutor` interface across asyncio/Temporal in Phase 1. The asyncio branch is dead weight that gets deleted in Phase 2; an abstraction would outlive the thing it abstracts.

---

## 9. Open Questions

1. **Should `is-worker` and `pipeline-worker` share a container?** Operationally simpler (one image, one deployment), but couples scaling. Recommendation: one container per queue from day one. Confirm with platform/ops owner.
2. **`pipeline_run_attempts` table or JSON column?** Per-attempt cost/error tracking — do we need a real table for analytics (audit, refund disputes) or is a `attempts JSONB` column on `pipeline_runs` enough? Lean toward column unless analytics asks otherwise.
3. **Signal authentication.** `POST /v3/agent/brain-answer` currently trusts `_PREFLIGHT_PENDING[run_id]`. After migration the route must verify `user_id == pipeline_runs.user_id` before issuing the signal — Temporal does not authorize. Owner: backend/security.
4. **Phase 3 trigger threshold.** What row count promotes a source upload from synchronous parse to `SourceEnrichmentWorkflow`? Initial proposal: 1000 rows. Needs benchmarking.
5. **Heartbeat granularity.** Should `run_is_brain` heartbeat every cycle, every tool call, or on a wall-clock interval? Wall clock (every 30s) is simplest; per-cycle gives finer recovery resolution at the cost of more chatter. Default to wall clock unless profiling shows a need.
6. **Compatibility of `_SESSION_SLOTS` cache.** This module-global lives in the api process today (`agent.py`). Once preflight runs on the worker, the cache miss rate goes to 100% unless we move it to Redis or pass it via workflow state. Recommendation: pass `preflight_prior_slots` as workflow input (already shown in §4.1) and persist post-preflight slots via a small DB write — drop the in-memory cache.
