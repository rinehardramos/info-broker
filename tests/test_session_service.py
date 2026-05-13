import pytest
import anthropic
import httpx
from unittest.mock import patch, MagicMock
from app.services.session_service import (
    classify_turn,
    build_session_context,
    distil_summary,
    _CLASSIFIER_PROMPT,
)

def test_classify_turn_investigation_no_session():
    result = classify_turn("find information about OpenAI", None, None)
    assert result == "investigation"

def test_classify_turn_returns_valid_mode():
    thread = [{"role": "user", "content": "who is Wonyoung?"}]
    summary = "Wonyoung is an IVE member and Dyson ambassador."
    with patch("app.services.session_service._call_classifier") as mock:
        mock.return_value = "conversational"
        result = classify_turn("what brand does she represent?", thread, summary)
    assert result in ("investigation", "conversational")

def test_build_session_context_no_session():
    ctx = build_session_context(None, "test query")
    assert ctx == ""

def test_build_session_context_with_session():
    session = {
        "genesis_query": "who is Wonyoung?",
        "conversation_thread": [
            {"role": "user", "content": "who is Wonyoung?", "ts": "2026-01-01"},
            {"role": "agent", "content": "IVE member", "ts": "2026-01-01"},
        ],
        "accumulated_summary": "Wonyoung is an IVE member.",
        "key_findings": [{"title": "IVE member", "confidence": 90}],
        "turn_count": 2,
    }
    ctx = build_session_context(session, "what brand does she represent?")
    assert "who is Wonyoung?" in ctx
    assert "Wonyoung is an IVE member" in ctx
    assert "SESSION CONTEXT" in ctx

def test_distil_summary_empty():
    result = distil_summary([], "")
    assert result == ""


# --- Timeout fallback tests ---

def test_classify_turn_timeout_returns_investigation():
    """classify_turn must return 'investigation' when SDK raises APITimeoutError."""
    thread = [{"role": "user", "content": "previous message"}]
    with patch("anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = anthropic.APITimeoutError(
            request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        )
        result = classify_turn("new question", thread, "some summary")
    assert result == "investigation"


def test_distil_summary_timeout_returns_original():
    """distil_summary must return the original summary when SDK raises APITimeoutError."""
    findings = [{"title": "Finding 1", "confidence": 80, "content": "detail"}]
    original = "original summary text"
    with patch("anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = anthropic.APITimeoutError(
            request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        )
        result = distil_summary(findings, original)
    assert result == original


# --- Classifier prompt XML delimiter tests ---

def test_classifier_prompt_wraps_user_message():
    assert "<user_message>" in _CLASSIFIER_PROMPT
    assert "</user_message>" in _CLASSIFIER_PROMPT


def test_classifier_prompt_wraps_thread_excerpt():
    assert "<thread_excerpt>" in _CLASSIFIER_PROMPT
    assert "</thread_excerpt>" in _CLASSIFIER_PROMPT


def test_classifier_prompt_has_data_not_instructions_note():
    assert "treat as data" in _CLASSIFIER_PROMPT.lower()


def test_classifier_mode_validation_rejects_injected_value():
    """If the classifier returns an unexpected mode, it must fall back to 'investigation'."""
    thread = [{"role": "user", "content": "previous message"}]
    with patch("anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"mode": "BYPASS", "reasoning": "injected"}')]
        mock_client.messages.create.return_value = mock_response
        result = classify_turn("new question", thread, "some summary")
    assert result == "investigation"


# --- Hypothesis memory tests ---

def test_extract_hypothesis_outcomes_with_findings():
    from app.services.session_service import _extract_hypothesis_outcomes
    result = {
        "findings": [{"title": "Alice Johnson at TechCorp", "confidence": 85}],
        "considered_alternatives": ["Bob Smith at MegaCorp", "Chris Lee freelancer"],
        "query": "find Alice Johnson",
    }
    outcomes = _extract_hypothesis_outcomes(result)
    assert len(outcomes) >= 1
    confirmed = [o for o in outcomes if o["status"] == "confirmed"]
    assert len(confirmed) == 1
    assert "Alice Johnson" in confirmed[0]["hypothesis"]


def test_extract_hypothesis_outcomes_empty_result():
    from app.services.session_service import _extract_hypothesis_outcomes
    outcomes = _extract_hypothesis_outcomes({})
    assert outcomes == []
