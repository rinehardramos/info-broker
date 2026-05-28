"""TDD tests for the tool-call capture hook in nodes_api.py.

These tests hit the real monitoring Redis (port 6380) and assert that
nodes_api.execute_node emits a ToolCallEvent to the mon:usage stream on both
the success and failure paths. A third test confirms the hook is fail-open
when the emitter is backed by a Redis that immediately errors.

All three tests use a fake PipelineNode so no Postgres/NodeRegistry access
is needed. Tests are async (pytest.mark.anyio) so the redis client and the
ASGI app share the same event loop.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient

import app.observability.usage_emitter_ref as _emitter_ref
from app.deps import require_api_key
from app.main import app
from platform_monitoring.usage.emitter import UsageEmitter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MONITORING_REDIS_URL = os.getenv("MONITORING_REDIS_URL", "redis://localhost:6380/0")
STREAM = "mon:usage"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_node(result=None, raise_exc=None):
    """Return a mock PipelineNode-like object."""
    node = MagicMock()
    node.node_type = "fake_node"
    node.display_name = "Fake Node"
    node.category = "source"
    node.config_schema = {}
    if raise_exc is not None:
        node.execute = AsyncMock(side_effect=raise_exc)
    else:
        node.execute = AsyncMock(return_value=result or [{"item": 1}, {"item": 2}])
    return node


# Shared patches applied to all three tests to avoid tracker PG calls and
# the stream push_event SSE sink.
_SHARED_PATCHES = [
    "app.routers.v3.nodes_api._get_node",
    "app.observability.tracker.tracker.start_session",
    "app.observability.tracker.tracker.log_call_start",
    "app.observability.tracker.tracker.log_call_complete",
    "app.routers.v3.nodes_api._maybe_emit_missing_key_gate",
    "app.routers.v3.stream.push_event",
]


# ---------------------------------------------------------------------------
# Test 1: success path emits a ToolCallEvent with status="ok"
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_success_path_emits_tool_call_event(monkeypatch):
    """After a successful node execution, a ToolCallEvent with status='ok' must
    appear in the mon:usage Redis stream."""
    # Set API key
    api_key = "test-hook-key"
    monkeypatch.setenv("INFO_BROKER_API_KEY", api_key)
    app.dependency_overrides[require_api_key] = lambda: api_key

    # Real redis client (same event loop as the async test)
    r = aioredis.Redis.from_url(MONITORING_REDIS_URL, decode_responses=False)
    emitter = UsageEmitter(r, stream=STREAM)

    prev_emitter = _emitter_ref._emitter
    _emitter_ref._emitter = emitter

    fake_node = _make_fake_node(result=[{"a": 1}, {"b": 2}, {"c": 3}])
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    # Read stream position before the call
    stream_len_before = await r.xlen(STREAM)

    try:
        with (
            pytest.MonkeyPatch().context() as mp2,
        ):
            # Patch all the side-effectful dependencies
            import unittest.mock as mock
            with (
                mock.patch("app.routers.v3.nodes_api._get_node", return_value=fake_node),
                mock.patch("app.observability.tracker.tracker.start_session", new_callable=AsyncMock),
                mock.patch("app.observability.tracker.tracker.log_call_start", new_callable=AsyncMock),
                mock.patch("app.observability.tracker.tracker.log_call_complete", new_callable=AsyncMock),
                mock.patch("app.routers.v3.nodes_api._maybe_emit_missing_key_gate", new_callable=AsyncMock),
                mock.patch("app.routers.v3.stream.push_event", new_callable=AsyncMock),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    resp = await client.post(
                        "/v3/nodes/fake_node/execute",
                        json={"query": "test"},
                        headers={
                            "X-API-Key": api_key,
                            "X-Caller-User-Id": user_id,
                            "X-Caller-Org-Id": org_id,
                            "X-Caller-Identity": "test-agent",
                        },
                    )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "success"
        assert body["count"] == 3

        # Read new entries since before the call
        raw = await r.xrange(STREAM, min=b"0-0", count=1000)
        new_entries = raw[stream_len_before:]
        assert new_entries, "Expected at least one new entry in mon:usage stream"

        events = []
        for _entry_id, fields in new_entries:
            data_bytes = fields.get(b"data")
            if data_bytes:
                events.append(json.loads(data_bytes))

        tool_events = [e for e in events if e.get("kind") == "tool_call"]
        assert tool_events, f"No tool_call events found; all events: {events}"

        ev = tool_events[0]
        assert ev["status"] == "ok"
        assert ev["node_type"] == "fake_node"
        assert ev["result_count"] == 3
        assert ev["duration_ms"] >= 0
        assert ev["error_kind"] is None

    finally:
        _emitter_ref._emitter = prev_emitter
        app.dependency_overrides.pop(require_api_key, None)
        await r.aclose()


# ---------------------------------------------------------------------------
# Test 2: failure path emits a ToolCallEvent with status="error" + error_kind
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_failure_path_emits_tool_call_event_with_error_kind(monkeypatch):
    """When the node raises an exception, a ToolCallEvent with status='error'
    and error_kind=<ExceptionClassName> must appear in the stream."""
    api_key = "test-hook-key"
    monkeypatch.setenv("INFO_BROKER_API_KEY", api_key)
    app.dependency_overrides[require_api_key] = lambda: api_key

    r = aioredis.Redis.from_url(MONITORING_REDIS_URL, decode_responses=False)
    emitter = UsageEmitter(r, stream=STREAM)
    prev_emitter = _emitter_ref._emitter
    _emitter_ref._emitter = emitter

    class _SomeNodeError(RuntimeError):
        pass

    fake_node = _make_fake_node(raise_exc=_SomeNodeError("boom"))
    user_id = str(uuid.uuid4())

    stream_len_before = await r.xlen(STREAM)

    try:
        import unittest.mock as mock
        with (
            mock.patch("app.routers.v3.nodes_api._get_node", return_value=fake_node),
            mock.patch("app.observability.tracker.tracker.start_session", new_callable=AsyncMock),
            mock.patch("app.observability.tracker.tracker.log_call_start", new_callable=AsyncMock),
            mock.patch("app.observability.tracker.tracker.log_call_complete", new_callable=AsyncMock),
            mock.patch("app.routers.v3.nodes_api._maybe_emit_missing_key_gate", new_callable=AsyncMock),
            mock.patch("app.routers.v3.stream.push_event", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/v3/nodes/fake_node/execute",
                    json={"query": "test"},
                    headers={
                        "X-API-Key": api_key,
                        "X-Caller-User-Id": user_id,
                        "X-Caller-Identity": "test-agent",
                    },
                )

        # The endpoint re-raises as 500 after logging
        assert resp.status_code == 500, f"Expected 500 but got {resp.status_code}"

        raw = await r.xrange(STREAM, min=b"0-0", count=1000)
        new_entries = raw[stream_len_before:]
        assert new_entries, "Expected at least one new entry in mon:usage stream"

        events = []
        for _entry_id, fields in new_entries:
            data_bytes = fields.get(b"data")
            if data_bytes:
                events.append(json.loads(data_bytes))

        tool_events = [e for e in events if e.get("kind") == "tool_call"]
        assert tool_events, f"No tool_call events found; all events: {events}"

        error_events = [e for e in tool_events if e.get("status") == "error"]
        assert error_events, f"No error-status tool_call events found; tool_events: {tool_events}"

        ev = error_events[0]
        assert ev["error_kind"] == "_SomeNodeError"
        assert ev["node_type"] == "fake_node"
        assert ev["duration_ms"] >= 0
        assert ev["result_count"] is None

    finally:
        _emitter_ref._emitter = prev_emitter
        app.dependency_overrides.pop(require_api_key, None)
        await r.aclose()


# ---------------------------------------------------------------------------
# Test 3: fail-open — bad Redis must NOT propagate to the response
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_emit_fail_open_with_bad_redis(monkeypatch):
    """If the emitter's underlying Redis is broken, the hook must swallow the
    error and the endpoint must still return 200 (fail-open invariant)."""
    api_key = "test-hook-key"
    monkeypatch.setenv("INFO_BROKER_API_KEY", api_key)
    app.dependency_overrides[require_api_key] = lambda: api_key

    # Create an emitter backed by a Redis client that always raises on xadd
    bad_redis = MagicMock()
    bad_redis.xadd = AsyncMock(side_effect=ConnectionError("redis is dead"))

    bad_emitter = UsageEmitter(bad_redis, stream=STREAM)
    prev_emitter = _emitter_ref._emitter
    _emitter_ref._emitter = bad_emitter

    fake_node = _make_fake_node(result=[{"x": 1}])

    try:
        import unittest.mock as mock
        with (
            mock.patch("app.routers.v3.nodes_api._get_node", return_value=fake_node),
            mock.patch("app.observability.tracker.tracker.start_session", new_callable=AsyncMock),
            mock.patch("app.observability.tracker.tracker.log_call_start", new_callable=AsyncMock),
            mock.patch("app.observability.tracker.tracker.log_call_complete", new_callable=AsyncMock),
            mock.patch("app.routers.v3.nodes_api._maybe_emit_missing_key_gate", new_callable=AsyncMock),
            mock.patch("app.routers.v3.stream.push_event", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/v3/nodes/fake_node/execute",
                    json={"query": "fail-open-test"},
                    headers={
                        "X-API-Key": api_key,
                        "X-Caller-Identity": "test-agent",
                    },
                )

        # Despite broken Redis, the response must still be success
        assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}: {resp.text}"
        assert resp.json()["status"] == "success"

    finally:
        _emitter_ref._emitter = prev_emitter
        app.dependency_overrides.pop(require_api_key, None)
