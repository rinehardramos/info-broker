# Memory Phase 3: Curation and Contradiction Detection - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Detect and auto-resolve contradictory entity observations in the knowledge graph, flag stale facts, and expose curation via REST API + MCP tool.

**Architecture:** A background Curator sweeps entity_observations via SQL self-join, normalizes values to catch formatting differences, auto-resolves by confidence + recency, and persists results to kg_contradictions + kg_stale_flags tables. A REST API + MCP tool expose curation state.

**Tech Stack:** Python, PostgreSQL (self-join queries), FastAPI (REST API), asyncio (background loop)

---

### Task 1: Database Schema -- kg_contradictions + kg_stale_flags

**Files:**
- Modify: `app/routers/v3/db.py` (insert after graph_materializer_state, before mcp_sessions)

- [ ] **Step 1: Add the two new tables to the migration string**

Find `CREATE TABLE IF NOT EXISTS mcp_sessions (` and insert before it:

```sql
CREATE TABLE IF NOT EXISTS kg_contradictions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref      VARCHAR(512) NOT NULL,
    attribute       VARCHAR(128) NOT NULL,
    value_a         TEXT NOT NULL,
    value_b         TEXT NOT NULL,
    confidence_a    INT NOT NULL DEFAULT 50,
    confidence_b    INT NOT NULL DEFAULT 50,
    observed_at_a   TIMESTAMPTZ,
    observed_at_b   TIMESTAMPTZ,
    source_run_a    UUID,
    source_run_b    UUID,
    observation_id_a UUID,
    observation_id_b UUID,
    winner          TEXT,
    status          VARCHAR(32) NOT NULL DEFAULT 'auto_resolved',
    resolved_by     VARCHAR(64) DEFAULT 'system',
    resolved_at     TIMESTAMPTZ DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_contradictions_entity ON kg_contradictions(entity_ref);
CREATE INDEX IF NOT EXISTS idx_contradictions_status ON kg_contradictions(status);
CREATE INDEX IF NOT EXISTS idx_contradictions_created ON kg_contradictions(created_at DESC);

CREATE TABLE IF NOT EXISTS kg_stale_flags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref      VARCHAR(512) NOT NULL,
    attribute       VARCHAR(128) NOT NULL,
    current_value   TEXT,
    observation_id  UUID,
    observed_at     TIMESTAMPTZ,
    ttl_days        INT NOT NULL,
    status          VARCHAR(32) NOT NULL DEFAULT 'stale',
    flagged_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    dismissed_by    VARCHAR(64),
    dismissed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_stale_entity ON kg_stale_flags(entity_ref);
CREATE INDEX IF NOT EXISTS idx_stale_status ON kg_stale_flags(status);
```

- [ ] **Step 2: Rebuild and verify tables exist**

- [ ] **Step 3: Commit**

```bash
git add app/routers/v3/db.py
git commit -m "schema: add kg_contradictions and kg_stale_flags tables"
```

---

### Task 2: Value Normalizer (TDD)

**Files:**
- Create: `[REDACTED:high-entropy-base64:24ch:hash=d2e06be8].py`
- Test: `[REDACTED:high-entropy-base64:31ch:hash=ba8d9077].py`

- [ ] **Step 1: Write failing tests**

Create test file with tests for: normalize_value (name, role, title, email, phone, location, default), values_equivalent (true + false cases). Key assertions:
- `normalize_value("name", "  john DOE  ") == "John Doe"`
- `normalize_value("name", "Dr. Jane Smith") == "Jane Smith"`
- `normalize_value("role", "CEO") == "chief executive officer"`
- `normalize_value("role", "VP of Sales") == "vice president of sales"`
- `normalize_value("email", "  John@Example.COM  ") == "john@example.com"`
- `normalize_value("phone", "+1-555-123-4567") == "15551234567"`
- `normalize_value("location", "City of Manila") == "manila"`
- `normalize_value("location", "New York, US") == "new york, united states"`
- `values_equivalent("role", "CEO", "Chief Executive Officer") is True`
- `values_equivalent("role", "CEO", "VP Sales") is False`
- `values_equivalent("email", "  JOHN@Example.COM  ", "john@example.com") is True`

Stub heavy deps (psycopg2) before imports as per test_signals.py pattern.

- [ ] **Step 2: Run tests -- verify FAIL** (module not found)

- [ ] **Step 3: Implement normalizer**

Pure-function module with:
- `_HONORIFICS` regex to strip Mr/Mrs/Dr/Prof prefixes
- `_ROLE_SYNONYMS` dict (~16 entries: ceo, cto, cfo, coo, cmo, cio, vp, svp, evp, avp, md, gm, etc.)
- `_COUNTRY_CODES` dict (~14 entries: ph, us, uk, sg, au, ca, de, fr, jp, kr, in, cn, hk)
- `normalize_value(attribute, value) -> str` dispatches by attribute type
- `values_equivalent(attribute, value_a, value_b) -> bool` compares normalized forms

- [ ] **Step 4: Run tests -- verify PASS**

- [ ] **Step 5: Commit**

```bash
git add [REDACTED:high-entropy-base64:24ch:hash=d2e06be8].py [REDACTED:high-entropy-base64:31ch:hash=ba8d9077].py
git commit -m "feat(curation): add value normalizer with role synonyms, country codes, honorific stripping"
```

---

### Task 3: Curator -- Contradiction Detection + Auto-Resolution (TDD)

**Files:**
- Create: `[REDACTED:high-entropy-base64:21ch:hash=ac246c2d].py`
- Test: `tests/knowledge/test_curator.py`

- [ ] **Step 1: Write failing tests**

