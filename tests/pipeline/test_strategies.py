"""Tests for the strategy module loader."""
from app.pipeline.strategies import get_strategy

def test_get_strategy_person_returns_string():
    result = get_strategy("person")
    assert isinstance(result, str)
    assert len(result) > 100

def test_get_strategy_person_contains_key_sections():
    result = get_strategy("person")
    assert "PERSON INVESTIGATION STRATEGY" in result
    assert "PRIORITY SELECTORS" in result
    assert "COMPLETENESS CHECKLIST" in result

def test_get_strategy_unknown_returns_empty():
    assert get_strategy("unknown_type_xyz") == ""
