# Memory Phase 3: Curation & Contradiction Detection — Design Spec

**Date:** 2026-05-08
**Status:** Draft
**Depends on:** Memory Phase 1 (retrieval fusion), Memory Phase 2 (procedural memory), Knowledge Graph (event store + Neo4j)

---

## Problem

The knowledge graph accumulates entity observations from multiple research runs over time. When different runs produce conflicting facts about the same entity (e.g., "CEO" vs "VP Sales" for the same person's role), the system has no mechanism to detect, flag, or resolve these contradictions. Similarly, observations become stale as the real world changes — a person's role from 6 months ago may no longer be accurate.

Without curation, the KG degrades silently. The IS brain retrieves contradictory facts and presents them as equally valid, eroding trust in research output.

## Solution

A background **Curator** service that periodically sweeps the `entity_observations` event store to:

1. **Detect contradictions** — same entity + same attribute, different normalized values
2. **Detect staleness** — observations past their attribute-type TTL
3. **Auto-resolve** — pick the canonical value by confidence + recency
4. **Persist results** — store in `kg_contradictions` and `kg_stale_flags` tables

## Architecture

### Trigger model: Background sweep

The Curator runs as an asyncio background task on a configurable interval (default: 10 minutes). It is idempotent — re-running produces the same results. Zero impact on research run latency.

### New files

| File | Purpose |
|------|---------|
| `app/knowledge/normalizer.py` | Value normalization rules per attribute type |
| `app/knowledge/curator.py` | Background sweep: contradiction + staleness detection + auto-resolution |
| `app/routers/v3/curation_api.py` | REST API for contradictions, stale flags, manual resolution |
| `tests/knowledge/test_normalizer.py` | Unit tests for normalizer |
| `tests/knowledge/test_curator.py` | Unit + integration tests for curator |

### Modified files

| File | Change |
|------|--------|
| `app/routers/v3/db.py` | Add `kg_contradictions` and `kg_stale_flags` tables |
| `app/main.py` | Register curation router, start background curator task |
| `mcp_server/server.py` | Add `curate_knowledge` tool |

### Data flow

```
entity_observations (event store)
        |
        v
  Curator (background, every 10 min)
   |-- normalize values (normalizer.py)
   |-- self-join: same entity_ref + attribute, different normalized_value
   |-- auto-resolve: highest confidence + most recent wins
   |-- detect stale: observed_at > TTL for attribute_type
        |
        v
  kg_contradictions + kg_stale_flags (PG tables)
        |
        v
  REST API: /v3/knowledge/contradictions, /v3/knowledge/stale
  MCP tool: curate_knowledge
```

---

## Normalization Layer

`app/knowledge/normalizer.py` — pure functions that canonicalize observation values before comparison.

### Rules by attribute type

| Attribute | Normalization |
|-----------|--------------|
| `name` | Strip whitespace, title case, remove honorifics (Mr/Mrs/Dr/Prof) |
| `role`, `title` | Lowercase, map synonyms (ceo = chief executive officer, cto = chief technology officer, vp = vice president, coo = chief operating officer, cfo = chief financial officer) |
| `email` | Lowercase, strip whitespace |
| `phone` | Strip non-digits, normalize to E.164 where possible |
| `location` | Lowercase, strip "city of", normalize country codes (PH = Philippines, US = United States, UK = United Kingdom) |
| `url` | Lowercase, strip trailing slash, remove www. prefix, remove protocol |
| Default | Lowercase, strip whitespace |

### API

```python
def normalize_value(attribute: str, value: str) -> str:
    """Return the normalized form of value for the given attribute type."""

def values_equivalent(attribute: str, value_a: str, value_b: str) -> bool:
    """Return True if two values are equivalent after normalization."""
```

The synonym map is a plain Python dict (~30 entries). No external dependencies.

---

## Contradiction Detection

### Core query

Self-join `entity_observations` to find conflicting attribute values:

```sql
SELECT a.id AS id_a, b.id AS id_b,
       a.entity_ref, a.attribute,
       a.value AS value_a, a.confidence AS conf_a,
       a.observed_at AS at_a, a.source_run_id AS run_a, a.source_tool AS tool_a,
       b.value AS value_b, b.confidence AS conf_b,
       b.observed_at AS at_b, b.source_run_id AS run_b, b.source_tool AS tool_b
FROM entity_observations a
JOIN entity_observations b
  ON a.entity_ref = b.entity_ref
 AND a.attribute = b.attribute
 AND a.id < b.id
WHERE a.value != b.value
  AND a.observed_at > now() - interval '1 year'
  AND b.observed_at > now() - interval '1 year'
```

### Post-processing in Python

1. Normalize both values via `normalizer.py`
2. If `values_equivalent(attribute, value_a, value_b)` is True: skip (formatting difference, not a contradiction)
3. If normalized values differ: genuine contradiction
4. Check if this contradiction already exists in `kg_contradictions` (by entity_ref + attribute + sorted values): skip if already tracked
5. Auto-resolve or flag for review

### Auto-resolution logic

```python
def pick_winner(conf_a: int, at_a: datetime, conf_b: int, at_b: datetime) -> str:
    """Return 'a' or 'b' as the winner.
    
    - Confidence gap >= 15: higher confidence wins (status: auto_resolved)
    - Confidence gap < 15: more recent wins (status: auto_resolved)
    - Same confidence AND within 7 days of each other: needs_review
    """
```

Resolution statuses:
- `auto_resolved` — system picked a winner automatically
- `needs_review` — confidence too close, timestamps too close, needs human input
- `user_resolved` — human manually picked a winner
- `dismissed` — human marked as not a real contradiction

---

## Staleness Detection

### TTL configuration

| Attribute | Default TTL (days) | Rationale |
|-----------|--------------------|-----------|
| `role`, `title` | 180 | People change jobs frequently |
| `company` | 365 | Company affiliations change |
| `email` | 365 | Email addresses can go stale |
| `phone` | 180 | Numbers change |
| `location` | 365 | People/companies relocate |
| `name` | 0 (never) | Names rarely change |
| Default | 365 | Safe default |

TTLs are stored as a Python dict in `curator.py`. Can be made configurable via `core_settings` later.

### Detection logic

```sql
SELECT entity_ref, attribute, value, observed_at, confidence
FROM entity_observations
WHERE attribute = %s
  AND observed_at < now() - interval '%s days'
  AND entity_ref NOT IN (
    -- Exclude entities that have a recent observation for the same attribute
    SELECT entity_ref FROM entity_observations
    WHERE attribute = %s AND observed_at >= now() - interval '%s days'
  )
```

Run once per attribute type. If the entity has NO recent observation for that attribute, it's stale.

### Deduplication

Before inserting a stale flag, check if one already exists for (entity_ref, attribute) with status = 'stale'. If so, skip.

---

## Database Schema

### `kg_contradictions`

```sql
CREATE TABLE IF NOT EXISTS kg_contradictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref VARCHAR(512) NOT NULL,
    attribute VARCHAR(128) NOT NULL,
    value_a TEXT NOT NULL,
    value_b TEXT NOT NULL,
    confidence_a INT NOT NULL DEFAULT 50,
    confidence_b INT NOT NULL DEFAULT 50,
    observed_at_a TIMESTAMPTZ,
    observed_at_b TIMESTAMPTZ,
    source_run_a UUID,
    source_run_b UUID,
    observation_id_a UUID,
    observation_id_b UUID,
    winner TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'auto_resolved',
    resolved_by VARCHAR(64) DEFAULT 'system',
    resolved_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_contradictions_entity ON kg_contradictions (entity_ref);
CREATE INDEX IF NOT EXISTS idx_contradictions_status ON kg_contradictions (status);
CREATE INDEX IF NOT EXISTS idx_contradictions_created ON kg_contradictions (created_at DESC);
```

### `kg_stale_flags`

```sql
CREATE TABLE IF NOT EXISTS kg_stale_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref VARCHAR(512) NOT NULL,
    attribute VARCHAR(128) NOT NULL,
    current_value TEXT,
    observation_id UUID,
    observed_at TIMESTAMPTZ,
    ttl_days INT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'stale',
    flagged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dismissed_by VARCHAR(64),
    dismissed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_stale_entity ON kg_stale_flags (entity_ref);
CREATE INDEX IF NOT EXISTS idx_stale_status ON kg_stale_flags (status);
```

---

## API Endpoints

All endpoints require authentication.

### Contradictions

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v3/knowledge/contradictions` | List contradictions. Query params: `status` (filter), `entity_ref` (filter), `limit` (default 50), `offset` |
| `POST` | `/v3/knowledge/contradictions/{id}/resolve` | Manual resolution. Body: `{"winner": "the correct value"}`. Sets status to `user_resolved`. |
| `POST` | `/v3/knowledge/contradictions/{id}/dismiss` | Mark as not a real contradiction. Sets status to `dismissed`. |

### Stale flags

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v3/knowledge/stale` | List stale flags. Query params: `status`, `attribute`, `entity_ref`, `limit`, `offset` |
| `POST` | `/v3/knowledge/stale/{id}/dismiss` | Mark stale flag as acceptable. Sets status to `dismissed`. |

### Curation stats

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v3/knowledge/curation/stats` | Summary: `{contradictions_total, contradictions_unresolved, stale_total, stale_active, last_sweep_at}` |

---

## MCP Tool

### `curate_knowledge`

Returns curation stats + recent unresolved contradictions so the IS brain can factor KG quality into research decisions.

```python
@server.tool()
async def curate_knowledge() -> dict:
    """Get knowledge graph curation status — contradictions and stale observations."""
    return {
        "contradictions_total": ...,
        "contradictions_unresolved": ...,
        "stale_total": ...,
        "recent_contradictions": [...],  # up to 10 unresolved
        "recent_stale": [...],           # up to 10 active stale flags
    }
```

---

## Background Task Integration

In `app/main.py`, register the curator as a startup background task:

```python
@app.on_event("startup")
async def start_curator():
    from app.knowledge.curator import run_curator_loop
    asyncio.create_task(run_curator_loop(interval_seconds=600))
```

The `run_curator_loop` function:
1. Waits `interval_seconds`
2. Calls `detect_contradictions()` — scans observations, inserts/updates `kg_contradictions`
3. Calls `detect_staleness()` — scans observations per attribute type, inserts `kg_stale_flags`
4. Logs summary: "Curator sweep: X new contradictions, Y auto-resolved, Z stale flags"
5. Repeats

---

## Testing Strategy

### Unit tests (`tests/knowledge/test_normalizer.py`)
- Test each attribute type normalization (name, role, email, phone, location, url)
- Test synonym mapping (ceo = chief executive officer)
- Test `values_equivalent()` for true/false cases
- Test edge cases: empty strings, None, unicode

### Unit tests (`tests/knowledge/test_curator.py`)
- Test `pick_winner()` logic: confidence gap >= 15, < 15, equal
- Test contradiction deduplication (same pair not inserted twice)
- Test staleness TTL per attribute type
- Test stale flag deduplication

### Integration tests
- Insert 2 conflicting observations for same entity+attribute
- Run `detect_contradictions()`
- Assert: contradiction row created with correct winner and status
- Insert old observation (> TTL)
- Run `detect_staleness()`
- Assert: stale flag created

---

## Scope Boundaries

**In scope:**
- Background contradiction detection via SQL sweep + normalization
- Auto-resolution by confidence + recency
- Staleness detection with per-attribute TTLs
- REST API for listing/resolving contradictions and stale flags
- MCP tool for IS brain awareness
- PG tables for persistence

**Out of scope (future phases):**
- Frontend UI for curation (can use API directly or build in Phase 4)
- LLM-assisted resolution (Phase 5: LLM-Assisted Memory Ops)
- Automatic re-research of stale entities (Phase 4: Tiered Lifecycle)
- Embedding-based semantic contradiction detection (upgrade path if needed)
- Neo4j graph updates based on resolution (materializer already handles this via event store)
