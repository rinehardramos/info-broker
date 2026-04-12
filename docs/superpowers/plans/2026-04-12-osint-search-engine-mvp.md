# OSINT Search Engine MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working async OSINT search engine with pluggable sources, heuristic grading, and user feedback.

**Architecture:** New `app/search_engine/` package inside the existing FastAPI app. Async endpoints under `/v2/`. JWT auth (stub issuer). DDG as the sole search plugin. Results stored in Postgres (metadata) + Qdrant (vectors + text). Feedback stored but learning loop deferred.

**Tech Stack:** FastAPI (async), asyncpg, httpx, PyJWT, Qdrant, Pydantic v2, existing `llm_providers.py` for embeddings

**MVP Scope — IN:** DB schema (7 tables), JWT auth stub, Plugin base + DDG, SearchExecutor with parallel fan-out, Heuristic scoring, Endpoints (submit/status/results/history/feedback/cancel), Qdrant collection

**MVP Scope — OUT:** Deep search, summary/conclusion reports, episodic memory, domain reputation learning, Wikipedia/Google RSS plugins, similar search, callbacks, plugin config endpoints

**Spec:** `docs/superpowers/specs/2026-04-12-osint-search-engine-design.md`

---

## File Structure

```
app/search_engine/
├── __init__.py              # empty
├── auth.py                  # JWT encode/decode, require_jwt, stub issuer
├── schemas.py               # Pydantic request/response models
├── db.py                    # asyncpg pool, DDL, CRUD
├── qdrant.py                # search_results collection, embed+upsert, hydrate
├── domain_tiers.py          # Static domain reliability map
├── grading.py               # Heuristic scorer
├── executor.py              # AsyncioSearchExecutor
├── feedback.py              # Feedback storage
├── router.py                # /v2/ endpoints
└── plugins/
    ├── __init__.py           # PluginRegistry
    ├── base.py               # SearchPlugin protocol + PluginResult
    └── ddg.py                # DuckDuckGo plugin
tests/
└── test_search_engine.py
```

---

## Task 1: Add New Dependencies

**Files:** Modify `requirements.txt`

- [ ] **Step 1:** Append `asyncpg>=0.30.0`, `PyJWT>=2.10.0`, `feedparser>=6.0.11` to requirements.txt
- [ ] **Step 2:** Run `uv pip install asyncpg PyJWT feedparser`
- [ ] **Step 3:** Commit: `chore: add asyncpg, PyJWT, feedparser dependencies`

---

## Task 2: Pydantic Schemas

**Files:** Create `app/search_engine/__init__.py`, `app/search_engine/schemas.py`, `tests/test_search_engine.py`

- [ ] **Step 1:** Create empty `app/search_engine/__init__.py`

- [ ] **Step 2:** Write schema tests in `tests/test_search_engine.py`. Test classes: `TestSchemas` covering SearchRequest defaults, empty query rejection, budget clamping to MAX_BUDGET=20, feedback range validation (1-5), TokenRequest, SearchResultItem shape, SearchJobStatus enum values.

- [ ] **Step 3:** Run tests — expect FAIL (module not found)

- [ ] **Step 4:** Implement `app/search_engine/schemas.py` with these models:
  - `SearchJobStatus` (str enum: pending/running/completed/failed/cancelled)
  - `TokenRequest` (username: str, min 1, max 128)
  - `TokenResponse` (access_token, token_type="bearer", expires_in)
  - `SearchRequest` (query min 1 max 1000, deep_search=False, max_parallel=None, max_budget=5 clamped to 20, plugins=None, callback_url=None)
  - `SearchSubmitResponse` (job_id, status, status_url, results_url)
  - `SearchJobResponse` (job_id, status, query, total_results, started_at, completed_at, error)
  - `SearchResultItem` (id, plugin, title, url, snippet, published_at, is_deep_child, scores dict, feedback dict|None)
  - `SearchResultsResponse` (job_id, query, status, total_results, results list, aggregate_confidence)
  - `SearchHistoryItem` (job_id, query, status, total_results, aggregate_confidence, created_at)
  - `SearchHistoryResponse` (jobs list, total, page, per_page)
  - `SearchFeedbackRequest` (interest 1-5, relevance 1-5, usefulness 1-5, comment)
  - `SearchFeedbackResponse` (id, result_id, saved)

