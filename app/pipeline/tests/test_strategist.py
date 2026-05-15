"""Tests for app/pipeline/strategist.py — MVP-M6.

Test strategy:
  - tactician_fn is always injected (no MCP / LLM calls).
  - wallet ops are mocked via unittest.mock.patch so DB is never touched.
  - Each test targets one structural property of the strategist.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.pipeline.catalogs.budget import BudgetEnvelope
from app.pipeline.catalogs.schemas import GateSpec, CheckSpec, PhaseSpec, Strategy
from app.pipeline.strategist import (
    PhaseOutput,
    RunResult,
    Strategist,
    _GATE_CHECKS,
    _resolve_hypothesis_count,
    _strip_finding,
    _topo_sort,
)

# ---------------------------------------------------------------------------
# Test helpers
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
    gate_checks = [CheckSpec(**c) for c in checks]
    return PhaseSpec(
        id=phase_id,
        depends_on=depends_on or [],
        unit_of_work_contract={"inputs": ["query"]},
        hypothesis_count_policy=hypothesis_count_policy,
        gate=GateSpec(checks=gate_checks, on_fail=on_fail),
    )


def _make_strategy(phases: list[PhaseSpec]) -> Strategy:
    return Strategy(
        id="test_strategy",
        applies_to={"signals": []},
        phases=phases,
        default_mode="investigation",
        budget_minimums={"hypothesis_count": "competing"},
    )


def _make_strategist(
    strategy: Strategy,
    hypothesis_count: str = "competing",
) -> Strategist:
    envelope = BudgetEnvelope(hypothesis_count=hypothesis_count)
    return Strategist(
        strategy=strategy,
        envelope=envelope,
        run_id="run-test-001",
        user_id="user-test-001",
        hold_id="hold-test-001",
    )


def _make_passing_output(
    candidate_name: str = "Candidate A",
    source_class: str = "web_search",
    primary_signals_count: int = 1,
) -> dict:
    """Minimal tactician output dict that passes typical gate checks."""
    return {
        "findings": [
            {
                "candidate_name": candidate_name,
                "source_class": source_class,
                "confidence": 0.7,
                "evidence_summary": "Found via web search",
                "raw_tool_output": "secret raw data",   # must be stripped
            }
        ],
        "metadata": {
            "primary_signals_count": primary_signals_count,
            "hypotheses_explored": 1,
            "disconfirm_count": 1,
            "surviving_hypothesis_count": 1,
            "actual_ru": 2,
        },
        "ranked_candidates": [],
    }


def run_sync(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# test_executes_phases_in_dependency_order
# Defends: strategist respects the DAG — a phase that depends_on another runs
#          only after its dependency has completed.
# ---------------------------------------------------------------------------


def test_executes_phases_in_dependency_order():
    """Phase execution order respects depends_on edges."""
    execution_order: list[str] = []

    phase_a = _make_phase("phase_a", depends_on=[])
    phase_b = _make_phase("phase_b", depends_on=["phase_a"])
    phase_c = _make_phase("phase_c", depends_on=["phase_b"])
    strategy = _make_strategy([phase_c, phase_b, phase_a])  # deliberately shuffled

    async def fake_tactician(phase, unit_of_work, slot_idx):
        execution_order.append(phase.id)
        return _make_passing_output()

    strategist = _make_strategist(strategy)

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "completed"
    assert execution_order == ["phase_a", "phase_b", "phase_c"]


# ---------------------------------------------------------------------------
# test_spawns_n_tacticians_per_hypothesis_count_dial
# Defends: hypothesis_count dial controls fan-out; isolation by count.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dial,expected_calls",
    [
        ("single", 1),
        ("paired", 2),
        ("competing", 3),
        ("adversarial", 5),
        ("swarm", 8),
    ],
)
def test_spawns_n_tacticians_per_hypothesis_count_dial(dial, expected_calls):
    """N parallel tacticians are spawned according to the hypothesis_count dial."""
    call_count = 0

    phase = _make_phase("broaden", hypothesis_count_policy="from_dial")
    strategy = _make_strategy([phase])

    async def fake_tactician(phase, unit_of_work, slot_idx):
        nonlocal call_count
        call_count += 1
        return _make_passing_output(candidate_name=f"Candidate {slot_idx}")

    strategist = _make_strategist(strategy, hypothesis_count=dial)

    with patch("app.pipeline.strategist.wallet.consume"):
        run_sync(strategist.execute("query", {}, fake_tactician))

    assert call_count == expected_calls


# ---------------------------------------------------------------------------
# test_gate_fail_terminate_returns_terminated_status
# Defends: on_fail="terminate" hard-stops the run and sets status.
# ---------------------------------------------------------------------------


def test_gate_fail_terminate_returns_terminated_status():
    """Gate failure with on_fail=terminate yields RunResult(status='terminated')."""
    phase = _make_phase(
        "broaden",
        on_fail="terminate",
        checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],  # impossible
    )
    strategy = _make_strategy([phase])

    async def fake_tactician(phase, unit_of_work, slot_idx):
        return _make_passing_output(primary_signals_count=0)

    strategist = _make_strategist(strategy)

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "terminated"
    assert result.terminate_reason is not None
    assert "broaden" in result.terminate_reason


# ---------------------------------------------------------------------------
# test_gate_fail_ask_user_returns_ask_user_status
# Defends: on_fail="ask_user" escalates with a user question, not hard-stop.
# ---------------------------------------------------------------------------


def test_gate_fail_ask_user_returns_ask_user_status():
    """Gate failure with on_fail=ask_user yields RunResult(status='ask_user')."""
    phase = _make_phase(
        "signal_extraction",
        on_fail="ask_user",
        checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],  # impossible
    )
    strategy = _make_strategy([phase])

    async def fake_tactician(phase, unit_of_work, slot_idx):
        return _make_passing_output(primary_signals_count=0)

    strategist = _make_strategist(strategy)

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "ask_user"
    assert result.user_question is not None
    assert len(result.user_question) > 0


# ---------------------------------------------------------------------------
# test_replan_on_fail_terminates_in_mvp
# Defends: replan/swap_tactic are not implemented in MVP; run terminates with
#          a distinct reason code so callers can detect the gap.
# TODO(P3): remove this test when replan logic is implemented.
# ---------------------------------------------------------------------------


def test_replan_on_fail_terminates_in_mvp():
    """on_fail=replan and on_fail=swap_tactic both terminate with 'replan_required_but_not_implemented'."""
    for on_fail in ("replan", "swap_tactic"):
        phase = _make_phase(
            "broaden",
            on_fail=on_fail,
            checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],
        )
        strategy = _make_strategy([phase])

        async def fake_tactician(phase, unit_of_work, slot_idx):
            return _make_passing_output(primary_signals_count=0)

        strategist = _make_strategist(strategy)

        with patch("app.pipeline.strategist.wallet.consume"):
            result = run_sync(strategist.execute("query", {}, fake_tactician))

        assert result.status == "terminated"
        assert result.terminate_reason == "replan_required_but_not_implemented"


# ---------------------------------------------------------------------------
# test_distinct_identity_count_gate_resolves_dial
# Defends: min_from_dial=True uses the hypothesis_count dial, not a hardcoded N.
# ---------------------------------------------------------------------------


def test_distinct_identity_count_gate_resolves_dial():
    """distinct_identity_count gate resolves min from envelope when min_from_dial=True."""
    from app.pipeline.strategist import (
        _gate_distinct_identity_count,
        PhaseOutput,
    )

    envelope_competing = BudgetEnvelope(hypothesis_count="competing")   # needs 3
    envelope_paired = BudgetEnvelope(hypothesis_count="paired")          # needs 2

    # 2 distinct candidates
    po = PhaseOutput(
        phase_id="broaden",
        aggregated_findings=[],
        distinct_candidate_names=["Alice", "Bob"],
        metadata={},
    )

    params = {"min_from_dial": True}
    assert _gate_distinct_identity_count(po, params, envelope_paired) is True   # 2 >= 2
    assert _gate_distinct_identity_count(po, params, envelope_competing) is False  # 2 < 3


# ---------------------------------------------------------------------------
# test_per_hypothesis_live_source_gate_rejects_all_rag_findings
# Defends: structural #89 fix — findings sourced only from prior_research /
#          training_knowledge fail this gate even with N distinct candidates.
# ---------------------------------------------------------------------------


def test_per_hypothesis_live_source_gate_rejects_all_rag_findings():
    """Structural #89 fix: gate fails when all findings are RAG/training-knowledge sourced."""
    from app.pipeline.strategist import _gate_per_hypothesis_live_source, PhaseOutput

    envelope = BudgetEnvelope(hypothesis_count="competing")
    params = {"min": 1}

    # Three distinct candidates, but ALL findings come from prior_research or training_knowledge
    po = PhaseOutput(
        phase_id="broaden",
        aggregated_findings=[
            {"candidate_name": "Zhao Lusi", "source_class": "prior_research"},
            {"candidate_name": "Wonyoung", "source_class": "training_knowledge"},
            {"candidate_name": "Karina", "source_class": "prior_research"},
        ],
        distinct_candidate_names=["Zhao Lusi", "Wonyoung", "Karina"],
        metadata={},
    )

    assert _gate_per_hypothesis_live_source(po, params, envelope) is False


