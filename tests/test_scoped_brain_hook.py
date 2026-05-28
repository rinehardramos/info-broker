"""TDD tests for the scoped tactician brain LLM cost hook in scoped_brain.py.

Parallel to test_brain_hook.py (Task 7). These tests monkeypatch the sentinel
_emitter in app.observability.usage_emitter_ref (same pattern the IS-brain hook
uses) and verify _emit_brain_usage_if_present fires, or doesn't fire, correctly.

No real Redis / subprocess required — uses AsyncMock.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.observability.usage_emitter_ref as _emitter_ref
import app.pipeline.runners.scoped_brain as sb


# ---------------------------------------------------------------------------
# Test 1: result event with usage + cost → one emit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scoped_brain_emits_llm_call_on_result(monkeypatch):
    """Stream contains a `result` event with usage + cost → one emit."""
    fake_emitter = AsyncMock()
    monkeypatch.setattr(_emitter_ref, "_emitter", fake_emitter)

    events = [
        {"type": "system", "subtype": "init", "apiKeySource": "claude_code"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
        {
            "type": "result",
            "is_error": False,
            "usage": {
                "input_tokens": 120,
                "output_tokens": 80,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
            "total_cost_usd": 0.0042,
            "duration_ms": 1500,
            "num_turns": 3,
            "model": "claude-sonnet-4-6",
        },
    ]

    await sb._emit_brain_usage_if_present(
        events=events,
        run_id="11111111-1111-1111-1111-111111111111",
        node_id="22222222-2222-2222-2222-222222222222",
        phase="tactician.execute",
        actor_user_id="33333333-3333-3333-3333-333333333333",
        actor_org_id="44444444-4444-4444-4444-444444444444",
        caller_identity="claude_code",
    )

    fake_emitter.emit_llm_call.assert_awaited_once()
    kwargs = fake_emitter.emit_llm_call.call_args.kwargs
    assert kwargs["cost_source"] == "subscription"
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["input_tokens"] == 120
    assert kwargs["output_tokens"] == 80
    assert kwargs["total_cost_usd"] == pytest.approx(0.0042)
    assert kwargs["duration_ms"] == 1500


# ---------------------------------------------------------------------------
# Test 2: no result event → no emit, no exception (fail-open)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scoped_brain_no_emit_when_no_result(monkeypatch):
    """No `result` event in the stream → no emit, no exception (fail-open)."""
    fake_emitter = AsyncMock()
    monkeypatch.setattr(_emitter_ref, "_emitter", fake_emitter)

    await sb._emit_brain_usage_if_present(
        events=[{"type": "system", "subtype": "init"}],
        run_id=None,
        node_id=None,
        phase="t",
        actor_user_id=None,
        actor_org_id=None,
        caller_identity=None,
    )
    fake_emitter.emit_llm_call.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 3: emitter not wired (None) → silent no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scoped_brain_no_emit_when_unwired(monkeypatch):
    """Emitter not yet registered (lifespan didn't run) → silent no-op."""
    monkeypatch.setattr(_emitter_ref, "_emitter", None)
    # Must not raise.
    await sb._emit_brain_usage_if_present(
        events=[{"type": "result", "usage": {}, "total_cost_usd": 0.0}],
        run_id=None,
        node_id=None,
        phase=None,
        actor_user_id=None,
        actor_org_id=None,
        caller_identity=None,
    )
