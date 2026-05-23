"""Tests for the research_skeleton factory and the overlay strategies it
emits.

The factory at app/pipeline/catalogs/builders/research_skeleton.py composes
a Strategy dict (extract → gather → [disconfirm →] synthesize) from per-phase
overlays. Each registry module imports it and supplies the diffs.

These tests pin the factory contract so future strategy modules can't drift,
and verify each of the 8 overlay strategies (plus generic_search) loads
cleanly through the catalog loader.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy
from app.pipeline.catalogs.loader import load_catalog
from app.pipeline.catalogs.schemas import Strategy

STRATEGIES_DIR = (
    Path(__file__).parent.parent
    / "catalogs"
    / "registries"
    / "strategies"
)


# ---------------------------------------------------------------------------
# Skeleton factory contract
# ---------------------------------------------------------------------------


class TestSkeletonFactory:
    def test_minimal_call_produces_valid_strategy(self):
        """No overlays → valid 3-phase Strategy with default briefings and
        empty (always-pass) gates."""
        s = build_research_strategy(id="x_test")
        # Round-trip through the Strategy Pydantic model — catches schema drift.
        Strategy.model_validate(s)
        assert s["id"] == "x_test"
        assert s["default_mode"] == "quick_lookup"
        phase_ids = [p["id"] for p in s["phases"]]
        assert phase_ids == ["extract", "gather", "synthesize"]

    def test_phase_dependency_chain(self):
        s = build_research_strategy(id="x_test")
        assert s["phases"][0]["depends_on"] == []
        assert s["phases"][1]["depends_on"] == ["extract"]
        assert s["phases"][2]["depends_on"] == ["gather"]

    def test_overlay_replaces_briefing(self):
        s = build_research_strategy(
            id="x_test",
            extract={"briefing": "CUSTOM-EXTRACT"},
        )
        assert s["phases"][0]["unit_of_work_contract"]["briefing"] == "CUSTOM-EXTRACT"
        # Other phases keep the default briefing.
        assert "search" in s["phases"][1]["unit_of_work_contract"]["briefing"].lower()

    def test_overlay_replaces_gate_checks(self):
        s = build_research_strategy(
            id="x_test",
            gather={"gate_checks": [{"kind": "some_check", "params": {"min": 1}}]},
        )
        assert s["phases"][1]["gate"]["checks"] == [
            {"kind": "some_check", "params": {"min": 1}}
        ]
        # Other phases keep empty gate (always-pass).
        assert s["phases"][0]["gate"]["checks"] == []

    def test_empty_default_gates_auto_pass(self):
        """Skeleton default is empty check lists — gates auto-pass.
        Documented in research_skeleton._build_phase."""
        s = build_research_strategy(id="x_test")
        for phase in s["phases"]:
            assert phase["gate"]["checks"] == []

    def test_default_mode_overridable(self):
        s = build_research_strategy(id="x_test", default_mode="investigation")
        assert s["default_mode"] == "investigation"

    def test_hypothesis_count_overridable(self):
        s = build_research_strategy(id="x_test", hypothesis_count="competing")
        assert s["budget_minimums"] == {"hypothesis_count": "competing"}


# ---------------------------------------------------------------------------
# Overlay strategies — discovery + per-strategy invariants
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalog() -> dict[str, Strategy]:
    return load_catalog("strategy", STRATEGIES_DIR)


# All 8 overlays + generic_search (which also uses the factory).
SKELETON_STRATEGIES = [
    "generic_search",
    "real_estate",
    "lead",
    "company",
    "place",
    "generation",
    "explanation",
    "prediction",
    "synthesis",
]


class TestOverlayStrategies:
    @pytest.mark.parametrize("strategy_id", SKELETON_STRATEGIES)
    def test_strategy_loads(self, catalog, strategy_id):
        """Every overlay strategy must be discoverable by the catalog loader."""
        assert strategy_id in catalog, f"{strategy_id} not found in catalog"

    @pytest.mark.parametrize("strategy_id", SKELETON_STRATEGIES)
    def test_has_three_phases(self, catalog, strategy_id):
        """Skeleton invariant: extract → gather → synthesize."""
        s = catalog[strategy_id]
        assert [p.id for p in s.phases] == ["extract", "gather", "synthesize"]

    @pytest.mark.parametrize("strategy_id", SKELETON_STRATEGIES)
    def test_default_mode_is_registered(self, catalog, strategy_id):
        """A strategy's default_mode must point at a registered mode (else
        _suggest_mode returns a mode the UI doesn't render)."""
        modes_dir = (
            Path(__file__).parent.parent / "catalogs" / "registries" / "modes"
        )
        mode_catalog = load_catalog("mode", modes_dir)
        assert catalog[strategy_id].default_mode in mode_catalog