def test_per_hypothesis_live_source_gate_passes_with_live_sources():
    """Gate passes when every distinct candidate has at least one live-source finding."""
    from app.pipeline.strategist import _gate_per_hypothesis_live_source, PhaseOutput

    envelope = BudgetEnvelope(hypothesis_count="competing")
    params = {"min": 1}

    po = PhaseOutput(
        phase_id="broaden",
        aggregated_findings=[
            {"candidate_name": "Zhao Lusi", "source_class": "web_search"},
            {"candidate_name": "Wonyoung", "source_class": "web_search"},
            {"candidate_name": "Karina", "source_class": "image_search"},
        ],
        distinct_candidate_names=["Zhao Lusi", "Wonyoung", "Karina"],
        metadata={},
    )

    assert _gate_per_hypothesis_live_source(po, params, envelope) is True


# ---------------------------------------------------------------------------
# test_strategist_calls_consume_after_each_phase
# Defends: wallet.consume() is called exactly once per completed phase.
# ---------------------------------------------------------------------------


def test_strategist_calls_consume_after_each_phase():
    """wallet.consume() is called once per phase that completes."""
    phase_a = _make_phase("phase_a", depends_on=[])
    phase_b = _make_phase("phase_b", depends_on=["phase_a"])
    strategy = _make_strategy([phase_a, phase_b])

    async def fake_tactician(phase, unit_of_work, slot_idx):
        return _make_passing_output()

    strategist = _make_strategist(strategy)

    with patch("app.pipeline.strategist.wallet.consume") as mock_consume:
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "completed"
    assert mock_consume.call_count == 2  # one per phase

    # Verify idempotency keys are distinct and contain phase ids
    idem_keys = [c.kwargs["idempotency_key"] for c in mock_consume.call_args_list]
    assert idem_keys[0] != idem_keys[1]
    assert "phase_a" in idem_keys[0]
    assert "phase_b" in idem_keys[1]


