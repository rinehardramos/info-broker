# Strategy Compression + RAG Rule Retrieval — Design Spec

**Date:** 2026-05-10
**Status:** Draft
**Triggered by:** Antipattern audit of 22,000-token strategy/tactic/technique prompt injection

## Problem Statement

The IS brain prompt injects ~10,000 tokens of strategy/tactic/technique text on every query. This text has:
- **6 contradictions** (conflicting source tiers, dead-end thresholds, anchor hierarchies)
- **11 duplications** (same rule stated 2-4x across files)
- **8 over-constraints** (person/OSINT rules in always-on text for non-OSINT queries)
- Static text injected regardless of query context (K-pop rules for company queries, Admiralty for synthesis)

## Solution

Three-layer architecture based on 2026 prompt engineering research:

### Layer 1: Static Prefix (cached)
Core identity + safety rules. Never changes. Prefix-cached by Claude at 90% token discount.

### Layer 2: RAG-Retrieved Rules (dynamic)
Rules stored as YAML chunks in Qdrant. Per query, retrieve only the top-K most relevant rules based on query + entity_type + category. Max ~1,500 tokens of rules per query (vs. current ~6,400).

### Layer 3: Entity Strategy + Techniques (dynamic, compressed)
The compiled entity strategy + relevant techniques. Compressed to telegraphic YAML format. Max ~1,500 tokens (vs. current ~3,500).

**Total target: ~3,000-3,500 tokens** (vs. current ~10,000)

---

## Part 1: Antipattern Fixes (prerequisite)

Before restructuring, fix the 6 contradictions:

### Fix 1: Unify source tier system
**Single canonical system** (5 tiers from anchoring.py):
```yaml
source_tiers:
  T1: gov registries, court records, corporate filings, licensing boards
  T2: primary documents, filings, contracts, official correspondence
  T3: regulated journalism, verified professional databases
  T4: social media, self-published profiles, company websites
  T5: anonymous forums, unverified posts, dark web
  confirmed: ">=2 sources from T1-T3, independent"
  candidate: "single source or T4-T5 only"
```
Remove the 3-tier system from tactics.py. Remove Admiralty from always-on; Admiralty applies ONLY when due_diligence strategy is active.

### Fix 2: Reconcile CONFIRMED threshold
Universal rule: "CONFIRMED = >=2 independent sources from T1-T3."
Admiralty (A1/B1 requirement) applies only under due_diligence entity_type, NOT universally.

### Fix 3: Fix dead-end threshold
Single rule: "Mark dead_end after 3 tool calls with 0 relevant results (including reformulations)." Remove the "2 failures" and "max 3 calls" contradiction.

### Fix 4: Align scope expansion with dead-end
Scope expansion triggers at dead_end (3 calls), not separately at "3+ locale calls." The dead_end event IS the scope expansion trigger.

### Fix 5: Clarify anchor hierarchy
person.py priority order = **seed input order** (what the user provides first).
anchoring.py hierarchy = **uniqueness rank** (for confirmation quality).
Add explicit note: "Priority order != uniqueness. full_name is provided first but confirmed last."

### Fix 6: Gate source-tier rules by entity type
Source tier rules only inject for: person, company, lead, due_diligence.
NOT injected for: generation, prediction, explanation, synthesis (these use academic evidence grading instead).

---

## Part 2: Rule Deduplication — Single Source of Truth

Each rule lives in exactly ONE canonical file:

| Rule | Canonical Home | Remove From |
|------|---------------|-------------|
| Triangulation (>=2 independent) | `anchoring.py` | tactics.py, person.py, due_diligence.py |
| Passive-first collection | `anchoring.py` | tactics.py, person.py |
| Anchor-before-widening | `anchoring.py` | tactics.py |
| Negative space signal | `scope_expansion.py` | tactics.py |
| Cross-language pivot | `tactics.py` | person.py celebrity section |
| Temporal anchoring | `temporal_analysis.py` | tactics.py |
| CIB/sock puppet detection | `platform_social_intel.py` | verification.py |
| Chronolocation/EXIF | `temporal_analysis.py` | verification.py |
| Korean entertainment search | `techniques.py` | person.py, tactics.py |

