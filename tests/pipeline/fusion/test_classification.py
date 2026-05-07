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
