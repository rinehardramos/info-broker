# URE Phase B: LLM-Inferred Tool Classification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the post-run analyzer to classify tool calls via LLM for all 5 research categories, enabling self-learning overlays beyond person investigations.

**Architecture:** New selectors module defines valid selectors per category. Analyzer routes person to static map (no regression) and other categories to an LLM classification call. Classified pivots feed into the existing overlay upsert system unchanged.

**Tech Stack:** Python, Claude Code CLI / Anthropic API (for classification), existing overlay DB

---

### Task 1: Selectors Module (TDD)

**Files:**
- Create: `app/pipeline/strategies/selectors.py`
- Create: `tests/pipeline/strategies/test_selectors.py`

- [ ] Write failing tests:
  - `get_selectors("person")` returns list containing "full_name", "email", "phone"
  - `get_selectors("generation")` returns list containing "problem_statement", "concept", "technique"
  - `get_selectors("prediction")` returns list containing "signal", "trend", "driver"
  - `get_selectors("explanation")` returns list containing "symptom", "hypothesis", "root_cause"
  - `get_selectors("synthesis")` returns list containing "study", "framework", "claim"
  - `get_selectors("unknown_category")` returns person selectors as fallback
  - All 5 categories return non-empty lists
- [ ] Run tests -- verify FAIL
- [ ] Implement: `CATEGORY_SELECTORS` dict with all 5 categories, `get_selectors(entity_type)` with person fallback
- [ ] Run tests -- verify PASS
- [ ] Commit: `git add app/pipeline/strategies/selectors.py tests/pipeline/strategies/test_selectors.py && git commit -m "feat(strategies): add category selector lists for all 5 research types"`

---

### Task 2: LLM Classification Function (TDD)

**Files:**
- Modify: `app/pipeline/strategies/analyzer.py`
- Create: `tests/pipeline/strategies/test_analyzer_llm.py`

- [ ] Write failing tests (mock the LLM call):
  - `classify_tool_calls_llm("generation", "build a new product", tool_calls)` with mocked LLM returning valid JSON returns list of dicts with selector_type and pivot_pattern
  - LLM returns garbage text -- fallback returns all calls mapped to first selector
  - LLM raises exception -- fallback returns all calls mapped to first selector
  - Empty tool_calls list returns empty list
  - Classification results have valid selector_types from the category's list
- [ ] Run tests -- verify FAIL
- [ ] Implement `classify_tool_calls_llm(entity_type, query, tool_calls)` in analyzer.py:
  - Import `get_selectors` from selectors module
  - Build classification prompt with category, query, valid selectors, formatted tool calls
  - Call LLM via `_call_llm` (same as analyzer node -- Claude Code CLI primary, API fallback)
  - Parse JSON response
  - On any failure: fallback to mapping all calls to first selector in category
  - Return `list[dict]` with keys: tool, selector_type, pivot_pattern, findings_count
- [ ] Run tests -- verify PASS
- [ ] Commit: `git add app/pipeline/strategies/analyzer.py tests/pipeline/strategies/test_analyzer_llm.py && git commit -m "feat(strategies): add LLM-inferred tool classification for non-person categories"`

---

### Task 3: Update analyze_run_pivots + Agent Wiring

**Files:**
- Modify: `app/pipeline/strategies/analyzer.py`
- Modify: `app/routers/v3/agent.py`

- [ ] Update `analyze_run_pivots` signature to accept `entity_type` parameter (default "person")
- [ ] Add routing logic: if entity_type == "person", use existing static `map_tool_to_pivot`. Otherwise, call `classify_tool_calls_llm` and use its output for overlay generation.
- [ ] In `app/routers/v3/agent.py`, find where `analyze_run_pivots` is called (post-run). Pass `entity_type=research_category` where `research_category` is the result of `classify_query()`.
- [ ] Run full tests: `uv run pytest tests/ -q --tb=short --ignore=tests/v3 --ignore=tests/e2e`
- [ ] Commit: `git add app/pipeline/strategies/analyzer.py app/routers/v3/agent.py && git commit -m "feat(strategies): route non-person runs to LLM classification in analyzer"`

---

### Task 4: Integration Test + Deploy

- [ ] Run all tests: `uv run pytest tests/ -q --tb=short --ignore=tests/v3 --ignore=tests/e2e`
  Expected: 848+ existing + ~15 new, all pass
- [ ] Docker build and deploy: `docker compose build info-broker-api && docker compose up -d info-broker-api`
- [ ] Verify by checking overlays table after a non-person research run:
  ```sql
  SELECT entity_type, selector_type, pivot_pattern, overlay_type, yield_rate
  FROM investigation_strategy_overlays
  WHERE entity_type != 'person'
  ORDER BY created_at DESC LIMIT 10
  ```
- [ ] Push: `git push origin main`
