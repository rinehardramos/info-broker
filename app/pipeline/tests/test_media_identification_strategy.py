"""Tests for the media_identification strategy catalog entry (MVP-M3).

Migrated to unified taxonomy (extract → gather → disconfirm → synthesize)
per spec 2026-05-23 (Task 11). Tests updated to match new phase ids.

Design ref: docs/intelligence/three-tier-brain-architecture.md §4.1, §8, §9
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.catalogs.loader import load_catalog
from app.pipeline.catalogs.schemas import Strategy

STRATEGIES_DIR = (
    Path(__file__).parent.parent
    / "catalogs"
    / "registries"
    / "strategies"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalog() -> dict[str, Strategy]:
    return load_catalog("strategy", STRATEGIES_DIR)


@pytest.fixture(scope="module")
def media_id(catalog: dict[str, Strategy]) -> Strategy:
    return catalog["media_identification"]


# ---------------------------------------------------------------------------
# Discovery test
# ---------------------------------------------------------------------------


def test_strategy_loads_via_catalog(catalog: dict[str, Strategy]) -> None:
    """Loader must discover media_identification from the registries directory."""
    assert "media_identification" in catalog
    assert isinstance(catalog["media_identification"], Strategy)


# ---------------------------------------------------------------------------
# DAG structure
# ---------------------------------------------------------------------------


def test_phases_form_valid_dag(media_id: Strategy) -> None:
    """Strategy validator already rejects cycles; this test asserts the assertion.

    We call Strategy.model_validate on the raw dict again to exercise the
    cycle-detection path directly and confirm the valid DAG passes.
    """
    from app.pipeline.catalogs.registries.strategies.media_identification import (
        STRATEGY as RAW,
    )

    # Should not raise — valid linear chain is cycle-free
    validated = Strategy.model_validate(RAW)
    phase_ids = [p.id for p in validated.phases]
    assert phase_ids == ["extract", "gather", "disconfirm", "synthesize"]


def test_phase_depends_on_chain(media_id: Strategy) -> None:
    """extract → gather → disconfirm → synthesize dependency chain."""
    phases = {p.id: p for p in media_id.phases}

    assert phases["extract"].depends_on == []
    assert phases["gather"].depends_on == ["extract"]
    assert phases["disconfirm"].depends_on == ["gather"]
    assert phases["synthesize"].depends_on == ["disconfirm"]


# ---------------------------------------------------------------------------
# Gate structure
# ---------------------------------------------------------------------------


def test_gather_gate_requires_distinct_identities(media_id: Strategy) -> None:
    """gather gate must check distinct_identity_count with min_from_dial=True."""
    phases = {p.id: p for p in media_id.phases}
    gather_gate = phases["gather"].gate
    check_kinds = {c.kind: c for c in gather_gate.checks}

    assert "distinct_identity_count" in check_kinds
    assert check_kinds["distinct_identity_count"].params.get("min_from_dial") is True

    # Second check: every hypothesis needs a live source
    assert "per_hypothesis_live_source" in check_kinds
    assert check_kinds["per_hypothesis_live_source"].params.get("min") == 1


def test_all_gate_on_fail_values_are_valid(media_id: Strategy) -> None:
    """Every phase gate on_fail must be one of the four allowed values."""
    allowed = {"replan", "swap_tactic", "ask_user", "terminate"}
    for phase in media_id.phases:
        assert phase.gate.on_fail in allowed, (
            f"Phase '{phase.id}' has unexpected on_fail='{phase.gate.on_fail}'"
        )


def test_disconfirm_gate_requires_disconfirm_per_hypothesis(media_id: Strategy) -> None:
    phases = {p.id: p for p in media_id.phases}
    disconfirm_gate = phases["disconfirm"].gate
    check_kinds = {c.kind for c in disconfirm_gate.checks}
    assert "disconfirm_logged_per_hypothesis" in check_kinds


def test_synthesize_gate_checks_top_candidate_confidence(media_id: Strategy) -> None:
    phases = {p.id: p for p in media_id.phases}
    synth_gate = phases["synthesize"].gate
    check_kinds = {c.kind: c for c in synth_gate.checks}
    assert "top_candidate_confidence" in check_kinds
    assert check_kinds["top_candidate_confidence"].params.get("min") == 0.4
    assert synth_gate.on_fail == "ask_user"


# ---------------------------------------------------------------------------
# Budget floor
# ---------------------------------------------------------------------------


def test_hypothesis_count_floor_competing(media_id: Strategy) -> None:
    """budget_minimums must set hypothesis_count to 'competing' (structural #89 fix)."""
    floor = media_id.budget_minimums.get("hypothesis_count")
    assert floor is not None, "budget_minimums.hypothesis_count must be set"

    # Tier ordering for the hypothesis_count dial (§5.2.3)
    tiers = ["single", "paired", "competing", "adversarial", "swarm"]
    assert floor in tiers, f"hypothesis_count floor '{floor}' is not a known tier"
    assert tiers.index(floor) >= tiers.index("competing"), (
        f"hypothesis_count floor must be >= 'competing', got '{floor}'"
    )


# ---------------------------------------------------------------------------
# Hypothesis count policies
# ---------------------------------------------------------------------------


def test_hypothesis_count_policies(media_id: Strategy) -> None:
    """Verify per-phase hypothesis count policies match the design doc."""
    phases = {p.id: p for p in media_id.phases}

    assert phases["extract"].hypothesis_count_policy == "fixed:1"
    assert phases["gather"].hypothesis_count_policy == "from_dial"
    assert phases["disconfirm"].hypothesis_count_policy == "from_prior_phase"
    assert phases["synthesize"].hypothesis_count_policy == "fixed:1"


# ---------------------------------------------------------------------------
# Unit-of-work contracts carry briefings
# ---------------------------------------------------------------------------


def test_all_phases_have_briefings(media_id: Strategy) -> None:
    """Every phase unit_of_work_contract must include a non-empty briefing string."""
    for phase in media_id.phases:
        briefing = phase.unit_of_work_contract.get("briefing")
        assert isinstance(briefing, str) and len(briefing) > 0, (
            f"Phase '{phase.id}' is missing a briefing in unit_of_work_contract"
        )


# ---------------------------------------------------------------------------
# Preferred tactic ids
# ---------------------------------------------------------------------------


def test_gather_preferred_tactic_is_hypothesis_first_search(media_id: Strategy) -> None:
    phases = {p.id: p for p in media_id.phases}
    assert phases["gather"].preferred_tactic_id == "hypothesis_first_search"


def test_synthesize_preferred_tactic_is_ach_rank(media_id: Strategy) -> None:
    phases = {p.id: p for p in media_id.phases}
    assert phases["synthesize"].preferred_tactic_id == "ach_rank"
