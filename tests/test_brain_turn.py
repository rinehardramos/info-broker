"""Tests for the brain_turn activity — parsing, delta-apply, snapshot behavior.

The subprocess spawn itself is mocked. The path that matters is:
  result_line → parse_delta_from_result → WorkingMemoryDelta.model_validate
  → WorkingMemory.apply → return JSON.
"""
from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock, patch
from uuid import uuid4

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.temporal.activities.brain_turn import (
    BrainTurnInput,
    InitWorkingMemoryInput,
    _parse_delta_from_result,
    init_working_memory,
    run_brain_turn,
)
from app.pipeline.runners.working_memory import WorkingMemory


def _wm_json(**overrides) -> str:
    base = {"run_id": uuid4(), "question": "what is X?"}
    base.update(overrides)
    return WorkingMemory(**base).model_dump_json()


def _claude_result_line(delta: dict) -> str:
    return json.dumps({"type": "result", "result": json.dumps(delta), "is_error": False})


# ── _parse_delta_from_result ──────────────────────────────────────────────────
def test_parse_delta_handles_plain_json_in_result_field():
    line = _claude_result_line({"new_findings": 3, "new_distinct_sources": 1})
    assert _parse_delta_from_result(line) == {"new_findings": 3, "new_distinct_sources": 1}


def test_parse_delta_handles_fenced_json_block():
    inner = json.dumps({"new_findings": 5})
    fenced = "Here is the delta:\n```json\n" + inner + "\n```\nDone."
    line = json.dumps({"type": "result", "result": fenced, "is_error": False})
    assert _parse_delta_from_result(line) == {"new_findings": 5}


def test_parse_delta_handles_prose_around_json():
    blob = 'Sure! The delta is {"new_findings": 2} and that is all.'
    line = json.dumps({"type": "result", "result": blob, "is_error": False})
    assert _parse_delta_from_result(line) == {"new_findings": 2}


def test_parse_delta_returns_empty_on_garbage():
    line = json.dumps({"type": "result", "result": "no json here at all", "is_error": False})
    assert _parse_delta_from_result(line) == {}


# ── init_working_memory ───────────────────────────────────────────────────────
def test_init_working_memory_seeds_a_graded_facts_only():
    past = [
        {
            "grade": "A",
            "findings": [
                {"title": "CEO is Jane Doe", "source_url": "https://example.test/ceo",
                 "source_tool": "web_search", "confidence": 90},
                {"title": "Founded 2018", "source_url": "https://example.test/founded",
                 "source_tool": "web_search", "confidence": 85},
            ],
        },
        {
            "grade": "B",   # NOT A-graded → should be skipped
            "findings": [{"title": "Should not be seeded", "source_url": "x", "confidence": 50}],
        },
    ]
    inp = InitWorkingMemoryInput(
        run_id=str(uuid4()), user_id=str(uuid4()),
        query="who is the CEO of Acme?", past_research=past,
    )
    with patch("app.temporal.activities.brain_turn._snapshot_to_db"):
        wm_json = asyncio.run(init_working_memory(inp))
    wm = WorkingMemory.model_validate_json(wm_json)
    assert len(wm.established_facts) == 2
    assert {f.claim for f in wm.established_facts} == {"CEO is Jane Doe", "Founded 2018"}
    assert all(f.verified_by == "user_grade_A" for f in wm.established_facts)
    assert wm.turn == 0
    assert wm.phase == "explore"


def test_init_working_memory_handles_empty_past_research():
    inp = InitWorkingMemoryInput(
        run_id=str(uuid4()), user_id=str(uuid4()),
        query="cold start", past_research=[],
    )
    with patch("app.temporal.activities.brain_turn._snapshot_to_db"):
        wm_json = asyncio.run(init_working_memory(inp))
    wm = WorkingMemory.model_validate_json(wm_json)
    assert wm.established_facts == []
    assert wm.turn == 0


# ── run_brain_turn (mocked subprocess) ────────────────────────────────────────
def test_run_brain_turn_applies_delta_and_increments_turn():
    wm_in = _wm_json()
    fake_result = _claude_result_line({
        "new_hypotheses": [{"statement": "Acme is in Singapore", "confidence": 0.4}],
        "new_findings_data": [
            {"title": "Acme HQ in Singapore", "source_url": "https://a.com", "source_tool": "web_search"},
            {"title": "Series B 2024", "source_url": "https://b.com", "source_tool": "web_search"},
        ],
    })
    inp = BrainTurnInput(
        run_id=str(uuid4()), user_id=str(uuid4()),
        working_memory_json=wm_in,
    )
    with patch(
        "app.temporal.activities.brain_turn._spawn_brain_turn_subprocess",
        new=AsyncMock(return_value=(fake_result, 3, None)),
    ), patch("app.temporal.activities.brain_turn._snapshot_to_db"):
        out = asyncio.run(run_brain_turn(inp))

    assert out.error is None
    assert out.tool_call_count == 3
    wm_out = WorkingMemory.model_validate_json(out.working_memory_json)
    assert wm_out.turn == 1
    assert len(wm_out.hypotheses) == 1
    assert wm_out.hypotheses[0].statement == "Acme is in Singapore"
    assert wm_out.findings_total == 2
    assert wm_out.distinct_sources == 2


