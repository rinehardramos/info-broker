"""Performance, latency, accuracy, persistence, and data quality tests for the memory package."""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

# Stub out heavy optional dependencies before any app imports so that
# module-level imports in signals.py / writer.py / neo4j_client.py don't fail in CI.
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
from app.memory.rrf import reciprocal_rank_fusion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(ref: str, source: str = "semantic", user_score: int = 0) -> MemoryResult:
    return MemoryResult(
        ref=ref,
        title=ref,
        content=f"Content for {ref}",
        source=source,
        score=1.0,
        user_score=user_score,
    )


def _make_signal(source: str, count: int, prefix: str = "doc") -> list[MemoryResult]:
    return [_make_result(f"{prefix}-{source}-{i}", source=source) for i in range(count)]


# ---------------------------------------------------------------------------
# Latency tests
# ---------------------------------------------------------------------------

def test_rrf_fusion_latency_500_items_under_10ms():
    """RRF over 5 signals * 100 items each (500 total) must complete in under 10ms."""
    signals = [_make_signal(f"signal_{s}", 100) for s in range(5)]

    start = time.monotonic()
    results = reciprocal_rank_fusion(signals)
    elapsed_ms = (time.monotonic() - start) * 1000

    assert len(results) == 500
    assert elapsed_ms < 10, f"RRF took {elapsed_ms:.2f}ms — must be under 10ms for 500 items"


def test_rrf_fusion_latency_2000_items_under_50ms():
    """RRF over 5 signals * 400 items each (2000 total) must complete in under 50ms."""
    signals = [_make_signal(f"signal_{s}", 400) for s in range(5)]

    start = time.monotonic()
    results = reciprocal_rank_fusion(signals)
    elapsed_ms = (time.monotonic() - start) * 1000

    assert len(results) == 2000
    assert elapsed_ms < 50, f"RRF took {elapsed_ms:.2f}ms — must be under 50ms for 2000 items"


def test_fused_retrieve_parallel_faster_than_sequential():
    """All 5 signals with 50ms sleep each should complete in <150ms (parallel, not ~250ms sequential)."""
    from app.memory import retriever

    async def _slow_signal(*_args, **_kwargs) -> list[MemoryResult]:
        await asyncio.sleep(0.05)
        return []

    with (
        patch.object(retriever, "semantic_search", new=AsyncMock(side_effect=_slow_signal)),
        patch.object(retriever, "bm25_search",     new=AsyncMock(side_effect=_slow_signal)),
        patch.object(retriever, "entity_search",   new=AsyncMock(side_effect=_slow_signal)),
        patch.object(retriever, "temporal_search", new=AsyncMock(side_effect=_slow_signal)),
        patch.object(retriever, "feedback_search", new=AsyncMock(side_effect=_slow_signal)),
    ):
        start = time.monotonic()
        asyncio.run(retriever.fused_retrieve("test query"))
        elapsed_ms = (time.monotonic() - start) * 1000

    assert elapsed_ms < 150, (
        f"fused_retrieve took {elapsed_ms:.2f}ms — signals must run in parallel, not sequentially"
    )


# ---------------------------------------------------------------------------
# Accuracy tests
# ---------------------------------------------------------------------------

def test_multi_signal_overlap_ranks_higher_than_single():
    """A ref appearing in 2 signals accumulates more RRF score than one appearing in only 1 signal."""
    overlap_result = _make_result("overlap")
    only_s1_result = _make_result("only-s1")

    signal1 = [overlap_result, only_s1_result]
    signal2 = [overlap_result]

    results = reciprocal_rank_fusion([signal1, signal2])
    refs = [r.ref for r in results]

    assert refs[0] == "overlap", (
        f"'overlap' (in 2 signals) should rank first, but got order: {refs}"
    )


def test_feedback_affects_ranking():
    """An item with user_score=1 should score higher than one at the same rank with user_score=0."""
    liked   = _make_result("liked",   user_score=1)
    neutral = _make_result("neutral", user_score=0)

    # Both at the same rank position in the same signal
    signal = [liked, neutral]
    results = reciprocal_rank_fusion([signal])

    liked_result   = next(r for r in results if r.ref == "liked")
    neutral_result = next(r for r in results if r.ref == "neutral")

    assert liked_result.score > neutral_result.score, (
        f"Liked item (user_score=1) should score higher than neutral: "
        f"liked={liked_result.score:.4f}, neutral={neutral_result.score:.4f}"
    )


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

def test_writer_produces_deterministic_ids():
    """uuid5(NAMESPACE_URL, 'run-abc:0') called twice must yield the same UUID."""
    namespace = uuid.NAMESPACE_URL
    id_first  = str(uuid.uuid5(namespace, "run-abc:0"))
    id_second = str(uuid.uuid5(namespace, "run-abc:0"))

    assert id_first == id_second, (
        f"Deterministic UUIDs must be identical: {id_first} != {id_second}"
    )


def test_writer_different_findings_produce_different_ids():
    """Different run_id or index must produce different UUIDs."""
    namespace = uuid.NAMESPACE_URL

    id_run_a_idx0 = str(uuid.uuid5(namespace, "run-aaa:0"))
    id_run_b_idx0 = str(uuid.uuid5(namespace, "run-bbb:0"))
    id_run_a_idx1 = str(uuid.uuid5(namespace, "run-aaa:1"))

    assert id_run_a_idx0 != id_run_b_idx0, "Different run_id must produce different UUIDs"
    assert id_run_a_idx0 != id_run_a_idx1, "Different index must produce different UUIDs"
    assert id_run_b_idx0 != id_run_a_idx1, "run-bbb:0 and run-aaa:1 must differ"


# ---------------------------------------------------------------------------
# Data quality tests
# ---------------------------------------------------------------------------

def test_writer_excludes_error_flagged_findings():
    """index_research_findings with 1 good + 1 error_flagged + 1 low-conf finding indexes exactly 2."""
    from app.memory.writer import index_research_findings

    good = {
        "title": "Good Finding",
        "content": "Solid content.",
        "source": "web_search",
        "confidence": 85,
        "error_flagged": False,
    }
    errored = {
        "title": "Error Finding",
        "content": "Something went wrong.",
        "source": "web_search",
        "confidence": 50,
        "error_flagged": True,
    }
    low_conf = {
        "title": "Low Confidence Finding",
        "content": "Uncertain content.",
        "source": "web_search",
        "confidence": 20,
        "error_flagged": False,
    }

    mock_client = MagicMock()
    _FAKE_VECTOR = [0.0] * 768

    with (
        patch("app.memory.writer._get_qdrant_client", return_value=mock_client),
        patch("app.memory.writer._embed_text", return_value=_FAKE_VECTOR),
    ):
        count = asyncio.run(
            index_research_findings(
                run_id="run-quality-test",
                query="Quality check",
                findings=[good, errored, low_conf],
            )
        )

    assert count == 2, (
        f"Expected 2 findings indexed (error_flagged excluded), got {count}"
    )
    call_kwargs = mock_client.upsert.call_args.kwargs
    assert len(call_kwargs["points"]) == 2, (
        f"Expected 2 points upserted, got {len(call_kwargs['points'])}"
    )
