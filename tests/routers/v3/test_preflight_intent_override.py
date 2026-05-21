"""Unit tests for intent override + intent catalog in v3 preflight router (#102, #103)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.v3.preflight import (
    _KNOWN_INTENTS,
    _VALID_INTENT_IDS,
    _classify_intent,
    _resolve_strategy,
    PreflightIn,
    list_intents,
)


# ---------------------------------------------------------------------------
# Intent catalog
# ---------------------------------------------------------------------------

def test_known_intents_includes_real_estate():
    assert "real_estate" in _VALID_INTENT_IDS

def test_known_intents_includes_core_categories():
    for needed in ("person", "lead", "company", "real_estate", "media_identification", "place"):
        assert needed in _VALID_INTENT_IDS

def test_known_intents_ids_are_unique():
    ids = [i for i, _ in _KNOWN_INTENTS]
    assert len(ids) == len(set(ids))

def test_known_intents_labels_human_readable():
    for _, label in _KNOWN_INTENTS:
        assert label and label[0].isupper()


# ---------------------------------------------------------------------------
# list_intents endpoint
# ---------------------------------------------------------------------------

def test_list_intents_returns_full_catalog():
    items = list_intents(_user={"id": "00000000-0000-0000-0000-000000000000"})
    assert {i.id for i in items} == _VALID_INTENT_IDS
    real_estate = next(i for i in items if i.id == "real_estate")
    assert real_estate.label == "Real Estate"


# ---------------------------------------------------------------------------
# Classifier — regression for #102
# ---------------------------------------------------------------------------

def test_classify_intent_property_query_not_person():
    assert _classify_intent("properties in pennsylvania") == "real_estate"

def test_classify_intent_falls_back_for_ambiguous():
    # Ambiguous queries still produce *some* intent (not the engine fallback).
    assert _classify_intent("Tell me about quantum computing") == "person"


# ---------------------------------------------------------------------------
# Strategy resolution from override
# ---------------------------------------------------------------------------

def test_resolve_strategy_clamps_unknown_to_media_identification():
    # real_estate isn't registered in engine_v2 yet, so it clamps.
    assert _resolve_strategy("real_estate") == "media_identification"


# ---------------------------------------------------------------------------
# PreflightIn validation
# ---------------------------------------------------------------------------

def test_preflight_in_accepts_intent_override():
    body = PreflightIn(query="x", intent_override="real_estate")
    assert body.intent_override == "real_estate"

def test_preflight_in_intent_override_optional():
    body = PreflightIn(query="x")
    assert body.intent_override is None