def test_run_brain_turn_treats_bad_delta_as_noop_with_error():
    wm_in = _wm_json()
    bad_result = json.dumps({"type": "result", "result": '{"new_findings": "not-a-number"}'})
    inp = BrainTurnInput(
        run_id=str(uuid4()), user_id=str(uuid4()),
        working_memory_json=wm_in,
    )
    with patch(
        "app.temporal.activities.brain_turn._spawn_brain_turn_subprocess",
        new=AsyncMock(return_value=(bad_result, 0, None)),
    ), patch("app.temporal.activities.brain_turn._snapshot_to_db"):
        out = asyncio.run(run_brain_turn(inp))

    assert out.error is not None
    assert "delta_validation_failed" in out.error
    wm_out = WorkingMemory.model_validate_json(out.working_memory_json)
    assert wm_out.hypotheses == []
    assert wm_out.findings_total == 0


def test_run_brain_turn_surfaces_subprocess_error():
    inp = BrainTurnInput(
        run_id=str(uuid4()), user_id=str(uuid4()),
        working_memory_json=_wm_json(),
    )
    with patch(
        "app.temporal.activities.brain_turn._spawn_brain_turn_subprocess",
        new=AsyncMock(return_value=("", 0, "claude exit 1: not authenticated")),
    ), patch("app.temporal.activities.brain_turn._snapshot_to_db"):
        out = asyncio.run(run_brain_turn(inp))
    assert out.error == "claude exit 1: not authenticated"



def test_init_working_memory_applies_decay_to_old_graded_priors():
    """A user-graded prior observed >shelf_life ago should be decayed before
    auto-seeding it as an established_fact."""
    from datetime import datetime, timezone, timedelta
    from unittest.mock import patch
    from app.memory.models import MemoryResult
    from app.temporal.activities.brain_turn import (
        InitWorkingMemoryInput, init_working_memory,
    )

    old_iso = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    old_prior = MemoryResult(
        ref="r1", title="Old phone number lookup", content="555-1234",
        source="semantic", score=0.7, run_id="prior-run",
        user_score=1, observed_at=old_iso, source_tool="phone_osint",
    )
    async def _fake_fused_retrieve(*a, **kw):
        return [old_prior]

    inp = InitWorkingMemoryInput(
        run_id=str(uuid4()), user_id=str(uuid4()), query="phone for X",
        past_research=[],
    )
    with patch("app.memory.retriever.fused_retrieve", side_effect=_fake_fused_retrieve), \
         patch("app.temporal.activities.brain_turn._snapshot_to_db"):
        wm_json = asyncio.run(init_working_memory(inp))

    wm = WorkingMemory.model_validate_json(wm_json)
    p = wm.cross_run_priors[0]
    assert p["data_type"] == "phone"
    assert p["base_confidence"] == 80
    # 200 days at exponential with 180-day shelf life → significant decay
    assert 0 < p["decayed_confidence"] < 60, p
    assert len(wm.established_facts) == 1
    fact_conf = wm.established_facts[0].confidence
    assert 0 < fact_conf < 0.6
    assert fact_conf == p["decayed_confidence"] / 100.0


def test_decay_zero_skips_seeding_to_avoid_zero_confidence_facts():
    """Fully-decayed (confidence=0) priors should not be seeded as facts."""
    from datetime import datetime, timezone, timedelta
    from unittest.mock import patch
    from app.memory.models import MemoryResult
    from app.temporal.activities.brain_turn import (
        InitWorkingMemoryInput, init_working_memory,
    )

    very_old_iso = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    stale_prior = MemoryResult(
        ref="r1", title="Old social", content="x", source="semantic",
        score=0.7, run_id="r", user_score=1,
        observed_at=very_old_iso, source_tool="facebook_pages",
    )
    async def _fake_fused_retrieve(*a, **kw):
        return [stale_prior]

    inp = InitWorkingMemoryInput(
        run_id=str(uuid4()), user_id=str(uuid4()), query="x",
        past_research=[],
    )
    with patch("app.memory.retriever.fused_retrieve", side_effect=_fake_fused_retrieve), \
         patch("app.temporal.activities.brain_turn._snapshot_to_db"):
        wm_json = asyncio.run(init_working_memory(inp))

    wm = WorkingMemory.model_validate_json(wm_json)
    assert wm.cross_run_priors[0]["decayed_confidence"] == 0
    assert wm.established_facts == []


def test_spawn_uses_phase_gated_allowedtools_arg(monkeypatch):
    """The subprocess command must contain a --allowedTools arg whose value
    is the comma-separated allowlist for the WM's current phase, NOT a
    wildcard."""
    import asyncio as _aio
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.temporal.activities.brain_turn import _spawn_brain_turn_subprocess

    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["argv"] = list(args)
        # Return a fake proc that yields no output cleanly.
        proc = MagicMock()
        proc.returncode = 0
        async def _empty_lines():
            return
            yield  # noqa - make this an async generator
        class _Stdout:
            def __aiter__(self): return _empty_lines()
        proc.stdout = _Stdout()
        proc.stderr = MagicMock()
        proc.stderr.read = AsyncMock(return_value=b"")
        proc.wait = AsyncMock(return_value=0)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec), \
         patch("app.temporal.activities.brain_turn._MCP_CONFIG") as mock_cfg:
        mock_cfg.exists.return_value = True
        mock_cfg.__str__ = MagicMock(return_value="/tmp/fake.json")
        _aio.run(_spawn_brain_turn_subprocess("test prompt", phase="synthesize"))

    argv = captured["argv"]
    assert "--allowedTools" in argv
    allowed = argv[argv.index("--allowedTools") + 1]
    # Synthesize allows only ask_user (no commas → single tool)
    assert allowed.endswith("ask_user")
    assert "," not in allowed
    assert "*" not in allowed   # no wildcard either
