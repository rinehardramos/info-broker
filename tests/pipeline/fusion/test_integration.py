"""Integration test: full fusion pipeline from findings to KG observations."""
from __future__ import annotations
import asyncio
from unittest.mock import patch

from app.pipeline.fusion.selectors import extract_selectors_from_findings
from app.pipeline.fusion.classification import rate_source, admiralty_info_credibility
from app.pipeline.fusion.writer import write_entities_to_kg, write_relationships_to_kg


def _arun(coro): return asyncio.run(coro)


def test_full_fusion_flow():
    """Findings -> selectors -> entities -> KG observations."""
    findings = [
        {
            "title": "LinkedIn Profile",
            "content": "John Doe, VP Sales at acme.com. Email: john.doe@acme.com",
            "source": "linkedin_profile",
        },
        {
            "title": "HIBP Check",
            "content": "john.doe@acme.com found in LinkedIn2021 breach",
            "source": "hibp_lookup",
        },
    ]

    # Step 1: Extract selectors
    selectors = extract_selectors_from_findings(findings)
    emails = [s for s in selectors if s["type"] == "email"]
    domains = [s for s in selectors if s["type"] == "domain"]
    assert len(emails) >= 1
    assert emails[0]["value"] == "john.doe@acme.com"
    # acme.com is an email domain so it must NOT appear in domain selectors
    assert all(d["value"] != "acme.com" for d in domains)

    # Step 2: Rate sources
    assert rate_source("linkedin_profile") == "B"
    assert rate_source("hibp_lookup") == "B"

    # Step 3: Assess corroboration (email found in 2 findings)
    assert admiralty_info_credibility(2) == 2  # Probably true

    # Step 4: Write to KG (mock DB)
    entities = [
        {
            "name": "John Doe",
            "type": "person",
            "attributes": {"role": "VP Sales", "company": "Acme"},
        },
    ]
    relationships = [
        {
            "from": "John Doe",
            "to": "Acme",
            "type": "works_at",
            "evidence": "LinkedIn profile",
        },
    ]

    with patch("app.pipeline.fusion.writer.execute") as mock_exec:
        entity_count = _arun(write_entities_to_kg("run-1", entities, "linkedin_profile"))
        rel_count = _arun(write_relationships_to_kg("run-1", relationships, "linkedin_profile"))

    assert entity_count >= 3  # name + role + company
    assert rel_count == 1
    assert mock_exec.call_count >= 4  # 3 entity obs + 1 relationship obs


def test_fusion_empty_findings():
    """Empty findings produce no selectors or KG writes."""
    selectors = extract_selectors_from_findings([])
    assert selectors == []

    with patch("app.pipeline.fusion.writer.execute") as mock_exec:
        _arun(write_entities_to_kg("run-1", [], "ddg_search"))
    assert mock_exec.call_count == 0


def test_fusion_source_rating_affects_confidence():
    """Higher-rated sources produce higher confidence observations."""
    entities = [{"name": "Test", "type": "person", "attributes": {}}]

    # A-rated source (government registry)
    with patch("app.pipeline.fusion.writer.execute") as mock_a:
        _arun(write_entities_to_kg("run-1", entities, "ph_sec_dti"))

    # D-rated source (web search)
    with patch("app.pipeline.fusion.writer.execute") as mock_d:
        _arun(write_entities_to_kg("run-1", entities, "ddg_search"))

    # Extract confidence values from the SQL params.
    # entity_observations INSERT param order:
    #   (id, entity_ref, entity_type, attribute, value, confidence, source_run_id, source_tool)
    #    0    1           2            3          4      5           6              7
    conf_a = mock_a.call_args_list[0][0][1][5]
    conf_d = mock_d.call_args_list[0][0][1][5]
    assert conf_a > conf_d  # A-rated source must produce higher confidence
