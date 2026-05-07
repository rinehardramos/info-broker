"""Tests for research query orchestrator."""
from app.pipeline.strategies.orchestrator import classify_query

def test_classify_retrieval_investigate():
    assert classify_query("Investigate John Doe's background") == "person"

def test_classify_retrieval_find():
    assert classify_query("Find everything about Acme Corp") == "person"

def test_classify_retrieval_profile():
    assert classify_query("Build a complete profile of Jane Smith") == "person"

def test_classify_generation_build():
    assert classify_query("Build a new authentication system") == "generation"

def test_classify_generation_create():
    assert classify_query("Create a cure for drug-resistant bacteria") == "generation"

def test_classify_generation_design():
    assert classify_query("Design a better search algorithm") == "generation"

def test_classify_explanation_why():
    assert classify_query("Why is our database performance degrading?") == "explanation"

def test_classify_explanation_root_cause():
    assert classify_query("Root cause analysis of the outage") == "explanation"

def test_classify_explanation_diagnose():
    assert classify_query("Diagnose why conversion rates dropped") == "explanation"

def test_classify_prediction_forecast():
    assert classify_query("Forecast AI adoption in healthcare for 2027") == "prediction"

def test_classify_prediction_trend():
    assert classify_query("What trends will shape fintech next year?") == "prediction"

def test_classify_prediction_future():
    assert classify_query("What will the future of remote work look like?") == "prediction"

def test_classify_synthesis_review():
    assert classify_query("Review all evidence on climate interventions") == "synthesis"

def test_classify_synthesis_compare():
    assert classify_query("Compare React vs Vue vs Svelte for our use case") == "synthesis"

def test_classify_synthesis_evaluate():
    assert classify_query("Evaluate whether our marketing strategy is working") == "synthesis"

def test_classify_default_ambiguous():
    assert classify_query("Tell me about quantum computing") == "person"  # default

def test_classify_empty():
    assert classify_query("") == "person"

def test_classify_case_insensitive():
    assert classify_query("BUILD a new product") == "generation"
    assert classify_query("WHY did this happen") == "explanation"
