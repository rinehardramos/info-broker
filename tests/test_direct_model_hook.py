"""TDD tests for the direct-model capture hook in _call_claude().

These tests wire a real UsageEmitter + PricingResolver into the
module-level sentinel refs in app.observability, stub out the
Anthropic SDK, call _call_claude(), and assert that a LlmCallEvent
was emitted to the monitoring Redis stream with the right fields.

Two scenarios:
  1. Pricing row present  → cost_source='estimated', pricing_id set, total_cost_usd > 0
  2. No pricing row       → cost_source='unknown_model', total_cost_usd=None, pricing_id=None
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import psycopg2
import pytest
import redis.asyncio as aioredis

import app.observability.usage_emitter_ref as _emitter_ref
import app.observability.pricing_ref as _pricing_ref
from app.observability.pricing import PricingResolver
from platform_monitoring.usage.emitter import UsageEmitter

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

MONITORING_REDIS_URL = os.getenv("MONITORING_REDIS_URL", "redis://localhost:6380/0")
STREAM = "mon:usage"

_PG_DSN = (
    f"dbname={os.getenv('POSTGRES_DB', 'info_broker')} "
    f"user={os.getenv('POSTGRES_USER', 'user')} "
    f"password={os.getenv('POSTGRES_PASSWORD', 'password')} "
    f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
    f"port={os.getenv('POSTGRES_PORT', '5432')}"
)


def _pg_conn():
    """Return an autocommit psycopg2 connection."""
    database_url = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(database_url) if database_url else psycopg2.connect(_PG_DSN)
    conn.autocommit = True
    return conn


def _insert_pricing_row(conn, model_id: str, *, pricing_id: str | None = None) -> str:
    pid = pricing_id or str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO llm_pricing "
        "(id, model_id, provider, input_usd_per_1m, output_usd_per_1m) "
        "VALUES (%s, %s, %s, %s, %s)",
        (pid, model_id, "anthropic", "3.0", "15.0"),
    )
    return pid


def _delete_pricing_row(conn, pricing_id: str) -> None:
    conn.cursor().execute("DELETE FROM llm_pricing WHERE id = %s", (pricing_id,))


# ---------------------------------------------------------------------------
# Shared fake Anthropic response builder
# ---------------------------------------------------------------------------

def _make_fake_response(
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
):
    """Build a minimal fake Anthropic Messages response object."""
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )
    block = SimpleNamespace(type="text", text="answer")
    return SimpleNamespace(
        content=[block],
        stop_reason="end_turn",
        usage=usage,
    )


# ---------------------------------------------------------------------------
# Test 1: pricing row present → estimated cost emitted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_direct_model_emit_with_pricing():
    """_call_claude with a known pricing row emits cost_source='estimated'."""
    from app.pipeline.nodes.intelligent_search import _call_claude

    model_id = "claude-test-direct-" + str(uuid.uuid4())[:8]

    # Real Redis for the emitter
    redis_client = aioredis.Redis.from_url(MONITORING_REDIS_URL, decode_responses=False)
    emitter = UsageEmitter(redis_client, stream=STREAM)

    # Real Postgres for the resolver
    conn = _pg_conn()
    pricing_id = _insert_pricing_row(conn, model_id)

    # PricingResolver pointing at real PG
    resolver = PricingResolver(_PG_DSN)

    # Save originals
    prev_emitter = _emitter_ref._emitter
    prev_resolver = _pricing_ref._resolver

    # Wire in real emitter + resolver
    _emitter_ref._emitter = emitter
    _pricing_ref._resolver = resolver

    stream_len_before = await redis_client.xlen(STREAM)

    # Build fake Anthropic response
    fake_response = _make_fake_response(input_tokens=1000, output_tokens=500)

    try:
        # Stub anthropic.Anthropic so no real API call is made
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = await _call_claude(
                model_id,
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )

        # Return shape preserved
        assert result is not None
        assert "content" in result
        assert result["stop_reason"] == "end_turn"

        # Allow background task to flush
        await asyncio.sleep(0.2)

        raw = await redis_client.xrange(STREAM, min=b"0-0", count=100_000)
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
        assert ev["model"] == model_id
        assert ev["provider"] == "anthropic"
        assert ev["cost_source"] == "estimated"
        assert ev["pricing_id"] == pricing_id
        assert ev["total_cost_usd"] is not None
        assert ev["total_cost_usd"] > 0
        assert ev["input_tokens"] == 1000
        assert ev["output_tokens"] == 500
        assert ev["status"] == "ok"

    finally:
        _emitter_ref._emitter = prev_emitter
        _pricing_ref._resolver = prev_resolver
        _delete_pricing_row(conn, pricing_id)
        conn.close()
        await redis_client.aclose()


# ---------------------------------------------------------------------------
# Test 2: no pricing row → unknown_model cost source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_direct_model_emit_unknown_model():
    """_call_claude with no pricing row emits cost_source='unknown_model'."""
    from app.pipeline.nodes.intelligent_search import _call_claude

    model_id = "claude-unknown-" + str(uuid.uuid4())[:8]

    redis_client = aioredis.Redis.from_url(MONITORING_REDIS_URL, decode_responses=False)
    emitter = UsageEmitter(redis_client, stream=STREAM)

    # Resolver backed by real PG but model_id has no row
    resolver = PricingResolver(_PG_DSN)

    prev_emitter = _emitter_ref._emitter
    prev_resolver = _pricing_ref._resolver

    _emitter_ref._emitter = emitter
    _pricing_ref._resolver = resolver

    stream_len_before = await redis_client.xlen(STREAM)

    fake_response = _make_fake_response(input_tokens=200, output_tokens=80)

    try:
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = await _call_claude(
                model_id,
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )

        assert result is not None
        assert "content" in result
        assert result["stop_reason"] == "end_turn"

        await asyncio.sleep(0.2)

        raw = await redis_client.xrange(STREAM, min=b"0-0", count=100_000)
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
        assert ev["model"] == model_id
        assert ev["cost_source"] == "unknown_model"
        assert ev["total_cost_usd"] is None
        assert ev["pricing_id"] is None
        assert ev["status"] == "ok"

    finally:
        _emitter_ref._emitter = prev_emitter
        _pricing_ref._resolver = prev_resolver
        await redis_client.aclose()