- [ ] **Step 5:** Run tests — expect PASS
- [ ] **Step 6:** Commit: `feat(search-engine): add Pydantic schemas`

---

## Task 3: JWT Auth Stub

**Files:** Create `app/search_engine/auth.py`, append to `tests/test_search_engine.py`

- [ ] **Step 1:** Write auth tests: `TestAuth` — create and decode roundtrip, expired token raises, invalid token raises, missing JWT_SECRET raises ValueError

- [ ] **Step 2:** Run tests — expect FAIL

- [ ] **Step 3:** Implement `app/search_engine/auth.py`:
  - `DUMMY_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")`
  - `ALGORITHM = "HS256"`, `ISSUER = "info-broker-dev"`
  - `_get_secret()` — reads `JWT_SECRET` env, raises ValueError if empty
  - `create_token(username, expiry_hours=None)` — HS256 JWT with sub=DUMMY_USER_ID, username, iss, iat, exp
  - `decode_token(token)` — verify and return payload
  - `require_jwt(authorization: Header)` — FastAPI dependency, extracts Bearer token, returns decoded payload, raises 401 on failure

- [ ] **Step 4:** Run tests — expect PASS
- [ ] **Step 5:** Commit: `feat(search-engine): add JWT auth stub`

---

## Task 4: Database Layer (asyncpg)

**Files:** Create `app/search_engine/db.py`, append to `tests/test_search_engine.py`

- [ ] **Step 1:** Write DB tests: `TestDb` — test `build_dsn()` includes db name and port from env vars, test `SEARCH_TABLES_DDL` contains all 7 table names

- [ ] **Step 2:** Run tests — expect FAIL

- [ ] **Step 3:** Implement `app/search_engine/db.py`:
  - `SEARCH_TABLES_DDL` — SQL string with CREATE TABLE IF NOT EXISTS for all 7 tables (search_users, search_jobs, search_results, search_reports, search_feedback, search_plugins_config, search_domain_scores) plus indexes. See spec Section 1 for column definitions. All use parameterized queries ($1, $2 style).
  - `build_dsn()` — assembles asyncpg DSN from env vars (POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT)
  - `get_pool()` / `close_pool()` — asyncpg pool lifecycle (min=2, max=10)
  - `run_migrations()` — execute DDL via pool
  - `ensure_user(username)` — SELECT or INSERT into search_users, return UUID
  - `create_job(user_id, query, config)` — INSERT search_jobs, return job_id
  - `update_job_status(job_id, status, error=None)` — UPDATE with appropriate timestamps
  - `get_job(job_id)` — SELECT * as dict
  - `get_job_result_count(job_id)` — SELECT count(*)
  - `insert_result(...)` — INSERT search_results, return result_id
  - `get_results_for_job(job_id)` — SELECT ordered by composite score desc
  - `get_user_jobs(user_id, page, per_page)` — paginated with total count
  - `insert_feedback(...)` — INSERT search_feedback, return feedback_id
  - `get_feedback_for_result(result_id)` — SELECT all feedback rows

- [ ] **Step 4:** Run tests — expect PASS
- [ ] **Step 5:** Commit: `feat(search-engine): add async DB layer with asyncpg`

---

## Task 5: Plugin Base + DDG Plugin

**Files:** Create `app/search_engine/plugins/__init__.py`, `plugins/base.py`, `plugins/ddg.py`, append tests

- [ ] **Step 1:** Write tests: `TestPluginBase` (PluginResult creation, DdgPlugin attributes, registry discover/get), `TestDdgPlugin` (mocked DDGS returns results, handles failure gracefully)

- [ ] **Step 2:** Run tests — expect FAIL

- [ ] **Step 3:** Implement `plugins/base.py`:
  - `PluginResult` dataclass (title, url, snippet, full_text, published_at, source_name, metadata)
  - `SearchPlugin` runtime_checkable Protocol (name, description, requires_api_key, search async method, available method)

