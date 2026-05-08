# URE Phase C: Domain Sub-Strategies — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 30 domain sub-strategies with a registry, LLM-based classifier, and compiler integration so the IS brain gets domain-specific guidance for each research query.

**Architecture:** Sub-strategies live in `domains/{category}/` directories. A registry auto-discovers them. After category classification, an LLM selects the most specific sub-strategy. The compiler loads it instead of the base category strategy. 14 sub-strategies already exist as flat files — these get reorganized + 16 new ones generated.

**Tech Stack:** Python, Claude Code CLI (for classifier + generator), existing overlay system

---

### Task 1: Registry + Directory Structure (TDD)

**Files:**
- Create: `app/pipeline/strategies/domains/__init__.py`
- Create: `app/pipeline/strategies/domains/registry.py`
- Create: `app/pipeline/strategies/domains/retrieval/__init__.py`
- Create: `app/pipeline/strategies/domains/generation/__init__.py`
- Create: `app/pipeline/strategies/domains/prediction/__init__.py`
- Create: `app/pipeline/strategies/domains/explanation/__init__.py`
- Create: `app/pipeline/strategies/domains/synthesis/__init__.py`
- Create: `tests/pipeline/strategies/test_registry.py`

- [ ] Write failing tests:
  - `list_substrategies("retrieval")` returns a list of dicts with name, display_name, description
  - `get_substrategy("retrieval", "due_diligence")` returns non-empty strategy text
  - `get_substrategy("retrieval", "nonexistent")` returns empty string
  - `list_substrategies("unknown_category")` returns empty list
  - Registry discovers files from all 5 category directories
- [ ] Run tests -- verify FAIL
- [ ] Implement registry.py: scan `domains/{category}/` for .py files with STRATEGY attribute. Load on first access. Provide `get_substrategy(category, name)` and `list_substrategies(category)`.
- [ ] Create all 5 category `__init__.py` files (empty)
- [ ] Create ONE example sub-strategy file to make tests pass: `domains/retrieval/due_diligence.py` — move content from existing `app/pipeline/strategies/due_diligence.py`
- [ ] Run tests -- verify PASS
- [ ] Commit: `git add app/pipeline/strategies/domains/ tests/pipeline/strategies/test_registry.py && git commit -m "feat(strategies): add domain sub-strategy registry with directory structure"`

---

### Task 2: Move Existing Sub-Strategies to Domains

**Files:** Move 14 existing sub-strategy files from flat structure to `domains/{category}/`

- [ ] Move existing files to correct category directories:
  - `due_diligence.py` -> `domains/retrieval/due_diligence.py`
  - `company.py` -> `domains/retrieval/company.py`
  - `lead.py` -> `domains/retrieval/lead.py`
  - `researcher.py` -> `domains/retrieval/researcher.py`
  - `product_innovation.py` -> `domains/generation/product_innovation.py`
  - `scientific_discovery.py` -> `domains/generation/scientific_discovery.py`
  - `engineering_rd.py` -> `domains/generation/engineering_rd.py`
  - `technology_forecast.py` -> `domains/prediction/technology_forecast.py`
  - `market_forecast.py` -> `domains/prediction/market_forecast.py`
  - `root_cause_analysis.py` -> `domains/explanation/root_cause_analysis.py`
  - `systems_analysis.py` -> `domains/explanation/systems_analysis.py`
  - `systematic_review.py` -> `domains/synthesis/systematic_review.py`
  - `strategic_assessment.py` -> `domains/synthesis/strategic_assessment.py`
  - `decision_analysis.py` -> `domains/synthesis/decision_analysis.py`
- [ ] Ensure each moved file has the required fields: CATEGORY, NAME, DISPLAY_NAME, DESCRIPTION, SELECTORS, STRATEGY. Add any missing fields.
- [ ] Update `app/pipeline/strategies/__init__.py` to load from domains registry instead of individual imports
- [ ] Run tests: `uv run pytest tests/ -q --tb=short --ignore=tests/v3 --ignore=tests/e2e`
- [ ] Commit: `git add app/pipeline/strategies/ && git commit -m "refactor(strategies): move 14 existing sub-strategies to domains/ directory structure"`

---

### Task 3: Generate Missing Sub-Strategies

