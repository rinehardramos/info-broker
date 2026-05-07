# Phase 2: Procedural Memory — Research Skills

## Research Foundation

Based on findings from research run `af36f7e0-94a8-47a8-8a3c-c4e093187a31`:

| # | Finding | Confidence | Relevance |
|---|---------|------------|-----------|
| 5 | Three cognitive memory types: semantic (facts), episodic (events), **procedural (skills)** — all three required | 90% | Procedural memory = learned workflows. info-broker already has semantic (KG) and episodic (research_trails). This phase adds procedural. |
| 12 | Hermes OS pattern: skill documents + event log → **40% faster** completion of similar research tasks | 75% | Directly applicable — store successful research strategies as reusable skills |
| 4 | Four-dimension framework: Storage, Curation, **Retrieval**, Lifecycle | 88% | Skills must be retrievable by similarity to new queries |

---

## Overview

After every successful IS brain research run, automatically extract and store a **skill** — a recorded research strategy capturing which tools were used, in what order, how many findings were produced, and how well users rated the results. When a similar query arrives, the IS brain prompt includes matching skills as "SUGGESTED STRATEGIES" so it can reuse proven approaches.

**Architecture:** Qdrant (embedding similarity for trigger matching) + PG (CRUD, lifecycle tracking, cost metrics).