- [ ] **Step 4:** Implement `plugins/ddg.py`:
  - `DdgPlugin` class with name="ddg", requires_api_key=False
  - `search()` — async, delegates to `_search_sync` via `run_in_executor`
  - `_search_sync()` — uses `DDGS().text()`, maps hits to PluginResult
  - `_try_scrape()` — best-effort via existing `app.lib.ddg_fallback.scrape_url`

- [ ] **Step 5:** Implement `plugins/__init__.py`:
  - `PluginRegistry` class with `auto_discover()`, `get(name)`, `available()`, `all()`
  - `_load_plugins()` — imports DdgPlugin, returns list of classes

- [ ] **Step 6:** Run tests — expect PASS
- [ ] **Step 7:** Commit: `feat(search-engine): add plugin protocol, DDG plugin, and registry`

---

## Task 6: Domain Tiers + Heuristic Grading

**Files:** Create `app/search_engine/domain_tiers.py`, `grading.py`, append tests

- [ ] **Step 1:** Write tests: `TestDomainTiers` (tier1=1.0, tier2=0.8, unknown=0.4, subdomain matches parent, None=0.4), `TestGrading` (freshness today=1.0, 7 days ~0.5, None=0.3, relevance high/low overlap, score_result returns all 4 keys in 0-1 range)

- [ ] **Step 2:** Run tests — expect FAIL

- [ ] **Step 3:** Implement `domain_tiers.py`:
  - `_DOMAIN_TIERS` dict: tier1 (reuters, apnews, wikipedia, gov sites) = 1.0, tier2 (bbc, nytimes, etc) = 0.8, tier3 (medium, reddit, etc) = 0.6
  - `DEFAULT_SCORE = 0.4`
  - `_extract_root_domain(hostname)` — handles subdomains and co.uk style TLDs
  - `get_domain_reliability(url_or_domain)` — accepts URL or bare domain, returns float

- [ ] **Step 4:** Implement `grading.py`:
  - Weights: relevance=0.4, freshness=0.3, reliability=0.3
  - `relevance_score(query, text)` — token overlap with substring boost
  - `freshness_score(published_at)` — exponential decay, None=0.3
  - `score_result(query, title, snippet, url, published_at)` — returns dict with all 4 scores

- [ ] **Step 5:** Run tests — expect PASS
- [ ] **Step 6:** Commit: `feat(search-engine): add domain tiers and heuristic scoring`

---

## Task 7: Qdrant Integration

**Files:** Create `app/search_engine/qdrant.py`, append tests

- [ ] **Step 1:** Write tests: `TestQdrant` — build_embedding_text joins fields, truncates to ~4100 chars, handles None full_text

- [ ] **Step 2:** Run tests — expect FAIL

- [ ] **Step 3:** Implement `qdrant.py`:
  - `COLLECTION = "search_results"`, `VECTOR_DIM = 768`
  - `_client()` — QdrantClient from QDRANT_HOST/PORT env
  - `ensure_collection()` — create if not exists (768-dim cosine)
  - `build_embedding_text(title, snippet, full_text)` — join with newlines, truncate full_text to 4000
  - `upsert_result(result_id, job_id, user_id, plugin, title, url, snippet, full_text)` — embed via llm_providers, upsert point
  - `get_result_payload(result_id)` — retrieve single point
  - `get_results_payloads(result_ids)` — batch retrieve, returns {result_id: payload}

- [ ] **Step 4:** Run tests — expect PASS
- [ ] **Step 5:** Commit: `feat(search-engine): add Qdrant integration`

---

## Task 8: Search Executor

**Files:** Create `app/search_engine/executor.py`, append tests

- [ ] **Step 1:** Write tests: `TestExecutorHelpers` — deduplicate by URL (first wins, None kept), empty list

- [ ] **Step 2:** Run tests — expect FAIL

