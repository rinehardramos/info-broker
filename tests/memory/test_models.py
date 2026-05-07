"""Tests for MemoryResult data model."""

import pytest

from app.memory.models import MemoryResult


def test_memory_result_creation():
    """Create a MemoryResult with required fields and verify defaults."""
    result = MemoryResult(
        ref="doc:123",
        title="Acme Corp Profile",
        content="Acme Corp is a software company...",
        source="semantic",
        score=0.85,
    )

    assert result.ref == "doc:123"
    assert result.title == "Acme Corp Profile"
    assert result.content == "Acme Corp is a software company..."
    assert result.source == "semantic"
    assert result.score == 0.85


def test_memory_result_with_all_fields():
    """Create a MemoryResult with all optional fields and verify each."""
    result = MemoryResult(
        ref="doc:456",
        title="John Doe Profile",
        content="John Doe is the CEO of Acme Corp...",
        source="entity",
        score=0.92,
        run_id="run-abc-123",
        entity_refs=["entity:john-doe", "entity:acme-corp"],
        observed_at="2026-05-06T12:00:00Z",
        user_score=1,
        signals={"semantic": 0.9, "bm25": 0.7},
    )

    assert result.ref == "doc:456"
    assert result.title == "John Doe Profile"
    assert result.content == "John Doe is the CEO of Acme Corp..."
    assert result.source == "entity"
    assert result.score == 0.92
    assert result.run_id == "run-abc-123"
    assert result.entity_refs == ["entity:john-doe", "entity:acme-corp"]
    assert result.observed_at == "2026-05-06T12:00:00Z"
    assert result.user_score == 1
    assert result.signals == {"semantic": 0.9, "bm25": 0.7}


def test_memory_result_defaults():
    """Verify default values: run_id=None, entity_refs=[], observed_at=None, user_score=0, signals={}."""
    result = MemoryResult(
        ref="doc:789",
        title="Some Title",
        content="Some content here.",
        source="bm25",
        score=0.5,
    )

    assert result.run_id is None
    assert result.entity_refs == []
    assert result.observed_at is None
    assert result.user_score == 0
    assert result.signals == {}


def test_memory_result_entity_refs_not_shared():
    """Verify entity_refs default factory creates independent lists per instance."""
    r1 = MemoryResult(ref="a", title="A", content="A", source="bm25", score=0.1)
    r2 = MemoryResult(ref="b", title="B", content="B", source="bm25", score=0.2)

    r1.entity_refs.append("entity:x")
    assert r2.entity_refs == [], "entity_refs must not be shared across instances"
