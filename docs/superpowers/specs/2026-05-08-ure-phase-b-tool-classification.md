# Universal Research Engine Phase B: LLM-Inferred Tool Classification

**Date:** 2026-05-08
**Status:** Draft
**Depends on:** Strategy system (analyzer, compiler, overlays), IS Brain, Phase A

---

## Problem

The post-run analyzer only tracks pivot yields for person investigations. It has a hardcoded PIVOT_TOOL_MAP mapping 31 tool names to person-specific selectors. When the IS brain runs generation, prediction, explanation, or synthesis research, no learning occurs.

## Solution

Add LLM-inferred tool call classification to the post-run analyzer. A lightweight LLM call classifies every tool call's purpose within the category's selector taxonomy. Classified pivots feed into the existing overlay system.

## Architecture

After each non-person run, the analyzer extracts tool calls from the result tree, batches them into an LLM prompt with the category's valid selectors, and gets back a classification. The rest of the flow (yield calculation, overlay upsert, compiler merge) is unchanged.

Person category continues using the proven static PIVOT_TOOL_MAP -- no regression.

---

## LLM Classification

**Model:** General model (Sonnet). Classification task, not reasoning.

**Batching:** Up to 20 tool calls per LLM call. 1-2 calls per run. Added latency: 2-5s.

**Prompt:** Includes category name, query, valid selectors, and formatted tool calls. Returns JSON array of classifications.

**Fallback:** If LLM fails, map all calls to the first selector in the category. Log warning, never block post-run flow.

---

## Selector Lists Per Category

| Category | Selectors |
|----------|-----------|
| person | full_name, email, phone, username, employer, address, photo |
| generation | problem_statement, concept, technique, prior_art, researcher, constraint, gap |
| prediction | signal, trend, driver, uncertainty, scenario, weak_signal, actor, constraint |
| explanation | symptom, hypothesis, variable, cause, root_cause, feedback_loop, leverage_point, evidence |
| synthesis | study, framework, criterion, claim, evidence, perspective, option |

---

## Changes

### analyzer.py
- Add `classify_tool_calls_llm(entity_type, query, tool_calls)` -- LLM classification
- Update `analyze_run_pivots()` to accept `entity_type` param
- Person: static map. Others: LLM classification.

### selectors.py (new)
- `CATEGORY_SELECTORS` dict with selector lists per category
- `get_selectors(entity_type)` helper

### agent.py
- Pass `entity_type=research_category` to `analyze_run_pivots()`

---

## New/Modified Files

| File | Change |
|------|--------|
| `app/pipeline/strategies/selectors.py` | New: category selector lists |
| `app/pipeline/strategies/analyzer.py` | Add LLM classification, entity_type param |
| `app/routers/v3/agent.py` | Pass entity_type to analyzer |
| `tests/pipeline/strategies/test_analyzer_llm.py` | New: mocked LLM tests |

---

## Testing

- Mock LLM returning valid JSON classifications
- Mock LLM returning garbage (fallback test)
- get_selectors for all 5 categories
- Person still uses static map (regression test)
- Overlay upsert for non-person entity_types
- Integration: generation run creates generation overlays

---

## Scope

**In scope:** LLM classification for 4 non-person categories, selectors module, analyzer update, tests.

**Out of scope:** Completeness validation (Phase C), domain sub-strategies (Phase C), overlay schema changes (not needed), compiler changes (already agnostic).