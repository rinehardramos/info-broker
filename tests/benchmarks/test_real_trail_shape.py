"""Tests that validate parsing of REAL research-trail fixtures.

These tests load the actual JSON fixtures captured from live runs and assert
that the benchmark harness correctly:
  - reads tool_calls from the top-level field (not trail["tool_calls"])
  - parses trail["phases"] as a list of strings
  - does NOT fire training_only for live_search branches
  - computes richness without crashing on aggregator-only findings
  - correctly identifies live sources in branches

No live stack required — tests run purely against the fixture JSON files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

from benchmarks.score import (  # noqa: E402
    _guard_training_only,
    _guard_skipped_phases,
    lead_richness,
    score_item,
)


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text())


def _parse_trail_response(raw: dict) -> tuple[dict, list[dict], int]:
    """Parse a research-trails API response into (trail, findings, tool_calls).

    Mirrors the logic that fetch_trail() will use after the fix.
    """
    # Top-level tool_calls (the real count)
    tool_calls: int = raw.get("tool_calls") or 0

    # trail may be a nested dict or a JSON string
    trail = raw.get("trail") or {}
    if isinstance(trail, str):
        trail = json.loads(trail)

    # findings may be a list or a JSON string
    findings = raw.get("findings") or []
    if isinstance(findings, str):
        findings = json.loads(findings)

    return trail, findings, tool_calls


class TestChicagoFixture:
    @pytest.fixture(scope="class")
    def data(self):
        return _load_fixture("real_trail_chicago.json")

    @pytest.fixture(scope="class")
    def parsed(self, data):
        trail, findings, tool_calls = _parse_trail_response(data)
        return trail, findings, tool_calls

    def test_top_level_tool_calls_is_nonzero(self, data):
        """Top-level tool_calls must be read, not trail["tool_calls"]."""
        assert data["tool_calls"] == 6

    def test_trail_tool_calls_is_null(self, data):
        """trail["tool_calls"] is null — confirms we must use top-level."""
        trail = data.get("trail") or {}
        assert trail.get("tool_calls") is None

    def test_phases_are_strings(self, parsed):
        trail, findings, tool_calls = parsed
        phases = trail.get("phases", [])
        assert len(phases) > 0
        assert all(isinstance(p, str) for p in phases), f"Expected strings, got: {phases}"

    def test_phases_include_gather(self, parsed):
        trail, findings, tool_calls = parsed
        assert "gather" in trail["phases"]

    def test_training_only_guard_does_not_fire(self, parsed):
        """chicago run has live_search branches — training_only must be False."""
        trail, findings, tool_calls = parsed
        # Inject top-level tool_calls into trail for the guard check
        trail_with_calls = dict(trail, tool_calls=tool_calls)
        result = _guard_training_only(trail_with_calls)
        assert result is None, (
            f"training_only guard fired unexpectedly: "
            f"trail branches={trail.get('branches', [])[:1]}"
        )

    def test_branches_have_live_search_source_class(self, parsed):
        trail, findings, tool_calls = parsed
        branches = trail.get("branches", [])
        source_classes = {b.get("source_class") for b in branches}
        assert "live_search" in source_classes

    def test_branches_technique_id_is_none(self, parsed):
        """technique_id is None in this trail shape — unregistered_tools guard must not fire."""
        trail, findings, tool_calls = parsed
        branches = trail.get("branches", [])
        # All branches should have technique_id=None (not recorded per-branch)
        for b in branches:
            assert b.get("technique_id") is None

    def test_skipped_phases_guard_passes_for_real_strategy(self, parsed):
        """real_estate_leads strategy does NOT include disconfirm — guard must not fire."""
        trail, findings, tool_calls = parsed
        # The real strategy phases for real_estate_leads: extract, gather, synthesize
        real_strategy_phases = ["extract", "gather", "synthesize"]
        result = _guard_skipped_phases(trail, real_strategy_phases)
        assert result is None

    def test_findings_have_source_class_live_search(self, parsed):
        trail, findings, tool_calls = parsed
        assert len(findings) > 0
        source_classes = {f.get("source_class") for f in findings}
        assert "live_search" in source_classes

    def test_findings_lack_structured_lead_fields(self, parsed):
        """Aggregator findings have no address/price/etc — richness should be ~0."""
        trail, findings, tool_calls = parsed
        for f in findings:
            assert "address" not in f or f.get("address") in (None, "")

    def test_lead_richness_does_not_crash(self, parsed):
        trail, findings, tool_calls = parsed
        result = lead_richness(findings, trail)
        assert "lead_count" in result
        assert "avg_completeness" in result
        assert result["lead_count"] == len(findings)
        # Aggregator findings → 0 enrichment fields → avg_completeness == 0
        assert result["avg_completeness"] == pytest.approx(0.0, abs=0.01)
        assert result["zero_enrichment_count"] == len(findings)

    def test_score_item_no_false_positive_training_only(self, parsed):
        """Full score_item pass must NOT trip training_only for chicago fixture."""
        trail, findings, tool_calls = parsed
        trail_with_calls = dict(trail, tool_calls=tool_calls)
        gold_item = {
            "id": "leads-gen-fsbo-chicago-001",
            "query": "Find for sale by owner properties in Chicago IL",
            "domain": "real_estate_leads",
            "expected_facts": [
                {
                    "claim": "Chicago Illinois has active for sale by owner residential listings",
                    "authoritative_source": "https://www.zillow.com/chicago-il/fsbo/",
                    "must_be_live": True,
                }
            ],
        }
        result = score_item(
            gold_item,
            trail_with_calls,
            findings,
            registered_technique_ids=frozenset(),  # skip guard 2
            strategy_phases=["extract", "gather", "synthesize"],
        )
        assert "training_only" not in result["gaming_flags"], (
            f"training_only guard fired — tool_calls={tool_calls}, "
            f"branches={trail_with_calls.get('branches', [])[:2]}"
        )


class TestAustinFixture:
    @pytest.fixture(scope="class")
    def data(self):
        return _load_fixture("real_trail_austin.json")

    @pytest.fixture(scope="class")
    def parsed(self, data):
        trail, findings, tool_calls = _parse_trail_response(data)
        return trail, findings, tool_calls

    def test_top_level_tool_calls_is_nonzero(self, data):
        assert data["tool_calls"] == 13

    def test_training_only_guard_does_not_fire(self, parsed):
        trail, findings, tool_calls = parsed
        trail_with_calls = dict(trail, tool_calls=tool_calls)
        result = _guard_training_only(trail_with_calls)
        assert result is None

    def test_phases_are_strings(self, parsed):
        trail, findings, tool_calls = parsed
        phases = trail.get("phases", [])
        assert all(isinstance(p, str) for p in phases)

    def test_lead_richness_does_not_crash(self, parsed):
        trail, findings, tool_calls = parsed
        result = lead_richness(findings, trail)
        assert result["lead_count"] == len(findings)
        # Aggregator findings → no structured lead fields → ~0 completeness
        assert result["avg_completeness"] == pytest.approx(0.0, abs=0.01)

    def test_score_item_no_false_positive_training_only(self, parsed):
        trail, findings, tool_calls = parsed
        trail_with_calls = dict(trail, tool_calls=tool_calls)
        gold_item = {
            "id": "leads-gen-rental-austin-001",
            "query": "Find rental property leads in Austin TX",
            "domain": "real_estate_leads",
            "expected_facts": [
                {
                    "claim": "Austin Texas has active rental listings with landlord contact information",
                    "authoritative_source": "https://www.zillow.com/austin-tx/rentals/",
                    "must_be_live": True,
                }
            ],
        }
        result = score_item(
            gold_item,
            trail_with_calls,
            findings,
            registered_technique_ids=frozenset(),
            strategy_phases=["extract", "gather", "synthesize"],
        )
        assert "training_only" not in result["gaming_flags"]
