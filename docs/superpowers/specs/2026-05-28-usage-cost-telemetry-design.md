# Usage & Cost Telemetry on the Monitoring Spine — Design

> Status: **APPROVED for plan-writing** · Owner: platform · Date: 2026-05-28
>
> Sequel to `2026-05-27-platform-monitoring-design.md` (Phase 1) and
> `2026-05-28-platform-monitoring-phase2-design.md` (Phase 2). Builds on the
> shipped `platform-monitoring` 0.2.2 library + dashboard.

## 1. Summary

Additively capture three completion-event streams into ClickHouse via the
existing monitoring spine, and surface cost/usage analytics in the admin
dashboard — **without** disturbing live Postgres reads. The three streams:

1. **`tool_call`** — mirrors `mcp_tool_calls` completion. One immutable event
   per call, emitted at `McpTracker.log_call_complete`.
2. **`step_run`** — mirrors `pipeline_step_runs` completion. One immutable
   event per node finish, emitted at the workflow's success/failure hook.
3. **`llm_call`** — **net-new**. Captured at the brain's `result`-event
   handler (subscription cost is reported by the brain directly) and at
   direct-model call sites (`intelligent_search.py` etc., where we estimate
   cost via an admin-managed pricing table).

Postgres remains the source of truth for live/operational reads (the UI
polls `pipeline_step_runs` for run progress; the admin page reads
`mcp_tool_calls` for tool stats). ClickHouse becomes the analytics store for
cost/usage. Postgres offload (TTL on the hot tables) is **out of scope** for
this effort — a safer follow-up once CH is proven for these streams.

## 2. Non-goals

- **No read-path migration.** The existing PG-backed admin tool-stats UI and
  live run-progress UI are untouched.
- **No retiring PG tables.** `mcp_tool_calls` and `pipeline_step_runs` keep
  their current schema, writes, and consumers. Adding a TTL is a later effort.
- **No webhook/alert integration for usage events** in this round. Rules
  remain HTTP-request-scoped (Phase 2). Cost spikes/threshold alerts are a
  natural follow-up using the same `RuleEngine`.
- **No retroactive backfill** from PG into CH. CH starts from deploy-time
  forward. The PG tables already hold history; this is additive.
- **No cross-process LLM-cost proxying.** We capture where the calls already
  happen (brain result handler + direct model sites). A future LLM gateway
  (north-star) can replace these hooks.

## 3. Decisions log (from brainstorm)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Migration strategy | Additive analytics layer (PG stays SoT; CH for analytics) |
| 2 | Deliverable scope | Full slice: capture + store + read API + new dashboard tab |
| 3 | Library structure | Extend `platform-monitoring` with a `usage/` module on a dedicated `mon:usage` Redis stream, same `monitoring-worker` |
| 4 | LLM pricing | **No hardcoded constants**. Admin-managed `llm_pricing` Postgres table, append-only history, audit columns, each event records the `pricing_id` it used |
| 5 | Unknown-model cost | `total_cost_usd=NULL`, `cost_source='unknown_model'`, surfaced in admin UI — **never silently estimated as 0** |
| 6 | Subscription brain cost | Use brain `result` event's `total_cost_usd` directly; pricing table not consulted |

## 4. Architecture & data flow

```
                                ┌──────────────────────────────────────┐
McpTracker.log_call_complete ───┤ emit_tool_call()                     │
workflow node finish ───────────┤ emit_step_run()    UsageEmitter      │── XADD ──► Redis mon:usage stream
brain `result` event handler ───┤ emit_llm_call()    (fire & forget,   │
direct model call sites ────────┤ emit_llm_call()    fail-open)        │
                                └──────────────────────────────────────┘
                                                                              │
                                                                              ▼
                                              monitoring-worker (consumer group "usage")
                                                  │ batch + route by `kind`
                                                  ▼
                                    ┌─────────────┬─────────────┬───────────────┐
                                    │ mon.tool_   │ mon.step_   │ mon.llm_      │
                                    │  calls      │  runs       │  calls        │
                                    └─────────────┴─────────────┴───────────────┘
                                                                              │
                                                                              ▼  (AggregatingMergeTree)
                                                    mon.llm_cost_daily,
                                                    mon.tool_usage_daily,
                                                    mon.step_throughput_daily
                                                                              │
                                                                              ▼
                                              /v3/monitoring/usage/* (admin-gated read API)
                                                                              │
                                                                              ▼
                                              @platform/monitoring-ui — "Cost & Usage" tab
```

