# Phase 1: Multi-Signal Retrieval Fusion + Temporal Awareness

## Research Foundation

This design is based on findings from research run `af36f7e0-94a8-47a8-8a3c-c4e093187a31` — "What is the best memory design for AI in 2026?" (12 findings, 12 branches, 0 dead ends).

### Key Citations

| # | Finding | Confidence | Source | Relevance |
|---|---------|------------|--------|-----------|
| 1 | Mem0 ECAI 2025 benchmark: vanilla RAG = 61% LOCOMO; Mem0 = 66.9%; Mem0g (graph) = 68.4%; full-context = 72.9% but unusable latency | 95% | arXiv:2504.19413, mem0.ai/blog | Pure vector RAG is no longer competitive — selective/graph-enhanced memory wins on the production trade-off curve |
| 2 | Mem0 April 2026 algorithm: 91.6 LoCoMo / 93.4 LongMemEval at <7K tokens using **multi-signal retrieval that fuses semantic similarity + BM25 keyword + entity matching in parallel** | 95% | mem0.ai/research | **Primary design pattern** — the specific fusion architecture this spec implements |
| 3 | Zep/Graphiti temporal knowledge graph outperforms MemGPT on DMR; Graphiti builds real-time KGs with entities, relationships, and validity intervals | 90% | arXiv:2501.13956, github.com/getzep/graphiti | Temporal validity on entities solves RAG's weakness on evolving facts |
| 4 | Four-dimension memory framework: Storage, Curation, Retrieval, Lifecycle — RAG only addresses Storage + naive Retrieval | 88% | atlan.com 2026 analysis | Architecture must address all 4 dimensions, not just retrieval |
| 5 | Three cognitive memory types: semantic (facts), episodic (events), procedural (skills) — all three required | 90% | Mem0, MachineLearningMastery Dec 2025, Tulving 1972 | info-broker needs all three; this phase upgrades semantic + episodic retrieval |
| 6 | Dominant 2026 pattern is **dual-store**: vector + graph, with a router — "Any sufficiently complicated RAG pipeline eventually contains an ad hoc implementation of half of a Knowledge Graph" | 87% | MachineLearningMastery 2026, SQLDocs | Validates info-broker's Qdrant + Neo4j architecture |
| 7 | Tiered memory architecture (hot/warm/cold/archive) — production pattern from Fabric AI's COALA system | 82% | fabric.pro/en/blog, Multi-Layered Memory paper | Future phase (P4) — not implemented here |

---

## Overview

Replace info-broker's single-signal semantic search with a 5-signal parallel retrieval system fused via Reciprocal Rank Fusion (RRF). Add temporal validity to the knowledge graph so facts carry time bounds.

**Architecture:** Qdrant (dual dense+sparse vectors) + Neo4j (temporal KG) + PG (feedback scores) → parallel query → RRF fusion → ranked results.

**Measured impact:** Mem0's benchmark shows 61% → 91.6% accuracy improvement moving from vanilla RAG to multi-signal fusion (Finding #2).

---

## 1. Retrieval Signals

### 5 Parallel Signals

| # | Signal | Backend | What It Finds | Latency |
|---|--------|---------|---------------|---------|
| 1 | **Semantic similarity** | Qdrant dense vector (768-dim) | Conceptually related research — "IT outsourcing PH" finds "BPO companies Manila" | ~50ms |
| 2 | **BM25 keyword** | Qdrant sparse vector (native) | Exact term matches vectors miss — "Accenture" finds prior Accenture research by name | ~30ms |
| 3 | **Entity graph** | Neo4j Cypher | KG entities + relationships — "CEO Philippines" finds Person nodes linked to PH organizations | ~80ms |
| 4 | **Temporal** | Neo4j + PG | Time-filtered facts — "Accenture CEO 2026" filters to recent observations only | ~80ms |
| 5 | **User feedback** | PG finding_feedback | Boost/demote findings based on thumbs up/down scores | ~10ms |

