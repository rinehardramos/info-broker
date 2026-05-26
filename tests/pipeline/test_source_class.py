"""Tests for source-class authority resolution in tactician.

A finding's provenance class is the BEST-supported among the brain's self-label,
the technique's class, and the URL's authority — so a real government record or
official-listing page gets correct (high) provenance instead of the brain's
uniform 'live_search'. live_official must be recognized as a live class.
"""
from __future__ import annotations

from app.pipeline.tactician import (
    _best_source_class,
    _technique_to_source_class,
    _url_derived_class,
)


def test_url_derived_class_government_records():
    assert _url_derived_class("https://datacatalog.cookcountyil.gov/resource/x.json") == "primary_official"
    assert _url_derived_class("https://example.gov/recorder/deed") == "primary_official"
    assert _url_derived_class("https://services.arcgis.com/abc/query?f=json") == "primary_official"


def test_url_derived_class_official_listing():
    assert _url_derived_class("https://www.zillow.com/homedetails/123") == "live_official"
    assert _url_derived_class("https://www.fsbo.com/listing/chicago-x") == "live_official"


def test_url_derived_class_generic_is_none():
    assert _url_derived_class("https://someblog.example.com/post") is None
    assert _url_derived_class("") is None
    assert _url_derived_class(None) is None


def test_best_source_class_picks_highest_authority():
    # brain says live_search, technique is primary, URL generic → primary wins
    assert _best_source_class("live_search", "primary_official", None) == "primary_official"
    # brain live_search, technique live_search, URL official-listing → live_official
    assert _best_source_class("live_search", "live_search", "live_official") == "live_official"
    # nothing authoritative → live_search default
    assert _best_source_class(None, None, None) == "live_search"
    # never downgrades a primary self-label
    assert _best_source_class("primary_official", "live_search", None) == "primary_official"


def test_property_records_techniques_are_primary():
    assert _technique_to_source_class("property_records_lookup") == "primary_official"
    assert _technique_to_source_class("property_history_records") == "primary_official"
    assert _technique_to_source_class("listing_detail_scrape") == "live_official"
    # a generic search technique stays live_search
    assert _technique_to_source_class("web_search") == "live_search"


def test_live_official_recognized_as_live_class():
    # The pipeline's live-source sets must include live_official, or promoted
    # findings would wrongly fail live-source gates.
    from app.pipeline.ach import _LIVE_SOURCE_CLASSES
    from app.pipeline.strategist import _PRIMARY_LIVE_CLASSES
    assert "live_official" in _LIVE_SOURCE_CLASSES
    assert "live_official" in _PRIMARY_LIVE_CLASSES
