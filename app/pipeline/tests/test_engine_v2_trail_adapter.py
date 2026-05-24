"""WorkingMemory.to_engine_v2_trail() — verify the IS-loop → v2-UI adapter.

Built to close the v3-broke-v2-UI gap: the Path B brain loop produces a
WorkingMemory whose natural shape doesn't fit the v2-UI's expectations
(PhaseDAGView, CandidateComparison, ACHMatrix). The adapter projects
WM state onto engine_v2's trail shape so /v3/runs/{id}/replay returns
populated phases/cards/candidates.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.pipeline.runners.working_memory import (
    Finding, Hypothesis, WorkingMemory,
)


def _wm_with(*, findings, hypotheses, phase="synthesize", phase_entered_at_turn=3) -> WorkingMemory:
    return WorkingMemory(
        run_id=uuid4(), question="q",
        findings=findings,
        hypotheses=hypotheses,
        phase=phase,
        phase_entered_at_turn=phase_entered_at_turn,
        turn=phase_entered_at_turn,
    )


def test_empty_wm_produces_empty_branches_and_phases():
    wm = _wm_with(findings=[], hypotheses=[], phase="explore", phase_entered_at_turn=0)
    trail, findings = wm.to_engine_v2_trail()
    assert trail["branches"] == []
    assert findings == []
    # Empty WM still emits the current phase entry so the UI shows the run
    # in its starting state rather than as a completely blank DAG.
    assert {p["phase_id"] for p in trail["phases_full"]} == {"explore"}
    assert trail["ranked_candidates"] == []
    assert trail["ach_matrix"] is None


def test_findings_become_branches_with_phase_assignment():
    h = Hypothesis(statement="Stripe was founded by the Collison brothers", status="supported", confidence=0.9)
    f1 = Finding(title="founding", content="2010 by Patrick + John Collison", turn=0, source_class="primary_official", confidence=0.9)
    f2 = Finding(title="company history", content="founded in Palo Alto", turn=2, source_class="news", confidence=0.7)
    h.supporting_finding_ids = [f1.id, f2.id]
    wm = _wm_with(findings=[f1, f2], hypotheses=[h])
    trail, findings = wm.to_engine_v2_trail()

    assert len(trail["branches"]) == 2
    # Each branch carries phase_id, candidate_name (from hypothesis), source fields
    phase_ids = {b["phase_id"] for b in trail["branches"]}
    assert "explore" in phase_ids  # turn-0 finding → explore
    cands = {b["candidate_name"] for b in trail["branches"]}
    assert "Stripe was founded by the Collison brothers" in cands
    # Findings list is parallel — has phase_id + technique_id + evidence_snippet
    assert len(findings) == 2
    assert all("phase_id" in f for f in findings)
    assert all("evidence_snippet" in f for f in findings)


def test_supported_hypotheses_become_ranked_candidates_sorted():
    h_strong = Hypothesis(statement="Strong claim", status="supported", confidence=0.9)
    h_weak   = Hypothesis(statement="Weak claim",   status="supported", confidence=0.4)
    h_refuted = Hypothesis(statement="Refuted",     status="refuted",   confidence=0.1)
    wm = _wm_with(findings=[], hypotheses=[h_weak, h_strong, h_refuted])
    trail, _ = wm.to_engine_v2_trail()

    names = [c["name"] for c in trail["ranked_candidates"]]
    assert names == ["Strong claim", "Weak claim"]  # refuted excluded; sorted desc
    assert trail["ranked_candidates"][0]["score"] == 0.9


def test_phases_full_includes_n_tacticians_and_gate_status():
    f = Finding(title="t", turn=0, confidence=0.5)
    wm = _wm_with(findings=[f], hypotheses=[], phase="synthesize", phase_entered_at_turn=2)
    trail, _ = wm.to_engine_v2_trail(status="succeeded", terminate_reason="synthesized")

    for p in trail["phases_full"]:
        assert p["metadata"]["num_tacticians"] == 1
        assert p["gate_status"] in ("pass", "fail", "ask_user")


def test_terminate_reason_threaded_through():
    wm = _wm_with(findings=[], hypotheses=[])
    trail, _ = wm.to_engine_v2_trail(status="ask_user", terminate_reason="max_turns_exceeded")
    assert trail["status"] == "ask_user"
    assert trail["terminate_reason"] == "max_turns_exceeded"
