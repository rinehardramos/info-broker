"""Tests for MVP-M4 gather-phase tactic catalog entries.

Covers:
- hypothesis_first_search loads and validates via load_catalog
- prior_research_seed loads and validates via load_catalog
- Both tactics declare "gather" phase compatibility
- hypothesis_first_search enforcement floor (min_distinct_outputs=3)
- prior_research_seed anti-tunneling enforcement (seeds_h_prior_only)
- required_techniques ids resolve in technique catalog (skipped if M5 absent)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.catalogs.loader import load_catalog

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TACTICS_DIR = _REPO_ROOT / "app/pipeline/catalogs/registries/tactics"
_TECHNIQUES_DIR = _REPO_ROOT / "app/pipeline/catalogs/registries/techniques"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tactics_catalog():
    return load_catalog("tactic", _TACTICS_DIR)


@pytest.fixture(scope="module")
def techniques_catalog():
    return load_catalog("technique", _TECHNIQUES_DIR)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_hypothesis_first_search_loads_via_catalog(tactics_catalog):
    assert "hypothesis_first_search" in tactics_catalog
    tactic = tactics_catalog["hypothesis_first_search"]
    assert tactic.id == "hypothesis_first_search"
    assert tactic.cost_class == "moderate"
    assert len(tactic.produces) == 3


def test_prior_research_seed_loads_via_catalog(tactics_catalog):
    assert "prior_research_seed" in tactics_catalog
    tactic = tactics_catalog["prior_research_seed"]
    assert tactic.id == "prior_research_seed"
    assert tactic.cost_class == "cheap"
    assert len(tactic.produces) == 1


def test_both_tactics_phase_compat_gather(tactics_catalog):
    for tactic_id in ("hypothesis_first_search", "prior_research_seed"):
        tactic = tactics_catalog[tactic_id]
        assert "gather" in tactic.phase_compatibility, (
            f"{tactic_id}.phase_compatibility does not include 'gather'"
        )


def test_hypothesis_first_search_min_distinct_outputs_3(tactics_catalog):
    tactic = tactics_catalog["hypothesis_first_search"]
    assert tactic.enforcement.get("min_distinct_outputs") == 3, (
        "gather gate floor must be 3 distinct identity candidates"
    )


def test_prior_research_seed_seeds_h_prior_only(tactics_catalog):
    """Defend the #89 anti-tunneling property at the catalog level.

    seeds_h_prior_only=True signals that this tactic contributes exactly
    ONE H_PRIOR slot — the RAG candidate is one hypothesis among N, not
    the answer.  Removing or falsifying this flag breaks the structural
    anti-tunneling guarantee described in §4.4.
    """
    tactic = tactics_catalog["prior_research_seed"]
    assert tactic.enforcement.get("seeds_h_prior_only") is True, (
        "prior_research_seed must set seeds_h_prior_only=True to enforce "
        "the anti-tunneling property (issue #89)"
    )
    assert tactic.enforcement.get("max_outputs") == 1, (
        "prior_research_seed must limit to max_outputs=1 to prevent RAG "
        "expansion into multiple hypotheses"
    )


def test_required_techniques_resolvable(tactics_catalog, techniques_catalog):
    """Verify every required_technique id resolves in the technique catalog.

    Skipped when M5 technique files are not yet present (only web_search
    exists at time of M4 authoring).
    """
    all_required = set()
    for tactic in tactics_catalog.values():
        all_required.update(tactic.required_techniques)

    missing_from_m5 = all_required - set(techniques_catalog)
    if missing_from_m5:
        pytest.skip(
            f"M5 technique files not yet present — missing ids: "
            f"{sorted(missing_from_m5)}. Re-run after M5 lands."
        )

    for tactic in tactics_catalog.values():
        for technique_id in tactic.required_techniques:
            assert technique_id in techniques_catalog, (
                f"Tactic '{tactic.id}' requires technique '{technique_id}' "
                f"which is not registered in the technique catalog"
            )
