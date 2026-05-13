"""Layer 3 (rules R1-R6) tests for app.pipeline.preflight.

Each rule gets a "fires" case and a "does not fire" case. We exercise these
at the validate() level by stubbing extract_slots() to return a controlled
SlotResult — that way each test pins exactly the slot configuration that
should (or should not) trigger the rule.

Note: preflight.py defines six rules (R1–R6). The implementation does not
expose a `rules_fired` field — instead, fired rules are observable via the
`slot` attribute on each MissingSlot. Mapping:

  R1 → "provenance"
  R2 → "disambiguator"
  R3 → "polysemous_disambig"
  R4 → "goal"
  R5 → "scope_time"
  R6 → "comparison_target"
"""
from __future__ import annotations

from typing import Any

import pytest

from app.pipeline import preflight
from app.pipeline.preflight import SlotResult, validate


def _stub_slots(monkeypatch: pytest.MonkeyPatch, slots: SlotResult) -> None:
    """Make extract_slots() return the given SlotResult, bypassing the LLM."""
    monkeypatch.setattr(
        preflight,
        "extract_slots",
        lambda _q, _e: slots,
    )


def _filled_slots(**overrides: Any) -> SlotResult:
    """SlotResult that, by itself, would not fire any LLM-dependent rule."""
    base = SlotResult(
        subject_kind="named",
        subject_value="Acme",
        subject_confidence=0.9,
        subject_ambiguity="low",
        provenance_present=True,
        provenance_value="youtube",
        provenance_confidence=0.9,
        scope_time="2025",
        scope_geo="US",
        scope_platform="youtube",
        goal_shape="identify",
        goal_confidence=0.9,
        has_disambiguator=True,
        disambiguator_value="the CEO",
        raw_interpretation="User wants to identify the CEO of Acme",
        _haiku_succeeded=True,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _fired(result: Any) -> set[str]:
    return {m.slot for m in result.missing}


# ---------------------------------------------------------------------------
# R1 — provenance (first-person evidence or referential phrase, no provenance)
# ---------------------------------------------------------------------------

def test_r1_fires_when_first_person_evidence_without_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_slots(monkeypatch, _filled_slots(provenance_present=False))
    result = validate("I saw an ad about a new gadget")
    assert "provenance" in _fired(result)


def test_r1_does_not_fire_when_named_platform_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_slots(monkeypatch, _filled_slots(provenance_present=False))
    result = validate("I saw the new gadget ad on YouTube")
    # "youtube" is a named platform → Layer-1 provides provenance even with slot False.
    assert "provenance" not in _fired(result)


# ---------------------------------------------------------------------------
# R2 — disambiguator (described subject, no disambiguator, identify goal)
# ---------------------------------------------------------------------------

def test_r2_fires_for_described_subject_without_disambiguator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_slots(
        monkeypatch,
        _filled_slots(
            subject_kind="described",
            has_disambiguator=False,
            goal_shape="identify",
        ),
    )
    # Use a query Layer 1 cannot itself flag (no first-person, no referential phrase).
    result = validate("Find the tallest building completed last year")
    assert "disambiguator" in _fired(result)


def test_r2_does_not_fire_for_named_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_slots(
        monkeypatch,
        _filled_slots(subject_kind="named", has_disambiguator=False),
    )
    result = validate("Find the tallest building completed last year")
    assert "disambiguator" not in _fired(result)


# ---------------------------------------------------------------------------
# R3 — polysemous_disambig
# ---------------------------------------------------------------------------

def test_r3_fires_for_polysemous_term_with_high_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_slots(
        monkeypatch,
        _filled_slots(subject_ambiguity="high", has_disambiguator=False),
    )
    # "Apple" is polysemous (in POLYSEMOUS_TERMS).
    result = validate("tell me about Apple")
    assert "polysemous_disambig" in _fired(result)


def test_r3_does_not_fire_when_disambiguator_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_slots(
        monkeypatch,
        _filled_slots(subject_ambiguity="high", has_disambiguator=True),
    )
    result = validate("tell me about Apple")
    assert "polysemous_disambig" not in _fired(result)


# ---------------------------------------------------------------------------
# R4 — goal (unknown or low-confidence goal_shape)
# ---------------------------------------------------------------------------

def test_r4_fires_when_goal_shape_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_slots(monkeypatch, _filled_slots(goal_shape=None, goal_confidence=0.0))
    result = validate("Acme Corporation")
    assert "goal" in _fired(result)


def test_r4_does_not_fire_when_goal_is_confident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_slots(monkeypatch, _filled_slots(goal_shape="identify", goal_confidence=0.9))
    result = validate("Acme Corporation")
    assert "goal" not in _fired(result)


# ---------------------------------------------------------------------------
# R5 — scope_time (temporal signal in query but no scope_time slot)
# ---------------------------------------------------------------------------

def test_r5_fires_when_temporal_signal_but_no_scope_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_slots(monkeypatch, _filled_slots(scope_time=None))
    # "new", "2025" → Layer 1 temporal_signal=True.
    result = validate("the new product launch in 2025")
    assert "scope_time" in _fired(result)


def test_r5_does_not_fire_without_temporal_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_slots(monkeypatch, _filled_slots(scope_time=None))
    result = validate("Who founded Microsoft Corporation")
    assert "scope_time" not in _fired(result)


# ---------------------------------------------------------------------------
# R6 — comparison_target (compare goal, named subject, no "vs"/"and")
# ---------------------------------------------------------------------------

def test_r6_fires_for_compare_goal_without_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_slots(
        monkeypatch,
        _filled_slots(
            goal_shape="compare",
            subject_kind="named",
            subject_value="Tesla",
        ),
    )
    result = validate("tell me about Tesla")
    assert "comparison_target" in _fired(result)


def test_r6_does_not_fire_when_query_has_vs(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_slots(
        monkeypatch,
        _filled_slots(
            goal_shape="compare",
            subject_kind="named",
            subject_value="Tesla",
        ),
    )
    result = validate("Tesla vs Rivian")
    assert "comparison_target" not in _fired(result)


# ---------------------------------------------------------------------------
# LLM-gated rules are suppressed when Haiku fails
# ---------------------------------------------------------------------------

def test_llm_dependent_rules_suppressed_when_haiku_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When _haiku_succeeded=False, Rules 2/3/4/5/6 must not fire even if their
    slot conditions would otherwise be true."""
    failed = SlotResult(
        subject_kind="described",
        has_disambiguator=False,
        goal_shape=None,
        goal_confidence=0.0,
        scope_time=None,
        _haiku_succeeded=False,
    )
    _stub_slots(monkeypatch, failed)
    result = validate("the new gadget launched last year")

    fired = _fired(result)
    assert "disambiguator" not in fired
    assert "goal" not in fired
    assert "scope_time" not in fired
    assert "comparison_target" not in fired
