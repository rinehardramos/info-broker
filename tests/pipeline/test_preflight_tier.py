"""Tier selection + regression tests for app.pipeline.preflight.validate().

Tier mapping in preflight.py:
  tier 1 → PROCEED (no missing slots, confidence ≥ 0.6)
  tier 2 → BLOCK   (at least one missing slot, blocking=True)
  tier 3 → PROCEED_WITH_DISCLAIMER (no missing slots but low confidence)

Regression cases (real bugs):
  - Amazon ad: "new series with girl in spiderman where man has a shotgun"
  - Dyson:     "who is the person in the Dyson commercial"
Both must NOT be tier 1 — they were silently passing through to research.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.pipeline import preflight
from app.pipeline.preflight import SlotResult, extract, validate


# Tiers that mean "do not silently research this query".
GATED_TIERS = {2, 3}


def _stub_slots(monkeypatch: pytest.MonkeyPatch, slots: SlotResult) -> None:
    monkeypatch.setattr(preflight, "extract_slots", lambda _q, _e: slots)


def _failed_haiku() -> SlotResult:
    return SlotResult(_haiku_succeeded=False)


def _complete_named_slots(**overrides: Any) -> SlotResult:
    base = SlotResult(
        subject_kind="named",
        subject_value="Microsoft",
        subject_confidence=0.95,
        subject_ambiguity="low",
        provenance_present=True,
        provenance_value="public knowledge",
        provenance_confidence=0.9,
        scope_time="historical",
        scope_geo="US",
        scope_platform=None,
        goal_shape="identify",
        goal_confidence=0.9,
        has_disambiguator=True,
        disambiguator_value="founder",
        raw_interpretation="User wants to identify who founded Microsoft",
        _haiku_succeeded=True,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


# ---------------------------------------------------------------------------
# Regression: Amazon ad query
# ---------------------------------------------------------------------------

def test_amazon_ad_regression_is_not_tier1(monkeypatch: pytest.MonkeyPatch) -> None:
    """A vague referential query about a streaming ad must be gated."""
    _stub_slots(monkeypatch, _failed_haiku())
    result = validate("new series with girl in spiderman where man has a shotgun")
    assert result.tier in GATED_TIERS, (
        f"Amazon ad regression: expected gated tier (2/3), got {result.tier}"
    )


def test_amazon_ad_extraction_flags_referential() -> None:
    e = extract("new series with girl in spiderman where man has a shotgun")
    assert e.referential_phrases, "expected referential phrase to be detected"
    assert e.temporal_signal is True  # "new"


# ---------------------------------------------------------------------------
# Regression: Dyson commercial query
# ---------------------------------------------------------------------------

def test_dyson_commercial_regression_is_not_tier1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_slots(monkeypatch, _failed_haiku())
    result = validate("who is the person in the Dyson commercial")
    assert result.tier in GATED_TIERS, (
        f"Dyson regression: expected gated tier (2/3), got {result.tier}"
    )


def test_dyson_extraction_flags_referential_phrase() -> None:
    e = extract("who is the person in the Dyson commercial")
    assert e.referential_phrases, "expected referential phrase for Dyson query"


# ---------------------------------------------------------------------------
# Tier 1 — complete, unambiguous query
# ---------------------------------------------------------------------------

def test_tier1_when_query_is_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_slots(monkeypatch, _complete_named_slots())
    result = validate("Who founded Microsoft Corporation")
    assert result.tier == 1
    assert result.blocking is False
    assert result.missing == []
    assert result.first_question is None
    assert result.disclaimer is None


# ---------------------------------------------------------------------------
# Tier 3 — LLM failure on a clean query
# ---------------------------------------------------------------------------

def test_tier3_disclaimer_path_when_haiku_fails_with_clean_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Haiku failed, but Layer 1 sees no problems → tier 1 by spec.
    (Layer-1-only mode uses a 0.7 base confidence — clean queries pass through.)
    """
    _stub_slots(monkeypatch, _failed_haiku())
    result = validate("Who founded Microsoft Corporation")
    # No referential, no first-person evidence, no temporal, no polysemous → tier 1.
    assert result.tier == 1
    assert result.missing == []


def test_tier3_disclaimer_path_on_low_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A SlotResult with no missing slots but low subject_confidence drives tier 3."""
    low_conf = SlotResult(
        subject_kind="named",
        subject_value="something",
        subject_confidence=0.2,
        subject_ambiguity="low",
        provenance_present=True,
        provenance_value="known",
        provenance_confidence=0.9,
        scope_time="historical",
        scope_geo=None,
        scope_platform=None,
        goal_shape="explain",
        goal_confidence=0.9,
        has_disambiguator=True,
        disambiguator_value="x",
        raw_interpretation="User wants to explain something",
        _haiku_succeeded=True,
    )
    _stub_slots(monkeypatch, low_conf)
    result = validate("explain this please")
    # No missing slots → not tier 2; low confidence → tier 3 with disclaimer.
    assert result.missing == []
    assert result.tier == 3
    assert result.blocking is False
    assert result.disclaimer is not None


# ---------------------------------------------------------------------------
# Priority ordering — highest-priority rule wins first_question
# ---------------------------------------------------------------------------

def test_first_question_uses_highest_priority_missing_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When multiple rules fire, first_question must come from priority=1."""
    # Trigger R1 (priority 1, provenance) AND R4 (priority 3, goal).
    slots = SlotResult(
        subject_kind="named",
        subject_value="thing",
        subject_confidence=0.8,
        provenance_present=False,
        goal_shape=None,
        goal_confidence=0.0,
        _haiku_succeeded=True,
    )
    _stub_slots(monkeypatch, slots)
    result = validate("I saw something interesting")

    assert result.tier == 2
    assert result.first_question is not None
    # The chosen first question must come from the priority-1 missing slot.
    assert result.missing[0].priority == 1
    assert result.missing[0].slot == "provenance"
    # first_question text matches that of the top-priority slot.
    assert result.first_question == result.missing[0].question


# ---------------------------------------------------------------------------
# Non-fatal: validate() never raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "a",
        "?" * 50,
        "very long " * 200,
        "🤖💥",
        "SELECT * FROM users; --",
        "new series with girl in spiderman where man has a shotgun",
        "who is the person in the Dyson commercial",
    ],
)
def test_validate_never_raises(query: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_slots(monkeypatch, _failed_haiku())
    # Must not raise — preflight is non-fatal by contract.
    result = validate(query)
    assert result.tier in (1, 2, 3)
