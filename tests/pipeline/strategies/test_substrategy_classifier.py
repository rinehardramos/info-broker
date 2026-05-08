# tests/pipeline/strategies/test_substrategy_classifier.py
"""TDD tests for classify_substrategy() in the strategies orchestrator module."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Stub out psycopg2 before any app imports so module-level DB imports don't fail.
for _mod in ["psycopg2", "psycopg2.extras"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from app.pipeline.strategies.orchestrator import classify_substrategy  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Happy path — LLM returns a valid sub-strategy name
# ---------------------------------------------------------------------------

class TestClassifySubstrategyHappyPath:
    def test_due_diligence_for_acquisition_query(self) -> None:
        """Mock LLM returning 'due_diligence' for an M&A evaluation query."""
        with patch(
            "app.pipeline.strategies.orchestrator._classify_substrategy_llm",
            new=AsyncMock(return_value="due_diligence"),
        ):
            result = _run(classify_substrategy("retrieval", "evaluate TechCorp for acquisition"))

        assert result == "due_diligence"

    def test_root_cause_analysis_for_incident_query(self) -> None:
        """Mock LLM returning 'root_cause_analysis' for a server crash query."""
        with patch(
            "app.pipeline.strategies.orchestrator._classify_substrategy_llm",
            new=AsyncMock(return_value="root_cause_analysis"),
        ):
            result = _run(classify_substrategy("explanation", "why did server crash"))

        assert result == "root_cause_analysis"

    def test_none_for_simple_lookup_query(self) -> None:
        """Mock LLM returning 'none' for a simple lookup query."""
        with patch(
            "app.pipeline.strategies.orchestrator._classify_substrategy_llm",
            new=AsyncMock(return_value="none"),
        ):
            result = _run(classify_substrategy("retrieval", "find email of John"))

        assert result == "none"


# ---------------------------------------------------------------------------
# Fallback: garbage LLM response
# ---------------------------------------------------------------------------

class TestClassifySubstrategyGarbageFallback:
    def test_garbage_response_returns_none(self) -> None:
        """Unparseable LLM output (garbage text) -> returns 'none'."""
        with patch(
            "app.pipeline.strategies.orchestrator._classify_substrategy_llm",
            new=AsyncMock(return_value="!!! not a valid substrategy @@@"),
        ):
            result = _run(classify_substrategy("retrieval", "find email of John"))

        assert result == "none"

    def test_unknown_name_from_llm_returns_none(self) -> None:
        """LLM returns a plausible-looking but unregistered name -> returns 'none'."""
        with patch(
            "app.pipeline.strategies.orchestrator._classify_substrategy_llm",
            new=AsyncMock(return_value="super_secret_strategy"),
        ):
            result = _run(classify_substrategy("retrieval", "find email of John"))

        assert result == "none"


# ---------------------------------------------------------------------------
# Fallback: LLM raises exception
# ---------------------------------------------------------------------------

class TestClassifySubstrategyExceptionFallback:
    def test_llm_exception_returns_none(self) -> None:
        """LLM call raises an exception -> returns 'none'."""
        with patch(
            "app.pipeline.strategies.orchestrator._classify_substrategy_llm",
            new=AsyncMock(side_effect=RuntimeError("LLM unavailable")),
        ):
            result = _run(classify_substrategy("retrieval", "evaluate TechCorp for acquisition"))

        assert result == "none"

    def test_llm_timeout_returns_none(self) -> None:
        """LLM call times out -> returns 'none'."""
        with patch(
            "app.pipeline.strategies.orchestrator._classify_substrategy_llm",
            new=AsyncMock(side_effect=TimeoutError("timed out")),
        ):
            result = _run(classify_substrategy("explanation", "why did server crash"))

        assert result == "none"


# ---------------------------------------------------------------------------
# Edge case: empty / unknown category with no sub-strategies
# ---------------------------------------------------------------------------

class TestClassifySubstrategyEmptyCategory:
    def test_empty_category_returns_none_without_llm_call(self) -> None:
        """Category with no registered sub-strategies -> returns 'none' immediately."""
        with patch(
            "app.pipeline.strategies.orchestrator._classify_substrategy_llm",
            new=AsyncMock(),
        ) as mock_llm:
            # Use a category that definitely has no sub-strategies
            result = _run(classify_substrategy("nonexistent_category_xyz", "any query"))

        assert result == "none"
        mock_llm.assert_not_called()

    def test_empty_query_with_valid_category_returns_none(self) -> None:
        """Empty query -> returns 'none' without calling LLM."""
        with patch(
            "app.pipeline.strategies.orchestrator._classify_substrategy_llm",
            new=AsyncMock(),
        ) as mock_llm:
            result = _run(classify_substrategy("retrieval", ""))

        assert result == "none"
        mock_llm.assert_not_called()