**Measured impact:** Hermes case study reports 40% faster completion on similar tasks after skill creation (Finding #12).

---

## 1. Skill Composition

A skill has 5 components:

### 1.1 Identity
- `skill_id` UUID
- `run_id` — source research run
- `created_at` — timestamp

### 1.2 Trigger Pattern (when to suggest this skill)
- `query` — original query text
- `entity_type` — detected entity type (person, company, concept, etc.)
- `keywords` — extracted keywords for fast matching
- `embedding` — 768-dim vector of the query (stored in Qdrant)

### 1.3 Strategy (what tools to use)
- `tool_sequence` — ordered list of tools used: `["ddg_search", "web_crawl", "linkedin_profile", ...]`
- `pipeline` — full pipeline JSON (`{nodes, edges}`) from `suggested_pipeline`
- `branch_pattern` — `{total_branches, max_depth, resolved, dead_ends}`

### 1.4 Outcomes (how well it worked)
- `findings_count` — number of findings produced
- `quality_score` — avg user feedback score (updated as feedback arrives)
- `error_rate` — fraction of findings that were error-flagged
- `entities_found` — count of entities extracted (if analysis was run)

### 1.5 Cost
- `tool_calls` — total MCP tool invocations
- `duration_seconds` — wall clock time
- `estimated_cost_usd` — estimated monetary cost (sum of per-tool costs)
- `efficiency` — findings per tool call

### 1.6 Lifecycle
- `times_suggested` — how many times this skill appeared in IS brain prompt
- `times_adopted` — how many times the brain used a similar tool sequence
- `last_suggested_at` — timestamp
- `disabled` — boolean (admin can disable without deleting)

---

## 2. Schema

### 2.1 PostgreSQL: `research_skills` table

```sql
CREATE TABLE IF NOT EXISTS research_skills (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID REFERENCES pipeline_runs(id),
    query           TEXT NOT NULL,
    entity_type     VARCHAR(64),
    keywords        TEXT[] DEFAULT '{}',
    tool_sequence   TEXT[] NOT NULL DEFAULT '{}',
    pipeline        JSONB,
    branch_pattern  JSONB DEFAULT '{}',
    findings_count  INT DEFAULT 0,
    quality_score   FLOAT DEFAULT 0.0,
    error_rate      FLOAT DEFAULT 0.0,
    entities_found  INT DEFAULT 0,
    tool_calls      INT DEFAULT 0,
    duration_seconds INT DEFAULT 0,
    estimated_cost_usd FLOAT DEFAULT 0.0,
    efficiency      FLOAT DEFAULT 0.0,
    times_suggested INT DEFAULT 0,
    times_adopted   INT DEFAULT 0,
    last_suggested_at TIMESTAMPTZ,
    disabled        BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_skills_quality ON research_skills (quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_skills_entity ON research_skills (entity_type);
```

### 2.2 Qdrant: Skill entries in `research_memory`

Skill entries stored alongside findings with `payload.type = "skill"`:

```python
PointStruct(
    id=skill_uuid,
    vector=embed_text(query),  # 768-dim
    payload={
        "type": "skill",       # distinguishes from "finding"
        "skill_id": str,
        "query": str,
        "entity_type": str,
        "tool_sequence": list[str],
        "findings_count": int,
        "quality_score": float,
        "estimated_cost_usd": float,
        "efficiency": float,
    }
)
```

---

## 3. Write Path

### 3.1 Auto-Save After IS Brain Run

In `app/routers/v3/agent.py` `_run_is_research()`, after saving research_trails and indexing findings:

```python
# Create skill from this run
from app.memory.skills import create_skill_from_run
await create_skill_from_run(
    run_id=run_id,
    query=query,
    result=result,  # contains tree, findings, suggested_pipeline
    duration_seconds=int((finished - started).total_seconds()),
)
```

### 3.2 Quality Score Update

When user submits feedback on findings (`submit_finding_feedback`):
1. Recalculate avg `quality_score` for the run
2. Update `research_skills.quality_score` WHERE `run_id`
3. Update Qdrant skill point payload

### 3.3 Cost Estimation

Per-tool cost tiers (configurable via core_settings):

| Tier | Cost/call | Tools |
|------|-----------|-------|
| free | $0.00 | ddg_search, web_crawl, wikipedia_api, opencorporates, whois_lookup, ph_sec_dti, ph_bir, google_news |
| moderate | $0.02 | ai_scoring, summarizer, web_search_fetch |
| expensive | $0.10 | linkedin_profile, apollo_zoominfo, headless_crawler, hunter_io, shodan_search |

`estimated_cost_usd = sum(cost_per_tool[tool] for tool in tool_calls)`

---

## 4. Read Path

### 4.1 Skill Retrieval

New signal in `app/memory/signals.py`:

```python
async def skill_search(query: str, limit: int = 5) -> list[MemoryResult]:
    """Search Qdrant for skills matching the query by embedding similarity."""
    # Filter: payload.type == "skill" AND payload.disabled != true
```

This signal joins the fused retrieval but results are separated into a `skills` list (not mixed with findings).

### 4.2 IS Brain Prompt Injection

In `app/is_prompt.py` `build_prompt()`:

```
## SUGGESTED STRATEGIES (from past successful research)

{strategies_section}
```

Each strategy shown as:
```
Strategy: "Find CEO of IT companies in Philippines" (quality: 0.73, cost: $1.25)
  Tools: ddg_search → web_crawl → linkedin_profile → apollo_zoominfo
  Branches: 12, depth 3, 15 findings
  Consider reusing this approach.
```

### 4.3 Adoption Tracking

After IS brain completes, compare its actual tool_sequence against suggested skill tool_sequences. If overlap > 60%, increment `times_adopted` for that skill.

---

## 5. New Module: `app/memory/skills.py`

```python
async def create_skill_from_run(run_id, query, result, duration_seconds) -> str:
    """Create a skill from a completed research run. Returns skill_id."""

async def get_matching_skills(query: str, limit: int = 3) -> list[dict]:
    """Find skills matching a query by embedding similarity."""

async def update_skill_quality(run_id: str) -> None:
    """Recalculate quality_score from user feedback."""

def estimate_cost(tool_calls: list[str]) -> float:
    """Estimate USD cost from tool call list."""
```

---

## 6. Files to Modify

| File | Change |
|------|--------|
| `app/routers/v3/db.py` | Add `research_skills` table |
| `app/memory/skills.py` | **New** — skill CRUD + cost estimation |
| `app/memory/signals.py` | Add `skill_search()` signal |
| `app/memory/retriever.py` | Separate skills from findings in fused results |
| `app/is_prompt.py` | Add SUGGESTED STRATEGIES section |
| `app/routers/v3/agent.py` | Create skill after run, pass skills to prompt |
| `app/routers/v3/research_api.py` | Update skill quality on feedback |
| `tests/memory/test_skills.py` | **New** — skill tests |

---

## 7. Verification

1. Run IS brain research → skill auto-created in PG + Qdrant
2. Run a similar query → IS brain prompt includes "SUGGESTED STRATEGIES"
3. Submit thumbs up on findings → skill quality_score increases
4. Skill has accurate cost estimate based on tool calls
5. `get_matching_skills("CEO Philippines")` returns relevant skills
6. Disabled skills don't appear in suggestions
