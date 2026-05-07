"""Tests for pivot pattern analyzer."""
from __future__ import annotations
from unittest.mock import patch, MagicMock
import asyncio

from app.pipeline.strategies.analyzer import (
    map_tool_to_pivot, calculate_yield_rate, determine_overlay_type,
    analyze_run_pivots, PIVOT_TOOL_MAP,
)

def _arun(coro): return asyncio.run(coro)


def test_pivot_tool_map_has_entries():
    assert len(PIVOT_TOOL_MAP) >= 10
    assert "hibp_lookup" in PIVOT_TOOL_MAP
    assert "linkedin_profile" in PIVOT_TOOL_MAP


def test_map_tool_known():
    sel, pivot = map_tool_to_pivot("hibp_lookup")
    assert sel == "email"
    assert pivot == "email -> hibp_lookup"


def test_map_tool_unknown():
    sel, pivot = map_tool_to_pivot("unknown_tool_xyz")
    assert sel == "unknown"
    assert pivot == "unknown -> unknown_tool_xyz"


def test_yield_rate_basic():
    assert calculate_yield_rate(3, 2) == 1.5
    assert calculate_yield_rate(0, 5) == 0.0
    assert calculate_yield_rate(3, 0) == 3.0  # edge: 0 tools -> treat as 1


def test_overlay_type_reinforce():
    assert determine_overlay_type(0.8, 3) == "reinforce"


def test_overlay_type_prune():
    assert determine_overlay_type(0.0, 0) == "prune"


def test_overlay_type_none_weak():
    # Low yield with some findings — not enough signal
    result = determine_overlay_type(0.3, 1)
    assert result is None or result == "discover"


def test_analyze_run_pivots_generates_overlays():
    mock_result = {
        "entity_type": "person",
        "tree": {
            "branches": [
                {"tool": "hibp_lookup", "result_count": 3},
                {"tool": "linkedin_profile", "result_count": 2},
                {"tool": "shodan_search", "result_count": 0},
            ]
        }
    }
    with patch("app.pipeline.strategies.analyzer.execute") as mock_exec:
        with patch("app.pipeline.strategies.analyzer.fetch_one", return_value=None):
            overlays = _arun(analyze_run_pivots("run-1", "John Doe", mock_result))
    assert len(overlays) >= 2  # at least hibp (reinforce) and shodan (prune)
    # Verify execute was called for upserts
    assert mock_exec.called
