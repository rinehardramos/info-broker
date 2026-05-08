# Memory Phase 5: LLM-Assisted Memory Ops

**Date:** 2026-05-08
**Status:** Draft
**Depends on:** Memory Phase 3 (curation), Phase 4 (tiered lifecycle), Knowledge Graph

---

## Problem

The curator (Phase 3) detected 112 contradictions but all are "needs_review" — the auto-resolution rules are too conservative for nuanced cases like "Co-Founder & President" vs "Co-Founder & President, Head of Strategy." A human reviewing 112+ contradictions is impractical. The system also can't merge duplicate entities or suggest which stale observations to re-research.

## Solution

LLM-assisted curation that runs as a background task:
1. **Contradiction resolution** — LLM evaluates each needs_review contradiction and picks the winner
2. **Entity deduplication** — LLM identifies entities that are the same real-world entity under different refs
3. **Curation suggestions** — LLM generates actionable recommendations (re-research stale entities, merge duplicates)

## Architecture

A new `LLMCurator` class that processes items in batches. Runs on a configurable schedule (default: daily) or on-demand via API. Uses the general model (Sonnet) for cost efficiency.

```
Unresolved contradictions (needs_review)
        |
        v
  LLM Contradiction Resolver (batch of 10)
  "Given these two values for the same entity+attribute,
   which is more likely correct and why?"
        |
        v
  Update kg_contradictions: status=llm_resolved, winner, reason

Entity observations with similar names
        |
        v
  LLM Entity Deduplicator (batch of 20 candidates)
  "Are any of these entity refs the same real-world entity?"
        |
        v
  Create entity_aliases for confirmed matches

Stale flags + low-confidence observations
        |
        v
  LLM Curation Advisor
  "Which of these stale entities are worth re-researching?"
        |
        v
  Store suggestions in kg_curation_suggestions table
```

---

## Contradiction Resolution

### Prompt
```
You are resolving data contradictions in a knowledge graph.

Entity: {entity_ref}
Attribute: {attribute}
Value A: {value_a} (confidence: {conf_a}, observed: {date_a}, source: {tool_a})
Value B: {value_b} (confidence: {conf_b}, observed: {date_b}, source: {tool_b})

Which value is more likely correct? Consider:
- More recent observations are often more accurate
- Higher confidence sources are more reliable
- Some differences are just formatting (ignore those)
- Context matters: a role change is real, a typo is not

Return JSON: {"winner": "a" or "b", "reason": "brief explanation", "confidence": 0.0-1.0}
```

### Batch processing
Process 10 contradictions per LLM call. Batch prompt lists all 10 and asks for JSON array response.

### Status update
After LLM resolves: `UPDATE kg_contradictions SET status = 'llm_resolved', winner = %s, resolved_by = 'llm', resolved_at = now() WHERE id = %s`

---

## Entity Deduplication

### Candidate detection
SQL query finds entity refs with similar names (Levenshtein or trigram similarity):

```sql
SELECT a.entity_ref as ref_a, b.entity_ref as ref_b,
       a.value as name_a, b.value as name_b
FROM entity_observations a
JOIN entity_observations b ON a.attribute = 'name' AND b.attribute = 'name'
  AND a.entity_ref < b.entity_ref
  AND similarity(lower(a.value), lower(b.value)) > 0.7
LIMIT 50
```

### LLM verification
Batch candidates to LLM: "Are these the same real-world entity? Consider name variations, abbreviations, spelling differences."

### Merge
For confirmed matches: insert `entity_aliases` row linking the secondary ref to the canonical ref.

---

## Curation Suggestions

LLM reviews stale flags and low-confidence observations to generate actionable suggestions:

```sql
CREATE TABLE IF NOT EXISTS kg_curation_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref VARCHAR(512),
    suggestion_type VARCHAR(32),  -- re_research, merge, archive, verify
    suggestion TEXT NOT NULL,
    priority VARCHAR(16) DEFAULT 'medium',  -- high, medium, low
    status VARCHAR(32) DEFAULT 'pending',  -- pending, accepted, dismissed
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### Suggestion types
- **re_research**: "Entity X's role was last observed 8 months ago — re-verify"
- **merge**: "Entity refs A and B appear to be the same company"
- **archive**: "Entity X has only 1 low-confidence observation — consider archiving"
- **verify**: "Entity X has conflicting data from 3 sources — needs human review"

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v3/knowledge/curation/resolve-batch` | Trigger LLM resolution of N contradictions |
| `POST` | `/v3/knowledge/curation/deduplicate` | Trigger LLM entity deduplication |
| `GET` | `/v3/knowledge/curation/suggestions` | List curation suggestions |
| `POST` | `/v3/knowledge/curation/suggestions/{id}/accept` | Accept a suggestion |
| `POST` | `/v3/knowledge/curation/suggestions/{id}/dismiss` | Dismiss a suggestion |

---

## New/Modified Files

### New
| File | Purpose |
|------|---------|
| `app/knowledge/llm_curator.py` | LLM contradiction resolver + deduplicator + advisor |
| `tests/knowledge/test_llm_curator.py` | Tests with mocked LLM |

### Modified
| File | Change |
|------|--------|
| `app/routers/v3/db.py` | Add kg_curation_suggestions table |
| `app/routers/v3/curation_api.py` | Add resolve-batch, deduplicate, suggestions endpoints |
| `app/main.py` | Optional: schedule daily LLM curation run |

---

## Testing

- Mock LLM returning valid resolution JSON
- Mock LLM returning garbage (fallback: skip, don't crash)
- Contradiction resolution updates status to llm_resolved
- Entity dedup creates alias entries
- Suggestions created with correct type and priority

---

## Scope

**In scope:** LLM contradiction resolution, entity deduplication candidates, curation suggestions table + API.

**Out of scope:** Frontend curation dashboard, automatic re-research execution, LLM cost tracking per curation run.
