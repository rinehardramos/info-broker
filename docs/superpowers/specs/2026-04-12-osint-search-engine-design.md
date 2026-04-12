# OSINT Search Engine — Design Spec

**Date:** 2026-04-12
**Status:** Approved
**Approach:** New isolated package (`app/search_engine/`) in the existing info-broker repo

## Overview

A general-purpose OSINT search engine that runs parallel web searches across pluggable free sources, supports deep search (follow-up queries to fill gaps), grades results with a hybrid heuristic + LLM + human feedback system, and serves results as raw lists, summarized reports, or opinionated conclusions. Fully async and non-blocking. Results stored in Qdrant (vectors + payload) with metadata in Postgres. User-scoped via JWT auth.

This is a standalone subsystem — separate from the existing LinkedIn profile research agent and `/v1/news` endpoint.

---

## 1. Data Model

### Postgres Tables (all prefixed `search_`)

#### `search_users`

Stub user table for JWT auth. Links API activity to a user identity. Will connect to an external auth service in production.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` |
| `username` | VARCHAR(128) UNIQUE | |
| `email` | VARCHAR(256) | nullable, for future auth service |
| `created_at` | TIMESTAMPTZ | default `now()` |
| `is_active` | BOOLEAN | default `true` |

#### `search_jobs`

One row per search request. Tracks lifecycle from submitted → running → completed/failed.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK → search_users | |
| `query` | TEXT | original user query |
| `config` | JSONB | `{max_parallel, deep_search, max_budget, depth, plugins}` |
| `status` | VARCHAR(20) | `pending`, `running`, `completed`, `failed`, `cancelled` |
| `callback_url` | TEXT | nullable, webhook to POST when done |
| `aggregate_confidence` | JSONB | nullable, filled after grading `{score, level, corroboration, completeness, breakdown}` |
| `created_at` | TIMESTAMPTZ | |
| `started_at` | TIMESTAMPTZ | nullable |
| `completed_at` | TIMESTAMPTZ | nullable |
| `error` | TEXT | nullable, failure reason |

#### `search_results`

Metadata only — full text lives in Qdrant.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `job_id` | UUID FK → search_jobs | |
| `plugin` | VARCHAR(64) | `ddg`, `wikipedia`, `google_rss`, etc. |
| `title` | TEXT | |
| `url` | TEXT | nullable |
| `published_at` | TIMESTAMPTZ | nullable |
| `heuristic_scores` | JSONB | `{relevance, freshness, source_reliability, composite}` — 0.0–1.0 each |
| `is_deep_child` | BOOLEAN | true if spawned by deep search |
| `parent_result_id` | UUID FK → search_results | nullable, links child to parent |
| `fetched_at` | TIMESTAMPTZ | |

#### `search_reports`

Cached LLM-generated outputs (summaries, conclusions). Lazily created on first request.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `job_id` | UUID FK → search_jobs | UNIQUE per (job_id, report_type) |
| `report_type` | VARCHAR(20) | `summary`, `conclusion` |
| `content` | TEXT | LLM-generated report |
| `model_used` | VARCHAR(128) | which LLM generated it |
| `created_at` | TIMESTAMPTZ | |

#### `search_feedback`

Human scores on individual search results, per-user.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `result_id` | UUID FK → search_results | |
| `user_id` | UUID FK → search_users | |
| `interest` | INT | 1–5 |
| `relevance` | INT | 1–5 |
| `usefulness` | INT | 1–5 |
| `comment` | TEXT | nullable |
| `created_at` | TIMESTAMPTZ | |

#### `search_plugins_config`

Registry of available plugins and per-user enable/disable.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK → search_users | nullable (null = system default) |
| `plugin_name` | VARCHAR(64) | `ddg`, `wikipedia`, `google_rss` |
| `enabled` | BOOLEAN | default `true` |
| `priority` | INT | execution order / weighting |
| `config` | JSONB | plugin-specific overrides |

#### `search_domain_scores`

Living domain reputation scores, updated by human feedback.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | UUID FK → search_users | |
| `domain` | VARCHAR(256) | |
| `score` | FLOAT | 0.0–1.0, exponential moving average |
| `sample_count` | INT | number of feedback events that contributed |
| `updated_at` | TIMESTAMPTZ | |
| PK | (user_id, domain) | composite primary key |

### Qdrant Collection: `search_results`

| Field | Value |
|-------|-------|
| **Point ID** | `uuid5(NAMESPACE_DNS, search_result.id)` |
| **Vector** | Embedding of `"{title}\n{snippet}\n{full_text[:4000]}"` (768-dim) |
| **Distance** | Cosine |
| **Payload** | `result_id`, `job_id`, `user_id`, `plugin`, `title`, `url`, `snippet` (first 500 chars), `full_text` (for retrieval without re-scraping) |

---

## 2. Plugin Architecture

Each search source is a plugin implementing a protocol. New sources are added by dropping a file into `app/search_engine/plugins/` — no core code changes.

### SearchPlugin Protocol

```python
class SearchPlugin(Protocol):
    name: str           # "ddg", "wikipedia", "google_rss"
    description: str    # human-readable
    requires_api_key: bool

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        config: dict | None = None,
    ) -> list[PluginResult]

    def available(self) -> bool: ...
