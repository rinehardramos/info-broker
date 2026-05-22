"""Brain-subprocess failure detection.

When the brain (Claude Code subprocess) hits an auth/HTTP/network error,
its event stream still appears "complete" — it emits a synthetic assistant
message, then a result event with is_error=true. The pre-existing
scoped_brain diagnostic just logged "produced 0 task_calls" and the
strategist's broaden gate then fails with "checks did not pass" — the
real cause (a 401, a 429, a timeout) is invisible.

These tests pin a structured failure-detector that surfaces the real
cause so log messages and downstream error reporting can name it.
"""
from __future__ import annotations

from app.pipeline.runners.scoped_brain import detect_brain_failure


# ---------------------------------------------------------------------------
# Auth failure (HTTP 401)
# ---------------------------------------------------------------------------


def _evt_init(api_src: str = "none") -> dict:
    return {"type": "system", "subtype": "init", "apiKeySource": api_src,
            "mcp_servers": [], "model": "claude-sonnet-4-6"}


def _evt_api_retry(attempt: int, status: int) -> dict:
    return {"type": "system", "subtype": "api_retry",
            "attempt": attempt, "max_retries": 10,
            "error_status": status, "error": "authentication_failed"}


def _evt_result_error(status: int, msg: str) -> dict:
    return {"type": "result", "subtype": "success", "is_error": True,
            "api_error_status": status, "duration_ms": 3000, "num_turns": 1,
            "result": msg, "stop_reason": "stop_sequence"}


def test_detects_401_in_result_event():
    events = [
        _evt_init("none"),
        _evt_api_retry(1, 401),
        _evt_api_retry(2, 401),
        _evt_result_error(401, "Failed to authenticate. API Error: 401 Invalid authentication credentials"),
    ]
    f = detect_brain_failure(events)
    assert f.is_fatal is True
    assert f.api_status == 401
    assert f.kind == "auth_failed"
    assert "401" in f.message
    assert f.retry_count == 2
    assert f.api_key_source == "none"


def test_detects_429_rate_limit():
    events = [
        _evt_init("oauth_token"),
        _evt_api_retry(1, 429),
        _evt_result_error(429, "Rate limited"),
    ]
    f = detect_brain_failure(events)
    assert f.is_fatal is True
    assert f.api_status == 429
    assert f.kind == "rate_limited"


def test_detects_500_server_error():
    events = [
        _evt_init("oauth_token"),
        _evt_result_error(500, "Internal server error"),
    ]
    f = detect_brain_failure(events)
    assert f.is_fatal is True
    assert f.api_status == 500
    assert f.kind == "upstream_error"


# ---------------------------------------------------------------------------
# Normal completion — no false positives
# ---------------------------------------------------------------------------


def test_normal_completion_returns_no_failure():
    events = [
        _evt_init("oauth_token"),
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "WebSearch", "input": {"query": "x"}}
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "results..."}
        ]}},
        {"type": "result", "subtype": "success", "is_error": False,
         "duration_ms": 5000, "num_turns": 3,
         "result": "Done", "stop_reason": "end_turn"},
    ]
    f = detect_brain_failure(events)
    assert f.is_fatal is False
    assert f.kind == "ok"
    assert f.api_status is None


def test_normal_completion_with_retries_but_recovered():
    """One retry that succeeds (not is_error in final result) — not fatal."""
    events = [
        _evt_init("oauth_token"),
        {"type": "system", "subtype": "api_retry", "attempt": 1, "error_status": 529},
        {"type": "result", "subtype": "success", "is_error": False, "result": "Done"},
    ]
    f = detect_brain_failure(events)
    assert f.is_fatal is False
    assert f.kind == "ok"
    # We still report retry_count for observability
    assert f.retry_count == 1


# ---------------------------------------------------------------------------
# Empty / malformed event streams shouldn't crash
# ---------------------------------------------------------------------------


def test_empty_events_returns_unknown_kind():
    f = detect_brain_failure([])
    assert f.is_fatal is True  # no result event at all = something broke
    assert f.kind == "no_result_event"


def test_missing_result_event_treated_as_fatal():
    events = [_evt_init("none")]
    f = detect_brain_failure(events)
    assert f.is_fatal is True
    assert f.kind == "no_result_event"