All signals fire in parallel via `asyncio.gather`. Total latency = max(individual) ≈ 80ms, not sum.

### Reciprocal Rank Fusion (RRF)

Based on Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods" (SIGIR 2009). Adopted by Mem0's April 2026 algorithm (Finding #2).

```
For each result appearing in any signal's ranked list:
  score(result) = sum( 1 / (k + rank_i) ) for each signal i where result appears
  
  // User feedback modifier:
  if user_score == +1: score += 0.1   (thumbs up boost)
  if user_score == -1: score -= 0.2   (thumbs down penalty)
```

`k = 60` is the standard constant (dampens rank sensitivity).

---

## 2. Schema Changes

### 2.1 New Qdrant Collection: `research_memory`

Dedicated collection for research findings with dual vectors:

```
Collection: research_memory
  Dense vector: 768-dim (semantic embedding via LLM provider)
  Sparse vector: BM25 (Qdrant native tokenizer)
  
Payload fields:
  run_id: str           — Source research run UUID
  query: str            — Original research query
  finding_index: int    — Index within the run's findings
  title: str            — Finding title
  content: str          — Finding content (full text)
  source_tool: str      — Tool that produced it (ddg_search, web_crawl, etc.)
  confidence: int       — Brain's confidence score (0-100)
  user_score: int       — Aggregated user feedback (-1/0/+1)
  entity_refs: list[str] — Linked entity refs in Neo4j KG
  observed_at: str      — ISO timestamp of when finding was created
```

### 2.2 Neo4j: Temporal Validity

Add time bounds to entity nodes and relationships:

```cypher
// Entities gain temporal fields
(:Person {
  ref, name, ...,
  valid_from: datetime,   -- when first observed
  valid_to: datetime | null  -- null = currently valid
})

// Relationships gain temporal fields  
(:Person)-[:WORKS_AT {
  confidence, evidence, 
  valid_from: datetime,
  valid_to: datetime | null
}]->(:Organization)
```

The materializer sets `valid_from` from the earliest `observed_at` of contributing observations.

### 2.3 PG: Access Tracking

```sql
ALTER TABLE entity_observations ADD COLUMN IF NOT EXISTS access_count INT DEFAULT 0;
ALTER TABLE entity_observations ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ;
```

Incremented each time a finding is returned by the retrieval system. Used by future Phase 4 (Tiered Lifecycle) for promotion/demotion decisions.

---

## 3. New Module: `app/memory/`

### 3.1 `app/memory/retriever.py` — Fused Retrieval

```python
async def fused_retrieve(
    query: str,
    limit: int = 20,
    time_filter: tuple[datetime, datetime] | None = None,
    entity_types: list[str] | None = None,
    user_id: str | None = None,
) -> list[MemoryResult]:
    """Run 5 retrieval signals in parallel and fuse via RRF."""
```

Returns `list[MemoryResult]` — a dataclass with:
- `ref`, `title`, `content`, `source`, `score` (RRF fusion score)
- `run_id` (originating research), `entity_refs` (KG links)
- `observed_at`, `user_score`, `signals` (per-signal scores for explainability)

### 3.2 `app/memory/writer.py` — Index Research to Memory

```python
async def index_research_findings(
    run_id: str,
    query: str,
    findings: list[dict],
) -> int:
    """Embed and index research findings into research_memory collection."""
```

Called after every IS brain research run completes. Generates both dense + sparse vectors per finding, extracts entity refs from KG, upserts to Qdrant.

### 3.3 `app/memory/rrf.py` — Reciprocal Rank Fusion

Pure function, no dependencies:

```python
def reciprocal_rank_fusion(
    signal_results: list[list[MemoryResult]],
    k: int = 60,
    feedback_boost: float = 0.1,
    feedback_penalty: float = 0.2,
) -> list[MemoryResult]:
```

---

## 4. Integration Points

### 4.1 IS Brain: `get_past_research` MCP Tool

