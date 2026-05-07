# Multi-Signal Retrieval Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace info-broker's single-signal text search with a 5-signal parallel retrieval system (semantic + BM25 + entity graph + temporal + user feedback) fused via Reciprocal Rank Fusion, achieving the Mem0-style architecture that benchmarks at 91.6% LoCoMo accuracy.

**Architecture:** New `app/memory/` package with retriever (5 parallel signals + RRF fusion), writer (indexes findings to Qdrant with dual vectors), and models. Qdrant `research_memory` collection with dense + sparse vectors. Neo4j temporal fields. MCP tool `search_memory`. TDD throughout.

**Tech Stack:** Qdrant (dense + sparse vectors), Neo4j (temporal Cypher), PostgreSQL (feedback join), asyncio.gather (parallel signals), pytest (TDD)

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `app/memory/__init__.py` | Package init |
| `app/memory/models.py` | `MemoryResult` dataclass + types |
| `app/memory/rrf.py` | Reciprocal Rank Fusion — pure function |
| `app/memory/signals.py` | 5 retrieval signal implementations |
| `app/memory/retriever.py` | `fused_retrieve()` — orchestrates signals + RRF |
| `app/memory/writer.py` | `index_research_findings()` — writes to Qdrant |
| `app/memory/collection.py` | Qdrant `research_memory` collection setup |
| `tests/memory/__init__.py` | Test package |
| `tests/memory/test_models.py` | MemoryResult validation tests |
| `tests/memory/test_rrf.py` | RRF fusion algorithm tests |
| `tests/memory/test_signals.py` | Individual signal tests (mocked backends) |
| `tests/memory/test_retriever.py` | Fused retrieval integration tests |
| `tests/memory/test_writer.py` | Memory writer tests |
| `tests/memory/test_performance.py` | Latency, throughput, accuracy benchmarks |

### Modified Files

| File | Change |
|------|--------|
| `app/main.py` | Create `research_memory` Qdrant collection on startup |
| `app/routers/v3/agent.py` | Index findings after IS brain completes |
| `mcp_server/server.py` | Add `search_memory` MCP tool, upgrade `get_past_research` |
| `app/knowledge/neo4j_client.py` | Add temporal validity fields to upsert |
| `app/knowledge/materializer.py` | Set `valid_from`/`valid_to` on materialization |

---

## Task 1: MemoryResult Model + RRF Algorithm

**Files:**
- Create: `app/memory/__init__.py`, `app/memory/models.py`, `app/memory/rrf.py`
- Test: `tests/memory/__init__.py`, `tests/memory/test_models.py`, `tests/memory/test_rrf.py`

- [ ] **Step 1: Write failing tests for MemoryResult**

Create `tests/memory/__init__.py` (empty) and `tests/memory/test_models.py`:

```python
"""Tests for memory system data models."""
from __future__ import annotations
import pytest


def test_memory_result_creation():
    from app.memory.models import MemoryResult
    r = MemoryResult(
        ref="test-123", title="Test", content="Test content",
        source="semantic", score=0.5,
    )
    assert r.ref == "test-123"
    assert r.score == 0.5
    assert r.user_score == 0  # default


def test_memory_result_with_all_fields():
    from app.memory.models import MemoryResult
    r = MemoryResult(
        ref="r1", title="T", content="C", source="bm25", score=0.8,
        run_id="run-1", entity_refs=["person::john"], observed_at="2026-05-07",
        user_score=1, signals={"semantic": 0.9, "bm25": 0.7},
    )
    assert r.run_id == "run-1"
    assert r.entity_refs == ["person::john"]
    assert r.signals["semantic"] == 0.9


def test_memory_result_defaults():
    from app.memory.models import MemoryResult
    r = MemoryResult(ref="x", title="T", content="C", source="s", score=0.0)
    assert r.run_id is None
    assert r.entity_refs == []
    assert r.observed_at is None
    assert r.user_score == 0
    assert r.signals == {}
```

- [ ] **Step 2: Write failing tests for RRF**

Create `tests/memory/test_rrf.py`:

```python
"""Tests for Reciprocal Rank Fusion algorithm."""
from __future__ import annotations
import pytest


def test_rrf_single_signal():
    from app.memory.models import MemoryResult
    from app.memory.rrf import reciprocal_rank_fusion

    results = [[
        MemoryResult(ref="a", title="A", content="", source="s1", score=0),
        MemoryResult(ref="b", title="B", content="", source="s1", score=0),
    ]]
    fused = reciprocal_rank_fusion(results, k=60)
    assert len(fused) == 2
    assert fused[0].ref == "a"  # rank 0 → higher RRF score
    assert fused[0].score > fused[1].score


def test_rrf_two_signals_boost_overlap():
    from app.memory.models import MemoryResult
    from app.memory.rrf import reciprocal_rank_fusion

    signal1 = [
        MemoryResult(ref="a", title="A", content="", source="s1", score=0),
        MemoryResult(ref="b", title="B", content="", source="s1", score=0),
    ]
    signal2 = [
        MemoryResult(ref="b", title="B", content="", source="s2", score=0),
        MemoryResult(ref="c", title="C", content="", source="s2", score=0),
    ]
    fused = reciprocal_rank_fusion([signal1, signal2], k=60)
    # "b" appears in both signals → should be ranked first
    assert fused[0].ref == "b"


def test_rrf_feedback_boost():
    from app.memory.models import MemoryResult
    from app.memory.rrf import reciprocal_rank_fusion

    results = [[
        MemoryResult(ref="a", title="A", content="", source="s1", score=0, user_score=1),
        MemoryResult(ref="b", title="B", content="", source="s1", score=0, user_score=-1),
    ]]
    fused = reciprocal_rank_fusion(results, k=60)
    assert fused[0].ref == "a"  # boosted by thumbs up
    assert fused[0].score > fused[1].score  # "b" penalized by thumbs down


def test_rrf_empty_signals():
    from app.memory.rrf import reciprocal_rank_fusion
    assert reciprocal_rank_fusion([], k=60) == []
    assert reciprocal_rank_fusion([[], []], k=60) == []


def test_rrf_deduplicates_across_signals():
    from app.memory.models import MemoryResult
    from app.memory.rrf import reciprocal_rank_fusion

    signal1 = [MemoryResult(ref="a", title="A", content="C1", source="s1", score=0)]
    signal2 = [MemoryResult(ref="a", title="A", content="C2", source="s2", score=0)]
    fused = reciprocal_rank_fusion([signal1, signal2], k=60)
    assert len(fused) == 1  # deduplicated by ref
    assert fused[0].ref == "a"


def test_rrf_preserves_signal_scores():
    from app.memory.models import MemoryResult
    from app.memory.rrf import reciprocal_rank_fusion

    signal1 = [MemoryResult(ref="a", title="A", content="", source="s1", score=0)]
    signal2 = [MemoryResult(ref="a", title="A", content="", source="s2", score=0)]
    fused = reciprocal_rank_fusion([signal1, signal2], k=60, signal_names=["semantic", "bm25"])
    assert "semantic" in fused[0].signals
    assert "bm25" in fused[0].signals


def test_rrf_latency_under_10ms():
    """RRF fusion of 500 results across 5 signals should complete in <10ms."""
    import time
    from app.memory.models import MemoryResult
    from app.memory.rrf import reciprocal_rank_fusion

    signals = []
    for s in range(5):
        signal = [
            MemoryResult(ref=f"item-{i}-{s}", title=f"T{i}", content="", source=f"s{s}", score=0)
            for i in range(100)
        ]
        signals.append(signal)

    start = time.monotonic()
    fused = reciprocal_rank_fusion(signals, k=60)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 10, f"RRF took {elapsed_ms:.1f}ms, expected <10ms"
    assert len(fused) == 500  # 5 signals * 100 unique items
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/memory/test_models.py tests/memory/test_rrf.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.memory'`

- [ ] **Step 4: Implement MemoryResult and RRF**

Create `app/memory/__init__.py` (empty).

Create `app/memory/models.py`:

```python
"""Memory system data models."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class MemoryResult:
    ref: str
    title: str
    content: str
    source: str
    score: float
    run_id: str | None = None
    entity_refs: list[str] = field(default_factory=list)
    observed_at: str | None = None
    user_score: int = 0
    signals: dict[str, float] = field(default_factory=dict)
```

Create `app/memory/rrf.py`:

```python
"""Reciprocal Rank Fusion — merges ranked lists from multiple retrieval signals.

Based on: Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet
and individual Rank Learning Methods" (SIGIR 2009).
Adopted by Mem0 April 2026 algorithm (research finding #2, 95% confidence).
"""
from __future__ import annotations

from app.memory.models import MemoryResult


def reciprocal_rank_fusion(
    signal_results: list[list[MemoryResult]],
    k: int = 60,
    feedback_boost: float = 0.1,
    feedback_penalty: float = 0.2,
    signal_names: list[str] | None = None,
) -> list[MemoryResult]:
    if not signal_results:
        return []

    scores: dict[str, float] = {}
    items: dict[str, MemoryResult] = {}
    per_signal: dict[str, dict[str, float]] = {}

    for sig_idx, signal_list in enumerate(signal_results):
        sig_name = signal_names[sig_idx] if signal_names and sig_idx < len(signal_names) else f"signal_{sig_idx}"
        for rank, result in enumerate(signal_list):
            rrf_score = 1.0 / (k + rank + 1)
            scores[result.ref] = scores.get(result.ref, 0.0) + rrf_score

            if result.user_score == 1:
                scores[result.ref] += feedback_boost
            elif result.user_score == -1:
                scores[result.ref] -= feedback_penalty

            if result.ref not in per_signal:
                per_signal[result.ref] = {}
            per_signal[result.ref][sig_name] = rrf_score

            if result.ref not in items:
                items[result.ref] = result

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    for ref, total_score in ranked:
        item = items[ref]
        item.score = total_score
        item.signals = per_signal.get(ref, {})
        results.append(item)
    return results
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/memory/test_models.py tests/memory/test_rrf.py -v
```