def test_strategist_consume_called_on_terminated_phase():
    """wallet.consume() is still called even when the phase gate fails (cost was incurred)."""
    phase = _make_phase(
        "broaden",
        on_fail="terminate",
        checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],
    )
    strategy = _make_strategy([phase])

    async def fake_tactician(phase, unit_of_work, slot_idx):
        return _make_passing_output(primary_signals_count=0)

    strategist = _make_strategist(strategy)

    with patch("app.pipeline.strategist.wallet.consume") as mock_consume:
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "terminated"
    assert mock_consume.call_count == 1


# ---------------------------------------------------------------------------
# test_raw_tool_output_not_in_aggregated_findings
# Defends: visibility invariant — raw_tool_output keys are stripped during
#          aggregation and never appear in PhaseOutput.aggregated_findings.
# ---------------------------------------------------------------------------


def test_raw_tool_output_not_in_aggregated_findings():
    """Strategist strips raw_tool_output (and any non-whitelisted keys) from aggregated findings."""
    phase = _make_phase("broaden")
    strategy = _make_strategy([phase])

    async def fake_tactician(phase, unit_of_work, slot_idx):
        # Returns a finding that includes raw_tool_output — must be stripped
        return {
            "findings": [
                {
                    "candidate_name": "Alice",
                    "source_class": "web_search",
                    "raw_tool_output": "secret internal tool response",
                    "confidence": 0.8,
                    "evidence_summary": "Found in search",
                }
            ],
            "metadata": {
                "primary_signals_count": 1,
                "hypotheses_explored": 1,
                "disconfirm_count": 0,
                "surviving_hypothesis_count": 1,
                "actual_ru": 1,
            },
        }

    strategist = _make_strategist(strategy)

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert len(result.phases) == 1
    phase_out = result.phases[0]
    for finding in phase_out.aggregated_findings:
        assert "raw_tool_output" not in finding, (
            "raw_tool_output must never appear in aggregated_findings"
        )
    # Whitelisted keys should be present
    assert phase_out.aggregated_findings[0]["candidate_name"] == "Alice"
    assert phase_out.aggregated_findings[0]["confidence"] == 0.8


# ---------------------------------------------------------------------------
# Additional structural tests
# ---------------------------------------------------------------------------


