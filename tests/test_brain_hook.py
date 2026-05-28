"""TDD tests for the IS brain result-event capture hook in app/is_brain.py.

These tests hit the real monitoring Redis (port 6380) and assert that when the
IS brain processes a 'result' event it emits a LlmCallEvent to the mon:usage
stream. Tests are fully self-contained and do not spawn a real Claude Code
subprocess.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as aioredis

import app.observability.usage_emitter_ref as _emitter_ref
from platform_monitoring.usage.emitter import UsageEmitter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MONITORING_REDIS_URL = os.getenv("MONITORING_REDIS_URL", "redis://localhost:6380/0")
STREAM = "mon:usage"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result_event(*, total_cost_usd=0.0042, model="claude-opus-4-5", num_turns=3):
    """Return a synthetic Claude Code stream-json 'result' event dict."""
    return {
        "type": "result",
        "model": model,
        "num_turns": num_turns,
        "duration_ms": 12345,
        "is_error": False,
        "total_cost_usd": total_cost_usd,
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_creation_input_tokens": 200,
            "cache_read_input_tokens": 100,
        },
        "result": '{"summary": "test", "findings": [], "tree": {}, "pipeline": null, "suggested_plugins": [], "gaps": [], "topic_clusters": []}',
    }


async def _invoke_brain_with_fake_result(result_event: dict, user_id: str) -> dict:
    """Drive run_research with a fake subprocess that emits a single result event.

    Patches asyncio.create_subprocess_exec to return a mock proc whose stdout
    yields the synthetic result_event JSON line, then EOF.
    """
    from app.is_brain import run_research

    result_json = json.dumps(result_event)

    # Build a fake async iterator for proc.stdout
    class _FakeStdout:
        def __init__(self):
            self._lines = [result_json.encode() + b"\n"]
            self._idx = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._idx >= len(self._lines):
                raise StopAsyncIteration
            val = self._lines[self._idx]
            self._idx += 1
            return val

    fake_proc = MagicMock()
    fake_proc.stdout = _FakeStdout()
    fake_proc.stderr = AsyncMock(return_value=b"")
    fake_proc.returncode = 0
    fake_proc.terminate = MagicMock()
    fake_proc.kill = MagicMock()
    fake_proc.wait = AsyncMock(return_value=0)

    async def _fake_create_subprocess(*args, **kwargs):
        return fake_proc

    with (
        patch("asyncio.create_subprocess_exec", side_effect=_fake_create_subprocess),
        patch("app.is_brain.ensure_claude_credentials"),
        patch("app.is_brain._MCP_CONFIG") as mock_path,
    ):
        mock_path.exists.return_value = False
        result = await run_research(query="test query", user_id=user_id)
    return result


# ---------------------------------------------------------------------------
# Test 1: brain result event emits LlmCallEvent with correct shape
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_brain_result_emit_shape():
    """A synthetic brain result event → emit_llm_call → LlmCallEvent in stream
    with kind=llm_call, cost_source=subscription, pricing_id=None,
    total_cost_usd=0.0042, correct token counts, model, num_turns."""
    r = aioredis.Redis.from_url(MONITORING_REDIS_URL, decode_responses=False)
    emitter = UsageEmitter(r, stream=STREAM)
    prev_emitter = _emitter_ref._emitter
    _emitter_ref._emitter = emitter

    user_id = str(uuid.uuid4())
    result_event = _make_result_event(total_cost_usd=0.0042)
    stream_len_before = await r.xlen(STREAM)

    try:
        await _invoke_brain_with_fake_result(result_event, user_id=user_id)

        # Allow the background task to flush
        await asyncio.sleep(0.15)

        raw = await r.xrange(STREAM, min=b"0-0", count=10000)
        new_entries = raw[stream_len_before:]
        assert new_entries, "Expected at least one new entry in mon:usage stream"

        events = []
        for _entry_id, fields in new_entries:
            data_bytes = fields.get(b"data")
            if data_bytes:
                events.append(json.loads(data_bytes))

        llm_events = [e for e in events if e.get("kind") == "llm_call"]
        assert llm_events, f"No llm_call events found; all events: {events}"

        ev = llm_events[0]
        assert ev["kind"] == "llm_call"
        assert ev["cost_source"] == "subscription"
        assert ev["pricing_id"] is None
        assert ev["total_cost_usd"] == pytest.approx(0.0042, rel=1e-6)
        assert ev["model"] == "claude-opus-4-5"
        assert ev["num_turns"] == 3
        assert ev["input_tokens"] == 1000
        assert ev["output_tokens"] == 500
        assert ev["cache_creation_tokens"] == 200
        assert ev["cache_read_tokens"] == 100
        assert ev["status"] == "ok"
        assert ev["provider"] == "anthropic"
        assert ev["run_id"] is None
        assert ev["actor"]["user_id"] == user_id

    finally:
        _emitter_ref._emitter = prev_emitter
        await r.aclose()


# ---------------------------------------------------------------------------
# Test 2: total_cost_usd=None still emits with cost_source='subscription'
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_brain_result_emit_no_cost():
    """When total_cost_usd is None, cost_source is still 'subscription' and
    total_cost_usd is None in the emitted event."""
    r = aioredis.Redis.from_url(MONITORING_REDIS_URL, decode_responses=False)
    emitter = UsageEmitter(r, stream=STREAM)
    prev_emitter = _emitter_ref._emitter
    _emitter_ref._emitter = emitter

    user_id = str(uuid.uuid4())
    result_event = _make_result_event(total_cost_usd=None)
    stream_len_before = await r.xlen(STREAM)

    try:
        await _invoke_brain_with_fake_result(result_event, user_id=user_id)

        # Allow the background task to flush
        await asyncio.sleep(0.15)

        raw = await r.xrange(STREAM, min=b"0-0", count=10000)
        new_entries = raw[stream_len_before:]
        assert new_entries, "Expected at least one new entry in mon:usage stream"

        events = []
        for _entry_id, fields in new_entries:
            data_bytes = fields.get(b"data")
            if data_bytes:
                events.append(json.loads(data_bytes))

        llm_events = [e for e in events if e.get("kind") == "llm_call"]
        assert llm_events, f"No llm_call events found; all events: {events}"

        ev = llm_events[0]
        assert ev["cost_source"] == "subscription"
        assert ev["total_cost_usd"] is None
        assert ev["pricing_id"] is None

    finally:
        _emitter_ref._emitter = prev_emitter
        await r.aclose()
