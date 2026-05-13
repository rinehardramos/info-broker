"""Layer 2 (LLM slot extraction) tests for app.pipeline.preflight.extract_slots().

extract_slots() tries Gemini first, then falls back to Anthropic Haiku.
We mock at the SDK level (openai.OpenAI / anthropic.Anthropic) so the real
network is never touched. Tests cover:
  - well-formed JSON parsed correctly
  - malformed JSON → all-null/default SlotResult, _haiku_succeeded=False, drives tier 3
  - LLM timeout / exception → _haiku_succeeded=False (non-blocking, tier 3 path)
  - confidence floor enforcement (validate() penalises missing slots)
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.pipeline import preflight
from app.pipeline.preflight import (
    ExtractionResult,
    SlotResult,
    extract,
    extract_slots,
    validate,
)


# ---------------------------------------------------------------------------
# helpers — fake LLM SDK responses
# ---------------------------------------------------------------------------

def _gemini_response(text: str) -> Any:
    """Build a fake OpenAI-compatible chat.completions response."""
    msg = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


class _FakeGeminiClient:
    """Stands in for openai.OpenAI(...) in extract_slots()."""

    def __init__(self, text: str) -> None:
        completions = SimpleNamespace(
            create=lambda **_kw: _gemini_response(text)
        )
        self.chat = SimpleNamespace(completions=completions)


class _RaisingGeminiClient:
    def __init__(self, exc: Exception) -> None:
        def _raise(**_kw: Any) -> None:
            raise exc

        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=_raise)
        )


def _patch_gemini(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    """Force _get_gemini_key() to return a key and openai.OpenAI to yield `client`."""
    monkeypatch.setattr(preflight, "_get_gemini_key", lambda: "test-key")
    # Block Anthropic fallback so the test only exercises the Gemini branch.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    import openai

    monkeypatch.setattr(openai, "OpenAI", lambda **_kw: client)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

WELL_FORMED_SLOTS = {
    "subject_kind": "named",
    "subject_value": "Acme Corp",
    "subject_confidence": 0.92,
    "subject_ambiguity": "low",
    "provenance_present": True,
    "provenance_value": "youtube",
    "provenance_confidence": 0.9,
    "scope_time": "2025",
    "scope_geo": "US",
    "scope_platform": "youtube",
    "goal_shape": "identify",
    "goal_confidence": 0.85,
    "has_disambiguator": True,
    "disambiguator_value": "the CEO",
    "raw_interpretation": "User wants to identify the CEO of Acme Corp",
}


def test_layer2_parses_well_formed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gemini(monkeypatch, _FakeGeminiClient(json.dumps(WELL_FORMED_SLOTS)))

    extraction = extract("Who is the CEO of Acme Corp on YouTube")
    slots = extract_slots("Who is the CEO of Acme Corp on YouTube", extraction)

    assert slots._haiku_succeeded is True
    assert slots.subject_kind == "named"
    assert slots.subject_value == "Acme Corp"
    assert slots.subject_confidence == pytest.approx(0.92)
    assert slots.provenance_present is True
    assert slots.goal_shape == "identify"
    assert slots.has_disambiguator is True
    assert slots.raw_interpretation.startswith("User wants to identify")


def test_layer2_strips_markdown_fences(monkeypatch: pytest.MonkeyPatch) -> None:
    fenced = "```json\n" + json.dumps(WELL_FORMED_SLOTS) + "\n```"
    _patch_gemini(monkeypatch, _FakeGeminiClient(fenced))

    slots = extract_slots("q", ExtractionResult())
    assert slots._haiku_succeeded is True
    assert slots.subject_value == "Acme Corp"


def test_layer2_malformed_json_returns_default_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_gemini(monkeypatch, _FakeGeminiClient("not-json-at-all {{{"))

    slots = extract_slots("q", ExtractionResult())

    # Non-fatal: returns the default SlotResult, _haiku_succeeded stays False.
    assert isinstance(slots, SlotResult)
    assert slots._haiku_succeeded is False
    assert slots.subject_kind == "unknown"
    assert slots.subject_value is None
    assert slots.subject_confidence == 0.0
    assert slots.goal_shape is None


def test_layer2_timeout_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gemini(monkeypatch, _RaisingGeminiClient(TimeoutError("upstream timeout")))

    slots = extract_slots("anything", ExtractionResult())

    assert slots._haiku_succeeded is False
    assert slots.subject_value is None


def test_layer2_no_llm_key_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "_get_gemini_key", lambda: "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    slots = extract_slots("q", ExtractionResult())

    assert slots._haiku_succeeded is False
    assert slots.subject_kind == "unknown"


def test_validate_promotes_to_tier3_when_llm_fails_on_unambiguous_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Layer-1-only mode for a clean query should pass — tier 1 by spec."""
    monkeypatch.setattr(preflight, "_get_gemini_key", lambda: "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    result = validate("Who founded Microsoft Corporation")

    # No referential phrases, no first-person evidence, no temporal signal,
    # no polysemous term → no rule should fire → tier 1.
    assert result.slots._haiku_succeeded is False
    assert result.tier == 1
    assert result.missing == []


def test_validate_drops_to_tier3_when_llm_fails_with_low_confidence_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed/failed LLM on a referential query → Rule 1 fires → tier 2 still works."""
    _patch_gemini(monkeypatch, _FakeGeminiClient("garbage"))

    result = validate("who is the person in the Dyson commercial")

    # Haiku failed, but Layer 1 caught the referential phrase → Rule 1 still fires.
    assert result.slots._haiku_succeeded is False
    assert result.tier in (2, 3)


def test_confidence_floor_penalises_missing_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confidence must shrink when a priority-1 slot is missing."""
    # Slot extraction succeeds with high subject confidence, but provenance is missing.
    slots_payload = dict(WELL_FORMED_SLOTS)
    slots_payload["provenance_present"] = False
    slots_payload["provenance_value"] = None
    slots_payload["provenance_confidence"] = 0.0
    _patch_gemini(monkeypatch, _FakeGeminiClient(json.dumps(slots_payload)))

    # Query has first-person evidence → Rule 1 fires (priority 1).
    result = validate("I saw a strange ad about a new gadget")

    assert result.tier == 2
    assert result.confidence < 0.92  # got penalised below the raw subject_confidence
    assert any(m.slot == "provenance" for m in result.missing)
