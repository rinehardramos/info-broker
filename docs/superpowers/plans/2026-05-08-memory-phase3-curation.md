# Memory Phase 3: Curation and Contradiction Detection - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect and auto-resolve contradictory entity observations in the knowledge graph, flag stale facts, and expose curation via REST API + MCP tool.

**Architecture:** A background Curator sweeps entity_observations via SQL self-join, normalizes values to catch formatting differences, auto-resolves by confidence + recency, and persists results to kg_contradictions + kg_stale_flags tables.

**Tech Stack:** Python, PostgreSQL, FastAPI, asyncio

---

### Task 1: Database Schema

**Files:** Modify `app/routers/v3/db.py`

- [ ] Add `kg_contradictions` table (UUID PK, entity_ref, attribute, value_a, value_b, confidence_a/b, observed_at_a/b, source_run_a/b, observation_id_a/b, winner, status, resolved_by, resolved_at, created_at) with indexes on entity_ref, status, created_at
- [ ] Add `kg_stale_flags` table (UUID PK, entity_ref, attribute, current_value, observation_id, observed_at, ttl_days, status, flagged_at, dismissed_by, dismissed_at) with indexes on entity_ref, status
- [ ] Rebuild API container, verify tables exist
- [ ] Commit

---

### Task 2: Value Normalizer (TDD)

**Files:** Create `app/knowledge/normalizer.py`, `tests/knowledge/test_normalizer.py`

- [ ] Write failing tests: normalize_value for name (strip/title-case/honorifics), role (synonyms: ceo=chief executive officer), email (lowercase), phone (digits only), location (country codes: US=United States), default (lowercase/strip). Test values_equivalent true/false cases.
- [ ] Run tests - verify FAIL
- [ ] Implement: _HONORIFICS regex, _ROLE_SYNONYMS dict (~16 entries), _COUNTRY_CODES dict (~14 entries), normalize_value dispatches by attribute, values_equivalent compares normalized forms
- [ ] Run tests - verify PASS
- [ ] Commit

---

### Task 3: Curator - Contradiction Detection + Staleness (TDD)

**Files:** Create `app/knowledge/curator.py`, `tests/knowledge/test_curator.py`

- [ ] Write failing tests: pick_winner (confidence gap >=15, <15, same+close dates=needs_review), detect_contradictions (finds conflicts, skips equivalent values, skips already tracked), detect_staleness (flags old observations, skips name attribute). Mock fetch_all/fetch_one/execute.
- [ ] Run tests - verify FAIL
- [ ] Implement: STALENESS_TTL dict, pick_winner(), detect_contradictions() with SQL self-join + normalization + dedup, detect_staleness() per attribute type, run_curator_loop(interval_seconds=600)
- [ ] Run tests - verify PASS
- [ ] Commit

---

### Task 4: Curation REST API

**Files:** Create `app/routers/v3/curation_api.py`

- [ ] Implement router (prefix=/v3/knowledge, tag=v3-curation): GET /contradictions (filterable by status, entity_ref, paginated), POST /contradictions/{id}/resolve (body: {winner}), POST /contradictions/{id}/dismiss, GET /stale (filterable), POST /stale/{id}/dismiss, GET /curation/stats
- [ ] Commit

---

### Task 5: Wire Into App

**Files:** Modify `app/main.py`

- [ ] Import and register curation_api router
- [ ] Add curator background task in lifespan (after materializer block)
- [ ] Verify endpoints accessible
- [ ] Commit

---

### Task 6: MCP Tool

**Files:** Modify `mcp_server/server.py`

- [ ] Add curate_knowledge tool: calls curation/stats + contradictions (needs_review, limit 10) + stale (stale, limit 10), returns combined JSON
- [ ] Commit

---

### Task 7: Integration Test + Deploy

- [ ] Run all unit tests (expect 614+ existing + ~21 new)
- [ ] Docker build and deploy
- [ ] Verify curation/stats API returns zeros
- [ ] Verify MCP curate_knowledge tool works
- [ ] Push to origin