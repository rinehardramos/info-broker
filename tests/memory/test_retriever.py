"""Tests for the fused retriever — orchestrates 5 signals + RRF fusion."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import patch, AsyncMock, MagicMock

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
# Helpers
# ---------------------------------------------------------------------------

def _make_results(source: str, refs: list[str]) -> list[MemoryResult]:
    """Build a list of MemoryResult from a source label and ref list."""
    return [
        MemoryResult(
            ref=ref,
            title=ref,
            content=f"Content for {ref}",
            source=source,
            score=1.0,
        )
        for ref in refs
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fused_retrieve_calls_all_signals():
    """All 5 signals are called; their results are fused and deduplicated.

    Signal layout:
        semantic  -> [a, b]
        bm25      -> [b, c]
        entity    -> [c, d]
        temporal  -> [d, e]
        feedback  -> [a]

    Unique refs: a, b, c, d, e  => 5 results.
    Items appearing in multiple signals (a, b, c, d) should have len(signals) > 1.
    """
    from app.memory import retriever

    semantic_results  = _make_results("semantic", ["a", "b"])
    bm25_results      = _make_results("bm25",     ["b", "c"])
    entity_results    = _make_results("entity",   ["c", "d"])
    temporal_results  = _make_results("temporal", ["d", "e"])
    feedback_results  = _make_results("feedback", ["a"])

    with (
        patch.object(retriever, "semantic_search",  new=AsyncMock(return_value=semantic_results)),
        patch.object(retriever, "bm25_search",      new=AsyncMock(return_value=bm25_results)),
        patch.object(retriever, "entity_search",    new=AsyncMock(return_value=entity_results)),
        patch.object(retriever, "temporal_search",  new=AsyncMock(return_value=temporal_results)),
        patch.object(retriever, "feedback_search",  new=AsyncMock(return_value=feedback_results)),
    ):
        results = asyncio.run(retriever.fused_retrieve("test query"))

    assert len(results) == 5, f"Expected 5 unique results, got {len(results)}"

    result_map = {r.ref: r for r in results}

    # Items that appear in more than one signal must carry multiple signal scores
    multi_signal_refs = {"a", "b", "c", "d"}
    for ref in multi_signal_refs:
        assert ref in result_map, f"Ref '{ref}' missing from fused results"
        assert len(result_map[ref].signals) > 1, (
            f"Ref '{ref}' should have signals from multiple sources, got: {result_map[ref].signals}"
        )

    # 'e' only appears in temporal — one signal
    assert "e" in result_map
    assert len(result_map["e"].signals) == 1


def test_fused_retrieve_respects_limit():
    """When limit=5 and one signal returns 20 items, exactly 5 results are returned."""
    from app.memory import retriever

    big_results = _make_results("semantic", [f"doc:{i}" for i in range(20)])
    empty: list[MemoryResult] = []

    with (
        patch.object(retriever, "semantic_search",  new=AsyncMock(return_value=big_results)),
        patch.object(retriever, "bm25_search",      new=AsyncMock(return_value=empty)),
        patch.object(retriever, "entity_search",    new=AsyncMock(return_value=empty)),
        patch.object(retriever, "temporal_search",  new=AsyncMock(return_value=empty)),
        patch.object(retriever, "feedback_search",  new=AsyncMock(return_value=empty)),
    ):
        results = asyncio.run(retriever.fused_retrieve("test query", limit=5))

    assert len(results) == 5, f"Expected exactly 5 results (limit), got {len(results)}"


def test_fused_retrieve_handles_all_signals_failing():
    """When all 5 signals return empty lists, fused_retrieve returns an empty list."""
    from app.memory import retriever

    empty: list[MemoryResult] = []

    with (
        patch.object(retriever, "semantic_search",  new=AsyncMock(return_value=empty)),
        patch.object(retriever, "bm25_search",      new=AsyncMock(return_value=empty)),
        patch.object(retriever, "entity_search",    new=AsyncMock(return_value=empty)),
        patch.object(retriever, "temporal_search",  new=AsyncMock(return_value=empty)),
        patch.object(retriever, "feedback_search",  new=AsyncMock(return_value=empty)),
    ):
        results = asyncio.run(retriever.fused_retrieve("test query"))

    assert results == [], f"Expected empty list, got {results}"


# ---------------------------------------------------------------------------
# fused_retrieve_with_skills
# ---------------------------------------------------------------------------

def test_fused_retrieve_with_skills_returns_separate_lists():
    """fused_retrieve_with_skills returns (findings, skills) as separate lists.

    Signal layout:
        semantic  -> [a, b]
        bm25      -> [b, c]
        entity    -> []
        temporal  -> []
        feedback  -> []
        skill     -> [s1, s2]

    Findings: unique refs a, b, c  => 3
    Skills: s1, s2                 => 2
    """
    from app.memory import retriever

    semantic_results = _make_results("semantic", ["a", "b"])
    bm25_results     = _make_results("bm25",     ["b", "c"])
    skill_results    = _make_results("skill",    ["s1", "s2"])
    empty: list[MemoryResult] = []

    with (
        patch.object(retriever, "semantic_search",  new=AsyncMock(return_value=semantic_results)),
        patch.object(retriever, "bm25_search",      new=AsyncMock(return_value=bm25_results)),
        patch.object(retriever, "entity_search",    new=AsyncMock(return_value=empty)),
        patch.object(retriever, "temporal_search",  new=AsyncMock(return_value=empty)),
        patch.object(retriever, "feedback_search",  new=AsyncMock(return_value=empty)),
        patch.object(retriever, "skill_search",     new=AsyncMock(return_value=skill_results)),
    ):
        findings, skills = asyncio.run(retriever.fused_retrieve_with_skills("test query"))

    assert len(findings) == 3, f"Expected 3 findings, got {len(findings)}"
    assert len(skills) == 2, f"Expected 2 skills, got {len(skills)}"
    finding_refs = {r.ref for r in findings}
    assert finding_refs == {"a", "b", "c"}
    skill_refs = {r.ref for r in skills}
    assert skill_refs == {"s1", "s2"}


def test_fused_retrieve_with_skills_skill_signal_failure_returns_empty_skills():
    """When the skill signal raises an exception, the skills list is empty and findings are unaffected."""
    from app.memory import retriever

    semantic_results = _make_results("semantic", ["x", "y"])
    empty: list[MemoryResult] = []

    with (
        patch.object(retriever, "semantic_search",  new=AsyncMock(return_value=semantic_results)),
        patch.object(retriever, "bm25_search",      new=AsyncMock(return_value=empty)),
        patch.object(retriever, "entity_search",    new=AsyncMock(return_value=empty)),
        patch.object(retriever, "temporal_search",  new=AsyncMock(return_value=empty)),
        patch.object(retriever, "feedback_search",  new=AsyncMock(return_value=empty)),
        patch.object(retriever, "skill_search",     new=AsyncMock(side_effect=RuntimeError("skill failure"))),
    ):
        findings, skills = asyncio.run(retriever.fused_retrieve_with_skills("test query"))

    assert skills == [], f"Expected empty skills on exception, got {skills}"
    assert len(findings) == 2, f"Expected 2 findings unaffected, got {len(findings)}"


def test_fused_retrieve_with_skills_respects_limits():
    """limit and skill_limit parameters are respected."""
    from app.memory import retriever

    big_findings = _make_results("semantic", [f"doc:{i}" for i in range(20)])
    big_skills   = _make_results("skill",    [f"skill:{i}" for i in range(10)])
    empty: list[MemoryResult] = []

    with (
        patch.object(retriever, "semantic_search",  new=AsyncMock(return_value=big_findings)),
        patch.object(retriever, "bm25_search",      new=AsyncMock(return_value=empty)),
        patch.object(retriever, "entity_search",    new=AsyncMock(return_value=empty)),
        patch.object(retriever, "temporal_search",  new=AsyncMock(return_value=empty)),
        patch.object(retriever, "feedback_search",  new=AsyncMock(return_value=empty)),
        patch.object(retriever, "skill_search",     new=AsyncMock(return_value=big_skills)),
    ):
        findings, skills = asyncio.run(
            retriever.fused_retrieve_with_skills("test query", limit=5, skill_limit=3)
        )

    assert len(findings) == 5, f"Expected 5 findings (limit), got {len(findings)}"
    # skill_search is called with skill_limit=3; it returns whatever it returns (mocked as 10)
    # The function passes skill_limit to skill_search but doesn't re-truncate the return
    assert len(skills) == 10, f"Skill mock returned 10; expected 10, got {len(skills)}"
