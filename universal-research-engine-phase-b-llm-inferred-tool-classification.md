# Universal Research Engine Phase B: LLM-Inferred Tool Classification

**Date:** 2026-05-08
**Status:** Draft
**Depends on:** Strategy system (analyzer, compiler, overlays), IS Brain, Phase A (scale classifier)

---

## Problem

The post-run analyzer only tracks pivot yields for person investigations. It has a hardcoded PIVOT_TOOL_MAP that maps 31 tool names to person-specific selectors (full_name, email, phone, etc.). When the IS brain runs generation, prediction, explanation, or synthesis research, no learning occurs -- the system cannot identify which tools worked well for which research patterns.

## Solution

Add LLM-inferred tool call classification to the post-run analyzer. After each non-person run, a lightweight LLM call classifies every tool call's purpose within the research category's selector taxonomy. The classified pivots feed into the same overlay system (reinforce, prune, discover) that already works for person investigations.

## Architecture

```
IS Brain run completes
        |
        v
  analyze_run_pivots(run_id, query, result, entity_type)
        |
        +-- entity_type == "person": use static PIVOT_TOOL_MAP (existing, proven)
        |
        +-- any other category: LLM classification
                |
                v
          Extract tool calls from result tree
                |
                v
          Batch classify via LLM (general model, ~500 tokens per batch)
          "Given category selectors, what was each tool call doing?"
                |
                v
          Returns: [{tool, selector_type, pivot_pattern}]
                |
                v
          Calculate yield_rate per (selector_type, tool)
                |
                v
          Upsert overlays to investigation_strategy_overlays table
                |
                v
          Next run: compiler merges learned overlays into strategy prompt
```

---

## LLM Classification

### Prompt

```
Classify each tool call by which research selector it was serving.

Research category: {entity_type}
Research query: {query}

Valid selectors for this category:
{selector_list}

Tool calls to classify:
{tool_calls_formatted}

Return ONLY a JSON array:
[{{"tool": "ddg_search", "query_used": "FDA regulations", "selector_type": "evidence", "confidence": 0.9}}]
```

### Model

Use the general model (Sonnet via Claude Code CLI or Anthropic API). This is a classification task -- fast, cheap, no deep reasoning needed.

### Batching

Classify up to 20 tool calls per LLM call. Most runs produce 5-30 tool calls, so 1-2 LLM calls total per post-run analysis. Total added latency: 2-5 seconds.

### Fallback

If LLM classification fails (timeout, parse error, empty response):
1. For person: use static PIVOT_TOOL_MAP (existing behavior)
2. For other categories: map all tool calls to the first selector in the category (coarse but non-breaking)
3. Log warning and continue -- never block the post-run flow

---

## Selector Lists

Extracted from each strategy's PRIORITY SELECTORS section. Stored as a Python dict in a new module.

| Category | Selectors |
|----------|-----------|
| person | full_name, email, phone, username, employer, address, photo |
| generation | problem_statement, concept, technique, prior_art, researcher, constraint, gap |
| prediction | signal, trend, driver, uncertainty, scenario, weak_signal, actor, constraint |
| explanation | symptom, hypothesis, variable, cause, root_cause, feedback_loop, leverage_point, evidence |
| synthesis | study, framework, criterion, claim, evidence, perspective, option |

---

## Changes to Analyzer

### Current (person-only)

```python
def map_tool_to_pivot(tool_name: str) -> tuple[str, str]:
    selector = PIVOT_TOOL_MAP.get(tool_name)
    if not selector:
        return ("unknown", f"unknown -> {tool_name}")
    return (selector, f"{selector} -> {tool_name}")
```

### New (category-aware)

