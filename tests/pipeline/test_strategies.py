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


from app.is_prompt import build_prompt

def test_build_prompt_includes_entity_strategy():
    prompt = build_prompt(
        query="profile John Doe",
        entity_strategy="=== TEST STRATEGY ===\nDo things.",
    )
    assert "=== TEST STRATEGY ===" in prompt

def test_build_prompt_entity_strategy_before_workflow():
    prompt = build_prompt(
        query="profile John Doe",
        entity_strategy="=== PERSON STRATEGY ===",
    )
    assert prompt.index("=== PERSON STRATEGY ===") < prompt.index("YOUR WORKFLOW")

def test_build_prompt_no_entity_strategy_by_default():
    prompt = build_prompt(query="test query")
    assert "=== PERSON INVESTIGATION STRATEGY ===" not in prompt