Fire-and-forget, fail-open, at-least-once write-before-ack — identical
discipline to the proven `MonitoringMiddleware` request pipeline.

## 5. Library additions — `platform-monitoring` v0.3.0

All new code lives in a focused submodule. The HTTP-request monitoring domain
is **unchanged**.

### 5.1 New module layout

```
~/library/packages/platform-monitoring/src/platform_monitoring/usage/
    __init__.py
    events.py            # UsageEventBase + ToolCallEvent + StepRunEvent + LlmCallEvent
    emitter.py           # UsageEmitter (XADD to mon:usage, fire-and-forget)
    query_models.py      # TS-mirrorable response shapes (epoch-ms, 0-1 fractions)
    router.py            # create_usage_router(admin_dependency) under /v3/monitoring/usage
    schema/clickhouse/
        001_tool_calls.sql
        002_step_runs.sql
        003_llm_calls.sql
        004_rollups.sql           # AggregatingMergeTree daily rollups
~/library/packages/platform-monitoring/src/platform_monitoring/ports/
    usage_sink.py        # new port
~/library/packages/platform-monitoring/src/platform_monitoring/adapters/
    clickhouse_usage_sink.py  # extends ClickHouseSink with write_usage_batch + query methods
~/library/packages/platform-monitoring/src/platform_monitoring/worker.py
    # extended to consume mon:usage (separate consumer group) and route by kind
```

### 5.2 Events (`usage/events.py`)

Pydantic v2 models, shared base. Epoch-ms timestamps to keep wire shape stable
across the boundary (matches existing monitoring conventions).

```python
class Actor(BaseModel):
    user_id: UUID | None = None
    org_id: UUID | None = None
    caller_identity: str | None = None   # opaque; never the API key itself

class UsageEventBase(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    ts: int                              # epoch ms
    kind: Literal["tool_call", "step_run", "llm_call"]
    actor: Actor
    run_id: UUID | None = None
    session_id: UUID | None = None
    node_id: UUID | None = None

class ToolCallEvent(UsageEventBase):
    kind: Literal["tool_call"] = "tool_call"
    tool_name: str
    node_type: str | None = None
    status: Literal["ok", "error"]
    duration_ms: int
    result_count: int | None = None
    error_kind: str | None = None        # short class, NOT the raw message

class StepRunEvent(UsageEventBase):
    kind: Literal["step_run"] = "step_run"
    node_type: str | None = None
    status: Literal["succeeded", "failed", "skipped"]
    item_count: int = 0
    duration_ms: int                      # finished_at - started_at
    error_kind: str | None = None

class LlmCallEvent(UsageEventBase):
    kind: Literal["llm_call"] = "llm_call"
    model: str
    provider: str                         # 'anthropic' | 'openai' | 'openrouter' | …
    status: Literal["ok", "error"]
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    duration_ms: int = 0
    num_turns: int | None = None
    phase: str | None = None
    total_cost_usd: float | None = None   # None when cost_source == 'unknown_model'
    cost_source: Literal["subscription", "estimated", "unknown_model"]
    pricing_id: UUID | None = None        # set when cost_source == 'estimated'
```

Validation rules:
- `duration_ms >= 0`. Negative → drop with a metric increment (fail-open).
- `error_kind` is a short class (e.g. `"TimeoutError"`, `"http_429"`), **never
  the raw exception message** (raw messages are PII risk and high-cardinality).
