"""Tests for category selectors module — TDD pass."""
from __future__ import annotations

import pytest

from app.pipeline.strategies.selectors import CATEGORY_SELECTORS, get_selectors


# ---------------------------------------------------------------------------
# CATEGORY_SELECTORS dict shape
# ---------------------------------------------------------------------------

def test_all_five_categories_present() -> None:
    expected = {"person", "generation", "prediction", "explanation", "synthesis"}
    assert expected == set(CATEGORY_SELECTORS.keys())


def test_all_categories_non_empty() -> None:
    for category, selectors in CATEGORY_SELECTORS.items():
        assert len(selectors) > 0, f"{category} selector list is empty"


def test_each_category_has_at_least_five_selectors() -> None:
    for category, selectors in CATEGORY_SELECTORS.items():
        assert len(selectors) >= 5, f"{category} has fewer than 5 selectors: {selectors}"


# ---------------------------------------------------------------------------
# Person category
# ---------------------------------------------------------------------------

def test_person_selectors_contain_required_fields() -> None:
    selectors = get_selectors("person")
    for field in ("full_name", "email", "phone"):
        assert field in selectors, f"'person' selectors missing '{field}'"


# ---------------------------------------------------------------------------
# Generation category
# ---------------------------------------------------------------------------

def test_generation_selectors_contain_required_fields() -> None:
    selectors = get_selectors("generation")
    for field in ("problem_statement", "concept"):
        assert field in selectors, f"'generation' selectors missing '{field}'"


# ---------------------------------------------------------------------------
# Prediction category
# ---------------------------------------------------------------------------

def test_prediction_selectors_contain_required_fields() -> None:
    selectors = get_selectors("prediction")
    for field in ("signal", "trend"):
        assert field in selectors, f"'prediction' selectors missing '{field}'"


# ---------------------------------------------------------------------------
# Explanation category
# ---------------------------------------------------------------------------

def test_explanation_selectors_contain_required_fields() -> None:
    selectors = get_selectors("explanation")
    for field in ("symptom", "root_cause"):
        assert field in selectors, f"'explanation' selectors missing '{field}'"


# ---------------------------------------------------------------------------
# Synthesis category
# ---------------------------------------------------------------------------

def test_synthesis_selectors_contain_required_fields() -> None:
    selectors = get_selectors("synthesis")
    for field in ("study", "framework"):
        assert field in selectors, f"'synthesis' selectors missing '{field}'"


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------

def test_unknown_category_falls_back_to_person_selectors() -> None:
    assert get_selectors("unknown") == get_selectors("person")


def test_empty_string_falls_back_to_person_selectors() -> None:
    assert get_selectors("") == get_selectors("person")


def test_get_selectors_returns_list() -> None:
    for category in CATEGORY_SELECTORS:
        result = get_selectors(category)
        assert isinstance(result, list), f"get_selectors('{category}') did not return a list"