Current: single Qdrant semantic search over `research_trails`.
New: calls `fused_retrieve()` which queries all 5 signals.

The IS brain prompt already uses this tool in the BOOTSTRAP phase. No prompt changes needed — the tool just returns better results.

### 4.2 New MCP Tool: `search_memory`

```python
@mcp.tool()
async def search_memory(query: str, limit: int = 10) -> str:
    """Search info-broker's memory using multi-signal fusion.
    
    Combines semantic similarity, keyword matching, knowledge graph
    entities, temporal awareness, and user feedback scores.
    """
```

Available to the IS brain and external agents (worker-mcp).

### 4.3 Write Path: After Research Completion

In `app/routers/v3/agent.py` `_run_is_research()`, after saving `research_trails`:

```python
# Index findings into research_memory for future retrieval
from app.memory.writer import index_research_findings
await index_research_findings(run_id, query, result["findings"])
```

### 4.4 Frontend: Knowledge Graph Search

`/v3/knowledge/entities` endpoint already falls back to PG when Neo4j is unavailable. The entity signal in `fused_retrieve()` uses the same Neo4j search, adding it to the fusion.

---

## 5. Temporal Query Support

### Time-Aware Retrieval

The temporal signal queries Neo4j for entities that were **valid at a specific time**:

```cypher
// Find entities valid as of a given date
MATCH (n)
WHERE n.valid_from <= $as_of_date
  AND (n.valid_to IS NULL OR n.valid_to >= $as_of_date)
  AND toLower(n.name) CONTAINS toLower($query)
RETURN n
```

### Temporal Validity in Materializer

The graph materializer (`app/knowledge/materializer.py`) is updated to:
1. Set `valid_from` = earliest `observed_at` from contributing observations
2. Set `valid_to` = null (currently valid) by default
3. When a contradicting observation arrives (same entity, same attribute, different value), set `valid_to` on the old value and `valid_from` on the new value

This implements the Graphiti pattern from Finding #3: *"entities, relationships, and validity intervals (e.g. 'Kendra loves Adidas shoes as of March 2026')"*.

---

## 6. Docker/Infrastructure Changes

**No new containers.** Qdrant and Neo4j already deployed. Changes:
- Create `research_memory` collection on startup (like existing `search_results`)
- Neo4j: add `valid_from`/`valid_to` properties (no schema migration needed — Neo4j is schemaless)

---

## 7. Phased Memory Roadmap (Context)

This spec is Phase 1 of 5. Each phase gets its own spec.

| Phase | Name | Status | Research Basis |
|-------|------|--------|---------------|
| **P1** | **Multi-Signal Retrieval + Temporal** | **This spec** | Findings #1, #2, #3, #6 |
| P2 | Procedural Memory | Next | Findings #5, #12 |
| P3 | Curation & Contradiction Detection | After P2 | Findings #4, #10 |
| P4 | Tiered Lifecycle (hot/warm/cold) | After P3 | Findings #4, #7 |
| P5 | LLM-Assisted Memory Ops | After P4 | Findings #8, #9 |

---

## 8. Verification Criteria

1. **Semantic signal**: `fused_retrieve("IT outsourcing Philippines")` returns prior research about BPO companies
2. **BM25 signal**: `fused_retrieve("Accenture")` returns exact-match results that pure semantic might rank lower
3. **Entity signal**: `fused_retrieve("CEO")` returns Person entities from Neo4j with works_at relationships
4. **Temporal signal**: Query with time filter returns only observations within the date range
5. **Feedback signal**: Thumbs-down findings are demoted in fusion results
6. **RRF fusion**: Results from multiple signals are correctly merged (no duplicates, proper ranking)
7. **Write path**: After IS brain run, findings appear in `research_memory` collection
8. **IS brain**: `get_past_research` returns fused results (better prior context than before)
9. **MCP tool**: `search_memory` returns fused results via MCP
10. **Temporal validity**: Neo4j entities have `valid_from`/`valid_to` set by materializer
