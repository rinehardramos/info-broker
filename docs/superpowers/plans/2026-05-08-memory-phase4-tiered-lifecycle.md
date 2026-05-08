# Memory Phase 4: Tiered Lifecycle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add hot/warm/cold/archive tiers to entity observations and research memory with automatic promotion/demotion based on age and access patterns.

**Architecture:** New tier + last_accessed_at columns on PG tables. Background lifecycle sweep every 30 min. All retrieval queries filter by tier. Access tracking in the retriever with debounce.

**Tech Stack:** Python, PostgreSQL, Qdrant, asyncio

---

### Task 1: Schema + Lifecycle Module (TDD)

**Files:**
- Modify: `app/routers/v3/db.py`
- Create: `app/memory/lifecycle.py`
- Create: `tests/memory/test_lifecycle.py`

- [ ] Add ALTER TABLE statements for tier + last_accessed_at on entity_observations and relationship_observations. Add index on tier.
- [ ] Write failing tests for lifecycle functions:
  - `get_tier_thresholds()` returns dict with age_days and idle_days per transition
  - `demote_tier("hot", "warm", age_days=30, idle_days=30)` with mocked DB returns count of demoted rows
  - `promote_recently_accessed(accessed_within_days=7)` with mocked DB returns count
  - `run_lifecycle_sweep()` calls demote 3 times + promote once
- [ ] Implement lifecycle.py with demote/promote functions and sweep loop
- [ ] Run tests -- verify PASS
- [ ] Commit

---

### Task 2: Query Filtering

**Files:**
- Modify: `app/memory/signals.py`
- Modify: `app/memory/retriever.py`

- [ ] In signals.py: add `AND tier IN ('hot', 'warm')` to bm25_search, temporal_search, feedback_search PG queries
- [ ] In signals.py: add tier payload filter to semantic_search Qdrant query
- [ ] In retriever.py: after fused_retrieve returns, batch-update last_accessed_at for returned results (with 1-hour debounce)
- [ ] In writer.py: set tier='hot' in Qdrant payload for new points
- [ ] Run tests
- [ ] Commit

---

### Task 3: Wire Background Task + Deploy

**Files:**
- Modify: `app/main.py`
- Modify: `app/knowledge/materializer.py`

- [ ] Start lifecycle sweep in main.py lifespan (after curator)
- [ ] In materializer: add tier filter to only process hot/warm observations
- [ ] Run all tests
- [ ] Docker build and deploy
- [ ] Push