**Files:**
- Create: `scripts/generate_substrategies.py`
- Create: ~16 new sub-strategy files in `domains/`

- [ ] Create the generator script that:
  1. Defines the 30 paradigms (name, category, display_name, description, source_paradigm)
  2. Checks which already exist in `domains/`
  3. For each missing one, calls Claude Code CLI with a prompt:
     "Generate a research sub-strategy following this template: [template]. Domain: [paradigm description]. Map tools to existing info-broker tools: ddg_search, web_search_fetch, google_news, document_search, sec_edgar, etc."
  4. Writes output to the correct file path
- [ ] Run the generator script: `python scripts/generate_substrategies.py`
- [ ] Verify all 30 files exist and have the required fields
- [ ] Run tests to ensure registry discovers all 30
- [ ] Commit: `git add app/pipeline/strategies/domains/ scripts/generate_substrategies.py && git commit -m "feat(strategies): generate 16 new domain sub-strategies via LLM"`

---

### Task 4: Sub-Strategy Classifier (TDD)

**Files:**
- Modify: `app/pipeline/strategies/orchestrator.py`
- Create: `tests/pipeline/strategies/test_substrategy_classifier.py`

- [ ] Write failing tests (mock LLM):
  - `classify_substrategy("retrieval", "evaluate TechCorp for acquisition")` returns "due_diligence"
  - `classify_substrategy("explanation", "why did the server crash")` returns "root_cause_analysis"
  - `classify_substrategy("retrieval", "find email of John")` returns "none" (too simple for sub-strategy)
  - LLM returns garbage: fallback to "none"
  - LLM raises exception: fallback to "none"
- [ ] Run tests -- verify FAIL
- [ ] Implement `classify_substrategy(category, query)` in orchestrator.py:
  - Load available sub-strategies via `list_substrategies(category)`
  - Build prompt with category, query, and sub-strategy options (name + description)
  - Call LLM (same `_call_llm_for_classification` from analyzer or similar pattern)
  - Parse response, validate against known names
  - Fallback: return "none"
- [ ] Run tests -- verify PASS
- [ ] Commit: `git add app/pipeline/strategies/orchestrator.py tests/pipeline/strategies/test_substrategy_classifier.py && git commit -m "feat(strategies): add LLM sub-strategy classifier"`

---

### Task 5: Compiler + Agent Integration

**Files:**
- Modify: `app/pipeline/strategies/compiler.py`
- Modify: `app/pipeline/strategies/__init__.py`
- Modify: `app/pipeline/strategies/selectors.py`
- Modify: `app/routers/v3/agent.py`

- [ ] Update `compile_strategy(entity_type, substrategy=None)`:
  - If substrategy is provided and found in registry, use it instead of base seed
  - Overlays still fetched by entity_type (or substrategy name for fine-grained learning)
  - Fallback: if substrategy not found, use base category strategy
- [ ] Update `get_strategy(entity_type, substrategy=None)` in __init__.py:
  - If substrategy provided, try `get_substrategy(category, substrategy)` from registry
  - Fallback to base category strategy
- [ ] Update selectors.py to load sub-strategy selectors when available:
  - If a sub-strategy has SELECTORS, use those instead of the base category selectors
- [ ] In agent.py, after `classify_query()`:
  - Call `classify_substrategy(research_category, query)` 
  - Pass result to `compile_strategy(research_category, substrategy=substrategy_name)`
  - Log the selected sub-strategy
- [ ] Run full tests: `uv run pytest tests/ -q --tb=short --ignore=tests/v3 --ignore=tests/e2e`
- [ ] Commit: `git add app/pipeline/strategies/ app/routers/v3/agent.py && git commit -m "feat(strategies): wire sub-strategy selection into compiler and agent"`

---

### Task 6: Integration Test + Deploy

- [ ] Run all tests: `uv run pytest tests/ -q --tb=short --ignore=tests/v3 --ignore=tests/e2e`
  Expected: 870+ existing + ~20 new, all pass
- [ ] Docker build and deploy: `docker compose build info-broker-api && docker compose up -d info-broker-api`
- [ ] Verify sub-strategy selection works by checking logs after a research run:
  ```bash
  docker compose logs info-broker-api --since 5m | grep "substrategy"
  ```
- [ ] Push: `git push origin main`
