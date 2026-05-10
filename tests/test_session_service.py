import pytest
from unittest.mock import patch
from app.services.session_service import (
    classify_turn,
    build_session_context,
    distil_summary,
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
