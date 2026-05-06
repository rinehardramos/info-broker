from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.observability.tracker import McpTracker, _scrub_params


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_start_session_returns_id():
    t = McpTracker()
    with patch("app.observability.tracker.execute") as mock_exec:
        sid = asyncio.run(t.start_session("agent-cli", "osint"))
    assert isinstance(sid, str)
    assert len(sid) == 36  # UUID format
    mock_exec.assert_called_once()
    sql, params = mock_exec.call_args[0]
    assert "INSERT INTO mcp_sessions" in sql
    assert params[0] == sid  # first param is the id


def test_log_tool_call_start():
    t = McpTracker()
    with patch("app.observability.tracker.execute") as mock_exec:
        row_id = asyncio.run(
            t.log_call_start(
                session_id="sess-1",
                tool_name="ddg_search",
                node_type="search",
                call_id="call-1",
                caller_identity="agent-cli",
                input_params={"query": "test"},
            )
        )
    assert isinstance(row_id, str)
    assert len(row_id) == 36
    # Two calls: INSERT into mcp_tool_calls + UPDATE mcp_sessions count
    assert mock_exec.call_count == 2
    first_sql = mock_exec.call_args_list[0][0][0]
    assert "INSERT INTO mcp_tool_calls" in first_sql
    second_sql = mock_exec.call_args_list[1][0][0]
    assert "tool_call_count" in second_sql


def test_log_tool_call_complete():
    t = McpTracker()
    with patch("app.observability.tracker.execute") as mock_exec:
        asyncio.run(
            t.log_call_complete(
                call_id="call-1",
                status="success",
                result_preview="some results",
                result_count=5,
                duration_ms=123,
            )
        )
    mock_exec.assert_called_once()
    sql, params = mock_exec.call_args[0]
    assert "UPDATE mcp_tool_calls" in sql
    assert "call-1" in params


def test_end_session():
    t = McpTracker()
    with patch("app.observability.tracker.execute") as mock_exec:
        asyncio.run(t.end_session("sess-1"))
    mock_exec.assert_called_once()
    sql, params = mock_exec.call_args[0]
    assert "UPDATE mcp_sessions" in sql
    assert "completed" in params
    assert "sess-1" in params


def test_scrub_secrets_from_params():
    params = {
        "query": "hello world",
        "api_key": "super-secret",
        "token": "Bearer abc123",
        "password": "hunter2",
        "secret": "mysecret",
        "auth": "Basic xyz",
        "credential": "cred-value",
        "key": "keyvalue",
        "normal_field": "visible",
        "count": 42,
    }
    result = _scrub_params(params)

    # Secrets must be replaced
    assert result["api_key"] == "***"
    assert result["token"] == "***"
    assert result["password"] == "***"
    assert result["secret"] == "***"
    assert result["auth"] == "***"
    assert result["credential"] == "***"
    assert result["key"] == "***"

    # Normal fields must be preserved
    assert result["query"] == "hello world"
    assert result["normal_field"] == "visible"
    assert result["count"] == 42


def test_scrub_params_none_returns_empty_dict():
    assert _scrub_params(None) == {}
