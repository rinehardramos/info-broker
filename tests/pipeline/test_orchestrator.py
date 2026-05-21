"""Tests for research query orchestrator."""
from app.pipeline.strategies.orchestrator import classify_query, classify_query_sequence, transform_selectors

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
    # "root cause" now routes to the specific root_cause_analysis variant
    assert classify_query("Root cause analysis of the outage") == "root_cause_analysis"

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


# ---------------------------------------------------------------------------
# Real-estate / property search — regression tests for issue #102
# ---------------------------------------------------------------------------

def test_classify_real_estate_properties_in_location():
    assert classify_query("properties in pennsylvania") == "real_estate"

def test_classify_real_estate_houses_for_sale():
    assert classify_query("houses for sale in cebu") == "real_estate"

def test_classify_real_estate_condo_for_rent():
    assert classify_query("condo for rent in makati") == "real_estate"

def test_classify_real_estate_phrase():
    assert classify_query("real estate listings philippines") == "real_estate"

def test_classify_real_estate_homes_in():
    assert classify_query("homes in austin texas") == "real_estate"

def test_classify_real_estate_does_not_break_person_default():
    # ambiguous query without property signals still defaults to person
    assert classify_query("Tell me about quantum computing") == "person"

def test_classify_real_estate_does_not_outrank_media_identification():
    # media_identification still wins over real_estate when both signals present
    assert classify_query("what show has homes in austin") == "media_identification"

def test_classify_empty():
    assert classify_query("") == "person"

def test_classify_case_insensitive():
    # "new product" now routes to the specific product_innovation variant
    assert classify_query("BUILD a new product") == "product_innovation"
    assert classify_query("WHY did this happen") == "explanation"


# ---------------------------------------------------------------------------
# Cross-category transition tests
# ---------------------------------------------------------------------------

def test_classify_sequence_single():
    seq = classify_query_sequence("Find John Doe's email")
    assert seq == ["person"]  # Single category

def test_classify_sequence_compound_build():
    seq = classify_query_sequence("Build a cure for cancer")
    assert len(seq) >= 2
    assert "generation" in seq or "product_innovation" in seq or "scientific_discovery" in seq

def test_classify_sequence_compound_why_and_fix():
    seq = classify_query_sequence("Why is our system slow and how to fix it?")
    assert len(seq) >= 2
    # Should have explanation + generation
    has_explanation = any(s in seq for s in ["explanation", "root_cause_analysis"])
    has_generation = any(s in seq for s in ["generation", "product_innovation", "engineering_rd"])
    assert has_explanation or has_generation

def test_classify_sequence_compound_review_and_predict():
    seq = classify_query_sequence("What is the state of AI and where is it going?")
    assert len(seq) >= 2

def test_transform_selectors_retrieval_to_generation():
    findings = [
        {"type": "finding", "content": "Existing CRISPR therapy achieves 40% response rate"},
    ]
    transformed = transform_selectors(findings, from_category="person", to_category="generation")
    assert any(t["type"] == "prior_art" for t in transformed)

def test_transform_selectors_explanation_to_generation():
    findings = [
        {"type": "root_cause", "content": "Tumor microenvironment suppresses T cells"},
    ]
    transformed = transform_selectors(findings, from_category="explanation", to_category="generation")
    assert any(t["type"] == "constraint" for t in transformed)

def test_transform_selectors_generation_to_explanation():
    findings = [
        {"type": "candidate_solution", "content": "Use engineered T cells with TGF-B resistance"},
    ]
    transformed = transform_selectors(findings, from_category="generation", to_category="explanation")
    assert any(t["type"] == "hypothesis" for t in transformed)

def test_transform_selectors_no_change_same_category():
    findings = [{"type": "finding", "content": "test"}]
    transformed = transform_selectors(findings, from_category="person", to_category="person")
    assert transformed[0]["type"] == "finding"  # Unchanged
