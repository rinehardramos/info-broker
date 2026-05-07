"""Tests for all strategy modules."""
from app.pipeline.strategies.generation import ENTITY_TYPE as GEN_TYPE, STRATEGY as GEN_STRATEGY
from app.pipeline.strategies.explanation import ENTITY_TYPE as EXP_TYPE, STRATEGY as EXP_STRATEGY
from app.pipeline.strategies.prediction import ENTITY_TYPE as PRE_TYPE, STRATEGY as PRE_STRATEGY
from app.pipeline.strategies.synthesis import ENTITY_TYPE as SYN_TYPE, STRATEGY as SYN_STRATEGY


def test_generation_entity_type():
    assert GEN_TYPE == "generation"


def test_generation_has_sections():
    assert "GENERATION RESEARCH STRATEGY" in GEN_STRATEGY
    assert "PRIORITY SELECTORS" in GEN_STRATEGY
    assert "COMPLETENESS CHECKLIST" in GEN_STRATEGY
    assert len(GEN_STRATEGY) > 500


def test_explanation_entity_type():
    assert EXP_TYPE == "explanation"


def test_explanation_has_sections():
    assert "EXPLANATION RESEARCH STRATEGY" in EXP_STRATEGY
    assert "5 Whys" in EXP_STRATEGY or "five whys" in EXP_STRATEGY.lower()
    assert "COMPLETENESS CHECKLIST" in EXP_STRATEGY


def test_prediction_entity_type():
    assert PRE_TYPE == "prediction"


def test_prediction_has_sections():
    assert "PREDICTION RESEARCH STRATEGY" in PRE_STRATEGY
    assert "scenario" in PRE_STRATEGY.lower()
    assert "COMPLETENESS CHECKLIST" in PRE_STRATEGY


def test_synthesis_entity_type():
    assert SYN_TYPE == "synthesis"


def test_synthesis_has_sections():
    assert "SYNTHESIS RESEARCH STRATEGY" in SYN_STRATEGY
    assert "framework" in SYN_STRATEGY.lower()
    assert "COMPLETENESS CHECKLIST" in SYN_STRATEGY
