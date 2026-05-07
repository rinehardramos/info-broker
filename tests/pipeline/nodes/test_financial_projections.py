"""Unit tests for FinancialProjectionsNode and helpers."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.nodes.financial_projections import (
    FinancialProjectionsNode,
    _format_findings,
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
# _format_findings
# ---------------------------------------------------------------------------

def test_format_findings_empty():
    result = _format_findings([])
    assert "No structured findings" in result


def test_format_findings_uses_title_and_content():
    items = [{"title": "Acme Revenue", "content": "Revenue grew 20% YoY", "source": "stripe", "confidence": 90}]
    result = _format_findings(items)
    assert "Acme Revenue" in result
    assert "Revenue grew 20%" in result
    assert "stripe" in result


def test_format_findings_fallback_to_query():
    items = [{"query": "market size", "snippet": "Market is large"}]
    result = _format_findings(items)
    assert "market size" in result


def test_format_findings_truncates_long_content():
    long_content = "x" * 1000
    items = [{"title": "Big Item", "content": long_content}]
    result = _format_findings(items)
    # Content is truncated to 600 chars in the formatter
    assert "x" * 600 in result
    assert "x" * 700 not in result


# ---------------------------------------------------------------------------
# _try_parse_json
# ---------------------------------------------------------------------------

def test_try_parse_json_direct():
    text = '{"assumptions": ["a1"], "projections": []}'
    result = _try_parse_json(text)
    assert result["assumptions"] == ["a1"]


def test_try_parse_json_fenced_block():
    text = "Here is the JSON:\n```json\n{\"assumptions\": [\"b1\"]}\n```"
    result = _try_parse_json(text)
    assert result["assumptions"] == ["b1"]


def test_try_parse_json_embedded():
    text = "Some preamble {\"assumptions\": [\"c1\"]} some trailing text"
    result = _try_parse_json(text)
    assert result["assumptions"] == ["c1"]


def test_try_parse_json_invalid_returns_empty():
    result = _try_parse_json("not json at all")
    assert result == {}


def test_try_parse_json_empty_string():
    result = _try_parse_json("")
    assert result == {}


# ---------------------------------------------------------------------------
# FinancialProjectionsNode.execute — success paths
# ---------------------------------------------------------------------------

_GOOD_LLM_RESPONSE = json.dumps({
    "assumptions": ["Revenue grows at 10% monthly", "No major churn"],
    "projections": [
        {"period": "Q1 2025", "metric": "Revenue", "value": "500000", "confidence": 75},
        {"period": "Q2 2025", "metric": "Revenue", "value": "550000", "confidence": 70},
    ],
    "risks": ["Competition may increase", "Regulatory changes"],
    "methodology": "Bottom-up revenue projection based on current run rate",
})


def test_execute_revenue_forecast():
    node = FinancialProjectionsNode()
    inputs = [
        {"title": "Company Data", "content": "Q3 revenue was $450k", "source": "stripe", "confidence": 90}
    ]

    with patch("app.pipeline.nodes.financial_projections._call_llm", new=AsyncMock(return_value=_GOOD_LLM_RESPONSE)):
        result = _arun(node.execute(
            {"projection_type": "revenue_forecast", "time_horizon": "6 months"},
            inputs,
            _ctx(),
        ))

    assert len(result) == 1
    r = result[0]
    assert r["source"] == "financial_projections"
    assert r["projection_type"] == "revenue_forecast"
    assert r["time_horizon"] == "6 months"
    assert len(r["assumptions"]) == 2
    assert len(r["projections"]) == 2
    assert r["projections"][0]["period"] == "Q1 2025"
    assert len(r["risks"]) == 2
    assert "Bottom-up" in r["methodology"]


def test_execute_market_sizing():
    llm_response = json.dumps({
        "assumptions": ["TAM is $10B"],
        "projections": [{"period": "Year 1", "metric": "SAM", "value": "1000000000", "confidence": 60}],
        "risks": ["Market may be smaller"],
        "methodology": "Top-down market sizing",
    })

    node = FinancialProjectionsNode()
    with patch("app.pipeline.nodes.financial_projections._call_llm", new=AsyncMock(return_value=llm_response)):
        result = _arun(node.execute(
            {"projection_type": "market_sizing"},
            [],
            _ctx(),
        ))

    assert result[0]["projection_type"] == "market_sizing"
    assert result[0]["methodology"] == "Top-down market sizing"


def test_execute_no_inputs_still_returns_result():
    node = FinancialProjectionsNode()
    with patch("app.pipeline.nodes.financial_projections._call_llm", new=AsyncMock(return_value=_GOOD_LLM_RESPONSE)):
        result = _arun(node.execute({}, [], _ctx()))
    assert len(result) == 1
    assert result[0]["source"] == "financial_projections"


# ---------------------------------------------------------------------------
# FinancialProjectionsNode.execute — LLM failure paths
# ---------------------------------------------------------------------------

def test_execute_llm_returns_empty_json():
    # An empty JSON object {} is falsy in Python — treated as parse failure
    node = FinancialProjectionsNode()
    with patch("app.pipeline.nodes.financial_projections._call_llm", new=AsyncMock(return_value="{}")):
        result = _arun(node.execute({}, [], _ctx()))
    r = result[0]
    assert r["projections"] == []
    assert "error" in r


def test_execute_llm_returns_garbage():
    node = FinancialProjectionsNode()
    with patch("app.pipeline.nodes.financial_projections._call_llm", new=AsyncMock(return_value="not json")):
        result = _arun(node.execute({}, [], _ctx()))
    r = result[0]
    assert "error" in r
    assert r["projections"] == []


# ---------------------------------------------------------------------------
# Default config values
# ---------------------------------------------------------------------------

def test_default_projection_type():
    node = FinancialProjectionsNode()
    with patch("app.pipeline.nodes.financial_projections._call_llm", new=AsyncMock(return_value=_GOOD_LLM_RESPONSE)):
        result = _arun(node.execute({}, [], _ctx()))
    # Default projection_type is revenue_forecast
    assert result[0]["projection_type"] == "revenue_forecast"


def test_default_time_horizon():
    node = FinancialProjectionsNode()
    with patch("app.pipeline.nodes.financial_projections._call_llm", new=AsyncMock(return_value=_GOOD_LLM_RESPONSE)):
        result = _arun(node.execute({}, [], _ctx()))
    assert result[0]["time_horizon"] == "12 months"


# ---------------------------------------------------------------------------
# Node metadata
# ---------------------------------------------------------------------------

def test_node_type():
    node = FinancialProjectionsNode()
    assert node.node_type == "financial_projections"
    assert node.display_name == "Financial Projections Builder"
    assert node.category == "enrich"


def test_config_schema():
    node = FinancialProjectionsNode()
    props = node.config_schema["properties"]
    assert "projection_type" in props
    assert "revenue_forecast" in props["projection_type"]["enum"]
    assert "break_even" in props["projection_type"]["enum"]
    assert "model" in props
    assert "time_horizon" in props
