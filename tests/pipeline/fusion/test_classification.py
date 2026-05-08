"""Tests for Admiralty source classification."""
from app.pipeline.fusion.classification import (
    rate_source, confidence_to_stix, admiralty_info_credibility, SOURCE_RATINGS
)


def test_source_ratings_has_entries():
    assert len(SOURCE_RATINGS) >= 15


def test_rate_source_government():
    assert rate_source("ph_sec_dti") == "A"
    assert rate_source("sec_edgar") == "A"
    assert rate_source("opencorporates") == "A"


def test_rate_source_professional():
    assert rate_source("linkedin_profile") == "B"
    assert rate_source("hibp_lookup") == "B"
    assert rate_source("smtp_verifier") == "B"


def test_rate_source_social():
    assert rate_source("facebook_pages") == "C"
    assert rate_source("instagram_profile") == "C"
    assert rate_source("twitter_search") == "C"


def test_rate_source_web():
    assert rate_source("ddg_search") == "D"
    assert rate_source("web_crawl") == "D"


def test_rate_source_unknown():
    assert rate_source("unknown_tool_xyz") == "F"


def test_rate_source_strips_run_prefix():
    assert rate_source("run_hibp_lookup") == "B"


def test_confidence_to_stix_capped():
    assert confidence_to_stix(150) == 100
    assert confidence_to_stix(-10) == 0
    assert confidence_to_stix(75) == 75


def test_admiralty_credibility_no_sources():
    assert admiralty_info_credibility(0) == 6  # Cannot judge


def test_admiralty_credibility_single():
    assert admiralty_info_credibility(1) == 3  # Possibly true


def test_admiralty_credibility_corroborated():
    assert admiralty_info_credibility(2) == 2  # Probably true


def test_admiralty_credibility_confirmed():
    assert admiralty_info_credibility(3) == 1  # Confirmed
    assert admiralty_info_credibility(5) == 1


# --- corroboration tracking ---

from app.pipeline.fusion.classification import track_corroboration


def test_corroboration_single_source():
    findings = [
        {"content": "John works at Acme Corp", "source": "linkedin_profile"},
    ]
    result = track_corroboration(findings)
    assert len(result) == 1
    assert result[0]["corroboration_level"] == "uncorroborated"
    assert result[0]["corroboration_count"] == 1
    assert result[0]["credibility"] == 3  # Possibly true


def test_corroboration_two_sources():
    findings = [
        {"content": "John works at Acme Corp as VP Sales", "source": "linkedin_profile"},
        {"content": "John Doe listed as VP at Acme Corp", "source": "apollo_zoominfo"},
    ]
    result = track_corroboration(findings)
    # Both mention "Acme Corp" - should detect corroboration
    acme_findings = [r for r in result if "acme" in r["content"].lower()]
    assert any(r["corroboration_level"] in ("corroborated", "multi_source") for r in acme_findings)


def test_corroboration_no_overlap():
    findings = [
        {"content": "John lives in Manila", "source": "facebook_pages"},
        {"content": "His email is john@example.com", "source": "hunter_io"},
    ]
    result = track_corroboration(findings)
    assert all(r["corroboration_level"] == "uncorroborated" for r in result)


def test_corroboration_three_plus_sources():
    findings = [
        {"content": "john.doe@acme.com is his email", "source": "hunter_io"},
        {"content": "Contact: john.doe@acme.com", "source": "linkedin_profile"},
        {"content": "john.doe@acme.com found in breach", "source": "hibp_lookup"},
    ]
    result = track_corroboration(findings)
    # Email appears in 3 sources
    multi = [r for r in result if r["corroboration_level"] == "multi_source"]
    assert len(multi) >= 1


def test_corroboration_same_source_not_counted():
    findings = [
        {"content": "John at Acme", "source": "ddg_search"},
        {"content": "John works at Acme Corp", "source": "ddg_search"},
    ]
    result = track_corroboration(findings)
    # Same source doesn't count as corroboration
    assert all(r["corroboration_level"] == "uncorroborated" for r in result)


def test_corroboration_enriches_findings():
    findings = [{"content": "test", "source": "a", "title": "T"}]
    result = track_corroboration(findings)
    # Original fields preserved
    assert result[0]["title"] == "T"
    assert "corroboration_level" in result[0]
    assert "corroboration_count" in result[0]
    assert "credibility" in result[0]
