"""Shared invariants for ACH-shaped strategy modules.

The ACH backbone (signal_extraction → broaden → red_team → rank_verify) is
the hand-written, non-skeleton strategy shape. Two strategies still use it
today (pending migration): media_identification, due_diligence.

person.py has been migrated to the unified taxonomy
(extract → gather → disconfirm → synthesize) per spec 2026-05-23.
Its structural invariants are now asserted in the
TestPersonUnifiedTaxonomy class below.

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

# Strategies still on the legacy ACH backbone (signal_extraction → broaden →
# red_team → rank_verify). Remove entries here as they are migrated to the
# unified taxonomy (extract → gather → disconfirm → synthesize).
# person migrated 2026-05-23 (Task 9) — see TestPersonUnifiedTaxonomy below.
# due_diligence migrated 2026-05-23 (Task 10) — see TestDueDiligenceUnifiedTaxonomy below.
ACH_STRATEGIES = ["media_identification"]


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


# ---------------------------------------------------------------------------
# person — unified taxonomy invariants (migrated 2026-05-23, Task 9)
# ---------------------------------------------------------------------------


class TestPersonUnifiedTaxonomy:
    """After migration person.py uses extract/gather/disconfirm/synthesize.

    These tests replace the legacy ACH backbone assertions that were
    removed from ACH_STRATEGIES above.  Gate checks, briefings, and
    preferred_tactic_ids are verified to confirm no semantic content
    was lost during migration.
    """

    @pytest.fixture(scope="class")
    def person(self, catalog):
        return catalog["person"]

    @pytest.fixture(scope="class")
    def phases(self, person):
        return {p.id: p for p in person.phases}

    def test_four_phase_unified_dag(self, phases):
        assert list(phases.keys()) == ["extract", "gather", "disconfirm", "synthesize"]

    def test_dependency_chain(self, phases):
        assert phases["extract"].depends_on == []
        assert phases["gather"].depends_on == ["extract"]
        assert phases["disconfirm"].depends_on == ["gather"]
        assert phases["synthesize"].depends_on == ["disconfirm"]

    def test_extract_requires_min_primary_signals(self, phases):
        kinds = {c.kind for c in phases["extract"].gate.checks}
        assert "min_primary_signals" in kinds

    def test_extract_on_fail_is_ask_user(self, phases):
        assert phases["extract"].gate.on_fail == "ask_user"

    def test_gather_gate_has_distinct_identity_and_live_source(self, phases):
        kinds = {c.kind for c in phases["gather"].gate.checks}
        assert "distinct_identity_count" in kinds
        assert "per_hypothesis_live_source" in kinds

    def test_gather_on_fail_is_terminate(self, phases):
        assert phases["gather"].gate.on_fail == "terminate"

    def test_gather_preferred_tactic_is_hypothesis_first_search(self, phases):
        assert phases["gather"].preferred_tactic_id == "hypothesis_first_search"

    def test_gather_hypothesis_count_policy_from_dial(self, phases):
        assert phases["gather"].hypothesis_count_policy == "from_dial"

    def test_disconfirm_logs_disconfirm_per_hypothesis(self, phases):
        kinds = {c.kind for c in phases["disconfirm"].gate.checks}
        assert "disconfirm_logged_per_hypothesis" in kinds

    def test_disconfirm_on_fail_is_terminate(self, phases):
        assert phases["disconfirm"].gate.on_fail == "terminate"

    def test_disconfirm_hypothesis_count_policy_from_prior_phase(self, phases):
        assert phases["disconfirm"].hypothesis_count_policy == "from_prior_phase"

    def test_synthesize_checks_top_candidate_confidence(self, phases):
        checks = {c.kind: c for c in phases["synthesize"].gate.checks}
        assert "top_candidate_confidence" in checks
        assert checks["top_candidate_confidence"].params.get("min", 0) >= 0.4

    def test_synthesize_on_fail_is_ask_user(self, phases):
        assert phases["synthesize"].gate.on_fail == "ask_user"

    def test_synthesize_preferred_tactic_is_ach_rank(self, phases):
        assert phases["synthesize"].preferred_tactic_id == "ach_rank"

    def test_hypothesis_count_floor_at_least_competing(self, person):
        tiers = ["single", "paired", "competing", "adversarial", "swarm"]
        floor = person.budget_minimums.get("hypothesis_count")
        assert floor is not None
        assert tiers.index(floor) >= tiers.index("competing")

    def test_has_five_ach_signals(self, person):
        assert len(person.ach_signals) == 5

    def test_ach_signal_weights_sum_to_one(self, person):
        total = sum(s["weight"] for s in person.ach_signals)
        assert abs(total - 1.0) < 0.01

    def test_default_mode_is_investigation(self, person):
        assert person.default_mode == "investigation"


# ---------------------------------------------------------------------------
# due_diligence — unified taxonomy invariants (migrated 2026-05-23, Task 10)
# ---------------------------------------------------------------------------


class TestDueDiligenceUnifiedTaxonomy:
    """After migration due_diligence.py uses extract/gather/disconfirm/synthesize.

    These tests replace the legacy ACH backbone assertions that were
    removed from ACH_STRATEGIES above.  Gate checks, briefings, and
    preferred_tactic_ids are verified to confirm no semantic content
    was lost during migration.
    """

    @pytest.fixture(scope="class")
    def due_diligence(self, catalog):
        return catalog["due_diligence"]

    @pytest.fixture(scope="class")
    def phases(self, due_diligence):
        return {p.id: p for p in due_diligence.phases}

    def test_four_phase_unified_dag(self, phases):
        assert list(phases.keys()) == ["extract", "gather", "disconfirm", "synthesize"]

    def test_dependency_chain(self, phases):
        assert phases["extract"].depends_on == []
        assert phases["gather"].depends_on == ["extract"]
        assert phases["disconfirm"].depends_on == ["gather"]
        assert phases["synthesize"].depends_on == ["disconfirm"]

    def test_extract_requires_min_primary_signals(self, phases):
        kinds = {c.kind for c in phases["extract"].gate.checks}
        assert "min_primary_signals" in kinds

    def test_extract_on_fail_is_ask_user(self, phases):
        assert phases["extract"].gate.on_fail == "ask_user"

    def test_gather_gate_has_distinct_identity_and_live_source(self, phases):
        kinds = {c.kind for c in phases["gather"].gate.checks}
        assert "distinct_identity_count" in kinds
        assert "per_hypothesis_live_source" in kinds

    def test_gather_on_fail_is_terminate(self, phases):
        assert phases["gather"].gate.on_fail == "terminate"

    def test_gather_preferred_tactic_is_hypothesis_first_search(self, phases):
        assert phases["gather"].preferred_tactic_id == "hypothesis_first_search"

    def test_gather_hypothesis_count_policy_from_dial(self, phases):
        assert phases["gather"].hypothesis_count_policy == "from_dial"

    def test_disconfirm_logs_disconfirm_per_hypothesis(self, phases):
        kinds = {c.kind for c in phases["disconfirm"].gate.checks}
        assert "disconfirm_logged_per_hypothesis" in kinds

    def test_disconfirm_on_fail_is_terminate(self, phases):
        assert phases["disconfirm"].gate.on_fail == "terminate"

    def test_disconfirm_hypothesis_count_policy_from_prior_phase(self, phases):
        assert phases["disconfirm"].hypothesis_count_policy == "from_prior_phase"

    def test_synthesize_checks_top_candidate_confidence(self, phases):
        checks = {c.kind: c for c in phases["synthesize"].gate.checks}
        assert "top_candidate_confidence" in checks
        assert checks["top_candidate_confidence"].params.get("min", 0) >= 0.4

    def test_synthesize_on_fail_is_ask_user(self, phases):
        assert phases["synthesize"].gate.on_fail == "ask_user"

    def test_synthesize_preferred_tactic_is_ach_rank(self, phases):
        assert phases["synthesize"].preferred_tactic_id == "ach_rank"

    def test_hypothesis_count_floor_at_least_competing(self, due_diligence):
        tiers = ["single", "paired", "competing", "adversarial", "swarm"]
        floor = due_diligence.budget_minimums.get("hypothesis_count")
        assert floor is not None
        assert tiers.index(floor) >= tiers.index("competing")

    def test_has_six_ach_signals(self, due_diligence):
        assert len(due_diligence.ach_signals) == 6

    def test_ach_signal_weights_sum_to_one(self, due_diligence):
        total = sum(s["weight"] for s in due_diligence.ach_signals)
        assert abs(total - 1.0) < 0.01

    def test_default_mode_is_investigation(self, due_diligence):
        assert due_diligence.default_mode == "investigation"

    def test_investigation_mode_suggests_due_diligence(self, mode_catalog):
        suggestions = mode_catalog["investigation"].strategy_suggestions
        assert "due_diligence" in suggestions
