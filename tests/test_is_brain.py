"""Unit tests for IS brain -- Claude Code subprocess orchestrator."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, patch

# Ensure ANTHROPIC_API_KEY is set so the early check doesn't short-circuit
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from app.is_prompt import build_prompt


# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


def test_build_prompt_includes_query():
    result = build_prompt("test query about OpenBao")
    assert "test query about OpenBao" in result


def test_build_prompt_includes_depth():
    result = build_prompt("q", max_depth=5)
    assert "5" in result


def test_build_prompt_includes_past_research():
    past = [{"query": "prior search", "findings": [{"title": "a"}, {"title": "b"}, {"title": "c"}]}]
    result = build_prompt("q", past_research=past)
    assert "prior search" in result
    assert "Findings (3)" in result


# ---------------------------------------------------------------------------
# IS brain subprocess tests (use asyncio.run, no pytest-asyncio needed)
# ---------------------------------------------------------------------------


def _make_mock_process(stdout: str, returncode: int = 0, stderr: str = ""):
    """Create a mock subprocess with async stdout line iteration."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.wait = AsyncMock(return_value=returncode)

    # Mock stdout as async iterator (line-by-line)
    lines = [line.encode() + b"\n" for line in stdout.split("\n") if line.strip()]

    class MockStdout:
        def __init__(self):
            self._lines = iter(lines)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._lines)
            except StopIteration:
                raise StopAsyncIteration

        async def read(self):
            return b""

    proc.stdout = MockStdout()

    # Mock stderr
    stderr_mock = AsyncMock()
    stderr_mock.read = AsyncMock(return_value=stderr.encode())
    proc.stderr = stderr_mock

    return proc


def test_run_research_parses_json_output():
    from app.is_brain import run_research

    inner = json.dumps({
        "summary": "Found info",
        "entity_type": "company",
        "findings": [{"title": "Result 1", "confidence": 90}],
        "tree": {"total_branches": 1, "resolved": 1, "dead_ends": 0,
                 "needs_tool": 0, "max_depth_reached": 1, "branches": [],
                 "can_go_deeper": False, "deeper_leads": []},
        "pipeline": None,
        "suggested_plugins": [],
        "gaps": [],
    })
    envelope = json.dumps({"type": "result", "result": inner})
    mock_proc = _make_mock_process(envelope)

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = asyncio.run(run_research("test query", "user-1"))

    assert result["summary"] == "Found info"
    assert result["entity_type"] == "company"
    assert len(result["findings"]) == 1


def test_run_research_handles_claude_error():
    from app.is_brain import run_research

    mock_proc = _make_mock_process("", returncode=1, stderr="Auth failed")

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = asyncio.run(run_research("test query", "user-1"))

    assert "failed" in result["summary"].lower() or "error" in result["summary"].lower()
    assert result["findings"] == []


def test_run_research_handles_no_result_line():
    from app.is_brain import run_research

    # Non-JSON lines are skipped in stream-json mode — no result line produced
    mock_proc = _make_mock_process("This is not JSON at all")

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = asyncio.run(run_research("test query", "user-1"))

    assert "no result" in result["summary"].lower()
    assert result["entity_type"] == "unknown"