- `LlmCallEvent`: when `cost_source == "estimated"`, `pricing_id` MUST be set;
  when `"subscription"`, `pricing_id` MUST be NULL; when `"unknown_model"`,
  `total_cost_usd` MUST be NULL. Enforced in pydantic validators.

### 5.3 ClickHouse schema

All tables use `ENGINE = MergeTree` with `ORDER BY (event_date, actor_org_id, ...)`
and **TTL = `event_date + INTERVAL 90 DAY`** (configurable via
`MonitoringSettings.usage_retention_days`, default 90; raw monitoring stays at
its existing 30-day TTL). Tables created idempotently on worker bootstrap.

```sql
-- 001_tool_calls.sql
CREATE TABLE IF NOT EXISTS mon.tool_calls (
    event_id        UUID,
    ts              DateTime64(3, 'UTC'),
    event_date      Date MATERIALIZED toDate(ts),
    user_id         Nullable(UUID),
    org_id          Nullable(UUID),
    caller_identity Nullable(String),
    run_id          Nullable(UUID),
    session_id      Nullable(UUID),
    node_id         Nullable(UUID),
    tool_name       LowCardinality(String),
    node_type       LowCardinality(Nullable(String)),
    status          LowCardinality(String),       -- 'ok' | 'error'
    duration_ms     UInt32,
    result_count    Nullable(Int32),
    error_kind      LowCardinality(Nullable(String))
) ENGINE = MergeTree
ORDER BY (event_date, org_id, tool_name, ts)
TTL event_date + INTERVAL 90 DAY;

-- 002_step_runs.sql  (analogous; ORDER BY event_date, org_id, node_type, ts)
-- 003_llm_calls.sql  (ORDER BY event_date, org_id, model, ts)
--   columns: event_id, ts, event_date, user_id, org_id, caller_identity,
--   run_id, node_id, model, provider, status, input_tokens, output_tokens,
--   cache_creation_tokens, cache_read_tokens, duration_ms, num_turns, phase,
--   total_cost_usd (Nullable(Float64)), cost_source LowCardinality(String),
--   pricing_id Nullable(UUID)
```

**Rollups (`004_rollups.sql`)** — AggregatingMergeTree materialized views for
fast dashboard queries (mirroring the existing `mon.requests_daily` pattern):

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS mon.llm_cost_daily
ENGINE = AggregatingMergeTree()
ORDER BY (event_date, org_id, model)
AS SELECT
    event_date,
    org_id,
    model,
    sumState(coalesce(total_cost_usd, 0))      AS cost_usd_state,
    sumState(toUInt64(input_tokens))            AS input_tokens_state,
    sumState(toUInt64(output_tokens))           AS output_tokens_state,
    sumState(toUInt64(cache_read_tokens))       AS cache_read_tokens_state,
    countState()                                 AS calls_state
FROM mon.llm_calls
GROUP BY event_date, org_id, model;

-- mon.tool_usage_daily        (calls, errors, p95(duration_ms) via quantilesState)
-- mon.step_throughput_daily   (succeeded/failed/skipped counts, p95 duration)
```

### 5.4 `UsageSink` port + ClickHouse adapter

A new port keeps the usage domain isolated:

```python
# ports/usage_sink.py
class UsageSink(Protocol):
    async def write_usage_batch(self, events: Sequence[UsageEventBase]) -> None: ...
    # Read methods used by the router:
    async def llm_cost_series(self, *, org_id, since_ts, until_ts, bucket) -> list[CostBucket]: ...
    async def llm_by_model(self, *, org_id, since_ts, until_ts) -> list[ModelRow]: ...
    async def cost_by_actor(self, *, since_ts, until_ts, top_n) -> list[ActorRow]: ...
    async def tool_top(self, *, since_ts, until_ts, top_n) -> list[ToolRow]: ...
    async def step_throughput(self, *, since_ts, until_ts, bucket) -> list[StepBucket]: ...
    async def usage_summary(self, *, since_ts, until_ts) -> UsageSummary: ...
    async def unpriced_models(self, *, since_ts, until_ts) -> list[UnpricedModel]: ...