def test_strip_finding_removes_non_whitelisted_keys():
    """_strip_finding only passes through keys in _FINDING_WHITELIST."""
    raw = {
        "candidate_name": "Alice",
        "source_class": "web_search",
        "raw_tool_output": "secret",
        "internal_trace": "debug_data",
        "confidence": 0.9,
    }
    stripped = _strip_finding(raw)
    assert "raw_tool_output" not in stripped
    assert "internal_trace" not in stripped
    assert stripped["candidate_name"] == "Alice"
    assert stripped["confidence"] == 0.9


def test_gate_dispatch_map_covers_all_expected_kinds():
    """All five gate check kinds used in media_identification strategy are registered."""
    expected_kinds = {
        "min_primary_signals",
        "distinct_identity_count",
        "per_hypothesis_live_source",
        "disconfirm_logged_per_hypothesis",
        "top_candidate_confidence",
    }
    assert expected_kinds.issubset(set(_GATE_CHECKS.keys()))


def test_from_prior_phase_policy_uses_surviving_candidates():
    """from_prior_phase resolves n_tacticians from distinct_candidate_names of parent phase."""
    broaden_phase = _make_phase("broaden", depends_on=[], hypothesis_count_policy="from_dial")
    red_team_phase = _make_phase(
        "red_team", depends_on=["broaden"], hypothesis_count_policy="from_prior_phase"
    )
    strategy = _make_strategy([broaden_phase, red_team_phase])

    call_counts: dict[str, int] = {"broaden": 0, "red_team": 0}

    async def fake_tactician(phase, unit_of_work, slot_idx):
        call_counts[phase.id] += 1
        # Broaden returns 2 distinct candidates
        return {
            "findings": [
                {"candidate_name": "Alice", "source_class": "web_search"},
                {"candidate_name": "Bob", "source_class": "web_search"},
            ],
            "metadata": {
                "primary_signals_count": 1,
                "hypotheses_explored": 2,
                "disconfirm_count": 2,
                "surviving_hypothesis_count": 2,
                "actual_ru": 1,
            },
        }

    # competing = 3 tacticians for broaden; red_team should derive from broaden's 2 candidates
    strategist = _make_strategist(strategy, hypothesis_count="competing")

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "completed"
    assert call_counts["broaden"] == 3      # from_dial (competing=3)
    assert call_counts["red_team"] == 2     # from_prior_phase: 2 distinct candidates from broaden


def test_completed_run_returns_last_phase_ranked_candidates():
    """RunResult.ranked_candidates is populated from the last phase's output (enriched shape)."""
    phase = _make_phase("rank_verify")
    strategy = _make_strategy([phase])

    async def fake_tactician(phase, unit_of_work, slot_idx):
        return {
            "findings": [
                {"candidate_name": "Alice", "source_class": "web_search", "confidence": 0.8}
            ],
            "metadata": {"primary_signals_count": 1, "actual_ru": 1,
                         "hypotheses_explored": 1, "disconfirm_count": 0,
                         "surviving_hypothesis_count": 1},
            "ranked_candidates": [{"name": "Alice", "confidence": 0.8}],
        }

    strategist = _make_strategist(strategy)

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "completed"
    assert len(result.ranked_candidates) == 1
    enriched = result.ranked_candidates[0]
    # Core identity and confidence preserved
    assert enriched["name"] == "Alice"
    assert enriched["confidence"] == 0.8
    # Enriched fields present with correct types
    assert "signal_scores" in enriched
    assert "evidence" in enriched
    assert isinstance(enriched["evidence"], list)
    assert "slot_idx" in enriched


# ---------------------------------------------------------------------------
# Enrichment tests (UI-P3 backend)
# ---------------------------------------------------------------------------


def test_signal_scores_heuristic_match_and_unknown():
    """signal_scores.primary is 'match' when findings have live source + confidence >= 0.6."""
    from app.pipeline.strategist import _enrich_ranked_candidates, PhaseOutput

    phase_output = PhaseOutput(
        phase_id="broaden",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.75,
                "evidence_snippet": "Alice confirmed",
                "source_url": "https://example.com/alice",
                "phase_id": "broaden",
                "hypothesis_slot": 0,
            },
            {
                "candidate_name": "Bob",
                "source_class": "training_knowledge",
                "confidence": 0.5,
                "evidence_snippet": "Bob maybe",
                "phase_id": "broaden",
                "hypothesis_slot": 1,
            },
        ],
        distinct_candidate_names=["Alice", "Bob"],
        metadata={},
        ranked_candidates=[],
    )

    raw_ranked = [
        {"name": "Alice", "confidence": 0.75},
        {"name": "Bob", "confidence": 0.5},
    ]
    enriched = _enrich_ranked_candidates(raw_ranked, [phase_output], strategy_id="test")

    alice = next(c for c in enriched if c["name"] == "Alice")
    bob = next(c for c in enriched if c["name"] == "Bob")

    # Alice has live_search + confidence >= 0.6 → primary: "match"
    assert alice["signal_scores"]["primary"] == "match"
    # Bob has training_knowledge (not in _PRIMARY_LIVE_CLASSES) → "unknown"
    assert bob["signal_scores"]["primary"] == "unknown"


