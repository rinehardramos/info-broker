# URE Phase C: Domain Sub-Strategies

**Date:** 2026-05-08
**Status:** Draft
**Depends on:** Strategy system, Phase A (orchestrator), Phase B (LLM classification)

---

## Problem

The system has 5 base research categories but no domain specialization. "Investigate Company X for acquisition" uses the same generic person/retrieval strategy as "find email of John Doe." Real research needs domain-specific execution models: due diligence has 7-12 parallel workstreams, patent search has CPC classification codes, threat modeling uses STRIDE + ATT&CK frameworks.

## Solution

Add 30 domain sub-strategies organized under the 5 categories. A two-level classification (category then sub-strategy via LLM) selects the right one. Sub-strategies are generated from the existing research paradigms reference doc using an LLM build script. Each defines domain-specific selectors, tool preferences, and completeness criteria.

## Architecture

Two-level strategy resolution:
1. `classify_query()` determines category (existing)
2. `classify_substrategy(category, query)` determines domain via LLM (new)
3. Compiler loads sub-strategy instead of base when one matches
4. Overlays work at sub-strategy level

---

## Sub-Strategy Registry

`app/pipeline/strategies/domains/registry.py` discovers and loads all sub-strategy modules from the `domains/` directory tree.

```
app/pipeline/strategies/domains/
  registry.py
  retrieval/
    due_diligence.py, competitive_intel.py, market_research.py,
    fact_checking.py, legal_research.py, genealogical.py,
    historical_archival.py, descriptive_research.py
  generation/
    patent_prior_art.py, drug_discovery.py, engineering_rd.py,
    design_thinking.py, biomimicry.py, scientific_discovery.py,
    morphological_analysis.py
  prediction/
    futures_foresight.py, technology_scouting.py,
    vc_deal_evaluation.py, market_forecasting.py,
    competitive_forecasting.py
  explanation/
    root_cause_analysis.py, systems_thinking.py,
    threat_modeling.py, grounded_theory.py,
    causal_experimental.py, user_research.py
  synthesis/
    systematic_review.py, evaluation_research.py,
    decision_analysis.py, patent_landscape.py
```

### Registry API

```python
def get_substrategy(category: str, name: str) -> str
def list_substrategies(category: str) -> list[dict]  # [{name, display_name, description}]
```

---

## Sub-Strategy Template

Each file follows a strict format:

```python
CATEGORY = "retrieval"
NAME = "due_diligence"
DISPLAY_NAME = "M&A Due Diligence"
DESCRIPTION = "Assess acquisition target across financial, legal, IP, operational workstreams"

SELECTORS = [
    "target_company", "financial_data", "legal_risk",
    "ip_portfolio", "customer_base", "team_quality", "market_position"
]

STRATEGY = triple-quoted string with:
  === STRATEGY NAME ===
  --- EXECUTION MODEL ---
  --- PRIORITY SELECTORS ---
  --- KEY PIVOT PATTERNS ---
  --- COMPLETENESS CHECKLIST ---
```

---

## Sub-Strategy Classifier

After category classification, a lightweight LLM call selects the sub-strategy:

Prompt includes: category, query, list of available sub-strategies with descriptions.
Returns: sub-strategy name or "none" (use base).
Model: general (Sonnet). Single call, ~200 tokens.
Fallback: "none" on any failure.

Added to orchestrator.py as `classify_substrategy(category, query)`.

---

## Full Sub-Strategy Catalog (30 paradigms)

### Retrieval (8)
| Name | Display | Source Paradigm |
|------|---------|----------------|
| person_investigation | Person OSINT | Intelligence/OSINT (existing) |
| due_diligence | M&A Due Diligence | Due Diligence (7-12 workstreams) |
| competitive_intel | Competitive Intelligence | Competitive Intelligence |
| market_research | Market Research | Market Research (secondary) |
| fact_checking | Fact-Checking | Claim verification, 2-source standard |
| legal_research | Legal Research | Hierarchical source authority |
| genealogical | Genealogical Research | GPS formal proof standard |
| historical_archival | Historical/Archival | Primary source analysis, dating |

### Generation (7)
| Name | Display | Source Paradigm |
|------|---------|----------------|
| patent_prior_art | Patent/Prior Art Search | CPC codes, claim analysis |
| drug_discovery | Drug Discovery | SAR optimization, clinical pipeline |
| engineering_rd | Engineering R&D | TRL 1-9 progression |
| design_thinking | Design Thinking | Empathize-Define-Ideate-Prototype-Test |
| biomimicry | Biomimicry | Nature-inspired solutions |
| scientific_discovery | Scientific Discovery | Hypothesis-experiment-falsification |
| morphological_analysis | Morphological Analysis | Zwicky box, combinatorial space |

