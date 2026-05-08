"""Tests for specific variant strategies."""
from app.pipeline.strategies import get_strategy
from app.pipeline.strategies.orchestrator import classify_query

# Generation variants
def test_product_innovation_loads():
    s = get_strategy("product_innovation")
    assert "PRODUCT INNOVATION STRATEGY" in s
    assert len(s) > 500

def test_scientific_discovery_loads():
    s = get_strategy("scientific_discovery")
    assert "SCIENTIFIC DISCOVERY STRATEGY" in s

def test_engineering_rd_loads():
    s = get_strategy("engineering_rd")
    assert "ENGINEERING R&D STRATEGY" in s
    assert "TRL" in s

# Prediction variants
def test_technology_forecast_loads():
    s = get_strategy("technology_forecast")
    assert "TECHNOLOGY FORECAST STRATEGY" in s

def test_market_forecast_loads():
    s = get_strategy("market_forecast")
    assert "MARKET FORECAST STRATEGY" in s
    assert "TAM" in s or "market size" in s.lower()

# Explanation variants
def test_root_cause_analysis_loads():
    s = get_strategy("root_cause_analysis")
    assert "ROOT CAUSE ANALYSIS STRATEGY" in s
    assert "5 Whys" in s or "five whys" in s.lower()

def test_systems_analysis_loads():
    s = get_strategy("systems_analysis")
    assert "SYSTEMS ANALYSIS STRATEGY" in s
    assert "feedback" in s.lower() or "leverage" in s.lower()

# Synthesis variants
def test_systematic_review_loads():
    s = get_strategy("systematic_review")
    assert "SYSTEMATIC REVIEW STRATEGY" in s

def test_strategic_assessment_loads():
    s = get_strategy("strategic_assessment")
    assert "STRATEGIC ASSESSMENT STRATEGY" in s
    assert "SWOT" in s or "PESTLE" in s

def test_decision_analysis_loads():
    s = get_strategy("decision_analysis")
    assert "DECISION ANALYSIS STRATEGY" in s

# Orchestrator routing
def test_routes_root_cause():
    assert classify_query("Root cause analysis of the outage") == "root_cause_analysis"

def test_routes_systematic_review():
    assert classify_query("Systematic review of climate interventions") == "systematic_review"

def test_routes_decision():
    assert classify_query("Decision matrix: which vendor should we pick?") == "decision_analysis"

def test_routes_market():
    assert classify_query("What is the TAM for AI in healthcare?") == "market_forecast"

def test_all_19_strategies_loadable():
    keys = [
        "person", "lead", "researcher", "company", "due_diligence",
        "generation", "product_innovation", "scientific_discovery", "engineering_rd",
        "prediction", "technology_forecast", "market_forecast",
        "explanation", "root_cause_analysis", "systems_analysis",
        "synthesis", "systematic_review", "strategic_assessment", "decision_analysis",
    ]
    for key in keys:
        s = get_strategy(key)
        assert len(s) > 100, f"Strategy '{key}' empty or too short ({len(s)} chars)"