```

### PluginResult

```python
@dataclass
class PluginResult:
    title: str
    url: str | None
    snippet: str
    full_text: str | None
    published_at: datetime | None
    source_name: str
    metadata: dict
```

### PluginRegistry

Auto-discovers plugins in the `plugins/` package at startup. Exposes:

- `registry.get(name) → SearchPlugin`
- `registry.available() → list[SearchPlugin]`
- `registry.for_user(user_id) → list[SearchPlugin]` — filtered by user's `search_plugins_config`

### Starter Plugins

| Plugin | Source | Scrapes full text? | Notes |
|--------|--------|--------------------|-------|
| `ddg` | DuckDuckGo web search | Yes (reuses `scrape_url`) | Wraps `ddgs.text()`, async via thread pool |
| `wikipedia` | Wikipedia REST API (`/api/rest_v1/`) | Yes (extract field) | Article summary + full extract |
| `google_rss` | Google News RSS (`news.google.com/rss/search`) | No (headlines + links) | Deep search can scrape linked articles |

---

## 3. Search Execution & Deep Search

### SearchExecutor

Core orchestrator at `app/search_engine/executor.py`.

**Lifecycle:**

1. `POST /v2/search` → `executor.submit()` → create `search_jobs` row (status=pending)
2. Return `job_id` immediately (202 Accepted)
3. Background task: set status=running → parallel plugin fan-out → deduplicate by URL → heuristic scoring → deep search (if enabled) → store results (Postgres + Qdrant) → set status=completed → fire callback webhook

**Parallel execution:** `config.max_parallel` controls how many plugins run simultaneously (default: all enabled). Plugin-internal concurrency (e.g., DDG scraping multiple URLs in parallel) is managed by each plugin's own `asyncio.Semaphore` — separate from the plugin-level parallelism.

### Deep Search

Runs after initial fan-out. Single level of depth (no recursion). Budget-constrained.

1. **Gap analysis** — LLM reviews initial results against the query, produces follow-up queries
2. **Budget check** — follow-up queries capped by `max_budget - len(initial_results)`
3. **Child search** — each follow-up runs through the same parallel plugin fan-out
4. **Merge** — children stored with `is_deep_child=true` and `parent_result_id`, deduplicated against initial results

**LLM prompt for follow-up generation:**

> Given the original query and the search results so far, identify 1–N information gaps. For each gap, produce a concise search query. Return JSON: `{"follow_ups": [{"query": "...", "reason": "..."}]}`

### SearchExecutor Interface (for future Redis swap)

```python
class SearchExecutor(Protocol):
    async def submit(self, query, config, user_id) -> UUID
    async def cancel(self, job_id) -> bool
    async def status(self, job_id) -> JobStatus
