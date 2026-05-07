"""Tests for Reciprocal Rank Fusion algorithm."""

import time

import pytest

from app.memory.models import MemoryResult
from app.memory.rrf import reciprocal_rank_fusion


def _make_result(ref: str, title: str = "", source: str = "semantic", user_score: int = 0) -> MemoryResult:
    return MemoryResult(
        ref=ref,
        title=title or ref,
        content=f"Content for {ref}",
        source=source,
        score=1.0,
        user_score=user_score,
    )


def test_rrf_single_signal():
    """2 items in 1 signal — first-ranked item should have higher RRF score."""
    signal = [_make_result("a"), _make_result("b")]
    results = reciprocal_rank_fusion([signal])

    assert len(results) == 2
    refs = [r.ref for r in results]
    assert refs[0] == "a", "First-ranked item should come out on top"
    assert results[0].score > results[1].score


def test_rrf_two_signals_boost_overlap():
    """Item 'b' appears in both signals — it should rank first due to double RRF contribution."""
    signal1 = [_make_result("a"), _make_result("b")]
    signal2 = [_make_result("b"), _make_result("c")]
    results = reciprocal_rank_fusion([signal1, signal2])

    refs = [r.ref for r in results]
    assert refs[0] == "b", "Item present in both signals should rank first"


def test_rrf_feedback_boost():
    """thumbs up (+1) boosts score; thumbs down (-1) penalizes score."""
    # Two items at same rank across signals; one has user_score=1, other user_score=-1
    signal = [
        _make_result("upvoted", user_score=1),
        _make_result("downvoted", user_score=-1),
    ]
    results = reciprocal_rank_fusion([signal])

    upvoted = next(r for r in results if r.ref == "upvoted")
    downvoted = next(r for r in results if r.ref == "downvoted")
    assert upvoted.score > downvoted.score, "Upvoted item should score higher than downvoted"


def test_rrf_empty_signals():
    """Empty input returns empty list."""
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[]]) == []


def test_rrf_deduplicates_across_signals():
    """Same ref in 2 signals should yield exactly 1 result."""
    signal1 = [_make_result("x")]
    signal2 = [_make_result("x")]
    results = reciprocal_rank_fusion([signal1, signal2])

    assert len(results) == 1
    assert results[0].ref == "x"


def test_rrf_preserves_signal_scores():
    """Each result should have per-signal scores stored in its .signals dict."""
    signal1 = [_make_result("a"), _make_result("b")]
    signal2 = [_make_result("b"), _make_result("c")]
    results = reciprocal_rank_fusion(
        [signal1, signal2],
        signal_names=["semantic", "bm25"],
    )

    result_b = next(r for r in results if r.ref == "b")
    assert "semantic" in result_b.signals, "signal 'semantic' score should be stored"
    assert "bm25" in result_b.signals, "signal 'bm25' score should be stored"
    assert result_b.signals["semantic"] > 0
    assert result_b.signals["bm25"] > 0

    result_a = next(r for r in results if r.ref == "a")
    assert "semantic" in result_a.signals
    assert "bm25" not in result_a.signals, "signal 'bm25' should not appear for 'a' (only in signal1)"


def test_rrf_latency_under_10ms():
    """Fuse 500 items across 5 signals in less than 10ms."""
    signals = [
        [_make_result(f"doc:{i}") for i in range(500)]
        for _ in range(5)
    ]

    start = time.perf_counter()
    results = reciprocal_rank_fusion(signals)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(results) == 500
    assert elapsed_ms < 10, f"RRF took {elapsed_ms:.2f}ms — must be under 10ms"
