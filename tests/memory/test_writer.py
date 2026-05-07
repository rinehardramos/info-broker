"""TDD tests for app.memory.writer -- research_memory Qdrant indexer."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock, patch

# Stub out heavy optional dependencies before any app imports so that
# module-level imports in writer.py don't fail in CI.
for _mod in [
    "qdrant_client",
    "qdrant_client.models",
    "neo4j",
    "psycopg2",
    "psycopg2.extras",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_FAKE_VECTOR = [0.1] * 768


def _arun(coro):
    return asyncio.run(coro)


def _make_finding(
    *,
    title: str = "Test Finding",
    content: str = "Some content about a company.",
    source_tool: str = "web_search",
    confidence: int = 80,
    error_flagged: bool = False,
    observed_at: str | None = "2026-05-06T12:00:00Z",
) -> dict:
    return {
        "title": title,
        "content": content,
        "source": source_tool,
        "confidence": confidence,
        "error_flagged": error_flagged,
        "observed_at": observed_at,
    }


# ---------------------------------------------------------------------------
# test_index_findings_creates_points
# ---------------------------------------------------------------------------


def test_index_findings_creates_points():
    """2 valid findings -> upsert called once with collection_name=research_memory and 2 points."""
    from app.memory.writer import index_research_findings

    finding_a = _make_finding(title="Finding A", content="Content A")
    finding_b = _make_finding(title="Finding B", content="Content B")

    mock_client = MagicMock()

    with (
        patch("app.memory.writer._get_qdrant_client", return_value=mock_client),
        patch("app.memory.writer._embed_text", return_value=_FAKE_VECTOR),
    ):
        count = _arun(
            index_research_findings(
                run_id="run-abc-123",
                query="Acme Corp",
                findings=[finding_a, finding_b],
            )
        )

    assert count == 2
    mock_client.upsert.assert_called_once()
    call_kwargs = mock_client.upsert.call_args.kwargs
    assert call_kwargs["collection_name"] == "research_memory"
    assert len(call_kwargs["points"]) == 2


# ---------------------------------------------------------------------------
# test_index_findings_skips_error_flagged
# ---------------------------------------------------------------------------


def test_index_findings_skips_error_flagged():
    """1 good + 1 error_flagged finding -> only 1 point upserted."""
    from app.memory.writer import index_research_findings

    good = _make_finding(title="Good Finding", error_flagged=False)
    bad = _make_finding(title="Error Finding", error_flagged=True)

    mock_client = MagicMock()

    with (
        patch("app.memory.writer._get_qdrant_client", return_value=mock_client),
        patch("app.memory.writer._embed_text", return_value=_FAKE_VECTOR),
    ):
        count = _arun(
            index_research_findings(
                run_id="run-xyz-456",
                query="Test Query",
                findings=[good, bad],
            )
        )

    assert count == 1
    mock_client.upsert.assert_called_once()
    call_kwargs = mock_client.upsert.call_args.kwargs
    assert len(call_kwargs["points"]) == 1


# ---------------------------------------------------------------------------
# test_index_findings_handles_empty
# ---------------------------------------------------------------------------


def test_index_findings_handles_empty():
    """Empty findings list -> returns 0 and upsert is never called."""
    from app.memory.writer import index_research_findings

    mock_client = MagicMock()

    with (
        patch("app.memory.writer._get_qdrant_client", return_value=mock_client),
        patch("app.memory.writer._embed_text", return_value=_FAKE_VECTOR),
    ):
        count = _arun(
            index_research_findings(
                run_id="run-empty-789",
                query="Empty Query",
                findings=[],
            )
        )

    assert count == 0
    mock_client.upsert.assert_not_called()