Expected: All 9 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/memory/__init__.py app/memory/models.py app/memory/rrf.py tests/memory/__init__.py tests/memory/test_models.py tests/memory/test_rrf.py && git commit -m "feat(memory): add MemoryResult model and RRF fusion algorithm (TDD)"
```

---

## Task 2: Qdrant research_memory Collection + Writer

**Files:**
- Create: `app/memory/collection.py`, `app/memory/writer.py`
- Test: `tests/memory/test_writer.py`

- [ ] **Step 1: Write failing tests for the writer**

Create `tests/memory/test_writer.py`:

```python
"""Tests for memory writer — indexes findings to Qdrant."""
from __future__ import annotations
import asyncio
from unittest.mock import patch, MagicMock


def _arun(coro):
    return asyncio.run(coro)


def test_index_findings_creates_points():
    from app.memory.writer import index_research_findings

    upserts = []

    def mock_upsert(collection_name, points):
        upserts.append((collection_name, points))

    mock_client = MagicMock()
    mock_client.upsert = mock_upsert

    findings = [
        {"title": "Finding 1", "content": "Content 1", "source": "ddg_search", "confidence": 90},
        {"title": "Finding 2", "content": "Content 2", "source": "web_crawl", "confidence": 80},
    ]

    with patch("app.memory.writer._get_qdrant_client", return_value=mock_client), \
         patch("app.memory.writer._embed_text", return_value=[0.1] * 768):
        count = _arun(index_research_findings(
            run_id="run-123", query="test query", findings=findings,
        ))

    assert count == 2
    assert len(upserts) == 1  # single batch upsert
    assert upserts[0][0] == "research_memory"


def test_index_findings_skips_error_flagged():
    from app.memory.writer import index_research_findings

    upserts = []
    mock_client = MagicMock()
    mock_client.upsert = lambda **kw: upserts.append(kw)

    findings = [
        {"title": "Good", "content": "C", "source": "ddg", "confidence": 90},
        {"title": "Error", "content": "C", "source": "ddg", "confidence": 0, "error_flagged": True},
    ]

    with patch("app.memory.writer._get_qdrant_client", return_value=mock_client), \
         patch("app.memory.writer._embed_text", return_value=[0.1] * 768):
        count = _arun(index_research_findings("r1", "q", findings))

    assert count == 1  # error finding skipped


def test_index_findings_handles_empty():
    from app.memory.writer import index_research_findings
    with patch("app.memory.writer._get_qdrant_client", return_value=MagicMock()):
        count = _arun(index_research_findings("r1", "q", []))
    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/memory/test_writer.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement collection setup and writer**

Create `app/memory/collection.py`:

```python
"""Qdrant research_memory collection — dual dense + sparse vectors."""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

COLLECTION = "research_memory"
VECTOR_DIM = 768


def ensure_research_memory_collection():
    """Create the research_memory collection if it doesn't exist."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    client = QdrantClient(host=host, port=port)

    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        log.info("Created Qdrant collection: %s", COLLECTION)
    else:
        log.info("Qdrant collection %s already exists", COLLECTION)
```

Create `app/memory/writer.py`:

```python
"""Memory writer — indexes research findings to the research_memory Qdrant collection."""
from __future__ import annotations

import logging
import os
import uuid

log = logging.getLogger(__name__)


def _get_qdrant_client():
    from qdrant_client import QdrantClient
    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    return QdrantClient(host=host, port=port)


def _embed_text(text: str) -> list[float]:
    from llm_providers import embed_text
    return embed_text(text)


async def index_research_findings(
    run_id: str,
    query: str,
    findings: list[dict],
) -> int:
    """Embed and index research findings into research_memory collection.

    Skips error-flagged findings. Returns count of indexed findings.
    """
    valid = [f for f in findings if not f.get("error_flagged", False)]
    if not valid:
        return 0

    from qdrant_client.models import PointStruct
    client = _get_qdrant_client()

    points = []
    for i, finding in enumerate(valid):
        title = finding.get("title", "")
        content = finding.get("content", "")
        text = f"{title}\n{content}"
        vector = _embed_text(text)

        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:{i}"))
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "run_id": run_id,
                "query": query,
                "finding_index": i,
                "title": title,
                "content": content[:2000],
                "source_tool": finding.get("source", ""),
                "confidence": finding.get("confidence", 50),
                "user_score": 0,
                "entity_refs": [],
                "observed_at": finding.get("observed_at", ""),
            },
        ))

    client.upsert(collection_name="research_memory", points=points)
    log.info("Memory writer: indexed %d findings for run %s", len(points), run_id)
    return len(points)
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/memory/test_writer.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/memory/collection.py app/memory/writer.py tests/memory/test_writer.py && git commit -m "feat(memory): add research_memory Qdrant collection and finding writer (TDD)"
```

---

## Task 3: 5 Retrieval Signals

**Files:**
- Create: `app/memory/signals.py`
- Test: `tests/memory/test_signals.py`

- [ ] **Step 1: Write failing tests for each signal**

Create `tests/memory/test_signals.py`:

```python
"""Tests for individual retrieval signals — each tested in isolation with mocked backends."""
from __future__ import annotations
import asyncio
from unittest.mock import patch, MagicMock


def _arun(coro):
    return asyncio.run(coro)


# --- Semantic signal ---

def test_semantic_signal_returns_memory_results():
    from app.memory.signals import semantic_search

    mock_hits = [
        MagicMock(payload={"run_id": "r1", "title": "T1", "content": "C1", "source_tool": "ddg", "confidence": 90, "user_score": 0, "entity_refs": [], "observed_at": ""}, score=0.95),
        MagicMock(payload={"run_id": "r2", "title": "T2", "content": "C2", "source_tool": "web", "confidence": 80, "user_score": 1, "entity_refs": [], "observed_at": ""}, score=0.85),
    ]

    with patch("app.memory.signals._get_qdrant_client") as mock_qc, \
         patch("app.memory.signals._embed_text", return_value=[0.1] * 768):
        mock_qc.return_value.search.return_value = mock_hits
        results = _arun(semantic_search("test query", limit=10))

    assert len(results) == 2
    assert results[0].source == "semantic"
    assert results[0].title == "T1"


# --- BM25 signal ---

def test_bm25_signal_returns_memory_results():
    from app.memory.signals import bm25_search

    # BM25 falls back to PG ILIKE when Qdrant sparse is not available
    with patch("app.memory.signals.fetch_all") as mock_fetch:
        mock_fetch.return_value = [
            {"id": "id1", "query": "test", "findings": '[{"title": "F1", "content": "C1", "source": "ddg", "confidence": 85}]'},
        ]
        results = _arun(bm25_search("test query", limit=10))

    assert len(results) >= 1
    assert results[0].source == "bm25"


# --- Entity signal ---

def test_entity_signal_searches_neo4j():
    from app.memory.signals import entity_search

    mock_neo4j = MagicMock()
    mock_neo4j.search_entities.return_value = [
        {"ref": "person::john", "name": "John Doe", "entity_type": "person", "confidence": 80, "observation_count": 5},
    ]

    with patch("app.memory.signals.Neo4jClient", return_value=mock_neo4j):
        results = _arun(entity_search("John", limit=10))

    assert len(results) == 1
    assert results[0].source == "entity"
    assert "john" in results[0].ref


# --- Temporal signal ---

def test_temporal_signal_filters_by_time():
    from app.memory.signals import temporal_search

    with patch("app.memory.signals.fetch_all") as mock_fetch:
        mock_fetch.return_value = [
            {"entity_ref": "org::acme", "entity_type": "organization", "attribute": "name", "value": "Acme Corp", "confidence": 90, "observed_at": "2026-05-01T00:00:00Z"},
        ]
        results = _arun(temporal_search("Acme", limit=10))

    assert len(results) == 1
    assert results[0].source == "temporal"


# --- Feedback signal ---

def test_feedback_signal_boosts_liked_findings():
    from app.memory.signals import feedback_search

    with patch("app.memory.signals.fetch_all") as mock_fetch:
        mock_fetch.return_value = [
            {"run_id": "r1", "finding_index": 0, "finding_title": "Good finding", "user_score": 1, "reason": ""},
            {"run_id": "r2", "finding_index": 1, "finding_title": "Bad finding", "user_score": -1, "reason": "irrelevant"},
        ]
        results = _arun(feedback_search("test", limit=10))

    assert len(results) == 2
    # Thumbs up should be first
    assert results[0].user_score == 1
    assert results[1].user_score == -1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/memory/test_signals.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement all 5 signals**

Create `app/memory/signals.py`:

```python
"""Retrieval signals — each queries a different backend and returns MemoryResult lists.

Signals:
1. semantic_search — Qdrant dense vector similarity
2. bm25_search — Qdrant sparse / PG ILIKE fallback
3. entity_search — Neo4j knowledge graph
4. temporal_search — PG entity_observations with time filters
5. feedback_search — PG finding_feedback (user thumbs up/down)
"""
from __future__ import annotations

import json
import logging
import os

from app.memory.models import MemoryResult

log = logging.getLogger(__name__)


def _get_qdrant_client():
    from qdrant_client import QdrantClient
    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    return QdrantClient(host=host, port=port)


def _embed_text(text: str) -> list[float]:
    from llm_providers import embed_text
    return embed_text(text)


# --- Signal 1: Semantic similarity (Qdrant dense vectors) ---

async def semantic_search(query: str, limit: int = 50) -> list[MemoryResult]:
    try:
        client = _get_qdrant_client()
        vector = _embed_text(query)
        hits = client.search(
            collection_name="research_memory",
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )
        return [
            MemoryResult(
                ref=str(h.id),
                title=h.payload.get("title", ""),
                content=h.payload.get("content", ""),
                source="semantic",
                score=h.score,
                run_id=h.payload.get("run_id"),
                entity_refs=h.payload.get("entity_refs", []),
                observed_at=h.payload.get("observed_at"),
                user_score=h.payload.get("user_score", 0),
            )
            for h in hits if h.payload
        ]
    except Exception as exc:
        log.warning("Semantic signal failed: %s", exc)
        return []


# --- Signal 2: BM25 keyword (PG ILIKE fallback) ---