```

`ClickHouseSink` (the existing class) implements both `EventSink` (requests)
and `UsageSink` (usage). `write_usage_batch` routes by `kind` to the right
INSERT; all queries are SQL-injection-safe via the existing `_esc()`.

### 5.5 Worker extension

The `monitoring-worker` process keeps its existing `mon:events` consumer and
adds a **second consumer group `usage`** on the **new `mon:usage` stream**.
Two cooperating tasks in the same process; one `ClickHouseSink` shared. Same
at-least-once, write-before-ack, exponential-backoff-on-CH-error discipline.
Heartbeat metric exposed.

Why separate stream + group: keeps high-volume request telemetry's backpressure
independent of usage telemetry, simplifies retention/maxlen tuning per stream,
and isolates failures (a CH failure on usage doesn't pause request capture).

### 5.6 `UsageEmitter` (`usage/emitter.py`)

```python
class UsageEmitter:
    def __init__(self, redis: AsyncRedis, *, stream: str = "mon:usage",
                 maxlen: int = 100_000):
        ...
    async def emit(self, event: UsageEventBase) -> None:
        # Serialize, XADD with MAXLEN ~ maxlen, retain task ref, swallow errors.
    # Conveniences:
    async def emit_tool_call(self, **kwargs) -> None: ...
    async def emit_step_run(self, **kwargs) -> None: ...
    async def emit_llm_call(self, **kwargs) -> None: ...