```python
async def analyze_run_pivots(run_id, query, result, entity_type="person"):
    tool_calls = extract_tool_calls(result)
    
    if entity_type == "person":
        # Proven static path -- no regression
        classified = [map_tool_to_pivot_static(tc) for tc in tool_calls]
    else:
        # LLM classification for non-person categories
        classified = await classify_tool_calls_llm(entity_type, query, tool_calls)
    
    # Rest of flow: yield calculation, overlay upsert (unchanged)
    for pivot in classified:
        yield_rate = calculate_yield(pivot, tool_calls)
        overlay_type = determine_overlay_type(yield_rate, pivot.findings_count)
        if overlay_type:
            upsert_overlay(entity_type, pivot.selector_type, pivot.pattern, overlay_type, yield_rate)
```

---

## New Module: selectors.py

`app/pipeline/strategies/selectors.py` -- a pure data module with no dependencies.

```python
CATEGORY_SELECTORS: dict[str, list[str]] = {
    "person": ["full_name", "email", "phone", "username", "employer", "address", "photo"],
    "generation": ["problem_statement", "concept", "technique", "prior_art", "researcher", "constraint", "gap"],
    "prediction": ["signal", "trend", "driver", "uncertainty", "scenario", "weak_signal", "actor", "constraint"],
    "explanation": ["symptom", "hypothesis", "variable", "cause", "root_cause", "feedback_loop", "leverage_point", "evidence"],
    "synthesis": ["study", "framework", "criterion", "claim", "evidence", "perspective", "option"],
}

def get_selectors(entity_type: str) -> list[str]:
    return CATEGORY_SELECTORS.get(entity_type, CATEGORY_SELECTORS["person"])
```

---

## Agent Wiring

In `app/routers/v3/agent.py`, update the post-run analyzer call to pass entity_type:

```python
# Before (person-only):
await analyze_run_pivots(run_id, query, result)

# After (category-aware):
await analyze_run_pivots(run_id, query, result, entity_type=research_category)
```

---

## LLM Call Implementation

Uses the same `_call_llm` pattern from analyzer.py (Claude Code CLI primary, API fallback):

```python
async def classify_tool_calls_llm(entity_type, query, tool_calls):
    from app.pipeline.strategies.selectors import get_selectors
    
    selectors = get_selectors(entity_type)
    
    prompt = f"""Classify each tool call by research selector.
Category: {entity_type}
Query: {query}
Valid selectors: {', '.join(selectors)}

Tool calls:
{format_tool_calls(tool_calls)}

Return JSON array: [{{"tool": "...", "selector_type": "...", "confidence": 0.9}}]"""
    
    raw = await _call_llm(prompt, model=general_model())
    return parse_classification(raw, selectors)
```

---

## New/Modified Files

### New files

| File | Purpose |
|------|---------|
| `app/pipeline/strategies/selectors.py` | Category selector lists |
| `tests/pipeline/strategies/test_analyzer_llm.py` | LLM classification tests (mocked) |

### Modified files

| File | Change |
|------|--------|
| `app/pipeline/strategies/analyzer.py` | Add classify_tool_calls_llm(), update analyze_run_pivots() to accept entity_type |
| `app/routers/v3/agent.py` | Pass entity_type to analyze_run_pivots() |

---

## Testing Strategy

### Unit tests
- classify_tool_calls_llm with mocked LLM returning valid JSON
- classify_tool_calls_llm with mocked LLM returning garbage (fallback test)
- get_selectors for all 5 categories
- Verify person category still uses static map (no regression)
- Verify overlay upsert works for non-person entity_types

### Integration test
- Run a mock generation query through the full flow
- Verify overlays are created with entity_type="generation"
- Verify compiler loads those overlays on next run

---

## Scope Boundaries

**In scope:**
- LLM-inferred tool classification for 4 non-person categories
- Selector list module for all 5 categories
- Updated analyzer with entity_type parameter
- Fallback to heuristic when LLM fails
- Tests with mocked LLM

**Out of scope:**
- Completeness validation against strategy checklists (Phase C)
- Domain sub-strategies (Phase C)
- Changes to the overlay table schema (already supports all categories)
- Changes to the compiler (already category-agnostic)