```

Current implementation: `AsyncioSearchExecutor`. Future: `ArqSearchExecutor` (Redis-backed) — same protocol, drop-in replacement.

---

## 4. Grading & Confidence

Three layers: algorithmic heuristics (instant), LLM assessment (on-demand), human feedback (async, self-improving).

### Layer 1: Heuristic Scoring (per result, at ingest)

Each result gets `heuristic_scores` JSONB:

| Dimension | Computation |
|-----------|-------------|
| **Relevance** (0.0–1.0) | Token overlap + fuzzy match between query and title+snippet (TF-IDF style) |
| **Freshness** (0.0–1.0) | Decay function on `published_at`: today=1.0, 1d=0.9, 7d=0.5, 30d=0.2, no date=0.3 |
| **Source reliability** (0.0–1.0) | From user's `search_domain_scores` (personalized), falling back to curated `domain_tiers.py` defaults |

**Composite** = weighted average: relevance 0.4, freshness 0.3, reliability 0.3.

### Layer 2: LLM Assessment (per job, on-demand)

Triggered when user requests `summary` or `conclusion` format. LLM produces:

```json
{
  "corroboration": 0.85,
  "completeness": 0.7,
  "confidence_level": "high",
  "confidence_score": 0.78,
  "rationale": "Multiple authoritative sources agree. Minor gap: no primary government data."
}
```

**Aggregate confidence:**
```
confidence_score = (avg_heuristic * 0.4) + (corroboration * 0.3) + (completeness * 0.3)
confidence_level = high (≥0.7) | medium (≥0.4) | low (<0.4)
```

Stored in `search_jobs.aggregate_confidence` — computed once, cached.

### Layer 3: Human Feedback (self-improvement loop)

Users score individual results: `interest`, `relevance`, `usefulness` (each 1–5) + optional comment.

**Feedback drives three automatic improvement mechanisms:**

#### 3a. Domain Reputation (heuristic layer)

Domain scores are living values, not static tiers:

- Initial: curated defaults (Reuters=1.0, unknown=0.4)
- Each feedback: `new_score = old_score * 0.9 + (normalized_feedback * 0.1)` (exponential moving average)
- Stored in `search_domain_scores` per user
- Domains with `sample_count < 3` fall back to global defaults
- Used by heuristic scorer instead of static tier map

#### 3b. Episodic Memory Injection (LLM layer)

Before generating deep-search follow-ups or reports, query Qdrant for semantically similar past results:

- **Negative examples**: past results rated poorly (relevance ≤ 2 OR usefulness ≤ 2)
- **Positive examples**: past results rated highly (relevance ≥ 4 AND usefulness ≥ 4)

Injected into LLM prompts to steer searches toward productive sources and away from known-bad ones.

#### 3c. Plugin Preference (execution layer)

Per-plugin utility tracked per user: `plugin_utility = avg(relevance × usefulness)` across last 50 rated results from that plugin.

- High-utility plugins get more `max_results` slots
- Plugins with `plugin_utility < 0.3` get deprioritized (fewer results), not disabled

All three mechanisms are **per-user** — one user's feedback does not affect another's search quality.

---

## 5. Output Modes & Async Flow

### Output Formats

All served from `GET /v2/search/{job_id}/results?format=<format>`:

| Format | Returns | LLM? | Cached? |
|--------|---------|------|---------|
| `list` | Raw results + heuristic scores, sorted by composite | No | No (live query) |
| `summary` | Key findings grouped by theme, with citations and confidence | Yes | Yes, in `search_reports` |
| `conclusion` | Direct answer with evidence assessment and caveats | Yes | Yes, in `search_reports` |

### Async Flow

```
Client                          API                         Background
──────                          ───                         ──────────
POST /v2/search ───────────→ create job (pending)
                              spawn task ─────────────────→ execute search
←──────────────────────────── 202 {"job_id", "status_url"}  │
                                                            ├─ fan-out plugins
                                                            ├─ score results
                                                            ├─ deep search (if enabled)
                                                            ├─ store in PG + Qdrant
GET /v2/search/{id}/status ──→                              │
←──────────────────────────── {"status": "running"}         │
                                                            ├─ set status=completed
                                                            └─ POST callback_url (if set)

GET /v2/search/{id}/results?format=list ──→ PG + Qdrant
←──────────────────────────── {results: [...]}

