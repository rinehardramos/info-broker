"""Tests for Retrieval variant strategies."""
from app.pipeline.strategies import get_strategy
from app.pipeline.strategies.orchestrator import classify_query

def test_lead_strategy_loads():
    s = get_strategy("lead")
    assert "LEAD GENERATION STRATEGY" in s
    assert "run_email_enumerator" in s or "run_hunter_io" in s
    assert len(s) > 500

def test_researcher_strategy_loads():
    s = get_strategy("researcher")
    assert "ACADEMIC RESEARCH STRATEGY" in s
    assert "run_openalex_search" in s or "run_semantic_scholar" in s

def test_company_strategy_loads():
    s = get_strategy("company")
    assert "COMPANY INVESTIGATION STRATEGY" in s
    assert "run_opencorporates" in s

def test_due_diligence_strategy_loads():
    s = get_strategy("due_diligence")
    assert "DUE DILIGENCE STRATEGY" in s
    assert "run_pep_sanctions_screen" in s
    assert "run_adverse_media" in s

def test_orchestrator_routes_lead():
    assert classify_query("Find leads for our outreach campaign") == "lead"
    assert classify_query("Build a prospect list of VPs of Engineering") == "lead"

def test_orchestrator_routes_researcher():
    assert classify_query("Find publications by Dr. Smith on CRISPR") == "researcher"
    assert classify_query("Search academic papers on transformer architectures") == "researcher"

def test_orchestrator_routes_company():
    assert classify_query("Company profile of Acme Corp") == "company"
    assert classify_query("Competitor analysis of the fintech market") == "company"

def test_orchestrator_routes_due_diligence():
    assert classify_query("Run KYC on this individual") == "due_diligence"
    assert classify_query("Due diligence background check for acquisition") == "due_diligence"

def test_all_strategies_loadable():
    for key in ["person", "lead", "researcher", "company", "due_diligence",
                "generation", "explanation", "prediction", "synthesis"]:
        s = get_strategy(key)
        assert len(s) > 100, f"Strategy '{key}' is empty or too short"
