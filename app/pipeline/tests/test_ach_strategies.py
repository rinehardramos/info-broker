"""Shared invariants for ACH-shaped strategy modules.

The ACH backbone (signal_extraction → broaden → red_team → rank_verify) is
the hand-written, non-skeleton strategy shape. Three strategies share it
today: media_identification, person, due_diligence.

These tests pin the structural contract so any new ACH-shaped strategy
that gets added must conform — no silent skipping of red_team or the
top_candidate_confidence gate.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.catalogs.loader import load_catalog
from app.pipeline.catalogs.schemas import Strategy

STRATEGIES_DIR = (
    Path(__file__).parent.parent / "catalogs" / "registries" / "strategies"
)
MODES_DIR = (
    Path(__file__).parent.parent / "catalogs" / "registries" / "modes"
)

# Every strategy listed here must have the full ACH backbone. Add new
# ACH-shaped strategy ids here as they're built; the parametrised tests
# below enforce the contract automatically.
ACH_STRATEGIES = ["media_identification", "person", "due_diligence"]


@pytest.fixture(scope="module")
def catalog() -> dict[str, Strategy]:
    return load_catalog("strategy", STRATEGIES_DIR)


@pytest.fixture(scope="module")
def mode_catalog():
    return load_catalog("mode", MODES_DIR)


# ---------------------------------------------------------------------------
# Discovery + DAG
# ---------------------------------------------------------------------------


class TestAchBackboneStructure:
    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_loads(self, catalog, strategy_id):
        assert strategy_id in catalog, f"{strategy_id} not registered"

    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_four_phase_dag(self, catalog, strategy_id):
        phase_ids = [p.id for p in catalog[strategy_id].phases]
        assert phase_ids == [
            "signal_extraction",
            "broaden",
            "red_team",
            "rank_verify",
        ], f"{strategy_id} must have the canonical ACH 4-phase DAG"

    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_phase_dependency_chain(self, catalog, strategy_id):
        phases = {p.id: p for p in catalog[strategy_id].phases}
        assert phases["signal_extraction"].depends_on == []
        assert phases["broaden"].depends_on == ["signal_extraction"]
        assert phases["red_team"].depends_on == ["broaden"]
        assert phases["rank_verify"].depends_on == ["red_team"]


# ---------------------------------------------------------------------------
# Gate-check structure (the contract that distinguishes ACH from skeleton)
# ---------------------------------------------------------------------------


class TestAchGateContract:
    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_signal_extraction_requires_min_primary_signals(self, catalog, strategy_id):
        phases = {p.id: p for p in catalog[strategy_id].phases}
        kinds = {c.kind for c in phases["signal_extraction"].gate.checks}
        assert "min_primary_signals" in kinds, (
            f"{strategy_id}.signal_extraction must require ≥1 primary signal"
        )

    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_broaden_gate_has_distinct_identity_and_live_source(self, catalog, strategy_id):
        phases = {p.id: p for p in catalog[strategy_id].phases}
        kinds = {c.kind for c in phases["broaden"].gate.checks}
        assert "distinct_identity_count" in kinds, (
            f"{strategy_id}.broaden must enforce distinct hypothesis identities"
        )
        assert "per_hypothesis_live_source" in kinds, (
            f"{strategy_id}.broaden must require a live source per hypothesis"
        )

    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_red_team_logs_disconfirm_per_hypothesis(self, catalog, strategy_id):
        phases = {p.id: p for p in catalog[strategy_id].phases}
        kinds = {c.kind for c in phases["red_team"].gate.checks}
        assert "disconfirm_logged_per_hypothesis" in kinds, (
            f"{strategy_id}.red_team must require a logged disconfirm per hypothesis"
        )

    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_rank_verify_checks_top_candidate_confidence(self, catalog, strategy_id):
        phases = {p.id: p for p in catalog[strategy_id].phases}
        checks = {c.kind: c for c in phases["rank_verify"].gate.checks}
        assert "top_candidate_confidence" in checks, (
            f"{strategy_id}.rank_verify must check top_candidate_confidence"
        )
        # Floor at 0.4 — below that, escalate to user (ask_user) rather than
        # commit to a low-confidence answer.
        assert checks["top_candidate_confidence"].params.get("min", 0) >= 0.4
        assert phases["rank_verify"].gate.on_fail == "ask_user", (
            f"{strategy_id}.rank_verify low-confidence path must escalate (ask_user)"
        )


# ---------------------------------------------------------------------------
# Budget floor — ACH strategies must NOT run on a single hypothesis
# ---------------------------------------------------------------------------


class TestAchBudgetFloor:
    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_hypothesis_count_floor_at_least_competing(self, catalog, strategy_id):
        """Structural anti-tunneling: ACH analysis is meaningless with 1
        hypothesis, so the floor is 'competing' (3-4) per design §5.2.3."""
        tiers = ["single", "paired", "competing", "adversarial", "swarm"]
        floor = catalog[strategy_id].budget_minimums.get("hypothesis_count")
        assert floor is not None
        assert floor in tiers
        assert tiers.index(floor) >= tiers.index("competing"), (
            f"{strategy_id} hypothesis_count floor '{floor}' must be ≥ 'competing'"
        )


# ---------------------------------------------------------------------------
# ACH signals — the weighted PIR criteria
# ---------------------------------------------------------------------------


class TestAchSignals:
    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_has_ach_signals(self, catalog, strategy_id):
        """ACH-shaped strategies must declare at least 3 weighted signals so
        the ranker has something to penalise mismatches against."""
        signals = catalog[strategy_id].ach_signals
        assert len(signals) >= 3, (
            f"{strategy_id} must declare ≥3 ACH signals (got {len(signals)})"
        )

    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_ach_signal_weights_sum_to_one(self, catalog, strategy_id):
        signals = catalog[strategy_id].ach_signals
        total = sum(s["weight"] for s in signals)
        # Allow tiny float drift from manual entry.
        assert abs(total - 1.0) < 0.01, (
            f"{strategy_id} ACH signal weights must sum to ~1.0 (got {total})"
        )

    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_ach_signals_have_required_fields(self, catalog, strategy_id):
        for s in catalog[strategy_id].ach_signals:
            for key in ("id", "label", "weight", "penalty_on_mismatch"):
                assert key in s, f"{strategy_id} ACH signal missing '{key}': {s}"


# ---------------------------------------------------------------------------
# Mode alignment
# ---------------------------------------------------------------------------


class TestAchModeAlignment:
    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_default_mode_is_investigation(self, catalog, strategy_id):
        """ACH-shaped strategies want the investigation envelope (slow, deep,
        adversarial hypotheses) — the mode whose dials match the backbone."""
        assert catalog[strategy_id].default_mode == "investigation"

    @pytest.mark.parametrize("strategy_id", ACH_STRATEGIES)
    def test_investigation_mode_suggests_this_strategy(self, mode_catalog, strategy_id):
        """investigation mode's strategy_suggestions must list this strategy
        so users picking investigation with a vague query route through ACH."""
        suggestions = mode_catalog["investigation"].strategy_suggestions
        assert strategy_id in suggestions, (
            f"investigation mode.strategy_suggestions missing {strategy_id!r}"
        )


# ---------------------------------------------------------------------------
# Resolver integration — _resolve_strategy now picks these directly
# ---------------------------------------------------------------------------


class TestResolverIntegratesAchStrategies:
    def test_person_intent_routes_to_person(self):
        from app.routers.v3.preflight import _resolve_strategy
        assert _resolve_strategy("person") == "person"

    def test_due_diligence_intent_routes_to_due_diligence(self):
        from app.routers.v3.preflight import _resolve_strategy
        assert _resolve_strategy("due_diligence") == "due_diligence"