### Prediction (5)
| Name | Display | Source Paradigm |
|------|---------|----------------|
| futures_foresight | Futures/Foresight | Scenario planning, Delphi, horizon scanning |
| technology_scouting | Technology Scouting | S-curve analysis, continuous monitoring |
| vc_deal_evaluation | VC Deal Evaluation | Multi-dimensional evaluation grid |
| market_forecasting | Market Forecasting | Conjoint analysis, statistical modeling |
| competitive_forecasting | Competitive Forecasting | Weak signal detection, PESTLE |

### Explanation (6)
| Name | Display | Source Paradigm |
|------|---------|----------------|
| root_cause_analysis | Root Cause Analysis | 5 Whys, fishbone, fault tree |
| systems_thinking | Systems Thinking | Feedback loops, Meadows leverage points |
| threat_modeling | Threat Modeling | STRIDE, ATT&CK, kill chains |
| grounded_theory | Grounded Theory | Constant comparative, theoretical saturation |
| causal_experimental | Causal Research | Controlled experiments, A/B tests |
| user_research | User Research | Contextual inquiry, diary studies |

### Synthesis (4)
| Name | Display | Source Paradigm |
|------|---------|----------------|
| systematic_review | Systematic Review | PRISMA, meta-analysis |
| evaluation_research | Evaluation Research | Formative + summative, logic models |
| decision_analysis | Decision Analysis | MCDA, AHP, decision trees |
| patent_landscape | Patent Landscape | Classification + citation analysis |

---

## LLM Strategy Generation Script

`scripts/generate_substrategies.py` — build-time script, not runtime.

1. Reads `docs/superpowers/specs/2026-05-07-research-paradigms-reference.md`
2. For each paradigm, calls LLM with the template + paradigm description
3. LLM generates: execution model, selectors, pivot patterns mapped to existing tools, completeness checklist
4. Writes output to the correct `domains/{category}/{name}.py` file
5. Output committed to git

---

## Integration Changes

### orchestrator.py
- Add `classify_substrategy(category, query)` — LLM call to select sub-strategy

### compiler.py
- Update `compile_strategy(entity_type, substrategy=None)` — loads sub-strategy when provided

### __init__.py
- Update `get_strategy()` to accept optional substrategy parameter

### agent.py
- After category classification, call `classify_substrategy()`
- Pass substrategy to `compile_strategy()`

### selectors.py
- Load sub-strategy selectors from registry when available

---

## New/Modified Files

### New
| File | Purpose |
|------|---------|
| `app/pipeline/strategies/domains/__init__.py` | Package |
| `app/pipeline/strategies/domains/registry.py` | Discovery + loading |
| `app/pipeline/strategies/domains/retrieval/*.py` | 8 files |
| `app/pipeline/strategies/domains/generation/*.py` | 7 files |
| `app/pipeline/strategies/domains/prediction/*.py` | 5 files |
| `app/pipeline/strategies/domains/explanation/*.py` | 6 files |
| `app/pipeline/strategies/domains/synthesis/*.py` | 4 files |
| `scripts/generate_substrategies.py` | Build-time generator |
| `tests/pipeline/strategies/test_registry.py` | Registry tests |
| `tests/pipeline/strategies/test_substrategy_classifier.py` | Classifier tests |

### Modified
| File | Change |
|------|--------|
| `app/pipeline/strategies/orchestrator.py` | Add classify_substrategy() |
| `app/pipeline/strategies/compiler.py` | Accept substrategy param |
| `app/pipeline/strategies/__init__.py` | Support sub-strategies |
| `app/pipeline/strategies/selectors.py` | Load sub-strategy selectors |
| `app/routers/v3/agent.py` | Pass substrategy to compiler |

---

## Testing

- Registry discovers all 30 sub-strategy files
- get_substrategy returns correct content for each
- classify_substrategy with mocked LLM returns valid names
- classify_substrategy fallback returns "none"
- Compiler loads sub-strategy when provided, base when not
- Each sub-strategy file has required fields (CATEGORY, NAME, SELECTORS, STRATEGY)
- Integration: query triggers correct sub-strategy selection

---

## Scope

**In scope:** Sub-strategy registry, 30 generated sub-strategy files, LLM classifier, compiler integration, orchestrator update.

**Out of scope:** Frontend sub-strategy selector UI, user-configurable sub-strategies, runtime strategy editing.