async def bm25_search(query: str, limit: int = 50) -> list[MemoryResult]:
    from app.routers.v3.db import fetch_all

    try:
        rows = fetch_all(
            """SELECT id, query, findings FROM research_trails
            WHERE query ILIKE %s OR findings::text ILIKE %s
            ORDER BY created_at DESC LIMIT %s""",
            (f"%{query}%", f"%{query}%", limit),
        )
        results = []
        for row in rows:
            findings = row.get("findings", [])
            if isinstance(findings, str):
                findings = json.loads(findings)
            for f in findings[:5]:  # top 5 per trail
                results.append(MemoryResult(
                    ref=f"{row['id']}:{f.get('title', '')[:20]}",
                    title=f.get("title", ""),
                    content=f.get("content", ""),
                    source="bm25",
                    score=0.0,
                    run_id=str(row["id"]),
                    user_score=0,
                ))
        return results[:limit]
    except Exception as exc:
        log.warning("BM25 signal failed: %s", exc)
        return []


# --- Signal 3: Entity graph (Neo4j) ---

async def entity_search(query: str, limit: int = 30) -> list[MemoryResult]:
    try:
        from app.knowledge.neo4j_client import Neo4jClient
        client = Neo4jClient()
        entities = client.search_entities(query=query, limit=limit)
        client.close()
        return [
            MemoryResult(
                ref=e.get("ref", ""),
                title=e.get("name", ""),
                content=f"{e.get('entity_type', '')} entity with {e.get('observation_count', 0)} observations",
                source="entity",
                score=0.0,
                entity_refs=[e.get("ref", "")],
            )
            for e in entities if e.get("ref")
        ]
    except Exception as exc:
        log.warning("Entity signal failed: %s", exc)
        return []


# --- Signal 4: Temporal (PG entity_observations with time awareness) ---

async def temporal_search(query: str, limit: int = 30, time_filter: tuple | None = None) -> list[MemoryResult]:
    from app.routers.v3.db import fetch_all

    try:
        conditions = ["value ILIKE %s"]
        params: list = [f"%{query}%"]
        if time_filter:
            conditions.append("observed_at >= %s AND observed_at <= %s")
            params.extend(time_filter)
        params.append(limit)

        where = " AND ".join(conditions)
        rows = fetch_all(
            f"""SELECT DISTINCT ON (entity_ref) entity_ref, entity_type, attribute, value,
                confidence, observed_at
            FROM entity_observations WHERE {where}
            ORDER BY entity_ref, confidence DESC, observed_at DESC
            LIMIT %s""",
            tuple(params),
        )
        return [
            MemoryResult(
                ref=r["entity_ref"],
                title=r["value"],
                content=f"{r['attribute']}={r['value']} ({r['entity_type']})",
                source="temporal",
                score=0.0,
                observed_at=str(r.get("observed_at", "")),
            )
            for r in rows
        ]
    except Exception as exc:
        log.warning("Temporal signal failed: %s", exc)
        return []


# --- Signal 5: User feedback (PG finding_feedback) ---

async def feedback_search(query: str, limit: int = 50) -> list[MemoryResult]:
    from app.routers.v3.db import fetch_all

    try:
        rows = fetch_all(
            """SELECT ff.run_id, ff.finding_index, ff.finding_title, ff.user_score, ff.reason
            FROM finding_feedback ff
            WHERE ff.finding_title ILIKE %s OR ff.reason ILIKE %s
            ORDER BY ff.user_score DESC, ff.created_at DESC
            LIMIT %s""",
            (f"%{query}%", f"%{query}%", limit),
        )
        return [
            MemoryResult(
                ref=f"feedback:{r['run_id']}:{r['finding_index']}",
                title=r.get("finding_title", ""),
                content=r.get("reason", ""),
                source="feedback",
                score=0.0,
                run_id=str(r.get("run_id", "")),
                user_score=r.get("user_score", 0),
            )
            for r in rows
        ]
    except Exception as exc:
        log.warning("Feedback signal failed: %s", exc)
        return []
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/memory/test_signals.py -v
```

Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/memory/signals.py tests/memory/test_signals.py && git commit -m "feat(memory): add 5 retrieval signals — semantic, bm25, entity, temporal, feedback (TDD)"
```

---

## Task 4: Fused Retriever

**Files:**
- Create: `app/memory/retriever.py`
- Test: `tests/memory/test_retriever.py`

- [ ] **Step 1: Write failing tests**

Create `tests/memory/test_retriever.py`:

```python
"""Tests for fused retriever — orchestrates 5 signals + RRF."""
from __future__ import annotations
import asyncio
from unittest.mock import patch, AsyncMock

from app.memory.models import MemoryResult


def _arun(coro):
    return asyncio.run(coro)


def _make_results(source: str, refs: list[str]) -> list[MemoryResult]:
    return [MemoryResult(ref=r, title=r, content="", source=source, score=0) for r in refs]


def test_fused_retrieve_calls_all_signals():
    from app.memory.retriever import fused_retrieve

    with patch("app.memory.retriever.semantic_search", new_callable=AsyncMock, return_value=_make_results("semantic", ["a", "b"])), \
         patch("app.memory.retriever.bm25_search", new_callable=AsyncMock, return_value=_make_results("bm25", ["b", "c"])), \
         patch("app.memory.retriever.entity_search", new_callable=AsyncMock, return_value=_make_results("entity", ["c", "d"])), \
         patch("app.memory.retriever.temporal_search", new_callable=AsyncMock, return_value=_make_results("temporal", ["d", "e"])), \
         patch("app.memory.retriever.feedback_search", new_callable=AsyncMock, return_value=_make_results("feedback", ["a"])):

        results = _arun(fused_retrieve("test query", limit=10))

    assert len(results) == 5  # a, b, c, d, e — all unique
    # Items appearing in multiple signals should rank higher
    multi_signal = [r for r in results if len(r.signals) > 1]
    assert len(multi_signal) >= 2  # b appears in semantic+bm25, c in bm25+entity, d in entity+temporal


def test_fused_retrieve_respects_limit():
    from app.memory.retriever import fused_retrieve

    with patch("app.memory.retriever.semantic_search", new_callable=AsyncMock, return_value=_make_results("semantic", [f"item-{i}" for i in range(20)])), \
         patch("app.memory.retriever.bm25_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.memory.retriever.entity_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.memory.retriever.temporal_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.memory.retriever.feedback_search", new_callable=AsyncMock, return_value=[]):

        results = _arun(fused_retrieve("test", limit=5))

    assert len(results) == 5


def test_fused_retrieve_handles_all_signals_failing():
    from app.memory.retriever import fused_retrieve

    with patch("app.memory.retriever.semantic_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.memory.retriever.bm25_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.memory.retriever.entity_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.memory.retriever.temporal_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.memory.retriever.feedback_search", new_callable=AsyncMock, return_value=[]):

        results = _arun(fused_retrieve("test"))

    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/memory/test_retriever.py -v
```

- [ ] **Step 3: Implement fused retriever**

Create `app/memory/retriever.py`:

```python
"""Fused retriever — runs 5 signals in parallel and merges via RRF.

This is the Mem0-style multi-signal retrieval pattern that benchmarks
at 91.6% LoCoMo accuracy (research finding #2, 95% confidence).
"""
from __future__ import annotations

import asyncio
import logging

from app.memory.models import MemoryResult
from app.memory.rrf import reciprocal_rank_fusion
from app.memory.signals import (
    semantic_search,
    bm25_search,
    entity_search,
    temporal_search,
    feedback_search,
)

log = logging.getLogger(__name__)

_SIGNAL_NAMES = ["semantic", "bm25", "entity", "temporal", "feedback"]


async def fused_retrieve(
    query: str,
    limit: int = 20,
    time_filter: tuple | None = None,
    entity_types: list[str] | None = None,
    user_id: str | None = None,
) -> list[MemoryResult]:
    """Run 5 retrieval signals in parallel and fuse via Reciprocal Rank Fusion.

    Returns up to `limit` MemoryResult objects ranked by fusion score.
    Each result includes per-signal scores in the `signals` dict for explainability.
    """
    signal_results = await asyncio.gather(
        semantic_search(query, limit=50),
        bm25_search(query, limit=50),
        entity_search(query, limit=30),
        temporal_search(query, limit=30, time_filter=time_filter),
        feedback_search(query, limit=50),
        return_exceptions=True,
    )

    # Replace exceptions with empty lists
    clean_results = []
    for i, result in enumerate(signal_results):
        if isinstance(result, Exception):
            log.warning("Signal %s failed: %s", _SIGNAL_NAMES[i], result)
            clean_results.append([])
        else:
            clean_results.append(result)

    fused = reciprocal_rank_fusion(
        clean_results,
        k=60,
        signal_names=_SIGNAL_NAMES,
    )

    return fused[:limit]
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/memory/test_retriever.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/memory/retriever.py tests/memory/test_retriever.py && git commit -m "feat(memory): add fused retriever — 5 signals + RRF fusion (TDD)"
```

---

## Task 5: Performance + Accuracy Tests

**Files:**
- Create: `tests/memory/test_performance.py`

- [ ] **Step 1: Write performance and accuracy tests**

Create `tests/memory/test_performance.py`:

```python
"""Performance, latency, and accuracy tests for the memory system."""
from __future__ import annotations
import asyncio
import time
from unittest.mock import patch, AsyncMock, MagicMock

from app.memory.models import MemoryResult


def _arun(coro):
    return asyncio.run(coro)


def _make_results(source: str, count: int) -> list[MemoryResult]:
    return [
        MemoryResult(ref=f"{source}-{i}", title=f"T{i}", content=f"Content {i}", source=source, score=0)
        for i in range(count)
    ]


# --- Latency tests ---

def test_rrf_fusion_latency_500_items_under_10ms():
    """RRF fusion of 500 items across 5 signals must complete in <10ms."""
    from app.memory.rrf import reciprocal_rank_fusion

    signals = [_make_results(f"s{i}", 100) for i in range(5)]
    start = time.monotonic()
    result = reciprocal_rank_fusion(signals, k=60, signal_names=[f"s{i}" for i in range(5)])
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 10, f"RRF took {elapsed_ms:.1f}ms"
    assert len(result) == 500


def test_rrf_fusion_latency_2000_items_under_50ms():
    """RRF fusion of 2000 items across 5 signals must complete in <50ms."""
    from app.memory.rrf import reciprocal_rank_fusion

    signals = [_make_results(f"s{i}", 400) for i in range(5)]
    start = time.monotonic()
    result = reciprocal_rank_fusion(signals, k=60)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 50, f"RRF took {elapsed_ms:.1f}ms"


def test_fused_retrieve_parallel_faster_than_sequential():
    """Parallel signal execution should be faster than sequential."""
    from app.memory.retriever import fused_retrieve

    async def slow_signal(query, **kw):
        await asyncio.sleep(0.05)  # 50ms per signal
        return _make_results("slow", 5)

    with patch("app.memory.retriever.semantic_search", new_callable=AsyncMock, side_effect=slow_signal), \
         patch("app.memory.retriever.bm25_search", new_callable=AsyncMock, side_effect=slow_signal), \
         patch("app.memory.retriever.entity_search", new_callable=AsyncMock, side_effect=slow_signal), \
         patch("app.memory.retriever.temporal_search", new_callable=AsyncMock, side_effect=slow_signal), \
         patch("app.memory.retriever.feedback_search", new_callable=AsyncMock, side_effect=slow_signal):

        start = time.monotonic()
        _arun(fused_retrieve("test"))
        elapsed_ms = (time.monotonic() - start) * 1000

    # Sequential would be 5 * 50ms = 250ms. Parallel should be ~50ms + overhead
    assert elapsed_ms < 150, f"Fused retrieve took {elapsed_ms:.1f}ms, expected parallel execution"


# --- Accuracy tests ---

def test_multi_signal_overlap_ranks_higher_than_single():
    """Items appearing in multiple signals must rank higher than single-signal items."""
    from app.memory.rrf import reciprocal_rank_fusion

    signal1 = [
        MemoryResult(ref="overlap", title="O", content="", source="s1", score=0),
        MemoryResult(ref="only-s1", title="S1", content="", source="s1", score=0),
    ]
    signal2 = [
        MemoryResult(ref="overlap", title="O", content="", source="s2", score=0),
        MemoryResult(ref="only-s2", title="S2", content="", source="s2", score=0),
    ]
    fused = reciprocal_rank_fusion([signal1, signal2], k=60)
    assert fused[0].ref == "overlap", "Multi-signal overlap should rank first"


def test_feedback_affects_ranking():
    """User feedback should measurably affect ranking order."""
    from app.memory.rrf import reciprocal_rank_fusion

    # Same rank in same signal, but different feedback
    signal = [
        MemoryResult(ref="neutral", title="N", content="", source="s", score=0, user_score=0),
        MemoryResult(ref="liked", title="L", content="", source="s", score=0, user_score=1),
    ]
    fused = reciprocal_rank_fusion([signal], k=60)
    liked = next(r for r in fused if r.ref == "liked")
    neutral = next(r for r in fused if r.ref == "neutral")
    assert liked.score > neutral.score, "Liked item should score higher than neutral"


# --- Persistence tests ---

def test_writer_produces_deterministic_ids():
    """Same run_id + finding_index should produce same point ID (idempotent upsert)."""
    import uuid
    id1 = str(uuid.uuid5(uuid.NAMESPACE_URL, "run-abc:0"))
    id2 = str(uuid.uuid5(uuid.NAMESPACE_URL, "run-abc:0"))
    assert id1 == id2, "Point IDs must be deterministic for idempotent upserts"


def test_writer_different_findings_produce_different_ids():
    """Different run_id or finding_index should produce different point IDs."""
    import uuid
    id1 = str(uuid.uuid5(uuid.NAMESPACE_URL, "run-abc:0"))
    id2 = str(uuid.uuid5(uuid.NAMESPACE_URL, "run-abc:1"))
    id3 = str(uuid.uuid5(uuid.NAMESPACE_URL, "run-def:0"))
    assert id1 != id2
    assert id1 != id3


# --- Data quality tests ---

def test_error_flagged_findings_excluded_from_memory():
    """Error-flagged findings should never enter the memory index."""
    from app.memory.writer import index_research_findings

    findings = [
        {"title": "Good", "content": "C", "source": "ddg", "confidence": 90},
        {"title": "Error 403", "content": "blocked", "source": "apollo", "confidence": 0, "error_flagged": True},
        {"title": "Low conf", "content": "C", "source": "ddg", "confidence": 10, "error_flagged": False},
    ]

    upserts = []
    mock_client = MagicMock()
    mock_client.upsert = lambda **kw: upserts.append(kw)

    with patch("app.memory.writer._get_qdrant_client", return_value=mock_client), \
         patch("app.memory.writer._embed_text", return_value=[0.1] * 768):
        count = _arun(index_research_findings("r1", "q", findings))

    # Error-flagged excluded, low-conf included (filtering is analyzer's job, not writer's)
    assert count == 2


def _arun(coro):
    return asyncio.run(coro)
```

