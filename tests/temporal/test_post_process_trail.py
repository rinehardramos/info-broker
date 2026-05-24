"""post_process must persist a research_trails row so /v3/runs/id/replay can
hydrate IS-loop runs. Regression guard: Path B previously marked
pipeline_runs succeeded but skipped the trail write, leaving the UI panel
empty for completed runs.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest


@pytest.mark.asyncio
async def test_post_process_inserts_research_trail():
    from app.temporal.activities.post_process import post_process, PostProcessInput

    brain_result = {
        "query": "founders of SpaceX",
        "entity_type": "company",
        "summary": "Musk founded SpaceX in 2002.",
        "findings": [
            {"title": "founding", "content": "2002", "source_class": "primary_official"},
        ],
        "tree": {"total_branches": 3},
        "pipeline": None,
    }

    captured: list[tuple[str, tuple]] = []

    def fake_execute(sql, params=()):
        captured.append((sql, params))

    fake_fetch_one = MagicMock(return_value={"status": "running"})

    with patch("app.routers.v3.db.execute", side_effect=fake_execute), \
         patch("app.routers.v3.db.fetch_one", fake_fetch_one), \
         patch("app.routers.v3.stream.push_event", AsyncMock(return_value=None)), \
         patch("app.memory.writer.index_research_findings", AsyncMock(return_value=0)):
        await post_process(PostProcessInput(
            run_id="11111111-1111-1111-1111-111111111111",
            user_id="22222222-2222-2222-2222-222222222222",
            session_id=None,
            brain_result=brain_result,
        ))

    inserts = [(s, p) for s, p in captured if "INSERT INTO research_trails" in s]
    assert len(inserts) == 1, f"expected exactly one trail INSERT, captured: {[s[:60] for s,_ in captured]}"

    _, params = inserts[0]
    # id, user_id, run_id, query, entity_type, trail, findings, tool_calls, pipeline
    assert params[1] == "22222222-2222-2222-2222-222222222222"
    assert params[2] == "11111111-1111-1111-1111-111111111111"
    assert params[3] == "founders of SpaceX"
    assert params[4] == "company"
    trail = json.loads(params[5])
    assert trail.get("total_branches") == 3
    findings = json.loads(params[6])
    assert findings[0]["title"] == "founding"
    assert params[7] == 3   # tool_calls = tree.total_branches
    assert params[8] is None  # suggested_pipeline


@pytest.mark.asyncio
async def test_post_process_uses_engine_v2_trail_when_present():
    """When the workflow attaches _engine_v2_trail / _engine_v2_findings, the
    trail JSONB column gets the engine_v2 shape (with branches / phases_full
    / ranked_candidates) so /v3/runs/{id}/replay returns populated data
    for the v3 UI."""
    from app.temporal.activities.post_process import post_process, PostProcessInput

    v2_trail = {
        "branches": [
            {"phase_id": "explore", "slot_idx": 0, "candidate_name": "c1",
             "evidence_snippet": "snip", "source_class": "primary_official",
             "confidence": 0.9, "technique_id": "brain_turn"},
        ],
        "phases_full": [
            {"phase_id": "explore", "status": "passed", "gate_status": "pass",
             "distinct_candidate_names": ["c1"],
             "metadata": {"num_tacticians": 1}, "gate_result": None},
        ],
        "ranked_candidates": [{"name": "c1", "score": 0.9, "evidence": []}],
        "ach_matrix": None,
        "status": "succeeded",
        "terminate_reason": "synthesized",
    }
    v2_findings = [
        {"title": "f", "phase_id": "explore", "hypothesis_slot": 0,
         "technique_id": "brain_turn", "evidence_snippet": "snip"},
    ]

    captured: list[tuple[str, tuple]] = []

    def fake_execute(sql, params=()):
        captured.append((sql, params))

    fake_fetch_one = MagicMock(return_value={"status": "running"})

    with patch("app.routers.v3.db.execute", side_effect=fake_execute), \
         patch("app.routers.v3.db.fetch_one", fake_fetch_one), \
         patch("app.routers.v3.stream.push_event", AsyncMock(return_value=None)), \
         patch("app.memory.writer.index_research_findings", AsyncMock(return_value=0)):
        await post_process(PostProcessInput(
            run_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            user_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            session_id=None,
            brain_result={
                "query": "q", "findings": [],
                "_engine_v2_trail": v2_trail,
                "_engine_v2_findings": v2_findings,
            },
        ))

    inserts = [(s, p) for s, p in captured if "INSERT INTO research_trails" in s]
    assert len(inserts) == 1
    _, params = inserts[0]
    trail_blob = json.loads(params[5])
    findings_blob = json.loads(params[6])
    # The engine_v2 shape should have flowed through, NOT the legacy `tree` shape
    assert "branches" in trail_blob
    assert "phases_full" in trail_blob
    assert trail_blob["ranked_candidates"][0]["name"] == "c1"
    assert findings_blob[0]["phase_id"] == "explore"
    assert params[7] == 1  # tool_calls = len(branches)


@pytest.mark.asyncio
async def test_post_process_idempotent_when_already_succeeded():
    """If pipeline_runs.status is already 'succeeded', skip everything."""
    from app.temporal.activities.post_process import post_process, PostProcessInput

    captured: list[tuple[str, tuple]] = []

    def fake_execute(sql, params=()):
        captured.append((sql, params))

    fake_fetch_one = MagicMock(return_value={"status": "succeeded"})

    with patch("app.routers.v3.db.execute", side_effect=fake_execute), \
         patch("app.routers.v3.db.fetch_one", fake_fetch_one):
        await post_process(PostProcessInput(
            run_id="00000000-0000-0000-0000-000000000000",
            user_id="00000000-0000-0000-0000-000000000000",
            session_id=None,
            brain_result={"query": "x", "findings": []},
        ))

    inserts = [s for s, _ in captured if "INSERT INTO research_trails" in s]
    assert not inserts, "post_process must not write trail when run already succeeded"