GET /v2/search/{id}/results?format=summary ──→ check cache → miss → LLM → cache
←──────────────────────────── {content, confidence}
```

### Callback Webhook

On completion, POSTs to `callback_url` (if provided):

```json
{
  "job_id": "uuid",
  "status": "completed",
  "total_results": 12,
  "results_url": "/v2/search/{job_id}/results"
}
```

SSRF-protected via `safe_fetch_url`. Fires once, no retries.

---

## 6. Auth & API Endpoints

### JWT Authentication

- **Stub issuer** for development: `POST /v2/auth/token` mints tokens for a dummy user
- **Token:** HS256 signed, payload: `{sub: user_id, username, exp, iss: "info-broker-dev"}`
- **Signing key:** `JWT_SECRET` env var
- **Existing auth unchanged:** `/v1/*` and profile endpoints stay on `X-API-Key`

### Endpoint Map

All JWT-gated except the token endpoint.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v2/auth/token` | Mint JWT (dev stub) |
| POST | `/v2/search` | Submit search job |
| GET | `/v2/search/{job_id}/status` | Poll job status + progress |
| GET | `/v2/search/{job_id}/results?format=list\|summary\|conclusion` | Retrieve results |
| POST | `/v2/search/{job_id}/cancel` | Cancel running job |
| POST | `/v2/search/{job_id}/results/{result_id}/feedback` | Submit human feedback |
| GET | `/v2/search/history` | List user's past jobs (paginated) |
| POST | `/v2/search/similar` | Semantic similarity search across past results |
| GET | `/v2/search/plugins` | List plugins + user state |
| PUT | `/v2/search/plugins/{plugin_name}` | Enable/disable plugin, set priority |

### Key Request/Response Shapes

**POST `/v2/search`:**
```json
{
  "query": "reasons for extreme weather in Manila",
  "deep_search": false,
  "max_parallel": 3,
  "max_budget": 5,
  "plugins": ["ddg", "wikipedia"],
  "callback_url": "https://my-agent.example.com/callback"
}
```
All fields except `query` are optional. Defaults: `deep_search=false`, `max_parallel=all enabled`, `max_budget=5`, `plugins=user's enabled set`, `callback_url=null`.

**Response (202):**
```json
{
  "job_id": "uuid",
  "status": "pending",
  "status_url": "/v2/search/{job_id}/status",
  "results_url": "/v2/search/{job_id}/results"
}
```

**GET `/v2/search/history`:**
```json
{
  "jobs": [
    {
      "job_id": "uuid",
      "query": "...",
      "status": "completed",
      "total_results": 12,
      "aggregate_confidence": {"level": "high", "score": 0.78},
      "created_at": "2026-04-12T..."
    }
  ],
  "total": 47,
  "page": 1,
  "per_page": 20
}
```

---

## 7. File Structure

```
app/search_engine/
├── __init__.py
├── auth.py                 # JWT decode, require_jwt dependency, stub token issuer
├── executor.py             # AsyncioSearchExecutor (submit, cancel, status)
├── grading.py              # Heuristic scorer, LLM confidence assessor
├── feedback.py             # Feedback storage, domain score updates, episodic recall
├── reports.py              # Summary/conclusion generation + caching
├── schemas.py              # Pydantic models for all request/response shapes
├── db.py                   # Async DB helpers (asyncpg connection, table creation)
├── qdrant.py               # search_results collection setup, embed+upsert, similarity search
├── domain_tiers.py         # Default domain reputation map
├── router.py               # FastAPI router with all /v2/search/* endpoints
└── plugins/
    ├── __init__.py          # PluginRegistry
    ├── base.py              # SearchPlugin protocol, PluginResult dataclass
    ├── ddg.py
    ├── wikipedia.py
    └── google_rss.py
```

---

## 8. New Dependencies

| Package | Purpose |
|---------|---------|
| `asyncpg` | Async PostgreSQL driver for search_engine module |
| `httpx` | Async HTTP client for plugins and callbacks |
| `PyJWT` | JWT token encode/decode |
| `feedparser` | Google News RSS parsing (google_rss plugin) |

---

## 9. Environment Variables (new)

| Variable | Purpose | Default |
|----------|---------|---------|
| `JWT_SECRET` | HS256 signing key for JWT tokens | (required) |
| `JWT_EXPIRY_HOURS` | Token lifetime | `24` |
| `SEARCH_DEFAULT_BUDGET` | Default max total results per search | `5` |
| `SEARCH_MAX_BUDGET` | Hard cap on budget | `20` |
| `SEARCH_DEFAULT_DEEP` | Deep search default | `false` |

---

## 10. Agent Interaction Pattern

Agents interact exclusively through the API — never touch Qdrant or Postgres directly.

```
User → Agent → POST /v2/search (gets job_id)
                    ↓
              Poll GET /v2/search/{job_id}/status (or receive callback)
                    ↓
              GET /v2/search/{job_id}/results?format=list|summary|conclusion
                    ↓
              Agent constructs answer for user
```

For cross-referencing past research: `POST /v2/search/similar` returns semantically related results from the user's history, all behind the API.