```

Single instance lives in the consumer app's lifespan, reuses the existing
monitoring Redis connection (no second pool needed). Mirrors the proven
`MonitoringMiddleware` emit pattern.

### 5.7 Read API (`usage/router.py`)

`create_usage_router(admin_dependency, sink: UsageSink)` mounted under the
existing monitoring router at `/v3/monitoring/usage`:

```
GET /v3/monitoring/usage/summary?since=<ms>&until=<ms>
GET /v3/monitoring/usage/llm/cost-series?since&until&bucket=hour|day
GET /v3/monitoring/usage/llm/by-model?since&until
GET /v3/monitoring/usage/llm/by-actor?since&until&top=20
GET /v3/monitoring/usage/llm/unpriced-models?since&until
GET /v3/monitoring/usage/tools/top?since&until&top=20
GET /v3/monitoring/usage/steps/throughput?since&until&bucket=hour|day
```

All admin-gated (the injected dependency the existing monitoring router uses).
Response shapes in `usage/query_models.py` use epoch-ms and 0-1 fractions,
matching the existing monitoring convention.

## 6. infobroker capture hooks

All thin, fire-and-forget; `UsageEmitter` is wired in `app/main.py`'s
lifespan using the same monitoring Redis the request middleware uses.

### 6.1 Tool calls

**File:** `app/observability/tracker.py`, `McpTracker.log_call_complete`
(after the existing `UPDATE mcp_tool_calls` SQL):

```python
# After PG update, emit usage event (fail-open).
await usage_emitter.emit_tool_call(
    ts=now_ms(),
    actor=resolve_actor(),                # same context the vault/X-Caller uses
    run_id=run_id,
    session_id=session_id,
    tool_name=tool_name,
    node_type=node_type,
    status="ok" if not error_message else "error",
    duration_ms=duration_ms,
    result_count=result_count,
    error_kind=classify_error(error_message),
)
```

### 6.2 Step runs

**File:** `app/pipeline/workflow.py`, immediately after the existing
`UPDATE pipeline_step_runs SET status = 'succeeded'/'failed' …`:

```python
duration_ms = int((finished_at - started_at).total_seconds() * 1000)
await usage_emitter.emit_step_run(
    ts=now_ms(),
    actor=resolve_actor(),
    run_id=run_id,
    node_id=node_id,
    node_type=node_type,
    status=final_status,                  # 'succeeded' | 'failed' | 'skipped'
    item_count=item_count,
    duration_ms=duration_ms,
    error_kind=classify_error(error_message),
)
```

### 6.3 LLM calls — subscription brain

**File:** the brain runner that processes the brain subprocess event stream
(`app/pipeline/runners/scoped_brain.py` and/or `app/is_brain.py` — the place
that sees `type == "result"`). When the `result` event arrives:

```python
usage = result_event.get("usage") or {}
await usage_emitter.emit_llm_call(
    ts=now_ms(),
    actor=resolve_actor(),
    run_id=run_id,
    node_id=node_id,
    phase=phase,
    model=result_event.get("model") or "claude-subscription",
    provider="anthropic",
    status="ok" if not result_event.get("is_error") else "error",
    input_tokens=usage.get("input_tokens", 0),
    output_tokens=usage.get("output_tokens", 0),
    cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
    cache_read_tokens=usage.get("cache_read_input_tokens", 0),
    duration_ms=int(result_event.get("duration_ms") or 0),
    num_turns=result_event.get("num_turns"),
    total_cost_usd=result_event.get("total_cost_usd"),   # may be None
    cost_source="subscription",
    pricing_id=None,
)
```

**Missing cost on subscription:** Claude Code's `result` event reliably carries
`usage`, but `total_cost_usd` is occasionally absent (older brain versions /
sandboxed runs). In that case emit with `total_cost_usd=None` and
`cost_source='subscription'` — tokens still capture; the dashboard surfaces
"cost unreported" cells distinct from "unpriced model". **Never** estimate
subscription cost from the pricing table — subscription is flat-rate, not
metered, and applying per-token estimates would mislead.

### 6.4 LLM calls — direct model

**File:** `app/pipeline/nodes/intelligent_search.py` (and any other direct
model-call sites that currently discard `response.usage`). Capture
`response.usage`, look up current pricing, emit:

```python
price = await pricing_resolver.get(model)   # see §8
total_cost_usd, cost_source, pricing_id = price.cost_for(usage) if price else (None, "unknown_model", None)
await usage_emitter.emit_llm_call(
    ts=now_ms(),
    actor=resolve_actor(),
    run_id=run_id, node_id=node_id, phase=phase,
    model=model, provider=price.provider if price else "unknown",
    status="ok" if response else "error",
    input_tokens=usage.get("input_tokens", 0),
    output_tokens=usage.get("output_tokens", 0),
    cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
    cache_read_tokens=usage.get("cache_read_input_tokens", 0),
    duration_ms=duration_ms,
    total_cost_usd=total_cost_usd,
    cost_source=cost_source,
    pricing_id=pricing_id,
)
```

## 7. Cost attribution

Every event carries `actor{user_id, org_id, caller_identity}`. The actor is
resolved from the **same server-side context the API-key vault and X-Caller
headers use** — opaque UUIDs only, **never the keys themselves** (load-bearing
invariant from the vault project).

**At capture time** (where the request context may not be in scope — e.g. an
async worker processing a pipeline step), the hook resolves the actor from
the persisted row it's about to emit for: `mcp_tool_calls.user_id` and the
session's caller_identity for tool calls; `pipeline_runs.user_id` joined via
`run_id` for step runs and LLM calls. `org_id` is looked up from the user
record (single membership today; multi-org tenancy is a north-star concern).
If a row predates user-attribution, the actor fields are NULL — the event
still records (anonymous/system).

`run_id` enables roll-ups of cost per run, node, user, org, and model. This
is the per-tenant-fairness data the scaling north-star wants.

## 8. LLM pricing — admin-managed (replaces hardcoded constants)

Per feedback: no hardcoded price tables. Source of truth is a Postgres table
with full audit history.

### 8.1 Postgres schema

```sql
CREATE TABLE IF NOT EXISTS llm_pricing (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id                  VARCHAR(128) NOT NULL,
    provider                  VARCHAR(32)  NOT NULL,
    input_usd_per_1m          NUMERIC(10,4) NOT NULL,
    output_usd_per_1m         NUMERIC(10,4) NOT NULL,
    cache_creation_usd_per_1m NUMERIC(10,4),
    cache_read_usd_per_1m     NUMERIC(10,4),
    effective_from            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                UUID,
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes                     TEXT
);
CREATE INDEX IF NOT EXISTS idx_llm_pricing_model_eff
    ON llm_pricing(model_id, effective_from DESC);
