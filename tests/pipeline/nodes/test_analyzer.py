"""Unit tests for the AnalyzerNode and its helpers."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.nodes.analyzer import (
    AnalyzerNode,
    _filter_errors,
    _format_items_for_llm,
    _try_parse_json,
)
from app.pipeline.nodes.base import RunContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx() -> RunContext:
    return RunContext(user_id="u1", run_id="r1", node_id="n1")


def _arun(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _filter_errors
# ---------------------------------------------------------------------------

def test_filter_errors_removes_flagged():
    items = [
        {"title": "ok", "confidence": 80},
        {"title": "bad", "error_flagged": True, "confidence": 90},
    ]
    result = _filter_errors(items)
    assert len(result) == 1
    assert result[0]["title"] == "ok"


def test_filter_errors_removes_low_confidence():
    items = [
        {"title": "high", "confidence": 75},
        {"title": "low", "confidence": 30},
        {"title": "exact", "confidence": 50},
    ]
    result = _filter_errors(items, min_confidence=50)
    assert len(result) == 2
    titles = {i["title"] for i in result}
    assert titles == {"high", "exact"}


def test_filter_errors_keeps_items_above_threshold():
    items = [
        {"title": "a", "confidence": 60},
        {"title": "b", "confidence": 100},
    ]
    result = _filter_errors(items, min_confidence=55)
    assert len(result) == 2


def test_filter_errors_handles_missing_fields():
    # No error_flagged, no confidence — should be kept (defaults: not flagged, confidence=100)
    items = [
        {"title": "no fields"},
        {"title": "with error", "error_flagged": True},
        {"title": "no confidence"},
    ]
    result = _filter_errors(items, min_confidence=50)
    # "no fields" and "no confidence" have no error_flagged and default confidence=100 >= 50
    assert len(result) == 2
    titles = {i["title"] for i in result}
    assert "with error" not in titles


# ---------------------------------------------------------------------------
# Node metadata
# ---------------------------------------------------------------------------

def test_node_metadata():
    node = AnalyzerNode()
    assert node.node_type == "analyzer"
    assert node.display_name == "Intelligence Analyzer"
    assert node.category == "enrich"
    schema = node.config_schema
    assert schema["type"] == "object"
    props = schema["properties"]
    assert "analysis_type" in props
    assert "min_confidence" in props
    assert "model" in props
    assert "context_prompt" in props
    assert props["analysis_type"]["default"] == "comprehensive"
    assert props["min_confidence"]["default"] == 50
    assert props["model"]["default"] == "claude-opus-4-7"


# ---------------------------------------------------------------------------
# Execute — all errors returns error summary
# ---------------------------------------------------------------------------

def test_execute_all_errors_returns_error_summary():
    node = AnalyzerNode()
    inputs = [
        {"title": "err1", "error_flagged": True, "source": "tool_a"},
        {"title": "err2", "error_flagged": True, "source": "tool_b"},
    ]
    result = _arun(node.execute({}, inputs, _ctx()))
    assert len(result) == 1
    r = result[0]
    assert r["source"] == "analyzer"
    assert r["entities"] == []
    assert r["relationships"] == []
    assert r["stats"]["findings_analyzed"] == 0
    assert r["stats"]["findings_filtered_as_errors"] == 2
    assert "No valid findings" in r["insights"][0]
    assert r["error_summary"]["total_errors"] == 2
    assert set(r["error_summary"]["tools_failing"]) == {"tool_a", "tool_b"}


def test_execute_empty_inputs_returns_error_summary():
    node = AnalyzerNode()
    result = _arun(node.execute({}, [], _ctx()))
    assert len(result) == 1
    r = result[0]
    assert r["stats"]["findings_analyzed"] == 0
    assert r["stats"]["findings_filtered_as_errors"] == 0


# ---------------------------------------------------------------------------
# Execute — valid inputs calls LLM and returns structured output
# ---------------------------------------------------------------------------

_MOCK_ENTITIES = [{"name": "Acme Corp", "type": "company", "attributes": {}, "evidence": [1]}]
_MOCK_RELATIONSHIPS = [{"from": "Acme Corp", "to": "Widgets Inc", "type": "partners_with", "evidence": "found in item 1"}]
_MOCK_SYNTHESIS = {
    "insights": ["Acme and Widgets are partners"],
    "recommendations": [{"action": "contact Acme", "reason": "partnership", "priority": "high"}],
    "research_gaps": [],
    "enrichment_targets": [],
}


def test_execute_valid_inputs_calls_llm_and_returns_result():
    node = AnalyzerNode()
    inputs = [
        {"title": "Finding 1", "content": "Acme Corp partners with Widgets Inc", "confidence": 80},
    ]

    entities_response = json.dumps({"entities": _MOCK_ENTITIES})
    relationships_response = json.dumps({"relationships": _MOCK_RELATIONSHIPS})
    synthesis_response = json.dumps(_MOCK_SYNTHESIS)

    call_sequence = [entities_response, relationships_response, synthesis_response]
    call_iter = iter(call_sequence)

    async def mock_call_llm(prompt: str, model: str = "claude-haiku-4-5-20251001") -> str:
        return next(call_iter)

    with patch("app.pipeline.nodes.analyzer._call_llm", side_effect=mock_call_llm):
        result = _arun(node.execute({}, inputs, _ctx()))

    assert len(result) == 1
    r = result[0]
    assert r["source"] == "analyzer"
    assert r["entities"] == _MOCK_ENTITIES
    assert r["relationships"] == _MOCK_RELATIONSHIPS
    assert r["insights"] == _MOCK_SYNTHESIS["insights"]
    assert r["stats"]["findings_analyzed"] == 1
    assert r["stats"]["entities_extracted"] == 1
    assert r["stats"]["relationships_found"] == 1


def test_execute_respects_analysis_type_config():
    node = AnalyzerNode()
    inputs = [{"title": "item", "confidence": 80}]

    async def mock_call_llm(prompt: str, model: str = "claude-haiku-4-5-20251001") -> str:
        return "{}"

    with patch("app.pipeline.nodes.analyzer._call_llm", side_effect=mock_call_llm):
        result = _arun(node.execute({"analysis_type": "competitive"}, inputs, _ctx()))

    assert result[0]["analysis_type"] == "competitive"


def test_execute_filters_by_min_confidence():
    node = AnalyzerNode()
    inputs = [
        {"title": "high conf", "confidence": 80},
        {"title": "low conf", "confidence": 20},
    ]

    async def mock_call_llm(prompt: str, model: str = "claude-haiku-4-5-20251001") -> str:
        return "{}"

    with patch("app.pipeline.nodes.analyzer._call_llm", side_effect=mock_call_llm):
        result = _arun(node.execute({"min_confidence": 50}, inputs, _ctx()))

    r = result[0]
    assert r["stats"]["findings_analyzed"] == 1
    assert r["stats"]["findings_filtered_as_errors"] == 1


# ---------------------------------------------------------------------------
# _try_parse_json
# ---------------------------------------------------------------------------

def test_try_parse_json_direct():
    text = '{"entities": [{"name": "Acme"}]}'
    result = _try_parse_json(text)
    assert result == {"entities": [{"name": "Acme"}]}


def test_try_parse_json_markdown_fenced():
    text = 'Here is the JSON:\n```json\n{"entities": [{"name": "Acme"}]}\n```'
    result = _try_parse_json(text)
    assert result == {"entities": [{"name": "Acme"}]}


def test_try_parse_json_markdown_fenced_no_lang():
    text = "Result:\n```\n{\"key\": \"value\"}\n```"
    result = _try_parse_json(text)
    assert result == {"key": "value"}


def test_try_parse_json_with_preamble():
    text = 'Sure, here is the analysis result: {"insights": ["key finding"]} Hope that helps!'
    result = _try_parse_json(text)
    assert result == {"insights": ["key finding"]}


def test_try_parse_json_invalid_returns_empty():
    result = _try_parse_json("this is plain text with no JSON")
    assert result == {}


def test_try_parse_json_empty_string():
    result = _try_parse_json("")
    assert result == {}


# ---------------------------------------------------------------------------
# _format_items_for_llm
# ---------------------------------------------------------------------------

def test_format_items_for_llm_basic():
    items = [
        {"title": "Test Corp", "content": "A leading firm", "source": "web", "url": "https://example.com", "confidence": 90},
    ]
    output = _format_items_for_llm(items)
    assert "[1] Test Corp" in output
    assert "Source: web" in output
    assert "Confidence: 90%" in output
    assert "https://example.com" in output
    assert "A leading firm" in output


def test_format_items_for_llm_uses_query_fallback():
    items = [{"query": "search term", "snippet": "result snippet"}]
    output = _format_items_for_llm(items)
    assert "search term" in output


def test_format_items_for_llm_uses_item_number_fallback():
    items = [{"content": "some content"}]
    output = _format_items_for_llm(items)
    assert "Item 1" in output


def test_format_items_for_llm_truncates_long_content():
    items = [{"title": "T", "content": "x" * 1000}]
    output = _format_items_for_llm(items)
    # Content is truncated at 500 chars
    assert "x" * 501 not in output
    assert "x" * 500 in output


def test_format_items_for_llm_multiple_items():
    items = [
        {"title": "First"},
        {"title": "Second"},
        {"title": "Third"},
    ]
    output = _format_items_for_llm(items)
    assert "[1] First" in output
    assert "[2] Second" in output
    assert "[3] Third" in output


def test_format_items_for_llm_empty():
    assert _format_items_for_llm([]) == ""