Tests for:
- `pick_winner(90, now, 60, now)` -> ("a", "auto_resolved") -- high confidence gap
- `pick_winner(50, now, 80, now)` -> ("b", "auto_resolved") -- b has higher confidence
- `pick_winner(80, old, 75, new)` -> ("b", "auto_resolved") -- close conf, recent wins
- `pick_winner(80, t1, 80, t2)` where t2 is 2 days after t1 -> ("b", "needs_review") -- same conf, close dates
- `detect_contradictions()` with mocked DB returning conflicting role values -> inserts into kg_contradictions
- `detect_contradictions()` with CEO vs "Chief Executive Officer" -> skips (equivalent after normalization)
- `detect_contradictions()` with already-tracked contradiction -> skips
- `detect_staleness()` with old observation -> flags as stale
- `STALENESS_TTL["name"] == 0` (never stale)

Mock `fetch_all`, `fetch_one`, `execute` from `app.knowledge.curator` module.

- [ ] **Step 2: Run tests -- verify FAIL**

- [ ] **Step 3: Implement curator**

Module with:
- `STALENESS_TTL` dict (role=180, title=180, company=365, email=365, phone=180, location=365, name=0)
- `pick_winner(conf_a, at_a, conf_b, at_b) -> (winner, status)` -- gap>=15: confidence wins; <15: recent wins; same conf + <7 days: needs_review
- `detect_contradictions() -> dict` -- SQL self-join on entity_observations, normalize + filter, dedup, auto-resolve, insert to kg_contradictions
- `_fetch_stale_for_attribute(attribute, ttl_days) -> list[dict]` -- SQL query for stale observations
- `detect_staleness() -> dict` -- iterate STALENESS_TTL, fetch stale, dedup, insert to kg_stale_flags
- `run_curator_loop(interval_seconds=600)` -- asyncio background loop calling both functions

- [ ] **Step 4: Run tests -- verify PASS**

- [ ] **Step 5: Commit**

```bash
git add [REDACTED:high-entropy-base64:21ch:hash=ac246c2d].py tests/knowledge/test_curator.py
git commit -m "feat(curation): add curator with contradiction detection, auto-resolution, staleness"
```

---

### Task 4: Curation REST API

**Files:**
- Create: `app/routers/v3/curation_api.py`

- [ ] **Step 1: Create the curation API router**

Router with prefix `/v3/knowledge`, tag `v3-curation`. Endpoints:
- `GET /contradictions` -- list with status/entity_ref filters, limit/offset pagination
- `POST /contradictions/{id}/resolve` -- body: `{"winner": "value"}`, sets user_resolved
- `POST /contradictions/{id}/dismiss` -- sets dismissed status
- `GET /stale` -- list with status/attribute/entity_ref filters, limit/offset
- `POST /stale/{id}/dismiss` -- sets dismissed status
- `GET /curation/stats` -- returns {contradictions_total, contradictions_unresolved, stale_total, stale_active}

All endpoints use `Depends(get_current_user)` for auth. Follow knowledge_api.py patterns.

- [ ] **Step 2: Commit**

```bash
git add app/routers/v3/curation_api.py
git commit -m "feat(curation): add REST API for contradictions, stale flags, curation stats"
```

---

### Task 5: Wire Into App -- Router + Background Task

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Register router and background task**

Add import: `from app.routers.v3.curation_api import router as v3_curation_router`
Add include: `app.include_router(v3_curation_router)`

In lifespan, after materializer block, add curator background task:
```python
    try:
        from app.knowledge.curator import run_curator_loop
        _aio.create_task(run_curator_loop([REDACTED:high-entropy-base64:20ch:hash=9128e205]))
    except Exception as exc:
        _log.warning("KG curator not started: %s", exc)
```

- [ ] **Step 2: Verify endpoints accessible via OpenAPI spec**

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat(curation): register curation router and start background curator loop"
```

---

### Task 6: MCP Tool -- curate_knowledge

**Files:**
- Modify: `mcp_server/server.py`

- [ ] **Step 1: Add curate_knowledge tool**

```python
@mcp.tool()
async def curate_knowledge() -> str:
    """Get knowledge graph curation status -- contradictions and stale observations."""
    stats = await api_call("GET", "/v3/knowledge/curation/stats")
    contradictions = await api_call("GET", "/v3/knowledge/contradictions", params={"status": "needs_review", "limit": 10})
    stale = await api_call("GET", "/v3/knowledge/stale", params={"status": "stale", "limit": 10})
    result = {**stats, "recent_contradictions": contradictions[:10] if isinstance(contradictions, list) else [], "recent_stale": stale[:10] if isinstance(stale, list) else []}
    return json.dumps(result, default=str)
```

- [ ] **Step 2: Commit**

```bash
git add mcp_server/server.py
git commit -m "feat(curation): add curate_knowledge MCP tool"
```

---

### Task 7: Integration Test + Docker Deploy

- [ ] **Step 1: Run all unit tests**

`uv run pytest tests/ -q --tb=short --ignore=tests/v3 --ignore=tests/e2e`
Expected: 614+ existing + ~21 new, all pass

- [ ] **Step 2: Docker build and deploy**

`docker compose build info-broker-api && docker compose up -d info-broker-api`

- [ ] **Step 3: Verify curation stats API**

Call GET /v3/knowledge/curation/stats with auth token.
Expected: `{"contradictions_total": 0, "contradictions_unresolved": 0, "stale_total": 0, "stale_active": 0}`

- [ ] **Step 4: Verify MCP curate_knowledge tool**

Expected: Returns stats JSON.

- [ ] **Step 5: Push**

`git push origin main`