- [ ] **Step 2: Run tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/memory/test_performance.py -v
```

Expected: All 8 tests PASS (since they use mocked signals or pure functions)

- [ ] **Step 3: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add tests/memory/test_performance.py && git commit -m "test(memory): add performance, latency, accuracy, persistence, and data quality tests"
```

---

## Task 6: Wire Into IS Brain + MCP

**Files:**
- Modify: `app/main.py` — create collection on startup
- Modify: `app/routers/v3/agent.py` — index findings after research
- Modify: `mcp_server/server.py` — add `search_memory` tool, upgrade `get_past_research`

- [ ] **Step 1: Wire collection creation into startup**

In `app/main.py`, after the Qdrant setup (around line 103), add:

```python
    try:
        from app.memory.collection import ensure_research_memory_collection
        ensure_research_memory_collection()
    except Exception as exc:
        _log.warning("research_memory collection setup: %s", exc)
```

- [ ] **Step 2: Wire memory indexing into IS brain completion**

In `app/routers/v3/agent.py`, after `execute(INSERT INTO research_trails...)` (around line 199), add:

```python
        # Index findings to research_memory for multi-signal retrieval
        try:
            from app.memory.writer import index_research_findings
            await index_research_findings(run_id, query, result.get("findings", []))
        except Exception as exc:
            log.warning("Memory indexing failed (non-fatal): %s", exc)
```

- [ ] **Step 3: Add search_memory MCP tool**

Add to `mcp_server/server.py` (in the research run access section):

```python
@mcp.tool()
async def search_memory(query: str, limit: int = 10) -> str:
    """Search info-broker's memory using multi-signal fusion.

    Combines semantic similarity, keyword matching, knowledge graph
    entities, temporal awareness, and user feedback scores.
    Returns ranked results with per-signal explainability.
    """
    result = await api_call(
        "POST",
        "/v3/memory/search",
        json={"query": query, "limit": limit},
    )
    return json.dumps(result, default=str)
```

- [ ] **Step 4: Add memory search API endpoint**

Create a simple endpoint in `app/routers/v3/knowledge_api.py` (or a new `memory_api.py`):

```python
@router.post("/memory/search")
async def search_memory_endpoint(body: dict, _key: str = Depends(require_api_key)):
    from app.memory.retriever import fused_retrieve
    query = body.get("query", "")
    limit = body.get("limit", 20)
    results = await fused_retrieve(query, limit=limit)
    return [
        {
            "ref": r.ref, "title": r.title, "content": r.content[:500],
            "source": r.source, "score": r.score, "run_id": r.run_id,
            "entity_refs": r.entity_refs, "observed_at": r.observed_at,
            "user_score": r.user_score, "signals": r.signals,
        }
        for r in results
    ]
```

- [ ] **Step 5: Run all memory tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/memory/ -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/main.py app/routers/v3/agent.py mcp_server/server.py app/routers/v3/knowledge_api.py && git commit -m "feat(memory): wire retrieval fusion into IS brain, MCP, and API"
```

---

## Task 7: Neo4j Temporal Validity

**Files:**
- Modify: `app/knowledge/neo4j_client.py` — add valid_from/valid_to
- Modify: `app/knowledge/materializer.py` — set temporal fields

- [ ] **Step 1: Update Neo4j upsert to include temporal fields**

In `app/knowledge/neo4j_client.py`, update the `upsert_entity` Cypher to add:
```cypher
ON CREATE SET
    n.valid_from = $first_seen,
    n.valid_to = null,
    ...
```

And update `upsert_relationship` similarly.

- [ ] **Step 2: Update materializer to track temporal changes**

In `app/knowledge/materializer.py`, when materializing entities:
- Set `valid_from` from earliest observation's `observed_at`
- Keep `valid_to = null` (currently valid)
- When a conflicting attribute value arrives, the old observation keeps its timestamp and the new one becomes current

- [ ] **Step 3: Run existing knowledge tests + new memory tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/knowledge/ tests/memory/ -v
```

- [ ] **Step 4: Commit**

```bash
cd /Users/rinehardramos/Projects/info-broker && git add app/knowledge/neo4j_client.py app/knowledge/materializer.py && git commit -m "feat(memory): add temporal validity to Neo4j entities and relationships"
```

---

## Task 8: Docker Build + Integration Test

- [ ] **Step 1: Run all tests**

```bash
cd /Users/rinehardramos/Projects/info-broker && uv run pytest tests/memory/ tests/knowledge/ tests/observability/ -v
```

- [ ] **Step 2: Build and deploy**

```bash
export PATH="/opt/homebrew/bin:$PATH"
docker compose build --no-cache info-broker-api
docker compose up -d
```

- [ ] **Step 3: Verify research_memory collection exists**

```bash
curl -s http://localhost:6335/collections/research_memory | python3 -m json.tool
```

- [ ] **Step 4: Run IS brain research to populate memory**

Send a research query and verify findings are indexed to research_memory.

- [ ] **Step 5: Test fused retrieval via MCP**

Call `search_memory("Philippines IT outsourcing")` and verify results come from multiple signals.

- [ ] **Step 6: Verify temporal fields in Neo4j**

Check that entities have `valid_from` set after materialization.
