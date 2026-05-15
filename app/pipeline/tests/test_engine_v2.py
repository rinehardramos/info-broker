"""Integration tests for engine_v2.py -- MVP-M9.

All LLM and MCP boundaries are injected as fakes.  The real
strategist / tactician / specialist code paths execute.

Run:
    cd /path/to/info-broker
    python -m pytest app/pipeline/tests/test_engine_v2.py -v
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.catalogs.budget import BudgetEnvelope
from app.pipeline.catalogs.schemas import (
    GateSpec,
    CheckSpec,
    PhaseSpec,
    Strategy,
    Tactic,
    Technique,
    TaskSpec,
)
from app.pipeline.strategist import RunResult, PhaseOutput
from app.pipeline.specialist import Finding


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_phase(
    phase_id: str,
    depends_on: list[str] | None = None,
    hypothesis_count_policy: str = "fixed:1",
    on_fail: str = "terminate",
    checks: list[dict] | None = None,
) -> PhaseSpec:
    if checks is None:
        checks = [{"kind": "min_primary_signals", "params": {"min": 1}}]
    return PhaseSpec(
        id=phase_id,
        depends_on=depends_on or [],
        unit_of_work_contract={
            "inputs": ["query"],
            "objective": "test objective",
            "briefing": "test briefing",
            "scope_in": "",
            "scope_out": "",
        },
        hypothesis_count_policy=hypothesis_count_policy,
        gate=GateSpec(checks=[CheckSpec(**c) for c in checks], on_fail=on_fail),
    )


def _make_strategy(phases: list[PhaseSpec]) -> Strategy:
    return Strategy(
        id="media_identification",
        applies_to={"signals": []},
        phases=phases,
        default_mode="investigation",
        budget_minimums={"hypothesis_count": "competing"},
    )


def _make_tactic(phase_ids: list[str]) -> Tactic:
    return Tactic(
        id="hypothesis_first_search",
        phase_compatibility=phase_ids,
        accepts={"query": "string"},
        produces=[
            TaskSpec(
                technique_id="web_search",
                params_template={"query": "test"},
                budget_ru=1,
            )
        ],
        cost_class="cheap",
        required_techniques=["web_search"],
        enforcement={"min_distinct_outputs": 1},
    )


def _make_technique() -> Technique:
    return Technique(
        id="web_search",
        tool_name="web_search",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {"results": {"type": "array"}},
            "required": ["results"],
        },
        cost_class="cheap",
        failure_modes=[],
        retry_policy={},
    )


def _make_envelope() -> BudgetEnvelope:
    return BudgetEnvelope(
        capability="general",
        hypothesis_count="competing",
        depth="search",
        speed="normal",
        resource="medium",
    )


# ---------------------------------------------------------------------------
# Shared test runner helper
# ---------------------------------------------------------------------------

FAKE_TACTIC_CANDIDATE = "Candidate A"
FAKE_TACTIC_SOURCE = "web_search_live"


async def _run_engine_v2_with_fakes(
    phases: list[PhaseSpec] | None = None,
    hold_amount_ru: int = 50,
    candidate_name: str = FAKE_TACTIC_CANDIDATE,
    source_class: str = FAKE_TACTIC_SOURCE,
    execute_tactician_override=None,
):
    """Run engine_v2 with all LLM/MCP/DB boundaries mocked.

    Returns:
        (result, emitted_events, mock_consume, mock_release, mock_refund, mock_trail)
    """
    from app.pipeline.tactician import TacticianOutput

    if phases is None:
        phases = [_make_phase("signal_extraction")]

    strategy = _make_strategy(phases)
    tactic = _make_tactic([p.id for p in phases])
    technique = _make_technique()

    strategies_catalog = {strategy.id: strategy}
    tactics_catalog = {tactic.id: tactic}
    techniques_catalog = {technique.id: technique}

    emitted: list[dict] = []

    async def _event_emit(payload: dict) -> None:
        emitted.append(payload)

    async def _default_fake_execute_tactician(
        phase,
        unit_of_work,
        slot_idx,
        tactics_catalog,
        techniques_catalog,
        specialist_fn,
        mcp_invoke_fn,
        capability_tier,
        budget_ru,
        tactic_runner_fn,
    ):
        return TacticianOutput(
            slot_idx=slot_idx,
            candidate_names=[candidate_name],
            findings=[
                {
                    "candidate": candidate_name,
                    "candidate_name": candidate_name,
                    "source_class": source_class,
                    "source_url": "https://example.com/test",
                    "evidence_snippet": "test snippet",
                    "confidence": 0.8,
                }
            ],
            tactic_used=tactic.id,
            specialist_calls=1,
            metadata={"hypotheses_explored": 1, "ru_spent": 2, "budget_ru": budget_ru},
        )

    fake_tactician = execute_tactician_override or _default_fake_execute_tactician

    with (
        patch(
            "app.pipeline.engine_v2._load_all_catalogs",
            return_value=(strategies_catalog, tactics_catalog, techniques_catalog),
        ),
        patch(
            "app.pipeline.engine_v2._classify_query_stub",
            return_value={"task_type": "celebrity_identification"},
        ),
        patch("app.pipeline.engine_v2.execute_tactician", side_effect=fake_tactician),
        patch("app.pipeline.engine_v2.wallet.consume") as mock_consume,
        patch("app.pipeline.engine_v2.wallet.release") as mock_release,
        patch("app.pipeline.engine_v2.wallet.refund") as mock_refund,
        patch("app.pipeline.engine_v2._write_research_trail") as mock_trail,
        patch("app.pipeline.strategist.wallet.consume"),
    ):
        from app.pipeline.engine_v2 import run_engine_v2

        result = await run_engine_v2(
            user_id="test-user",
            run_id="test-run-id",
            hold_id="test-hold-id",
            hold_amount_ru=hold_amount_ru,
            query="asian girl with mole in cheekbone using a curling iron",
            envelope=_make_envelope(),
            strategy_id="media_identification",
            event_emit=_event_emit,
        )

    return result, emitted, mock_consume, mock_release, mock_refund, mock_trail


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_engine_v2_runs_all_phases_in_order():
    """All phases defined in strategy execute in topological order."""
    phases = [
        _make_phase("signal_extraction"),
        _make_phase("broaden", depends_on=["signal_extraction"]),
        _make_phase("disconfirm", depends_on=["broaden"]),
        _make_phase("rank_verify", depends_on=["disconfirm"]),
    ]

    result, emitted, *_ = asyncio.run(_run_engine_v2_with_fakes(phases=phases))

    assert result.status == "completed"
    assert len(result.phases) == 4
    phase_ids = [p.phase_id for p in result.phases]
    assert phase_ids == ["signal_extraction", "broaden", "disconfirm", "rank_verify"]


def test_engine_v2_emits_expected_events():
    """phase_start, tactician_start, tactician_complete, phase_complete, run_complete fire in order.

    Addendum assertions (UI-P2 PhaseProgress):
    - One is.phase_complete fires per phase that ran.
    - Each has gate_status set to a valid value ("pass", "fail", "ask_user").
    - Ordering: each is.phase_complete for phase N fires AFTER all is.tactician_complete
      events for phase N and BEFORE run_complete.
    """
    result, emitted, *_ = asyncio.run(_run_engine_v2_with_fakes())

    event_types = [e["type"] for e in emitted]

    assert "is.phase_start" in event_types
    assert "is.tactician_start" in event_types
    assert "is.tactician_complete" in event_types
    assert "is.phase_complete" in event_types, "is.phase_complete must be emitted"
    assert "is.run_complete" in event_types

    phase_start_idx = next(i for i, t in enumerate(event_types) if t == "is.phase_start")
    tact_start_idx = next(i for i, t in enumerate(event_types) if t == "is.tactician_start")
    tact_complete_idx = next(i for i, t in enumerate(event_types) if t == "is.tactician_complete")
    phase_complete_idx = next(i for i, t in enumerate(event_types) if t == "is.phase_complete")
    run_complete_idx = next(i for i, t in enumerate(event_types) if t == "is.run_complete")

    # Core ordering: phase_start < tactician_start < tactician_complete < phase_complete < run_complete
    assert phase_start_idx < tact_start_idx < tact_complete_idx < phase_complete_idx < run_complete_idx

    # is.phase_complete shape and gate_status validity
    valid_gate_statuses = {"pass", "fail", "ask_user"}
    phase_complete_events = [e for e in emitted if e["type"] == "is.phase_complete"]
    # Single-phase run → exactly one is.phase_complete
    assert len(phase_complete_events) == 1
    pc = phase_complete_events[0]
    assert "run_id" in pc
    assert "phase_id" in pc
    assert "gate_status" in pc
    assert "distinct_candidate_names" in pc
    assert "n_tacticians" in pc
    assert pc["gate_status"] in valid_gate_statuses, (
        f"gate_status {pc['gate_status']!r} not in {valid_gate_statuses}"
    )
    # Passing run → gate_status must be "pass"
    assert pc["gate_status"] == "pass"

    run_complete = next(e for e in emitted if e["type"] == "is.run_complete")
    assert "status" in run_complete
    assert "ru_consumed" in run_complete
    assert "ru_released" in run_complete


def test_engine_v2_releases_unused_hold_on_success():
    """wallet.release is called on success; wallet.refund is NOT called."""
    result, emitted, mock_consume, mock_release, mock_refund, _ = (
        asyncio.run(_run_engine_v2_with_fakes(hold_amount_ru=50))
    )

    assert result.status == "completed"
    mock_release.assert_called_once()
    mock_refund.assert_not_called()

    release_args = mock_release.call_args[0]
    release_kwargs = mock_release.call_args[1]
    remaining_ru = release_args[2]
    idempotency_key = release_kwargs.get("idempotency_key") or (
        release_args[3] if len(release_args) > 3 else ""
    )
    assert remaining_ru >= 0
    assert idempotency_key.endswith(":release")


def test_engine_v2_refunds_on_system_error():
    """wallet.refund is called with the full hold_amount when catalog load raises."""
    hold_amount = 50

    with patch(
        "app.pipeline.engine_v2._load_all_catalogs",
        side_effect=RuntimeError("catalog exploded"),
    ):
        with patch("app.pipeline.engine_v2.wallet.refund") as mock_refund:
            from app.pipeline.engine_v2 import run_engine_v2

            with pytest.raises(RuntimeError, match="catalog exploded"):
                asyncio.run(run_engine_v2(
                    user_id="test-user",
                    run_id="refund-run-id",
                    hold_id="refund-hold-id",
                    hold_amount_ru=hold_amount,
                    query="test",
                    envelope=_make_envelope(),
                    strategy_id="media_identification",
                    event_emit=AsyncMock(),
                ))

            mock_refund.assert_called_once()
            args = mock_refund.call_args[0]
            kwargs = mock_refund.call_args[1]
            assert args[2] == hold_amount
            # idempotency_key passed as kwarg or positional
            idem_key = kwargs.get("idempotency_key") or (args[3] if len(args) > 3 else "")
            assert idem_key.endswith(":refund")


def test_engine_v2_consumes_ru_per_phase():
    """run_complete event includes non-negative ru_consumed reflecting phase spending."""
    phases = [
        _make_phase("signal_extraction"),
        _make_phase("broaden", depends_on=["signal_extraction"]),
    ]

    result, emitted, *_ = asyncio.run(_run_engine_v2_with_fakes(phases=phases))

    assert result.status == "completed"
    run_complete = next(e for e in emitted if e["type"] == "is.run_complete")
    assert run_complete["ru_consumed"] >= 0
    assert run_complete["ru_released"] >= 0


def test_engine_v2_writes_research_trail_with_branches_per_tactician():
    """_write_research_trail receives a RunResult with phase outputs per tactician."""
    result, emitted, _, _, _, mock_trail = asyncio.run(_run_engine_v2_with_fakes())

    assert result.status == "completed"
    mock_trail.assert_called_once()

    call_args = mock_trail.call_args[0]
    run_result: RunResult = call_args[3]
    assert len(run_result.phases) >= 1
    for phase_output in run_result.phases:
        assert hasattr(phase_output, "aggregated_findings")


def test_89_regression_simulation_with_canned_data():
    """Simulated issue-89 regression: 3 distinct candidates + live source per candidate.

    Proves that the strategist's distinct_identity_count and
    per_hypothesis_live_source gates PASS when the brain provides proper
    multi-candidate broaden output -- which was the failure mode in #89.

    This is the SIMULATED regression.  Real #89 end-to-end verification is
    the manual smoke test in docs/intelligence/mvp-m9-smoke-test.md.
    """
    from app.pipeline.tactician import TacticianOutput

    broaden_checks = [
        {"kind": "distinct_identity_count", "params": {"min": 3}},
        {"kind": "per_hypothesis_live_source", "params": {"min": 1}},
    ]
    phases = [
        _make_phase("signal_extraction"),
        _make_phase(
            "broaden",
            depends_on=["signal_extraction"],
            hypothesis_count_policy="fixed:3",
            checks=broaden_checks,
        ),
    ]

    canned_candidates = [
        ("Candidate A", "web_search_live"),
        ("Candidate B", "image_search_live"),
        ("Candidate C", "news_search_live"),
    ]

    slot_counter = [0]

    async def _multi_candidate_tactician(
        phase,
        unit_of_work,
        slot_idx,
        tactics_catalog,
        techniques_catalog,
        specialist_fn,
        mcp_invoke_fn,
        capability_tier,
        budget_ru,
        tactic_runner_fn,
    ):
        if phase.id == "signal_extraction":
            # Signal extraction: return all three candidates so broaden can diverge
            all_findings = [
                {
                    "candidate": cand,
                    "candidate_name": cand,
                    "source_class": src,
                    "source_url": "https://example.com",
                    "evidence_snippet": "test",
                    "confidence": 0.7,
                }
                for cand, src in canned_candidates
            ]
            return TacticianOutput(
                slot_idx=0,
                candidate_names=[c[0] for c in canned_candidates],
                findings=all_findings,
                tactic_used="hypothesis_first_search",
                specialist_calls=3,
                metadata={"hypotheses_explored": 3, "ru_spent": 3, "budget_ru": budget_ru},
            )

        # broaden: each slot_idx maps to a distinct candidate
        idx = slot_counter[0] % len(canned_candidates)
        slot_counter[0] += 1
        cand, src = canned_candidates[idx]
        return TacticianOutput(
            slot_idx=slot_idx,
            candidate_names=[cand],
            findings=[
                {
                    "candidate": cand,
                    "candidate_name": cand,
                    "source_class": src,
                    "source_url": "https://example.com/live",
                    "evidence_snippet": "live evidence",
                    "confidence": 0.8,
                }
            ],
            tactic_used="hypothesis_first_search",
            specialist_calls=1,
            metadata={"hypotheses_explored": 1, "ru_spent": 2, "budget_ru": budget_ru},
        )

    result, emitted, *_ = asyncio.run(_run_engine_v2_with_fakes(
        phases=phases,
        execute_tactician_override=_multi_candidate_tactician,
    ))

    assert result.status == "completed", f"Expected completed, got {result.status}: {result.terminate_reason}"

    # Verify broaden phase output meets the #89 fix criteria
    broaden_output = next(
        (p for p in result.phases if p.phase_id == "broaden"), None
    )
    assert broaden_output is not None

    # Gate 1: distinct_identity_count >= 3 (structural anti-tunnel property)
    assert len(broaden_output.distinct_candidate_names) >= 3, (
        f"Expected >= 3 distinct candidates, got {broaden_output.distinct_candidate_names}"
    )

    # Gate 2: per_hypothesis_live_source -- none of the source_classes are
    # 'prior_research' or 'training_knowledge' (live sources only)
    dead_sources = {"prior_research", "training_knowledge"}
    for finding in broaden_output.aggregated_findings:
        assert finding.get("source_class") not in dead_sources, (
            f"Finding for {finding.get('candidate_name')} has dead source: "
            f"{finding.get('source_class')}"
        )

    # Verify none of the candidates is the known-tunnel candidate from #89
    zhoa_lusi_variants = {"zhao lusi", "zhao-lusi", "zhaolusi"}
    for name in broaden_output.distinct_candidate_names:
        assert name.lower() not in zhoa_lusi_variants, (
            f"#89 tunnel candidate leaked into broaden output: {name}"
        )

    # run_complete event carries ranked_candidates or status
    run_complete = next(e for e in emitted if e["type"] == "is.run_complete")
    assert run_complete["status"] == "completed"


def test_engine_v2_gate_fail_terminates_run():
    """A failing gate causes status=terminated, not an unhandled exception."""
    # Require 1000 primary signals -- impossible with canned single finding
    phases = [
        _make_phase(
            "signal_extraction",
            checks=[{"kind": "min_primary_signals", "params": {"min": 1000}}],
        ),
    ]

    result, emitted, _, _, mock_refund, _ = asyncio.run(_run_engine_v2_with_fakes(phases=phases))

    assert result.status == "terminated"
    assert result.terminate_reason is not None
    # Gate fail is structural, not a system error -- refund must NOT fire
    mock_refund.assert_not_called()


def test_89_regression_run_complete_has_enriched_ranked_candidates():
    """is.run_complete payload includes enriched ranked_candidates with signal_scores,
    evidence[], and slot_idx matching the RankedCandidate frontend type shape.

    Extends test_89_regression_simulation_with_canned_data to assert the UI-P3
    enriched payload shape on the run_complete event.

    The tactician_fn wrapper in engine_v2 always returns ranked_candidates=[] to
    strategist._aggregate; the enrichment is exercised via a custom tactician_fn
    that bypasses the engine_v2 wrapper by patching strategist.execute directly.
    """
    from app.pipeline.strategist import Strategist, RunResult, PhaseOutput
    from app.pipeline.catalogs.budget import BudgetEnvelope
    from app.pipeline.catalogs.schemas import GateSpec, CheckSpec, PhaseSpec, Strategy

    phase = _make_phase(
        "broaden",
        hypothesis_count_policy="fixed:2",
        checks=[{"kind": "min_primary_signals", "params": {"min": 1}}],
    )
    strategy = _make_strategy([phase])
    envelope = _make_envelope()

    canned_findings = [
        {
            "candidate_name": "Candidate A",
            "source_class": "live_search",
            "source_url": "https://example.com/candidate-a",
            "evidence_snippet": "Evidence for Candidate A",
            "confidence": 0.82,
            "phase_id": "broaden",
            "hypothesis_slot": 0,
        },
        {
            "candidate_name": "Candidate B",
            "source_class": "primary_official",
            "source_url": "https://example.com/candidate-b",
            "evidence_snippet": "Evidence for Candidate B",
            "confidence": 0.71,
            "phase_id": "broaden",
            "hypothesis_slot": 1,
        },
    ]

    async def _fake_strategist_execute(query, classifier_output, tactician_fn, phase_complete_cb=None):
        """Return a RunResult as if the strategist ran 2 slots and produced 2 candidates."""
        phase_out = PhaseOutput(
            phase_id="broaden",
            aggregated_findings=canned_findings,
            distinct_candidate_names=["Candidate A", "Candidate B"],
            metadata={"primary_signals_count": 2, "actual_ru": 4, "num_tacticians": 2,
                      "hypotheses_explored": 2, "disconfirm_count": 0,
                      "surviving_hypothesis_count": 2},
            ranked_candidates=[
                {"name": "Candidate A", "confidence": 0.82},
                {"name": "Candidate B", "confidence": 0.71},
            ],
        )
        from app.pipeline.strategist import _enrich_ranked_candidates
        enriched = _enrich_ranked_candidates(
            phase_out.ranked_candidates,
            [phase_out],
            strategy_id="media_identification",
        )
        return RunResult(
            run_id="test-run-id",
            status="completed",
            phases=[phase_out],
            ranked_candidates=enriched,
        )

    emitted: list[dict] = []

    async def _event_emit(payload: dict) -> None:
        emitted.append(payload)

    with (
        patch("app.pipeline.engine_v2._load_all_catalogs", return_value=(
            {"media_identification": strategy},
            {"hypothesis_first_search": _make_tactic([phase.id])},
            {"web_search": _make_technique()},
        )),
        patch("app.pipeline.engine_v2._classify_query_stub",
              return_value={"task_type": "celebrity_identification"}),
        patch.object(Strategist, "execute", side_effect=_fake_strategist_execute),
        patch("app.pipeline.engine_v2.wallet.consume"),
        patch("app.pipeline.engine_v2.wallet.release"),
        patch("app.pipeline.engine_v2.wallet.refund"),
        patch("app.pipeline.engine_v2._write_research_trail"),
        patch("app.pipeline.strategist.wallet.consume"),
    ):
        from unittest.mock import patch as _patch
        from app.pipeline.engine_v2 import run_engine_v2

        result = asyncio.run(run_engine_v2(
            user_id="test-user",
            run_id="test-run-id",
            hold_id="test-hold-id",
            hold_amount_ru=50,
            query="test query",
            envelope=envelope,
            strategy_id="media_identification",
            event_emit=_event_emit,
        ))

    run_complete = next(e for e in emitted if e["type"] == "is.run_complete")
    assert run_complete["status"] == "completed"

    candidates = run_complete["ranked_candidates"]
    assert isinstance(candidates, list)
    assert len(candidates) == 2, (
        f"Expected 2 enriched candidates, got {len(candidates)}: {candidates}"
    )

    for c in candidates:
        assert "name" in c, "RankedCandidate must have 'name'"
        assert "confidence" in c, "RankedCandidate must have 'confidence'"
        assert "signal_scores" in c, "RankedCandidate must have 'signal_scores'"
        assert isinstance(c["signal_scores"], dict), "signal_scores must be a dict"
        assert "evidence" in c, "RankedCandidate must have 'evidence'"
        assert isinstance(c["evidence"], list), "evidence must be a list"
        assert "slot_idx" in c, "RankedCandidate must have 'slot_idx'"
        assert isinstance(c["slot_idx"], int), "slot_idx must be an int"

        # signal_scores values are one of the allowed literals
        valid_scores = {"match", "mismatch", "unknown", None}
        for score_key in ("primary", "supporting", "medium", "recency"):
            val = c["signal_scores"].get(score_key)
            assert val in valid_scores, (
                f"signal_scores.{score_key}={val!r} not in {valid_scores}"
            )

        # evidence entries have required fields
        for ev in c["evidence"]:
            assert "source_class" in ev
            assert "snippet" in ev
            assert "is_disconfirm" in ev
            assert isinstance(ev["is_disconfirm"], bool)

    # Candidate A has live_search + confidence 0.82 >= 0.6 → primary: match
    cand_a = next(c for c in candidates if c["name"] == "Candidate A")
    assert cand_a["signal_scores"]["primary"] == "match"
    assert cand_a["slot_idx"] == 0  # hypothesis_slot was 0

    # Candidate B has primary_official + confidence 0.71 >= 0.6 → primary: match
    cand_b = next(c for c in candidates if c["name"] == "Candidate B")
    assert cand_b["signal_scores"]["primary"] == "match"
    assert cand_b["slot_idx"] == 1  # hypothesis_slot was 1


def test_engine_v2_classifier_output_has_rag_hits_key():
    """P4: classifier_output passed to strategist always has a rag_hits key.

    Even when the RAG retriever is absent (MVP stub mode), the key must be
    present so _compute_forbidden_per_slot can safely read it.
    """
    from app.pipeline.engine_v2 import _classify_query_stub

    # Without a retriever_fn (MVP mode) — rag_hits present and empty
    result = _classify_query_stub("asian girl with mole in cheekbone")
    assert "rag_hits" in result, "classifier_output must have 'rag_hits' key"
    assert isinstance(result["rag_hits"], list)

    # With a fake retriever_fn that returns some names
    def _fake_retriever(query):
        return ["Zhao Lusi", "Wonyoung"]

    result_with_rag = _classify_query_stub(
        "asian girl with mole in cheekbone",
        retriever_fn=_fake_retriever,
    )
    assert result_with_rag["rag_hits"] == ["Zhao Lusi", "Wonyoung"]
    assert "classifier_top_candidates" in result_with_rag