After dedup: each rule appears once, in the file that "owns" that domain.

---

## Part 3: YAML Rule Format

All rules converted to telegraphic YAML. No prose. Key-value pairs with nesting.

### Example: Universal tactics (before vs. after)

**Before (prose, ~650 tokens):**
```
--- TACTIC: CONFIDENCE TRIANGULATION [ALL strategies] ---
A fact is CONFIRMED only when >=2 independent sources agree.
Independence test: Source B must NOT derive from Source A (same press
release, same wire, same DB mirror = NOT independent).
Track source provenance — reject "consensus" when all sources cite
the same primary. Single-source findings = CANDIDATE (flag explicitly,
do not present as confirmed).
```

**After (YAML, ~80 tokens):**
```yaml
triangulation:
  confirmed: ">=2 independent T1-T3 sources"
  not_independent: same wire/DB/press release
  single_source: CANDIDATE — flag explicitly
  reject: false consensus from same primary
```

### Compression targets per file:

| File | Current tokens | Target tokens | Reduction |
|------|---------------|--------------|-----------|
| tactics.py | 647 | 300 | 54% |
| anchoring.py | 464 | 200 | 57% |
| person.py | 2,298 | 900 | 61% |
| techniques.py | 1,203 | 500 | 58% |
| Other meta files | ~3,700 | 1,500 | 59% |
| **Total** | **~8,300** | **~3,400** | **59%** |

---

## Part 4: Qdrant RAG Rule Retrieval

### Architecture

```
Rule files (YAML) → embed each rule → store in Qdrant "strategy_rules" collection
                                         ↓
Per query: embed query → retrieve top-K rules (K=10-15) → inject as {dynamic_rules}
```

### Rule Chunk Structure

Each rule is a separate Qdrant point with metadata:

```python
{
    "id": "triangulation",
    "vector": embed("confidence triangulation confirmed independent sources"),
    "payload": {
        "name": "triangulation",
        "category": "universal",         # universal | osint | academic | compliance
        "entity_types": ["all"],         # or ["person", "company", "due_diligence"]
        "always_on": false,              # true = always inject regardless of relevance
        "priority": 1,                   # 1=critical, 2=important, 3=helpful
        "rule_yaml": "triangulation:\n  confirmed: >=2 independent T1-T3 sources\n  ...",
        "tokens": 80,                   # pre-counted token cost
    }
}
```

### Retrieval Logic

```python
async def retrieve_rules(query: str, entity_type: str, max_tokens: int = 1500) -> str:
    """Retrieve relevant rules for this query context."""
    # 1. Always include priority-1 rules (critical safety rules)
    always_on = get_always_on_rules()
    
    # 2. Filter by entity_type compatibility
    entity_filter = Filter(should=[
        FieldCondition(key="entity_types", match=MatchAny(any=["all", entity_type]))
    ])
    
    # 3. Semantic search for relevant rules
    hits = client.query_points(
        collection_name="strategy_rules",
        query=embed(query),
        query_filter=entity_filter,
        limit=20,
    )
    
    # 4. Token budget: accumulate rules until max_tokens reached
    selected = always_on.copy()
    token_count = sum(r["tokens"] for r in selected)
    
    for hit in hits:
        rule = hit.payload
        if rule["name"] in {r["name"] for r in selected}:
            continue  # already included
        if token_count + rule["tokens"] > max_tokens:
            break
        selected.append(rule)
        token_count += rule["tokens"]
    
    # 5. Format as YAML block
    return format_rules_yaml(selected)
```

### Token Budget per Query

| Component | Max Tokens | Notes |
|-----------|-----------|-------|
| Static prefix (cached) | 2,000 | Identity, output format, core workflow. 90% cached. |
| RAG-retrieved rules | 1,500 | Top-K relevant rules in YAML |
| Entity strategy (compiled) | 800 | Compressed from ~2,300 |
| Techniques (relevant only) | 400 | Only matching techniques, not all 11 |
| Suggested strategies (procedural memory) | 300 | Top-3 matching skills |
| **Total dynamic** | **~3,000** | vs. current ~10,000 |

