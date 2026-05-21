"""Tests for the strategy resolution chain in app/routers/v3/preflight.py.

Verifies the 4-step fallback chain that maps (intent, mode) → strategy_id:

    1. Intent has a dedicated strategy module      → use it
    2. Mode has strategy_suggestions               → first registered wins
    3. generic_search is registered                → fallback floor
    4. media_identification (legacy floor)         → ultimate fallback

Catches regressions like the b0e457a4 run, where every non-media intent was
silently routed through media_identification's broaden gate.
"""
from __future__ import annotations

from unittest.mock import patch

from app.routers.v3.preflight import (
    _classify_query,
    _resolve_strategy,
    _suggest_mode,
)


# ---------------------------------------------------------------------------
# Step 1: dedicated intent module wins
# ---------------------------------------------------------------------------


class TestIntentDirectMatch:
    def test_real_estate_intent_routes_to_real_estate_module(self):
        assert _resolve_strategy("real_estate") == "real_estate"

    def test_media_identification_intent_routes_to_media_identification(self):
        assert _resolve_strategy("media_identification") == "media_identification"

    def test_each_registered_intent_routes_to_itself(self):
        """Every overlay strategy I shipped must self-route on its own intent
        — that's the definition of having a dedicated module."""
        for intent in [
            "real_estate", "lead", "company", "place",
            "generation", "explanation", "prediction", "synthesis",
            "generic_search", "media_identification",
        ]:
            assert _resolve_strategy(intent) == intent


# ---------------------------------------------------------------------------
# Step 2: mode-anchored fallback when intent has no dedicated module
# ---------------------------------------------------------------------------


class TestModeAnchorFallback:
    def test_unknown_intent_with_academic_mode_picks_synthesis(self):
        """academic_research's strategy_suggestions = ['researcher',
        'synthesis', 'generic_search']. 'researcher' isn't registered, so
        the resolver walks past it and lands on 'synthesis'."""
        assert _resolve_strategy("unknown_intent", mode="academic_research") == "synthesis"

    def test_unknown_intent_with_leads_mode_picks_lead(self):
        assert _resolve_strategy("unknown_intent", mode="leads_generation") == "lead"

    def test_unknown_intent_with_data_retrieval_picks_real_estate(self):
        """data_retrieval suggests real_estate first; all are registered."""
        assert _resolve_strategy("unknown_intent", mode="data_retrieval") == "real_estate"

    def test_unknown_intent_with_investigation_picks_media_identification(self):
        """investigation prefers media_identification (the only ACH strategy)."""
        assert _resolve_strategy("unknown_intent", mode="investigation") == "media_identification"


# ---------------------------------------------------------------------------
# Step 3: generic_search floor when no intent and no mode match
# ---------------------------------------------------------------------------


class TestGenericSearchFloor:
    def test_unknown_intent_no_mode_falls_to_generic_search(self):
        assert _resolve_strategy("unknown_intent") == "generic_search"

    def test_unknown_intent_unknown_mode_falls_to_generic_search(self):
        assert _resolve_strategy("unknown_intent", mode="not_a_real_mode") == "generic_search"


# ---------------------------------------------------------------------------
# End-to-end: _classify_query (the function preflight handler actually calls)
# ---------------------------------------------------------------------------


class TestClassifyQuery:
    def test_property_query_routes_to_real_estate(self):
        """The original b0e457a4 failing query must now route to real_estate
        (not media_identification → broaden gate hard-fail)."""
        assert _classify_query("show me properties for rent in chicago") == "real_estate"

    def test_media_query_still_routes_to_media_identification(self):
        assert _classify_query(
            "what show is the girl in the new netflix series"
        ) == "media_identification"

    def test_person_query_routes_to_person(self):
        """'investigate <name>' → person intent → routes to person.py
        (added in the ACH-strategies batch). Was 'generic_search' before
        person.py existed."""
        assert _classify_query("investigate Acme Corp") == "person"

    def test_due_diligence_query_routes_to_due_diligence(self):
        """'kyc on <entity>' → due_diligence intent → due_diligence.py
        (added in the ACH-strategies batch)."""
        assert _classify_query("kyc on Acme Corp") == "due_diligence"


# ---------------------------------------------------------------------------
# _suggest_mode now reads strategy.default_mode from catalog
# ---------------------------------------------------------------------------


class TestSuggestMode:
    def test_media_identification_default_mode_is_investigation(self):
        assert _suggest_mode("media_identification") == "investigation"

    def test_real_estate_default_mode_is_data_retrieval(self):
        assert _suggest_mode("real_estate") == "data_retrieval"

    def test_lead_default_mode_is_leads_generation(self):
        assert _suggest_mode("lead") == "leads_generation"

    def test_prediction_default_mode_is_market_analysis(self):
        assert _suggest_mode("prediction") == "market_analysis"

    def test_synthesis_default_mode_is_academic_research(self):
        assert _suggest_mode("synthesis") == "academic_research"

    def test_unknown_strategy_falls_back_to_quick_lookup(self):
        assert _suggest_mode("not_a_real_strategy") == "quick_lookup"
