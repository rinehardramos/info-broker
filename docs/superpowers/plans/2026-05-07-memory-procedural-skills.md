# Procedural Memory (Research Skills) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-save successful research strategies as reusable skills with cost tracking, and inject matching skills into the IS brain prompt for 40% faster similar research.

**Architecture:** PG `research_skills` table for CRUD/lifecycle + Qdrant `research_memory` collection (type=skill) for similarity search. New `app/memory/skills.py` module handles creation, retrieval, and cost estimation. IS brain prompt gets a SUGGESTED STRATEGIES section.

**Tech Stack:** PostgreSQL, Qdrant, asyncio, pytest (TDD)

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `app/memory/skills.py` | Skill CRUD, cost estimation, quality updates |
| `tests/memory/test_skills.py` | Skill tests (TDD) |

### Modified Files

| File | Change |
|------|--------|
| `app/routers/v3/db.py` | Add `research_skills` table + seed cost tiers |
| `app/memory/signals.py` | Add `skill_search()` signal |
| `app/memory/retriever.py` | Separate skills from findings in fused results |
| `app/is_prompt.py` | Add SUGGESTED STRATEGIES template section |
| `app/routers/v3/agent.py` | Create skill after run, pass skills to prompt |
| `app/routers/v3/research_api.py` | Update skill quality on feedback |

---

## Task 1: PG Schema + Skills Module (TDD)

**Files:**
- Create: `app/memory/skills.py`
- Create: `tests/memory/test_skills.py`
- Modify: `app/routers/v3/db.py`

- [ ] **Step 1: Write failing tests**

Create `tests/memory/test_skills.py`:

```python
"""Tests for procedural memory — research skills."""
from __future__ import annotations
import asyncio
from unittest.mock import patch, MagicMock

def _arun(coro):
    return asyncio.run(coro)

def test_estimate_cost_free_tools():
    from app.memory.skills import estimate_cost
    tools = ["ddg_search", "web_crawl", "wikipedia_api"]
    assert estimate_cost(tools) == 0.0

def test_estimate_cost_mixed_tools():
    from app.memory.skills import estimate_cost
    tools = ["ddg_search", "linkedin_profile", "ai_scoring", "apollo_zoominfo"]
    cost = estimate_cost(tools)
    assert cost > 0
    assert cost == 0.0 + 0.10 + 0.02 + 0.10  # free + expensive + moderate + expensive

def test_estimate_cost_empty():
    from app.memory.skills import estimate_cost
    assert estimate_cost([]) == 0.0

def test_extract_tool_sequence_from_trail():
    from app.memory.skills import extract_tool_sequence
    trail = {
        "branches": [
            {"tools_used": ["ddg_search", "web_crawl"]},
            {"tools_used": ["linkedin_profile"]},
            {"tools_used": ["ddg_search", "apollo_zoominfo"]},
        ]
    }
    seq = extract_tool_sequence(trail)
    # Deduplicated, preserves first-seen order
    assert seq == ["ddg_search", "web_crawl", "linkedin_profile", "apollo_zoominfo"]

def test_extract_tool_sequence_empty():
    from app.memory.skills import extract_tool_sequence
    assert extract_tool_sequence({}) == []
    assert extract_tool_sequence({"branches": []}) == []

def test_create_skill_from_run():
    from app.memory.skills import create_skill_from_run
    inserts = []
    def mock_execute(sql, params=()):
        inserts.append((sql, params))
    
    with patch("app.memory.skills.execute", side_effect=mock_execute), \
         patch("app.memory.skills._index_skill_to_qdrant"):
        _arun(create_skill_from_run(
            run_id="run-123",
            query="Find CEO in Philippines",
            result={
                "entity_type": "person",
                "tree": {"total_branches": 10, "max_depth_reached": 3, "resolved": 8, "dead_ends": 2, "branches": [{"tools_used": ["ddg_search"]}]},
                "findings": [{"title": "F1", "confidence": 90}, {"title": "F2", "error_flagged": True}],
                "pipeline": {"nodes": [], "edges": []},
            },
            duration_seconds=120,
        ))
    
    assert len(inserts) == 1
    assert "research_skills" in inserts[0][0]

def test_get_matching_skills():
    from app.memory.skills import get_matching_skills
    with patch("app.memory.skills.fetch_all") as mock_fetch:
        mock_fetch.return_value = [
            {"id": "s1", "query": "CEO Philippines", "tool_sequence": ["ddg_search"], "quality_score": 0.8, "estimated_cost_usd": 0.5, "findings_count": 10, "entity_type": "person"},
        ]
        skills = _arun(get_matching_skills("CEO IT Philippines"))
    assert len(skills) == 1
    assert skills[0]["quality_score"] == 0.8
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/memory/test_skills.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Add research_skills table to db.py**

Add to the `_MIGRATION` string in `app/routers/v3/db.py`:

```sql
CREATE TABLE IF NOT EXISTS research_skills (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID REFERENCES pipeline_runs(id),
    query             TEXT NOT NULL,
    entity_type       VARCHAR(64),
    keywords          TEXT[] DEFAULT '{}',
    tool_sequence     TEXT[] NOT NULL DEFAULT '{}',
    pipeline          JSONB,
    branch_pattern    JSONB DEFAULT '{}',
    findings_count    INT DEFAULT 0,
    quality_score     FLOAT DEFAULT 0.0,
    error_rate        FLOAT DEFAULT 0.0,
    entities_found    INT DEFAULT 0,
    tool_calls        INT DEFAULT 0,
    duration_seconds  INT DEFAULT 0,
    estimated_cost_usd FLOAT DEFAULT 0.0,
    efficiency        FLOAT DEFAULT 0.0,
    times_suggested   INT DEFAULT 0,
    times_adopted     INT DEFAULT 0,
    last_suggested_at TIMESTAMPTZ,
    disabled          BOOLEAN DEFAULT false,
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_skills_quality ON research_skills (quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_skills_entity ON research_skills (entity_type);
```

- [ ] **Step 4: Create app/memory/skills.py**

```python
"""Procedural memory — research skills (learned strategies)."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from app.routers.v3.db import execute, fetch_all, fetch_one

log = logging.getLogger(__name__)

# Per-tool cost tiers (USD per call)
_TOOL_COSTS = {
    # Free
    "ddg_search": 0.0, "web_crawl": 0.0, "wikipedia_api": 0.0,
    "opencorporates": 0.0, "whois_lookup": 0.0, "ph_sec_dti": 0.0,
    "ph_bir": 0.0, "google_news": 0.0, "rss_monitor": 0.0,
    "facebook_pages": 0.0, "twitter_search": 0.0, "instagram_profile": 0.0,
    # Moderate
    "ai_scoring": 0.02, "summarizer": 0.02, "web_search_fetch": 0.02,
    "analyzer": 0.05,
    # Expensive
    "linkedin_profile": 0.10, "apollo_zoominfo": 0.10,
    "headless_crawler": 0.10, "hunter_io": 0.05, "shodan_search": 0.05,
    "clutch_goodfirms": 0.0, "clutch_buyer": 0.0,
}


def estimate_cost(tool_calls: list[str]) -> float:
    """Estimate USD cost from a list of tool names."""
    return sum(_TOOL_COSTS.get(t, 0.01) for t in tool_calls)


def extract_tool_sequence(trail: dict) -> list[str]:
    """Extract deduplicated tool sequence from a research trail tree."""
    seen = set()
    sequence = []
    for branch in trail.get("branches", []):
        for tool in branch.get("tools_used", []):
            if tool not in seen:
                seen.add(tool)
                sequence.append(tool)
    return sequence


async def create_skill_from_run(
    run_id: str,
    query: str,
    result: dict,
    duration_seconds: int = 0,
) -> str:
    """Create a skill from a completed research run. Returns skill_id."""
    skill_id = str(uuid.uuid4())
    tree = result.get("tree", {})
    findings = result.get("findings", [])
    pipeline = result.get("pipeline")

    tool_seq = extract_tool_sequence(tree)
    valid_findings = [f for f in findings if not f.get("error_flagged")]
    error_count = len(findings) - len(valid_findings)
    error_rate = error_count / len(findings) if findings else 0.0
    cost = estimate_cost(tool_seq)
    efficiency = len(valid_findings) / len(tool_seq) if tool_seq else 0.0

    # Extract keywords from query
    stop_words = {"the", "and", "for", "from", "with", "that", "this", "not", "are", "what", "how", "who", "where", "when", "in", "of", "to", "a", "an", "is", "it"}
    keywords = [w.lower() for w in query.split() if len(w) > 2 and w.lower() not in stop_words]

    execute(
        """INSERT INTO research_skills
        (id, run_id, query, entity_type, keywords, tool_sequence, pipeline,
         branch_pattern, findings_count, error_rate, tool_calls,
         duration_seconds, estimated_cost_usd, efficiency)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (skill_id, run_id, query,
         result.get("entity_type", "unknown"),
         keywords, tool_seq,
         json.dumps(pipeline) if pipeline else None,
         json.dumps({"total_branches": tree.get("total_branches", 0),
                      "max_depth": tree.get("max_depth_reached", 0),
                      "resolved": tree.get("resolved", 0),
                      "dead_ends": tree.get("dead_ends", 0)}),
         len(valid_findings), error_rate,
         tree.get("total_branches", 0),
         duration_seconds, cost, efficiency),
    )

    # Index to Qdrant for similarity search
    await _index_skill_to_qdrant(skill_id, query, tool_seq, len(valid_findings), cost, efficiency)

    log.info("Skill created: %s (tools=%s, findings=%d, cost=$%.2f)",
             skill_id, tool_seq[:3], len(valid_findings), cost)
    return skill_id


async def _index_skill_to_qdrant(
    skill_id: str, query: str, tool_sequence: list[str],
    findings_count: int, cost: float, efficiency: float,
) -> None:
    """Index a skill to Qdrant research_memory for similarity matching."""
    try:
        from app.memory.writer import _get_qdrant_client, _embed_text
        from qdrant_client.models import PointStruct

        client = _get_qdrant_client()
        vector = _embed_text(query)
        client.upsert(
            collection_name="research_memory",
            points=[PointStruct(
                id=skill_id,
                vector=vector,
                payload={
                    "type": "skill",
                    "skill_id": skill_id,
                    "query": query,
                    "tool_sequence": tool_sequence,
                    "findings_count": findings_count,
                    "quality_score": 0.0,
                    "estimated_cost_usd": cost,
                    "efficiency": efficiency,
                },
            )],
        )
    except Exception as exc:
        log.warning("Skill Qdrant index failed (non-fatal): %s", exc)


async def get_matching_skills(query: str, limit: int = 3) -> list[dict]:
    """Find skills matching a query. Uses PG keyword search + entity type."""
    rows = fetch_all(
        """SELECT id, query, entity_type, tool_sequence, pipeline,
                  findings_count, quality_score, estimated_cost_usd, efficiency,
                  branch_pattern, times_suggested
        FROM research_skills
        WHERE disabled = false
        ORDER BY quality_score DESC, findings_count DESC
        LIMIT %s""",
        (limit * 3,),  # overfetch, filter by relevance
    )
    # Simple keyword overlap scoring
    query_words = set(query.lower().split())
    scored = []
    for r in rows:
        skill_words = set(r["query"].lower().split())
        overlap = len(query_words & skill_words)
        if overlap > 0:
            scored.append((overlap, dict(r)))
    scored.sort(key=lambda x: (-x[0], -x[1].get("quality_score", 0)))
    return [s[1] for s in scored[:limit]]


async def update_skill_quality(run_id: str) -> None:
    """Recalculate quality_score from user feedback for a skill."""
    row = fetch_one(
        """SELECT AVG(user_score) AS avg_score
        FROM finding_feedback WHERE run_id = %s""",
        (run_id,),
    )
    if row and row.get("avg_score") is not None:
        execute(
            "UPDATE research_skills SET quality_score = %s WHERE run_id = %s",
            (float(row["avg_score"]), run_id),
        )


def format_skills_for_prompt(skills: list[dict]) -> str:
    """Format matching skills as a prompt section for the IS brain."""
    if not skills:
        return ""
    lines = ["## SUGGESTED STRATEGIES (from past successful research)\n"]
    for i, s in enumerate(skills, 1):
        tools = " -> ".join(s.get("tool_sequence", [])[:6])
        q = s.get("query", "")[:60]
        quality = s.get("quality_score", 0)
        cost = s.get("estimated_cost_usd", 0)
        findings = s.get("findings_count", 0)
        bp = s.get("branch_pattern", {})
        branches = bp.get("total_branches", "?")
        depth = bp.get("max_depth", "?")
        lines.append(
            f"Strategy {i}: \"{q}\" (quality: {quality:.1f}, cost: ${cost:.2f})\n"
            f"  Tools: {tools}\n"
            f"  Branches: {branches}, depth {depth}, {findings} findings\n"
            f"  Consider reusing this approach.\n"
        )
    return "\n".join(lines)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/memory/test_skills.py -v
```

Expected: All 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/memory/skills.py tests/memory/test_skills.py app/routers/v3/db.py
git commit -m "feat(memory): add procedural memory — research skills with cost tracking (TDD)"
```

---

## Task 2: Skill Search Signal + Retriever Integration

**Files:**
- Modify: `app/memory/signals.py`
- Modify: `app/memory/retriever.py`

- [ ] **Step 1: Add skill_search signal to signals.py**

```python
async def skill_search(query: str, limit: int = 5) -> list[MemoryResult]:
    """Search Qdrant for skills matching the query."""
    try:
        client = _get_qdrant_client()
        vector = _embed_text(query)
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        hits = client.search(
            collection_name="research_memory",
            query_vector=vector,
            query_filter=Filter(must=[
                FieldCondition(key="type", match=MatchValue(value="skill")),
            ]),
            limit=limit,
            with_payload=True,
        )
        return [
            MemoryResult(
                ref=str(h.id),
                title=f"Skill: {h.payload.get('query', '')[:50]}",
                content=f"Tools: {' -> '.join(h.payload.get('tool_sequence', [])[:6])}",
                source="skill",
                score=h.score,
                run_id=h.payload.get("skill_id"),
                user_score=0,
            )
            for h in hits if h.payload
        ]
    except Exception as exc:
        log.warning("Skill signal failed: %s", exc)
        return []
```

- [ ] **Step 2: Update retriever to separate skills**

In `app/memory/retriever.py`, update `fused_retrieve` to add skill_search as a 6th signal and return skills separately:

```python
async def fused_retrieve(query, limit=20, ...) -> list[MemoryResult]:
    # ... existing 5 signals ...
    # Add 6th: skill_search
    
async def fused_retrieve_with_skills(query, limit=20, skill_limit=3, ...) -> tuple[list[MemoryResult], list[MemoryResult]]:
    """Returns (findings, skills) as separate lists."""
```

- [ ] **Step 3: Commit**

```bash
git add app/memory/signals.py app/memory/retriever.py
git commit -m "feat(memory): add skill_search signal and retriever skill separation"
```

---

## Task 3: IS Brain Prompt Integration

**Files:**
- Modify: `app/is_prompt.py`
- Modify: `app/routers/v3/agent.py`

- [ ] **Step 1: Add strategies_section to build_prompt**

In `app/is_prompt.py`, add `strategies_section` parameter to `build_prompt()` and inject it after the AVAILABLE MCP TOOLS section.

- [ ] **Step 2: Wire skill retrieval into agent.py**

In `app/routers/v3/agent.py` `_run_is_research()`, before calling `run_research()`:

```python
# Get matching skills for procedural memory
from app.memory.skills import get_matching_skills, format_skills_for_prompt
matching_skills = await get_matching_skills(query, limit=3)
strategies_section = format_skills_for_prompt(matching_skills)

# Increment times_suggested for matched skills
for s in matching_skills:
    execute("UPDATE research_skills SET times_suggested = times_suggested + 1, last_suggested_at = now() WHERE id = %s", (s["id"],))
```

Pass `strategies_section` to `build_prompt()`.

- [ ] **Step 3: Create skill after run completes**

In `_run_is_research()`, after saving research_trails and indexing findings:

```python
# Create procedural memory skill
try:
    from app.memory.skills import create_skill_from_run
    started = ... # capture start time
    await create_skill_from_run(run_id, query, result, duration_seconds=...)
except Exception as exc:
    log.warning("Skill creation failed (non-fatal): %s", exc)
```

- [ ] **Step 4: Update skill quality on feedback**

In `app/routers/v3/research_api.py` `submit_finding_feedback()`, after the existing feedback insert:

```python
# Update procedural skill quality
try:
    from app.memory.skills import update_skill_quality
    import asyncio
    asyncio.create_task(update_skill_quality(run_id))
except Exception:
    pass
```

- [ ] **Step 5: Commit**

```bash
git add app/is_prompt.py app/routers/v3/agent.py app/routers/v3/research_api.py
git commit -m "feat(memory): inject SUGGESTED STRATEGIES into IS brain prompt + create skills on completion"
```

---

## Task 4: Docker Build + Live Test

- [ ] **Step 1: Run all tests**

```bash
uv run pytest tests/memory/ -v
```

- [ ] **Step 2: Build and deploy**

```bash
docker compose build info-broker-api && docker compose up -d info-broker-api
```

- [ ] **Step 3: Verify schema migration**

Check `research_skills` table exists.

- [ ] **Step 4: Run IS brain research**

Send a query, verify a skill is created.

- [ ] **Step 5: Run a similar query**

Verify the IS brain prompt includes SUGGESTED STRATEGIES from the first run.

- [ ] **Step 6: Submit feedback**

Thumbs up on findings, verify skill quality_score updates.

---

## Self-Review

- **Spec Section 1 (Skill Composition):** Covered by Task 1 `create_skill_from_run` — all 5 components stored
- **Spec Section 2 (Schema):** Covered by Task 1 `research_skills` table + Qdrant indexing
- **Spec Section 3 (Write Path):** Task 1 + Task 3 (auto-save after run, quality update on feedback)
- **Spec Section 4 (Read Path):** Task 2 (skill_search signal) + Task 3 (prompt injection)
- **Spec Section 5 (skills.py):** Task 1 creates the full module
- **Spec Section 6 (Files):** All files covered across tasks 1-3
- **Spec Section 7 (Verification):** Task 4 covers all verification criteria