```

Append-only — edits insert a new row. Current price for a model =
the newest row with `effective_from <= now()`.

### 8.2 `PricingResolver` (in-process cache)

A small async resolver, lifespan singleton:

```python
class PricingResolver:
    def __init__(self, db_pool, *, ttl_seconds: int = 60): ...
    async def get(self, model_id: str) -> PriceSnapshot | None:
        # Returns None when model has no pricing row → cost_source='unknown_model'.
        # Cached in-memory for ttl_seconds; refresh fetches the newest row
        # with effective_from <= now() per model_id.
```

`PriceSnapshot.cost_for(usage_dict)` computes:

```
cost_usd = (input_tokens / 1_000_000) * input_usd_per_1m
         + (output_tokens / 1_000_000) * output_usd_per_1m
         + (cache_creation_tokens / 1_000_000) * cache_creation_usd_per_1m  -- if set
         + (cache_read_tokens / 1_000_000) * cache_read_usd_per_1m          -- if set
```

Returns `(cost_usd, "estimated", pricing_id)`.

### 8.3 Admin API + UI

`/v3/admin/llm-pricing` CRUD endpoints (admin-gated, audited via existing
admin audit log). Edits create new rows; the UI shows the current price per
model plus a small "history" expander. Lives in the **Cost & Usage** tab as
a "Pricing" panel (with a "Manage prices" affordance), so price changes and
cost analytics are co-located.

### 8.4 Unknown-model handling — never silent-zero

When `PricingResolver.get(model)` returns `None`, the emitted event has
`total_cost_usd=NULL` and `cost_source='unknown_model'`. The
`/v3/monitoring/usage/llm/unpriced-models` endpoint surfaces these, and the
Cost & Usage tab shows a banner: **"N unpriced models in last 24h — add
pricing"** with a one-click link to the pricing CRUD.

## 9. UI — Cost & Usage tab (`@platform/monitoring-ui`)

A new 5th tab in the existing `MonitoringDashboard`. Panels:

1. **Summary cards** — total cost (last 24h / 7d), input vs output tokens,
   cache-read hit rate, calls count.
2. **LLM cost over time** — area chart, hour/day buckets, stack by model.
3. **Cost by model** — bar chart, sorted desc; rows per provider.
4. **Cost by user / org** — table, sortable; top N.
5. **Tools** — top tools by calls, p95 duration, error rate.
6. **Step throughput** — line chart of succeeded/failed/skipped per bucket.
7. **Unpriced-models banner** — links to Pricing panel.
8. **Pricing panel** — current-prices table + per-model edit modal + history
   expander (admin only).

Reuses existing client/hooks/recharts patterns; new TS types in
`@platform/monitoring-ui/types.ts` mirror the new Pydantic `query_models`
exactly.

## 10. Error handling, idempotency, fail-open

- **Emit errors:** swallowed and counted (Prometheus-style metric on the
  emitter). Orchestration never blocks or fails on telemetry.
- **Redis down:** XADD raises; emitter swallows; orchestration unaffected;
  events drop (bounded). Same behavior as the request middleware.
- **Worker retry:** at-least-once consumer group; CH error → backoff +
  retry; `event_id` is the dedupe key (queries can use `argMin(event_id)`
  if needed, but we accept rare duplicates as acceptable for analytics).
- **ClickHouse outage:** worker buffers in the consumer group and resumes
  on recovery (same as Phase 1).
- **Schema migrations:** worker bootstraps tables idempotently
  (`CREATE TABLE IF NOT EXISTS …`), same pattern as the existing
  `mon.requests` schema.

## 11. Testing strategy (real-stack, per feedback)

### Library (`platform-monitoring`)

- Unit tests for envelopes (validators + invariants).
- `ClickHouseSink.write_usage_batch` + queries against a **real ClickHouse
  container** (24-alpine on :8123). Verify row shapes, rollup merges.
- `UsageEmitter` round-trip against **real Redis** (XADD, then read by a
  consumer): event shape preserved.
- Worker: consume mon:usage from real Redis, write to real CH, verify rows.
- mypy --strict, ruff.

### infobroker

- Capture-hook unit tests with a real monitoring Redis: assert `emit_*`
  produces the right event shape on real tool/step/brain completion paths.
- `PricingResolver` tests against real Postgres: cache TTL, history lookup,
  unknown-model returns None.
- **End-to-end functional run with the real brain:** trigger a real run,
  assert `mon.llm_calls` rows carry tokens + cost (brain result event came
  through), `mon.tool_calls` and `mon.step_runs` populate, and the
  `/v3/monitoring/usage/*` endpoints return real data. Cost & Usage tab
  renders charts.
- Vendored wheel + tarball bump + api/worker rebuild +
  `docker compose up -d --build --renew-anon-volumes` (per the operational
  notes in `project_platform_monitoring`).

## 12. Versioning & deploy

- `platform-monitoring` → **v0.3.0** (new usage domain); `@platform/monitoring-ui`
  → **v0.3.0** (new Cost & Usage tab).
- Tag `platform-monitoring-v0.3.0` on `~/library` main.
- Re-vendor: wheel into `infobroker/vendor/platform_monitoring-0.3.0-py3-none-any.whl`;
  UI tgz into `infobroker/frontend/vendor/platform-monitoring-ui-0.3.0.tgz`.
  Update `pyproject.toml` source path and `frontend/package.json` file: dep.
- Compose: no new services needed (worker reused). Update `.env.example` with
  `USAGE_RETENTION_DAYS` (default 90).
- Frontend deploys via the existing Cloudflare Pages CD on push to `main`
  (see `project_platform_monitoring` operational notes).

## 13. Open questions / future

- **Cost-spike alerts:** the existing `RuleEngine` (Phase 2) is request-scoped.
  Extending it to evaluate sliding cost windows is a natural follow-up
  (re-uses the same `mon:alerts` + webhook path).
- **PG offload:** once CH coverage is proven (≥30 days clean), add a TTL to
  `mcp_tool_calls` (e.g. 14d) and `pipeline_step_runs` (e.g. 30d). Separate effort.
- **LLM gateway (north-star):** when the platform centralizes model calls
  through a gateway service, the LLM-cost hook moves to that one place and
  the direct-call hooks (§6.4) retire.
- **Per-user rate-limit on cost:** the throttle override (library 0.2.2)
  is per-IP req/min; a future per-user cost-quota throttle is a clean
  extension on the same hot-store machinery.

## 14. Acceptance criteria

1. Push to `~/library` main is tagged `platform-monitoring-v0.3.0`; vendored
   artifacts present in `infobroker/vendor` and `infobroker/frontend/vendor`.
2. `docker compose up -d --build --renew-anon-volumes` brings up the api +
   worker; CH bootstraps `mon.tool_calls`, `mon.step_runs`, `mon.llm_calls`
   and the three rollup MVs.
3. A real benchmark run produces ≥1 row in each of `mon.tool_calls`,
   `mon.step_runs`, `mon.llm_calls` with non-null tokens; brain-originated
   `mon.llm_calls` rows have `cost_source='subscription'` and non-null
   `total_cost_usd`.
4. `/v3/monitoring/usage/summary` returns non-zero counters (admin token).
5. `/v3/monitoring/usage/llm/unpriced-models` surfaces any direct-model
   calls whose model_id isn't in `llm_pricing`.
6. The Cost & Usage tab renders in the admin dashboard (live at
   infobroker.tech) with all panels populated.
7. Pricing CRUD: admin adds a row → next direct-model call records that
   `pricing_id`; an older event still references its original `pricing_id`.
8. Tearing down monitoring Redis does NOT break orchestration (capture
   silently drops; PG writes unaffected; orchestration completes).

---
