# Memory Phase 4: Tiered Lifecycle

**Date:** 2026-05-08
**Status:** Draft
**Depends on:** Memory Phase 1-3, Knowledge Graph, Qdrant research_memory

---

## Problem

All entity observations and research findings have equal status regardless of age or usage. A 1-year-old observation about a person's role sits alongside today's fresh finding. As the KG grows, stale data pollutes retrieval, slows queries, and degrades research quality.

## Solution

Four-tier lifecycle (hot/warm/cold/archive) with automatic promotion/demotion based on age and access patterns. A background sweep manages transitions. Cold and archived data is excluded from default queries but preserved for on-demand access.

## Tiers

| Tier | Retrieval | Age threshold | Access threshold |
|------|-----------|---------------|------------------|
| **hot** | Always included | Default for new data | Accessed in last 30 days |
| **warm** | Included, ranked lower | >30 days old | No access in 30 days |
| **cold** | Excluded by default | >90 days old | No access in 60 days |
| **archive** | Excluded from all | >365 days old | No access in 180 days |

### Promotion rules
- Any tier + accessed in last 7 days -> promote to hot
- Cold + accessed -> promote to warm

### Demotion rules
- Hot + no access in 30 days + age >30 days -> warm
- Warm + no access in 60 days + age >90 days -> cold
- Cold + no access in 180 days + age >365 days -> archive

---

## Schema Changes

### entity_observations
```sql
ALTER TABLE entity_observations ADD COLUMN IF NOT EXISTS tier VARCHAR(8) DEFAULT 'hot';
ALTER TABLE entity_observations ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_entity_obs_tier ON entity_observations(tier);
```

### relationship_observations
```sql
ALTER TABLE relationship_observations ADD COLUMN IF NOT EXISTS tier VARCHAR(8) DEFAULT 'hot';
ALTER TABLE relationship_observations ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ;
```

### Qdrant research_memory
Add `tier` field to point payloads. New points default to `"hot"`. Lifecycle sweep updates tier in Qdrant when it changes in PG.

---

## Access Tracking

When retrieval signals read observations, batch-update `last_accessed_at`:

- After `fused_retrieve()` returns results, collect the run_ids/refs
- Batch UPDATE: `SET last_accessed_at = now() WHERE run_id IN (...) AND last_accessed_at < now() - interval '1 hour'`
- The 1-hour debounce prevents excessive writes from repeated queries

Tracked in: `app/memory/retriever.py` after fused_retrieve returns.

---

## Lifecycle Sweep

Background task running every 30 minutes (like curator). Processes in batches of 500 rows.

```python
async def run_lifecycle_sweep():
    # Demotions (process in order: hot->warm, warm->cold, cold->archive)
    demote("hot", "warm", age_days=30, idle_days=30)
    demote("warm", "cold", age_days=90, idle_days=60)
    demote("cold", "archive", age_days=365, idle_days=180)
    
    # Promotions (recently accessed data moves up)
    promote_recently_accessed(accessed_within_days=7, target_tier="hot")
```

Each demote/promote call:
1. SELECT matching rows (batched)
2. UPDATE tier in PG
3. Update tier in Qdrant payload (for research_memory points)

---

## Query Filtering

### PG queries (entity_observations, relationship_observations)
Add `AND tier IN ('hot', 'warm')` to all retrieval queries in:
- `app/memory/signals.py` (bm25_search, temporal_search, feedback_search)
- `app/knowledge/neo4j_client.py` (materializer only processes hot/warm)

### Qdrant queries
Add payload filter `tier IN ['hot', 'warm']` to:
- `app/memory/signals.py` (semantic_search)
- `app/routers/v3/sources_api.py` (query endpoint)
- `app/pipeline/nodes/qdrant_search.py`

### On-demand cold access
API endpoint `GET /v3/knowledge/entities/{ref}/all-observations` returns ALL tiers including cold/archive for explicit deep dives.

---

## New/Modified Files

### New
| File | Purpose |
|------|---------|
| `app/memory/lifecycle.py` | Tier sweep logic, promote/demote functions |
| `tests/memory/test_lifecycle.py` | Tier transition tests |

### Modified
| File | Change |
|------|--------|
| `app/routers/v3/db.py` | ALTER TABLE: add tier + last_accessed_at columns |
| `app/memory/signals.py` | Add tier filter to all PG + Qdrant queries |
| `app/memory/retriever.py` | Track access after fused_retrieve |
| `app/memory/writer.py` | Set tier='hot' on new points |
| `app/knowledge/materializer.py` | Only materialize hot/warm observations |
| `app/main.py` | Start lifecycle sweep background task |

---

## Testing

- New observations default to tier='hot'
- Observation >30 days old with no access demotes to warm
- Warm >90 days with no access demotes to cold
- Cold >365 days with no access demotes to archive
- Recently accessed cold observation promotes to hot
- Retrieval queries exclude cold/archive by default
- Access tracking updates last_accessed_at with debounce

---

## Scope

**In scope:** Tier columns, lifecycle sweep, query filtering, access tracking, Qdrant sync.

**Out of scope:** UI for tier management, manual tier override API, per-entity tier policies, archival to S3.
