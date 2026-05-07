"""Tests for multi-signal retrieval — semantic, bm25, entity, temporal, feedback, skill."""

from __future__ import annotations

import asyncio
import json
import sys
from unittest.mock import MagicMock, patch

# Stub out heavy optional dependencies before any app imports so that
# module-level imports in signals.py / neo4j_client.py don't fail in CI.
for _mod in [
    "qdrant_client",
    "qdrant_client.models",
    "neo4j",
    "psycopg2",
    "psycopg2.extras",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from app.memory.models import MemoryResult


# ---------------------------------------------------------------------------
# 1. Semantic signal (Qdrant dense vector search)
# ---------------------------------------------------------------------------

def test_semantic_signal_returns_memory_results():
    """Mock Qdrant client.search returning 2 hits; verify 2 MemoryResults with source='semantic'."""
    hit1 = MagicMock()
    hit1.score = 0.92
    hit1.payload = {
        "ref": "doc:001",
        "title": "Acme Corp",
        "content": "Acme Corp is a software company.",
        "run_id": "run-abc",
        "entity_refs": ["entity:acme"],
    }

    hit2 = MagicMock()
    hit2.score = 0.75
    hit2.payload = {
        "ref": "doc:002",
        "title": "Globex Inc",
        "content": "Globex Inc is a rival.",
        "run_id": None,
        "entity_refs": [],
    }

    mock_client = MagicMock()
    query_resp = MagicMock()
    query_resp.points = [hit1, hit2]
    mock_client.query_points.return_value = query_resp

    with patch("app.memory.signals._get_qdrant_client", return_value=mock_client), \
         patch("app.memory.signals._embed_text", return_value=[0.1] * 768):
        from app.memory import signals
        results = asyncio.run(signals.semantic_search("Acme Corp"))

    assert len(results) == 2
    assert all(isinstance(r, MemoryResult) for r in results)
    assert all(r.source == "semantic" for r in results)
    refs = {r.ref for r in results}
    assert refs == {"doc:001", "doc:002"}
    scores = {r.ref: r.score for r in results}
    assert scores["doc:001"] == 0.92
    assert scores["doc:002"] == 0.75


# ---------------------------------------------------------------------------
# 2. BM25 signal (PG ILIKE on research_trails)
# ---------------------------------------------------------------------------

def test_bm25_signal_returns_memory_results():
    """Mock fetch_all returning research_trails rows with findings JSON; verify source='bm25'."""
    trail_rows = [
        {
            "id": "trail-001",
            "query": "Acme Corp",
            "run_id": "run-001",
            "findings": json.dumps([
                {"title": "Finding A", "content": "Content A"},
                {"title": "Finding B", "content": "Content B"},
            ]),
        },
        {
            "id": "trail-002",
            "query": "Acme Corp research",
            "run_id": "run-002",
            "findings": json.dumps([
                {"title": "Finding C", "content": "Content C"},
            ]),
        },
    ]

    with patch("app.memory.signals.fetch_all", return_value=trail_rows):
        from app.memory import signals
        results = asyncio.run(signals.bm25_search("Acme Corp"))

    assert len(results) == 3
    assert all(isinstance(r, MemoryResult) for r in results)
    assert all(r.source == "bm25" for r in results)
    titles = {r.title for r in results}
    assert titles == {"Finding A", "Finding B", "Finding C"}


# ---------------------------------------------------------------------------
# 3. Entity signal (Neo4j search_entities)
# ---------------------------------------------------------------------------

def test_entity_signal_searches_neo4j():
    """Mock Neo4jClient.search_entities; verify results with source='entity'."""
    neo4j_rows = [
        {"ref": "entity:acme", "name": "Acme Corp", "entity_type": "organization", "confidence": 90, "observation_count": 5},
        {"ref": "entity:john", "name": "John Doe", "entity_type": "person", "confidence": 75, "observation_count": 3},
    ]

    mock_neo4j = MagicMock()
    mock_neo4j.search_entities.return_value = neo4j_rows

    with patch("app.memory.signals.Neo4jClient", return_value=mock_neo4j):
        from app.memory import signals
        results = asyncio.run(signals.entity_search("Acme Corp"))

    assert len(results) == 2
    assert all(isinstance(r, MemoryResult) for r in results)
    assert all(r.source == "entity" for r in results)
    refs = {r.ref for r in results}
    assert refs == {"entity:acme", "entity:john"}
    # client should be closed after use
    mock_neo4j.close.assert_called_once()


# ---------------------------------------------------------------------------
# 4. Temporal signal (PG entity_observations filtered by time)
# ---------------------------------------------------------------------------

def test_temporal_signal_filters_by_time():
    """Mock fetch_all on entity_observations; verify results with source='temporal'."""
    obs_rows = [
        {
            "entity_ref": "entity:acme",
            "entity_type": "organization",
            "attribute": "revenue",
            "value": "Acme Corp revenue 2025",
            "confidence": 80,
            "observed_at": "2025-01-15T10:00:00Z",
            "source_run_id": "run-xyz",
        },
        {
            "entity_ref": "entity:john",
            "entity_type": "person",
            "attribute": "role",
            "value": "Acme Corp CEO",
            "confidence": 70,
            "observed_at": "2025-02-01T09:00:00Z",
            "source_run_id": None,
        },
    ]

    with patch("app.memory.signals.fetch_all", return_value=obs_rows):
        from app.memory import signals
        results = asyncio.run(
            signals.temporal_search(
                "Acme Corp",
                time_filter=("2025-01-01", "2025-12-31"),
            )
        )

    assert len(results) == 2
    assert all(isinstance(r, MemoryResult) for r in results)
    assert all(r.source == "temporal" for r in results)
    refs = {r.ref for r in results}
    assert refs == {"entity:acme", "entity:john"}
    # observed_at should be populated from the row
    for r in results:
        assert r.observed_at is not None


# ---------------------------------------------------------------------------
# 5. Feedback signal (boosts thumbs-up findings)
# ---------------------------------------------------------------------------

def test_feedback_signal_boosts_liked_findings():
    """Mock fetch_all on finding_feedback; verify thumbs-up (user_score=1) comes first, source='feedback'."""
    fb_rows = [
        {
            "run_id": "run-001",
            "finding_index": 0,
            "finding_title": "Acme Corp is excellent",
            "user_score": 1,
            "reason": "Very relevant Acme Corp finding",
        },
        {
            "run_id": "run-002",
            "finding_index": 1,
            "finding_title": "Acme Corp news",
            "user_score": -1,
            "reason": "Not relevant",
        },
        {
            "run_id": "run-003",
            "finding_index": 2,
            "finding_title": "Acme Corp overview",
            "user_score": 0,
            "reason": None,
        },
    ]

    with patch("app.memory.signals.fetch_all", return_value=fb_rows):
        from app.memory import signals
        results = asyncio.run(signals.feedback_search("Acme Corp"))

    assert len(results) == 3
    assert all(isinstance(r, MemoryResult) for r in results)
    assert all(r.source == "feedback" for r in results)
    # Thumbs-up (user_score=1) should be first
    assert results[0].user_score == 1
    assert results[0].title == "Acme Corp is excellent"


# ---------------------------------------------------------------------------
# 6. Skill signal (Qdrant research_memory, type="skill")
# ---------------------------------------------------------------------------

def test_skill_signal_returns_memory_results():
    """Mock Qdrant client.search returning 2 skill hits; verify source='skill' and title/content formatting."""
    hit1 = MagicMock()
    hit1.id = "skill-001"
    hit1.score = 0.88
    hit1.payload = {
        "query": "How to search company filings",
        "tool_sequence": ["search_web", "extract_text", "summarize"],
        "skill_id": "skill-uuid-001",
    }

    hit2 = MagicMock()
    hit2.id = "skill-002"
    hit2.score = 0.71
    hit2.payload = {
        "query": "Competitor analysis workflow",
        "tool_sequence": ["search_web", "entity_extract"],
        "skill_id": "skill-uuid-002",
    }

    mock_client = MagicMock()
    query_resp = MagicMock()
    query_resp.points = [hit1, hit2]
    mock_client.query_points.return_value = query_resp

    with patch("app.memory.signals._get_qdrant_client", return_value=mock_client), \
         patch("app.memory.signals._embed_text", return_value=[0.1] * 768):
        from app.memory import signals
        results = asyncio.run(signals.skill_search("company research"))

    assert len(results) == 2
    assert all(isinstance(r, MemoryResult) for r in results)
    assert all(r.source == "skill" for r in results)
    refs = {r.ref for r in results}
    assert refs == {"skill-001", "skill-002"}
    assert results[0].score == 0.88
    assert results[0].title.startswith("Skill:")
    assert "search_web" in results[0].content
    assert results[0].run_id == "skill-uuid-001"
    assert results[0].user_score == 0


def test_skill_signal_returns_empty_on_exception():
    """When Qdrant raises an exception, skill_search returns [] without re-raising."""
    mock_client = MagicMock()
    query_resp = MagicMock()
    query_resp.points = []
    mock_client.query_points.side_effect = RuntimeError("Qdrant unavailable")

    with patch("app.memory.signals._get_qdrant_client", return_value=mock_client), \
         patch("app.memory.signals._embed_text", return_value=[0.1] * 768):
        from app.memory import signals
        results = asyncio.run(signals.skill_search("company research"))

    assert results == []
