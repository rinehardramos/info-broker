"""Tests for the pre-research conflict-detection gate."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import patch, MagicMock

from app.temporal.activities.conflict_check import (
    ConflictCheckInput, ConflictCheckResult, conflict_check, _strip_fences,
)


def test_fail_open_when_no_llm_key():
    """Without a Gemini key the gate must NOT block the run."""
    with patch("app.temporal.activities.conflict_check._get_gemini_key", return_value=""):
        out = asyncio.run(conflict_check(ConflictCheckInput(query="anything")))
    assert out.ambiguous is False
    assert "no_llm_available" in out.raw_reasoning


def test_fail_open_on_llm_error():
    """If the LLM call raises, return ambiguous=False (don't block)."""
    with patch("app.temporal.activities.conflict_check._get_gemini_key", return_value="fake"), \
         patch("openai.OpenAI", side_effect=RuntimeError("api down")):
        out = asyncio.run(conflict_check(ConflictCheckInput(query="anything")))
    assert out.ambiguous is False
    assert out.raw_reasoning.startswith("error:")


def _mock_openai_returning(json_str: str):
    msg = MagicMock(); msg.content = json_str
    choice = MagicMock(); choice.message = msg
    resp = MagicMock(); resp.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return MagicMock(return_value=client)


def test_unambiguous_query_returns_false():
    raw = '{"ambiguous": false}'
    with patch("app.temporal.activities.conflict_check._get_gemini_key", return_value="fake"), \
         patch("openai.OpenAI", _mock_openai_returning(raw)):
        out = asyncio.run(conflict_check(ConflictCheckInput(query="What is Grab's FY2024 net loss?")))
    assert out.ambiguous is False


def test_ambiguous_query_returns_clarification():
    raw = json.dumps({
        "ambiguous": True,
        "ambiguity_kind": "entity",
        "clarification_question": "Which Acme — the fintech or the food company?",
        "options": ["Acme fintech", "Acme food"],
    })
    with patch("app.temporal.activities.conflict_check._get_gemini_key", return_value="fake"), \
         patch("openai.OpenAI", _mock_openai_returning(raw)):
        out = asyncio.run(conflict_check(ConflictCheckInput(query="Tell me about Acme")))
    assert out.ambiguous is True
    assert out.ambiguity_kind == "entity"
    assert "Acme" in out.clarification_question
    assert out.options == ["Acme fintech", "Acme food"]


def test_strips_markdown_fences():
    assert _strip_fences("```json\n{\"x\": 1}\n```") == '{"x": 1}'
    assert _strip_fences("```\n{}\n```") == "{}"
    assert _strip_fences('{"x":1}') == '{"x":1}'


def test_options_capped_at_six():
    raw = json.dumps({
        "ambiguous": True,
        "ambiguity_kind": "entity",
        "clarification_question": "Which one?",
        "options": [f"opt{i}" for i in range(10)],
    })
    with patch("app.temporal.activities.conflict_check._get_gemini_key", return_value="fake"), \
         patch("openai.OpenAI", _mock_openai_returning(raw)):
        out = asyncio.run(conflict_check(ConflictCheckInput(query="ambiguous")))
    assert len(out.options) == 6


def test_malformed_json_fails_open():
    with patch("app.temporal.activities.conflict_check._get_gemini_key", return_value="fake"), \
         patch("openai.OpenAI", _mock_openai_returning("not json at all")):
        out = asyncio.run(conflict_check(ConflictCheckInput(query="x")))
    assert out.ambiguous is False
    assert out.raw_reasoning.startswith("parse_failed:")


def test_json_with_prose_wrapping_is_extracted():
    """Gemini sometimes wraps JSON in explanatory prose despite directives."""
    raw = 'Here is the analysis: {"ambiguous": true, "ambiguity_kind": "entity", "clarification_question": "Which X?", "options": ["a","b"]} Done.'
    with patch("app.temporal.activities.conflict_check._get_gemini_key", return_value="fake"), \
         patch("openai.OpenAI", _mock_openai_returning(raw)):
        out = asyncio.run(conflict_check(ConflictCheckInput(query="ambiguous q")))
    assert out.ambiguous is True
    assert out.options == ["a", "b"]