- [ ] **Step 3:** Implement `executor.py`:
  - `_deduplicate_results(results)` — dedup by normalized URL, first wins, None URLs kept
  - `get_registry()` — lazy singleton PluginRegistry
  - `AsyncioSearchExecutor`:
    - `submit(query, config, user_id)` — create DB job, spawn asyncio.create_task, return job_id
    - `cancel(job_id)` — cancel task, update DB
    - `_execute(job_id, query, config, user_id)` — background task: update status→running, get plugins, fan-out with asyncio.gather+Semaphore, flatten, dedup, cap at budget, score each result, insert to DB, upsert to Qdrant (best-effort), update status→completed. Handle CancelledError→cancelled, Exception→failed.

- [ ] **Step 4:** Run tests — expect PASS
- [ ] **Step 5:** Commit: `feat(search-engine): add AsyncioSearchExecutor`

---

## Task 9: Feedback Storage

**Files:** Create `app/search_engine/feedback.py`, append tests

- [ ] **Step 1:** Write tests: `TestFeedback` — verify function signatures exist

- [ ] **Step 2:** Run tests — expect FAIL

- [ ] **Step 3:** Implement `feedback.py`:
  - `validate_feedback_ownership(result_id, user_id)` — JOIN search_results→search_jobs, check user_id matches
  - `save_feedback(result_id, user_id, interest, relevance, usefulness, comment)` — delegates to db.insert_feedback

- [ ] **Step 4:** Run tests — expect PASS
- [ ] **Step 5:** Commit: `feat(search-engine): add feedback storage`

---

## Task 10: FastAPI Router + Wire Into App

**Files:** Create `app/search_engine/router.py`, modify `app/main.py`, append tests

- [ ] **Step 1:** Write router tests: `TestRouter` — submit returns 202 with job_id (mock executor+db), requires auth, token endpoint works, status endpoint returns job info (mock db)

- [ ] **Step 2:** Run tests — expect FAIL

- [ ] **Step 3:** Implement `router.py` with `APIRouter(prefix="/v2", tags=["search-engine"])`:
  - `POST /v2/auth/token` — mint JWT, no auth required
  - `POST /v2/search` — submit job (202), JWT required
  - `GET /v2/search/{job_id}/status` — poll status, JWT + ownership
  - `GET /v2/search/{job_id}/results` — list results, hydrate from Qdrant, JWT + ownership
  - `POST /v2/search/{job_id}/cancel` — cancel, JWT + ownership
  - `GET /v2/search/history` — paginated user history, JWT
  - `POST /v2/search/{job_id}/results/{result_id}/feedback` — store feedback, JWT + ownership

- [ ] **Step 4:** Wire into `app/main.py`:
  - Import and include `search_engine_router`
  - In lifespan: call `run_migrations()` (async) and `ensure_collection()` after existing psycopg2 migrations
  - On shutdown: call `close_pool()`

- [ ] **Step 5:** Run search engine tests — expect PASS
- [ ] **Step 6:** Run ALL tests — expect no regressions
- [ ] **Step 7:** Commit: `feat(search-engine): add /v2/ router and wire into app`

---

## Task 11: E2E Smoke Test

**Files:** Append to `tests/test_search_engine.py`

- [ ] **Step 1:** Write `TestE2EFlow` — mocks DB and Qdrant, verifies all modules import and wire together: schema construction, grading produces correct scores for known domains, plugin registry discovers DDG, token creation works

- [ ] **Step 2:** Run — expect PASS
- [ ] **Step 3:** Run full suite — expect all PASS
- [ ] **Step 4:** Commit: `test(search-engine): add E2E smoke test`

---

## Task 12: Manual Verification Against Live Services

Requires Docker (Postgres + Qdrant) running.

- [ ] **Step 1:** `docker compose up -d`
- [ ] **Step 2:** Start app with JWT_SECRET set, verify migrations run
- [ ] **Step 3:** POST `/v2/auth/token` — get a token
- [ ] **Step 4:** POST `/v2/search` with Bearer token — submit a search, get job_id
- [ ] **Step 5:** GET `/v2/search/{job_id}/status` — wait for completed
- [ ] **Step 6:** GET `/v2/search/{job_id}/results` — verify results with scores
- [ ] **Step 7:** Fix any issues, commit