# ---------------------------------------------------------------------------
# generic_search invariants — it's the floor, must stay maximally permissive
# ---------------------------------------------------------------------------


class TestGenericSearchInvariants:
    def test_all_gates_empty_always_pass(self, catalog):
        s = catalog["generic_search"]
        for phase in s.phases:
            assert phase.gate.checks == [], (
                f"generic_search.{phase.id} must have empty gate (always pass)"
            )

    def test_single_hypothesis_floor(self, catalog):
        """generic_search must NOT impose a competing/adversarial floor; it
        is the cheap fallback."""
        assert catalog["generic_search"].budget_minimums == {"hypothesis_count": "single"}


# ---------------------------------------------------------------------------
# New tests: optional disconfirm phase + preferred_tactic_id (Task 6)
# ---------------------------------------------------------------------------


def test_build_research_strategy_accepts_optional_disconfirm():
    """When disconfirm overlay is provided, the strategy has 4 phases."""
    from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy
    strategy = build_research_strategy(
        id="test_4phase",
        default_mode="comprehensive_investigation",
        hypothesis_count="multi",
        extract={"briefing": "ex"},
        gather={"briefing": "ga"},
        disconfirm={"briefing": "di"},
        synthesize={"briefing": "sy"},
    )
    phase_ids = [p["id"] for p in strategy["phases"]]
    assert phase_ids == ["extract", "gather", "disconfirm", "synthesize"]
    # synthesize depends on disconfirm in the 4-phase variant
    synth = next(p for p in strategy["phases"] if p["id"] == "synthesize")
    assert synth["depends_on"] == ["disconfirm"]


def test_build_research_strategy_omits_disconfirm_by_default():
    """When disconfirm is omitted, strategy has 3 phases and synthesize depends on gather."""
    from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy
    strategy = build_research_strategy(
        id="test_3phase",
        default_mode="data_retrieval",
        hypothesis_count="single",
        extract={"briefing": "ex"},
        gather={"briefing": "ga"},
        synthesize={"briefing": "sy"},
    )
    phase_ids = [p["id"] for p in strategy["phases"]]
    assert phase_ids == ["extract", "gather", "synthesize"]
    synth = next(p for p in strategy["phases"] if p["id"] == "synthesize")
    assert synth["depends_on"] == ["gather"]


def test_build_phase_threads_preferred_tactic_id():
    """The overlay key preferred_tactic_id is passed through to the phase dict."""
    from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy
    strategy = build_research_strategy(
        id="test_pref",
        default_mode="data_retrieval",
        hypothesis_count="single",
        gather={
            "preferred_tactic_id": "listings_gather",
            "briefing": "use Apify Zillow",
        },
    )
    gather = next(p for p in strategy["phases"] if p["id"] == "gather")
    assert gather["preferred_tactic_id"] == "listings_gather"


def test_build_phase_rejects_unknown_overlay_key():
    """Typos in overlay dict are caught at build time, not runtime."""
    from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy
    import pytest
    with pytest.raises(ValueError, match=r"Unknown overlay keys"):
        build_research_strategy(
            id="test_typo",
            default_mode="data_retrieval",
            hypothesis_count="single",
            gather={"breifing": "typo"},   # 'breifing' should be 'briefing'
        )
