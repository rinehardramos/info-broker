"""Tests for the PIR coverage integration into the loop."""
from __future__ import annotations

from app.pipeline.fusion.pir import (
    infer_entity_type, decompose_query_to_pirs,
    map_findings_to_pirs, generate_coverage_report,
)


def test_infer_entity_type_company():
    assert infer_entity_type("Grab Holdings Ltd FY2024 revenue") == "company"
    assert infer_entity_type("What was Apple Inc.'s Q3 result?") == "company"
    assert infer_entity_type("Tesla NASDAQ:TSLA recent filings") == "company"


def test_infer_entity_type_person():
    assert infer_entity_type("Who is the CEO of Acme?") == "person"
    assert infer_entity_type("Background check on Jane Doe") == "person"
    assert infer_entity_type("Profile of John Smith founder of XYZ") == "person"


def test_infer_entity_type_generic_falls_back():
    assert infer_entity_type("What is the weather in Singapore?") == "generic"
    assert infer_entity_type("Explain quantum entanglement") == "generic"


def test_pir_company_coverage_with_findings():
    """Findings that mention CEO + employer + product give partial coverage on
    the company PIR template — proves the keyword matching reaches into the
    real templates, not just the heuristic."""
    pirs = decompose_query_to_pirs("Profile of Acme Corp", "company")
    findings = [
        {"title": "Acme Corp is a Singapore-incorporated fintech", "content": "incorporated in 2018"},
        {"title": "Acme founded by John Smith", "content": "founder John Smith owner"},
    ]
    pirs = map_findings_to_pirs(pirs, findings)
    report = generate_coverage_report(pirs)
    assert report["total_eeis"] > 0
    # At least some EEIs resolved by these keyword-rich findings
    assert report["resolved_eeis"] > 0
    assert 0.0 < report["overall_coverage"] <= 1.0
    # Gaps are well-formed PIR > SIR > EEI strings
    if report["gaps"]:
        assert " > " in report["gaps"][0]


def test_pir_zero_findings_reports_zero_coverage():
    pirs = decompose_query_to_pirs("Profile of Acme", "company")
    pirs = map_findings_to_pirs(pirs, [])
    report = generate_coverage_report(pirs)
    assert report["resolved_eeis"] == 0
    assert report["overall_coverage"] == 0.0
    # Every EEI is a gap
    assert len(report["gaps"]) == report["total_eeis"]


def test_pir_unknown_entity_type_uses_generic_template():
    pirs = decompose_query_to_pirs("What is X?", "alien-entity")
    # Generic template has at least one PIR
    assert len(pirs) >= 1
    assert pirs[0]["name"] == "Core Research Question"
