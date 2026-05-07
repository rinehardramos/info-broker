"""Tests for strategy compiler."""
from __future__ import annotations
from unittest.mock import patch
import asyncio

from app.pipeline.strategies.compiler import compile_strategy, _merge_overlays


def _arun(coro): return asyncio.run(coro)


def test_merge_overlays_empty():
    seed = "original strategy text"
    assert _merge_overlays(seed, []) == seed


def test_merge_overlays_reinforce():
    seed = "Use run_hibp_lookup for breach checking\nOther line"
    overlays = [{"pivot_pattern": "email -> hibp_lookup", "overlay_type": "reinforce", "yield_rate": 0.85, "run_count": 5}]
    result = _merge_overlays(seed, overlays)
    assert "[HIGH PRIORITY" in result
    assert "85%" in result


def test_merge_overlays_prune():
    seed = "Use run_shodan_search for infrastructure\nOther line"
    overlays = [{"pivot_pattern": "domain -> shodan_search", "overlay_type": "prune", "yield_rate": 0.0, "run_count": 4}]
    result = _merge_overlays(seed, overlays)
    assert "[LOW PRIORITY" in result


def test_merge_overlays_discover():
    seed = "existing strategy text"
    overlays = [{"pivot_pattern": "email -> new_tool", "overlay_type": "discover",
                 "yield_rate": 0.6, "run_count": 3, "selector_type": "email"}]
    result = _merge_overlays(seed, overlays)
    assert "DISCOVERED PIVOTS" in result
    assert "new_tool" in result


def test_compile_strategy_unknown_entity():
    result = _arun(compile_strategy("nonexistent_xyz"))
    assert result == ""


def test_compile_strategy_no_overlays():
    with patch("app.pipeline.strategies.compiler._fetch_overlays", return_value=[]):
        result = _arun(compile_strategy("person"))
    assert "PERSON INVESTIGATION STRATEGY" in result
    assert "[HIGH PRIORITY" not in result  # no overlays = no annotations


def test_compile_strategy_with_overlays():
    overlays = [
        {"pivot_pattern": "email -> hibp_lookup", "overlay_type": "reinforce",
         "yield_rate": 0.9, "run_count": 5, "selector_type": "email"},
    ]
    with patch("app.pipeline.strategies.compiler._fetch_overlays", return_value=overlays):
        result = _arun(compile_strategy("person"))
    assert "PERSON INVESTIGATION STRATEGY" in result
    assert "[HIGH PRIORITY" in result
