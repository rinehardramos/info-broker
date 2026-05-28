"""TDD tests for the step-run capture hook in app/pipeline/workflow.py.

These tests hit the real monitoring Redis (port 6380) and assert that
execute_node emits a StepRunEvent to the mon:usage stream on both the
succeeded and failed paths. A third test confirms the hook is fail-open
when the emitter is backed by a Redis that immediately errors.

The execute_node Temporal activity is invoked directly (not through a
Temporal worker) by mocking its database and WebSocket dependencies.
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


def _make_activity_input(*, raise_exc=None, result=None):
    """Return a fake ActivityInput-like object."""
    from app.pipeline.workflow import ActivityInput, NodeSpec

    node = NodeSpec(
        node_id=str(uuid.uuid4()),
        node_type="fake_step_node",
        label="Fake Step",
        config={},
    )
    return ActivityInput(
        run_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        node=node,
        inputs=[],
    ), raise_exc, result


async def _run_execute_node(inp, raise_exc=None, result=None):
    """Drive execute_node with all side-effectful deps patched away."""
    from app.pipeline.workflow import execute_node

    fake_node = MagicMock()
    fake_node.node_type = "fake_step_node"
    fake_node.display_name = "Fake Step"
    if raise_exc is not None:
        fake_node.execute = AsyncMock(side_effect=raise_exc)
    else:
        fake_node.execute = AsyncMock(return_value=result or [{"item": 1}, {"item": 2}])

    # NodeRegistry and db_execute are imported inside execute_node's function body,
    # so we patch them at their source module locations.
    with (
        patch("app.pipeline.nodes.NodeRegistry.auto_discover"),
        patch("app.pipeline.nodes.NodeRegistry.get", return_value=fake_node),
        patch("app.routers.v3.db.execute"),  # no PG needed
        patch("app.routers.v3.stream.push_event", new_callable=AsyncMock),
    ):
        # execute_node is a Temporal @activity.defn; call the underlying function directly
        return await execute_node(inp)


# ---------------------------------------------------------------------------
# Test 1: succeeded branch emits StepRunEvent
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_step_run_succeeded_emit():
    """After a successful node execution, a StepRunEvent with status='succeeded'
    must appear in the mon:usage Redis stream with correct run_id, item_count,
    and duration_ms >= 0."""
    r = aioredis.Redis.from_url(MONITORING_REDIS_URL, decode_responses=False)
    emitter = UsageEmitter(r, stream=STREAM)
    prev_emitter = _emitter_ref._emitter
    _emitter_ref._emitter = emitter

    inp, _, _ = _make_activity_input(result=[{"a": 1}, {"b": 2}, {"c": 3}])
    stream_len_before = await r.xlen(STREAM)

    try:
        await _run_execute_node(inp, result=[{"a": 1}, {"b": 2}, {"c": 3}])

        # Allow the background task to flush
        await asyncio.sleep(0.1)

        raw = await r.xrange(STREAM, min=b"0-0", count=1000)
        new_entries = raw[stream_len_before:]
        assert new_entries, "Expected at least one new entry in mon:usage stream"

        events = []
        for _entry_id, fields in new_entries:
            data_bytes = fields.get(b"data")
            if data_bytes:
                events.append(json.loads(data_bytes))

        step_events = [e for e in events if e.get("kind") == "step_run"]
        assert step_events, f"No step_run events found; all events: {events}"

        ev = step_events[0]
        assert ev["status"] == "succeeded"
        assert ev["item_count"] == 3
        assert ev["duration_ms"] >= 0
        assert ev["error_kind"] is None
        assert ev["run_id"] == inp.run_id
        assert ev["node_id"] == inp.node.node_id

    finally:
        _emitter_ref._emitter = prev_emitter
        await r.aclose()


# ---------------------------------------------------------------------------
# Test 2: failed branch emits StepRunEvent with error_kind
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_step_run_failed_emit():
    """When a node raises an exception, a StepRunEvent with status='failed'
    and error_kind=<ExceptionClassName> must appear in the stream."""
    r = aioredis.Redis.from_url(MONITORING_REDIS_URL, decode_responses=False)
    emitter = UsageEmitter(r, stream=STREAM)
    prev_emitter = _emitter_ref._emitter
    _emitter_ref._emitter = emitter

    class _SomePipelineError(RuntimeError):
        pass

    inp, _, _ = _make_activity_input()
    stream_len_before = await r.xlen(STREAM)

    try:
        with pytest.raises(_SomePipelineError):
            await _run_execute_node(inp, raise_exc=_SomePipelineError("step boom"))

        # Allow the background task to flush
        await asyncio.sleep(0.1)

        raw = await r.xrange(STREAM, min=b"0-0", count=1000)
        new_entries = raw[stream_len_before:]
        assert new_entries, "Expected at least one new entry in mon:usage stream"

        events = []
        for _entry_id, fields in new_entries:
            data_bytes = fields.get(b"data")
            if data_bytes:
                events.append(json.loads(data_bytes))

        step_events = [e for e in events if e.get("kind") == "step_run"]
        assert step_events, f"No step_run events found; all events: {events}"

        failed_events = [e for e in step_events if e.get("status") == "failed"]
        assert failed_events, f"No failed step_run events; all step events: {step_events}"

        ev = failed_events[0]
        assert ev["error_kind"] == "_SomePipelineError"
        assert ev["duration_ms"] >= 0
        assert ev["item_count"] == 0
        assert ev["run_id"] == inp.run_id

    finally:
        _emitter_ref._emitter = prev_emitter
        await r.aclose()


# ---------------------------------------------------------------------------
# Test 3: fail-open — bad Redis must NOT cause execute_node to raise
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_step_run_fail_open():
    """If the emitter's underlying Redis is broken, the hook must swallow the
    error and execute_node must still return normally (fail-open invariant)."""
    bad_redis = MagicMock()
    bad_redis.xadd = AsyncMock(side_effect=ConnectionError("redis is dead"))

    bad_emitter = UsageEmitter(bad_redis, stream=STREAM)
    prev_emitter = _emitter_ref._emitter
    _emitter_ref._emitter = bad_emitter

    inp, _, _ = _make_activity_input(result=[{"x": 1}])

    try:
        # Should NOT raise even though Redis is broken
        result = await _run_execute_node(inp, result=[{"x": 1}])
        assert isinstance(result, list)
        assert len(result) == 1

    finally:
        _emitter_ref._emitter = prev_emitter