def test_evidence_collected_from_aggregated_findings():
    """Each candidate's evidence[] count matches findings for that name."""
    from app.pipeline.strategist import _enrich_ranked_candidates, PhaseOutput

    phase_output = PhaseOutput(
        phase_id="broaden",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.8,
                "evidence_snippet": "Alice ev 1",
                "phase_id": "broaden",
            },
            {
                "candidate_name": "Alice",
                "source_class": "primary_official",
                "confidence": 0.9,
                "evidence_snippet": "Alice ev 2",
                "phase_id": "broaden",
            },
            {
                "candidate_name": "Bob",
                "source_class": "live_search",
                "confidence": 0.7,
                "evidence_snippet": "Bob ev 1",
                "phase_id": "broaden",
            },
        ],
        distinct_candidate_names=["Alice", "Bob"],
        metadata={},
        ranked_candidates=[],
    )

    raw_ranked = [
        {"name": "Alice", "confidence": 0.8},
        {"name": "Bob", "confidence": 0.7},
    ]
    enriched = _enrich_ranked_candidates(raw_ranked, [phase_output])

    alice = next(c for c in enriched if c["name"] == "Alice")
    bob = next(c for c in enriched if c["name"] == "Bob")

    assert len(alice["evidence"]) == 2
    assert len(bob["evidence"]) == 1


def test_disconfirm_findings_flagged_in_evidence():
    """Findings from red_team or disconfirm phases have is_disconfirm=True in evidence."""
    from app.pipeline.strategist import _enrich_ranked_candidates, PhaseOutput

    broaden_output = PhaseOutput(
        phase_id="broaden",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.8,
                "evidence_snippet": "Supporting evidence",
                "phase_id": "broaden",
            },
        ],
        distinct_candidate_names=["Alice"],
        metadata={},
        ranked_candidates=[],
    )

    red_team_output = PhaseOutput(
        phase_id="red_team",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.7,
                "evidence_snippet": "Contradicting evidence",
                "phase_id": "red_team",
            },
        ],
        distinct_candidate_names=["Alice"],
        metadata={},
        ranked_candidates=[],
    )

    raw_ranked = [{"name": "Alice", "confidence": 0.8}]
    enriched = _enrich_ranked_candidates(
        raw_ranked, [broaden_output, red_team_output]
    )

    alice = enriched[0]
    assert len(alice["evidence"]) == 2

    # Supporting evidence is first (is_disconfirm=False sorts before True)
    assert alice["evidence"][0]["is_disconfirm"] is False
    assert alice["evidence"][0]["snippet"] == "Supporting evidence"

    # Red-team evidence is last, flagged as disconfirm
    assert alice["evidence"][1]["is_disconfirm"] is True
    assert alice["evidence"][1]["snippet"] == "Contradicting evidence"


def test_slot_idx_lowest_wins_for_consensus_candidate():
    """When 2 slots both produced the same candidate, slot_idx is the lower one."""
    from app.pipeline.strategist import _enrich_ranked_candidates, PhaseOutput

    # Two slots both found "Alice" but at different slot positions
    phase_output = PhaseOutput(
        phase_id="broaden",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.8,
                "evidence_snippet": "Alice slot 2",
                "phase_id": "broaden",
                "hypothesis_slot": 2,
            },
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.75,
                "evidence_snippet": "Alice slot 0",
                "phase_id": "broaden",
                "hypothesis_slot": 0,
            },
        ],
        distinct_candidate_names=["Alice"],
        metadata={},
        ranked_candidates=[],
    )

    raw_ranked = [{"name": "Alice", "confidence": 0.8}]
    enriched = _enrich_ranked_candidates(raw_ranked, [phase_output])

    alice = enriched[0]
    # Lowest slot_idx among findings for Alice is 0
    assert alice["slot_idx"] == 0