---

## Part 5: Prefix Caching Strategy

### What to Cache (static, never changes per deployment)

```
System prompt:
  - Role identity ("You are an intelligent research agent")
  - Temporal grounding
  - Output format specification
  - Tool list (static tools)
  - Core workflow (BOOTSTRAP → PLAN → RECURSE → DELIVER)
  - Budget constraints
```

This is ~2,000 tokens that repeats on every call. With prefix caching at 90% discount, this costs ~200 effective tokens per call.

### What NOT to Cache (dynamic, changes per query)

```
  - RAG-retrieved rules (varies by query)
  - Entity strategy + overlays (varies by entity type + learned state)
  - Techniques (varies by relevance)
  - Past research context
  - User sources
  - Research plan
```

### Prompt Structure for Caching

```
[CACHED PREFIX - 2000 tokens, 90% discount]
System prompt + role + output format + tools + workflow

[DYNAMIC SECTION - ~3000 tokens, full price]
{rag_rules_section}     # relevant rules in YAML
{entity_strategy}        # compressed strategy
{techniques_section}     # relevant techniques
{strategies_section}     # procedural memory
{context_section}        # past research + user sources
QUERY: {query}
```

---

## Part 6: Rule Indexing Pipeline

### Bootstrap: Index all rules to Qdrant

```python
def index_all_rules():
    """One-time: read all rule files, chunk into individual rules, embed, store."""
    rules = []
    
    # Parse each meta-strategy file
    for meta_file in meta_dir.glob("*.py"):
        module = import_module(meta_file)
        strategy_text = module.STRATEGY_TEXT
        chunks = parse_yaml_rules(strategy_text)  # split into individual rules
        for chunk in chunks:
            rules.append({
                "name": chunk["name"],
                "category": infer_category(module),
                "entity_types": module.ENTITY_TYPES,
                "always_on": module.ALWAYS_ON,
                "priority": chunk.get("priority", 2),
                "rule_yaml": chunk["yaml"],
                "tokens": count_tokens(chunk["yaml"]),
            })
    
    # Parse entity strategies
    for strategy_file in strategies_dir.glob("*.py"):
        # Extract pivot patterns as individual rules
        ...
    
    # Embed and upsert to Qdrant
    for rule in rules:
        vector = embed(f"{rule['name']} {rule['rule_yaml']}")
        client.upsert(collection="strategy_rules", points=[...])
```

### Incremental Updates

When a strategy file changes (new overlay, new rule):
- Re-embed the changed rules only
- Upsert to Qdrant (idempotent by rule name)

---

## Part 7: Implementation Phases

### Phase A: Fix Antipatterns (no architecture change)
- Fix 6 contradictions in existing files
- Deduplicate 11 repeated rules to single source of truth
- Remove person-specific content from always-on files
- Verify all tests pass

### Phase B: YAML Compression (format change only)
- Convert all rule text to telegraphic YAML format
- Update test assertions for new format
- Measure token reduction

### Phase C: Qdrant Rule Store (new infrastructure)
- Create `strategy_rules` Qdrant collection
- Index all rules with metadata
- Build `retrieve_rules()` function
- Replace static injection with RAG retrieval

### Phase D: Prefix Caching (optimization)
- Restructure `is_prompt.py` for cache-friendly prefix
- Move dynamic sections after the cacheable prefix
- Enable prefix caching on API calls

## Expected Results

| Metric | Current | After |
|--------|---------|-------|
| Strategy tokens per query | ~10,000 | ~3,000 |
| Contradictions | 6 | 0 |
| Duplicated rules | 11 | 0 |
| Over-constraints | 8 | 0 |
| Rules injected per query | ALL (~80) | Top-K relevant (~15) |
| Prefix cache savings | 0% | 90% on ~2,000 static tokens |
