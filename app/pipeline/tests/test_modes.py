"""Tests for optimization mode catalog entries (UI-P1).

Verifies all 6 modes:
  - Load and validate against OptimizationMode schema
  - Have all 5 dial defaults present with valid values
  - Match the design-doc dial table (§4.4 / architecture doc)

Design ref: docs/intelligence/three-tier-brain-architecture.md §4.4
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.catalogs.budget import (
    CAPABILITY_LEVELS,
    DEPTH_LEVELS,
    HYPOTHESIS_COUNT_LEVELS,
    RESOURCE_LEVELS,
    SPEED_LEVELS,
)
from app.pipeline.catalogs.loader import load_catalog
from app.pipeline.catalogs.schemas import OptimizationMode

# ---------------------------------------------------------------------------
# Fixture — load all 6 modes from the real registry directory
# ---------------------------------------------------------------------------

_MODES_DIR = (
    Path(__file__).resolve().parent.parent
    / "catalogs"
    / "registries"
    / "modes"
)


@pytest.fixture(scope="module")
def mode_catalog() -> dict[str, OptimizationMode]:
    catalog = load_catalog("mode", _MODES_DIR)
    return catalog


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------


class TestModeCatalogLoads:
    def test_all_six_modes_present(self, mode_catalog: dict[str, OptimizationMode]):
        expected = {
            "quick_lookup",
            "leads_generation",
            "data_retrieval",
            "market_analysis",
            "investigation",
            "academic_research",
        }
        assert expected == set(mode_catalog.keys()), (
            f"Missing modes: {expected - set(mode_catalog.keys())}"
        )

    def test_each_mode_is_optimization_mode_instance(self, mode_catalog: dict[str, OptimizationMode]):
        for mode_id, entry in mode_catalog.items():
            assert isinstance(entry, OptimizationMode), f"{mode_id} not OptimizationMode"

    def test_each_mode_has_all_five_dial_defaults(self, mode_catalog: dict[str, OptimizationMode]):
        required_dials = {"speed", "capability", "resource", "depth", "hypothesis_count"}
        for mode_id, entry in mode_catalog.items():
            present = set(entry.dial_defaults.keys())
            assert required_dials == present, (
                f"Mode '{mode_id}' missing dials: {required_dials - present}"
            )

    def test_each_mode_dial_values_are_valid(self, mode_catalog: dict[str, OptimizationMode]):
        domains = {
            "speed": SPEED_LEVELS,
            "capability": CAPABILITY_LEVELS,
            "resource": RESOURCE_LEVELS,
            "depth": DEPTH_LEVELS,
            "hypothesis_count": HYPOTHESIS_COUNT_LEVELS,
        }
        for mode_id, entry in mode_catalog.items():
            for dial, domain in domains.items():
                val = entry.dial_defaults.get(dial)
                assert val in domain, (
                    f"Mode '{mode_id}' dial '{dial}' has invalid value '{val}'. "
                    f"Allowed: {domain}"
                )


# ---------------------------------------------------------------------------
# Per-mode dial default assertions (from design doc §4.4 table)
# ---------------------------------------------------------------------------


class TestModeDialDefaults:
    """Assert exact dial defaults from the §4.4 table in the architecture doc."""

    def _defaults(self, mode_catalog: dict[str, OptimizationMode], mode_id: str) -> dict:
        return mode_catalog[mode_id].dial_defaults

    def test_quick_lookup_defaults(self, mode_catalog):
        d = self._defaults(mode_catalog, "quick_lookup")
        assert d["speed"] == "fast"
        assert d["capability"] == "light"
        assert d["resource"] == "tiny"
        assert d["depth"] == "shallow"
        assert d["hypothesis_count"] == "single"

    def test_leads_generation_defaults(self, mode_catalog):
        d = self._defaults(mode_catalog, "leads_generation")
        assert d["speed"] == "fast"
        assert d["capability"] == "general"
        assert d["resource"] == "heavy"
        assert d["depth"] == "shallow"
        assert d["hypothesis_count"] == "paired"

    def test_data_retrieval_defaults(self, mode_catalog):
        d = self._defaults(mode_catalog, "data_retrieval")
        assert d["speed"] == "fast"
        assert d["capability"] == "light"
        assert d["resource"] == "medium"
        assert d["depth"] == "search"
        assert d["hypothesis_count"] == "single"

    def test_market_analysis_defaults(self, mode_catalog):
        d = self._defaults(mode_catalog, "market_analysis")
        assert d["speed"] == "normal"
        assert d["capability"] == "general"
        assert d["resource"] == "heavy"
        assert d["depth"] == "deep"
        assert d["hypothesis_count"] == "competing"

    def test_investigation_defaults(self, mode_catalog):
        d = self._defaults(mode_catalog, "investigation")
        assert d["speed"] == "slow"
        assert d["capability"] == "high"
        assert d["resource"] == "heavy"
        assert d["depth"] == "deep"
        assert d["hypothesis_count"] == "adversarial"

    def test_academic_research_defaults(self, mode_catalog):
        d = self._defaults(mode_catalog, "academic_research")
        assert d["speed"] == "slow"
        assert d["capability"] == "high"
        assert d["resource"] == "medium"
        assert d["depth"] == "abyss"
        assert d["hypothesis_count"] == "competing"


# ---------------------------------------------------------------------------
# tactic_bias and strategy_suggestions are MVP-empty (post-MVP TODO)
# ---------------------------------------------------------------------------


class TestModePostMvpFields:
    def test_tactic_bias_empty_for_all_modes(self, mode_catalog: dict[str, OptimizationMode]):
        for mode_id, entry in mode_catalog.items():
            assert entry.tactic_bias == {}, (
                f"Mode '{mode_id}' tactic_bias should be empty dict for MVP"
            )

    def test_strategy_suggestions_empty_for_all_modes(self, mode_catalog: dict[str, OptimizationMode]):
        for mode_id, entry in mode_catalog.items():
            assert entry.strategy_suggestions == [], (
                f"Mode '{mode_id}' strategy_suggestions should be empty list for MVP"
            )
