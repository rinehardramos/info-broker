# tests/pipeline/strategies/test_analyzer_llm.py
"""TDD tests for classify_tool_calls_llm() in the strategies analyzer module."""

from __future__ import annotations

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Stub out psycopg2 before any app imports so module-level DB imports don't fail.
for _mod in [
    "psycopg2",
    "psycopg2.extras",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from app.pipeline.strategies.analyzer import classify_tool_calls_llm  # noqa: E402
from app.pipeline.strategies.selectors import get_selectors  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _make_tool_calls(*tools: tuple[str, int]) -> list[dict]:
    """Build a minimal list of tool call dicts: (tool_name, result_count)."""
    return [
        {"tool": t, "result_count": rc, "params": {"query": "test query"}}
        for t, rc in tools
    ]


_GENERATION_SELECTORS = get_selectors("generation")


# ---------------------------------------------------------------------------
# Happy path — valid JSON returned by LLM
# ---------------------------------------------------------------------------

class TestClassifyToolCallsLlmHappyPath:
    def test_returns_correct_selector_types(self) -> None:
        """Mock LLM returns valid JSON; verify selector_types match."""
        tool_calls = _make_tool_calls(("ddg_search", 3), ("web_crawl", 1))
        llm_response = json.dumps([
            {"tool": "ddg_search", "selector_type": "problem_statement", "confidence": 0.9},
            {"tool": "web_crawl", "selector_type": "prior_art", "confidence": 0.75},
        ])

        with patch(
            "app.pipeline.strategies.analyzer._call_llm_for_classification",
            new=AsyncMock(return_value=llm_response),
        ):
            result = _run(classify_tool_calls_llm("generation", "test query", tool_calls))

        assert len(result) == 2
        selector_types = {r["tool"]: r["selector_type"] for r in result}
        assert selector_types["ddg_search"] == "problem_statement"
        assert selector_types["web_crawl"] == "prior_art"

    def test_pivot_pattern_format(self) -> None:
        """Verify pivot_pattern is '{selector_type} -> {tool}'."""
        tool_calls = _make_tool_calls(("ddg_search", 5))
        llm_response = json.dumps([
            {"tool": "ddg_search", "selector_type": "concept", "confidence": 0.85},
        ])

        with patch(
            "app.pipeline.strategies.analyzer._call_llm_for_classification",
            new=AsyncMock(return_value=llm_response),
        ):
            result = _run(classify_tool_calls_llm("generation", "test query", tool_calls))

        assert result[0]["pivot_pattern"] == "concept -> ddg_search"

    def test_findings_count_preserved(self) -> None:
        """Verify findings_count matches result_count from tool call."""
        tool_calls = _make_tool_calls(("google_news", 7))
        llm_response = json.dumps([
            {"tool": "google_news", "selector_type": "researcher", "confidence": 0.8},
        ])

        with patch(
            "app.pipeline.strategies.analyzer._call_llm_for_classification",
            new=AsyncMock(return_value=llm_response),
        ):
            result = _run(classify_tool_calls_llm("generation", "research query", tool_calls))

        assert result[0]["findings_count"] == 7

    def test_all_returned_selector_types_are_valid_for_category(self) -> None:
        """All selector_types in result must belong to the category's selector list."""
        tool_calls = _make_tool_calls(("ddg_search", 2), ("web_search_fetch", 4))
        llm_response = json.dumps([
            {"tool": "ddg_search", "selector_type": "gap", "confidence": 0.7},
            {"tool": "web_search_fetch", "selector_type": "technique", "confidence": 0.9},
        ])

        with patch(
            "app.pipeline.strategies.analyzer._call_llm_for_classification",
            new=AsyncMock(return_value=llm_response),
        ):
            result = _run(classify_tool_calls_llm("generation", "query", tool_calls))

        valid_selectors = get_selectors("generation")
        for item in result:
            assert item["selector_type"] in valid_selectors, (
                f"selector_type '{item['selector_type']}' not in {valid_selectors}"
            )

    def test_invalid_selector_type_from_llm_falls_back_to_first(self) -> None:
        """If LLM returns a selector_type not in the category list, use first selector."""
        tool_calls = _make_tool_calls(("ddg_search", 1))
        llm_response = json.dumps([
            {"tool": "ddg_search", "selector_type": "INVALID_SELECTOR", "confidence": 0.9},
        ])

        with patch(
            "app.pipeline.strategies.analyzer._call_llm_for_classification",
            new=AsyncMock(return_value=llm_response),
        ):
            result = _run(classify_tool_calls_llm("generation", "query", tool_calls))

        first_selector = get_selectors("generation")[0]
        assert result[0]["selector_type"] == first_selector


# ---------------------------------------------------------------------------
# Fallback: garbage text from LLM
# ---------------------------------------------------------------------------

class TestClassifyToolCallsLlmGarbageFallback:
    def test_garbage_response_falls_back_to_first_selector(self) -> None:
        """Unparseable LLM output -> all tool calls mapped to first selector."""
        tool_calls = _make_tool_calls(("ddg_search", 2), ("web_crawl", 0))

        with patch(
            "app.pipeline.strategies.analyzer._call_llm_for_classification",
            new=AsyncMock(return_value="this is not json at all!!!"),
        ):
            result = _run(classify_tool_calls_llm("generation", "query", tool_calls))

        first_selector = _GENERATION_SELECTORS[0]
        assert len(result) == 2
        for item in result:
            assert item["selector_type"] == first_selector

    def test_garbage_response_pivot_pattern_uses_first_selector(self) -> None:
        """Fallback pivot_pattern is '{first_selector} -> {tool}'."""
        tool_calls = _make_tool_calls(("ddg_search", 1))

        with patch(
            "app.pipeline.strategies.analyzer._call_llm_for_classification",
            new=AsyncMock(return_value="not json"),
        ):
            result = _run(classify_tool_calls_llm("generation", "query", tool_calls))

        first_selector = _GENERATION_SELECTORS[0]
        assert result[0]["pivot_pattern"] == f"{first_selector} -> ddg_search"


# ---------------------------------------------------------------------------
# Fallback: LLM raises exception
# ---------------------------------------------------------------------------

class TestClassifyToolCallsLlmExceptionFallback:
    def test_exception_falls_back_to_first_selector(self) -> None:
        """LLM call raises -> all tool calls mapped to first selector."""
        tool_calls = _make_tool_calls(("ddg_search", 3))

        with patch(
            "app.pipeline.strategies.analyzer._call_llm_for_classification",
            new=AsyncMock(side_effect=RuntimeError("LLM unavailable")),
        ):
            result = _run(classify_tool_calls_llm("generation", "query", tool_calls))

        first_selector = _GENERATION_SELECTORS[0]
        assert len(result) == 1
        assert result[0]["selector_type"] == first_selector

    def test_exception_findings_count_preserved(self) -> None:
        """Even on fallback, findings_count reflects the original result_count."""
        tool_calls = _make_tool_calls(("google_news", 9))

        with patch(
            "app.pipeline.strategies.analyzer._call_llm_for_classification",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = _run(classify_tool_calls_llm("generation", "query", tool_calls))

        assert result[0]["findings_count"] == 9


# ---------------------------------------------------------------------------
# Edge case: empty tool_calls
# ---------------------------------------------------------------------------

class TestClassifyToolCallsLlmEmpty:
    def test_empty_tool_calls_returns_empty_list(self) -> None:
        """Empty input -> empty output, no LLM call made."""
        with patch(
            "app.pipeline.strategies.analyzer._call_llm_for_classification",
            new=AsyncMock(),
        ) as mock_llm:
            result = _run(classify_tool_calls_llm("generation", "query", []))

        assert result == []
        mock_llm.assert_not_called()


# ---------------------------------------------------------------------------
# Category variation — prediction
# ---------------------------------------------------------------------------

class TestClassifyToolCallsLlmPredictionCategory:
    def test_prediction_selectors_used(self) -> None:
        """Uses prediction category selectors when entity_type='prediction'."""
        tool_calls = _make_tool_calls(("ddg_search", 2))
        prediction_selectors = get_selectors("prediction")
        first_selector = prediction_selectors[0]

        llm_response = json.dumps([
            {"tool": "ddg_search", "selector_type": first_selector, "confidence": 0.85},
        ])

        with patch(
            "app.pipeline.strategies.analyzer._call_llm_for_classification",
            new=AsyncMock(return_value=llm_response),
        ):
            result = _run(classify_tool_calls_llm("prediction", "query", tool_calls))

        assert result[0]["selector_type"] == first_selector
        assert result[0]["selector_type"] in prediction_selectors
