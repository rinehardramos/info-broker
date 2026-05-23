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
    _compute_forbidden_per_slot,
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

    phase_a = _make_phase("extract", depends_on=[])
    phase_b = _make_phase("gather", depends_on=["extract"])
    phase_c = _make_phase("disconfirm", depends_on=["gather"])
    strategy = _make_strategy([phase_c, phase_b, phase_a])  # deliberately shuffled

    async def fake_tactician(phase, unit_of_work, slot_idx):
        execution_order.append(phase.id)
        return _make_passing_output()

    strategist = _make_strategist(strategy)

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "completed"
    assert execution_order == ["extract", "gather", "disconfirm"]


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

    phase = _make_phase("gather", hypothesis_count_policy="from_dial")
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
        "gather",
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
    assert "gather" in result.terminate_reason


# ---------------------------------------------------------------------------
# test_gate_fail_ask_user_returns_ask_user_status
# Defends: on_fail="ask_user" escalates with a user question, not hard-stop.
# ---------------------------------------------------------------------------


def test_gate_fail_ask_user_returns_ask_user_status():
    """Gate failure with on_fail=ask_user yields RunResult(status='ask_user')."""
    phase = _make_phase(
        "extract",
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
# test_replan_on_fail_with_no_budget_terminates_immediately (P3 replacement)
# Defends: replan/swap_tactic with depth=shallow (0 replans) terminates
#          immediately rather than hanging on the old stub reason code.
# ---------------------------------------------------------------------------


def test_replan_on_fail_with_no_budget_terminates_immediately():
    """on_fail=replan with depth=shallow (0 replans) terminates without replanning."""
    phase = _make_phase(
        "gather",
        on_fail="replan",
        checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],
    )
    strategy = _make_strategy([phase])

    async def fake_tactician(phase, unit_of_work, slot_idx):
        return _make_passing_output(primary_signals_count=0)

    # shallow depth -> 0 replans
    envelope = BudgetEnvelope(hypothesis_count="competing", depth="shallow")
    strategist = Strategist(
        strategy=strategy,
        envelope=envelope,
        run_id="run-test-001",
        user_id="user-test-001",
        hold_id="hold-test-001",
    )

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "terminated"
    assert result.terminate_reason is not None
    assert "replan_required_but_not_implemented" not in result.terminate_reason


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
        phase_id="gather",
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
        phase_id="gather",
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
        phase_id="gather",
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
    phase_a = _make_phase("extract", depends_on=[])
    phase_b = _make_phase("gather", depends_on=["extract"])
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
    assert "extract" in idem_keys[0]
    assert "gather" in idem_keys[1]


def test_strategist_consume_called_on_terminated_phase():
    """wallet.consume() is still called even when the phase gate fails (cost was incurred)."""
    phase = _make_phase(
        "gather",
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
    phase = _make_phase("gather")
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
    gather_phase = _make_phase("gather", depends_on=[], hypothesis_count_policy="from_dial")
    disconfirm_phase = _make_phase(
        "disconfirm", depends_on=["gather"], hypothesis_count_policy="from_prior_phase"
    )
    strategy = _make_strategy([gather_phase, disconfirm_phase])

    call_counts: dict[str, int] = {"gather": 0, "disconfirm": 0}

    async def fake_tactician(phase, unit_of_work, slot_idx):
        call_counts[phase.id] += 1
        # Gather returns 2 distinct candidates
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

    # competing = 3 tacticians for gather; disconfirm should derive from gather's 2 candidates
    strategist = _make_strategist(strategy, hypothesis_count="competing")

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "completed"
    assert call_counts["gather"] == 3      # from_dial (competing=3)
    assert call_counts["disconfirm"] == 2     # from_prior_phase: 2 distinct candidates from gather


def test_completed_run_returns_last_phase_ranked_candidates():
    """RunResult.ranked_candidates is populated from the last phase's output (enriched shape)."""
    phase = _make_phase("synthesize")
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
        phase_id="gather",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.75,
                "evidence_snippet": "Alice confirmed",
                "source_url": "https://example.com/alice",
                "phase_id": "gather",
                "hypothesis_slot": 0,
            },
            {
                "candidate_name": "Bob",
                "source_class": "training_knowledge",
                "confidence": 0.5,
                "evidence_snippet": "Bob maybe",
                "phase_id": "gather",
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
    enriched, _matrix = _enrich_ranked_candidates(raw_ranked, [phase_output], strategy_id="test")

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
        phase_id="gather",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.8,
                "evidence_snippet": "Alice ev 1",
                "phase_id": "gather",
            },
            {
                "candidate_name": "Alice",
                "source_class": "primary_official",
                "confidence": 0.9,
                "evidence_snippet": "Alice ev 2",
                "phase_id": "gather",
            },
            {
                "candidate_name": "Bob",
                "source_class": "live_search",
                "confidence": 0.7,
                "evidence_snippet": "Bob ev 1",
                "phase_id": "gather",
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
    enriched, _matrix = _enrich_ranked_candidates(raw_ranked, [phase_output])

    alice = next(c for c in enriched if c["name"] == "Alice")
    bob = next(c for c in enriched if c["name"] == "Bob")

    assert len(alice["evidence"]) == 2
    assert len(bob["evidence"]) == 1


def test_disconfirm_findings_flagged_in_evidence():
    """Findings from disconfirm phase have is_disconfirm=True in evidence."""
    from app.pipeline.strategist import _enrich_ranked_candidates, PhaseOutput

    gather_output = PhaseOutput(
        phase_id="gather",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.8,
                "evidence_snippet": "Supporting evidence",
                "phase_id": "gather",
            },
        ],
        distinct_candidate_names=["Alice"],
        metadata={},
        ranked_candidates=[],
    )

    disconfirm_output = PhaseOutput(
        phase_id="disconfirm",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.7,
                "evidence_snippet": "Contradicting evidence",
                "phase_id": "disconfirm",
            },
        ],
        distinct_candidate_names=["Alice"],
        metadata={},
        ranked_candidates=[],
    )

    raw_ranked = [{"name": "Alice", "confidence": 0.8}]
    enriched, _matrix = _enrich_ranked_candidates(
        raw_ranked, [gather_output, disconfirm_output]
    )

    alice = enriched[0]
    assert len(alice["evidence"]) == 2

    # Supporting evidence is first (is_disconfirm=False sorts before True)
    assert alice["evidence"][0]["is_disconfirm"] is False
    assert alice["evidence"][0]["snippet"] == "Supporting evidence"

    # Disconfirm evidence is last, flagged as disconfirm
    assert alice["evidence"][1]["is_disconfirm"] is True
    assert alice["evidence"][1]["snippet"] == "Contradicting evidence"


def test_slot_idx_lowest_wins_for_consensus_candidate():
    """When 2 slots both produced the same candidate, slot_idx is the lower one."""
    from app.pipeline.strategist import _enrich_ranked_candidates, PhaseOutput

    # Two slots both found "Alice" but at different slot positions
    phase_output = PhaseOutput(
        phase_id="gather",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.8,
                "evidence_snippet": "Alice slot 2",
                "phase_id": "gather",
                "hypothesis_slot": 2,
            },
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.75,
                "evidence_snippet": "Alice slot 0",
                "phase_id": "gather",
                "hypothesis_slot": 0,
            },
        ],
        distinct_candidate_names=["Alice"],
        metadata={},
        ranked_candidates=[],
    )

    raw_ranked = [{"name": "Alice", "confidence": 0.8}]
    enriched, _matrix = _enrich_ranked_candidates(raw_ranked, [phase_output])

    alice = enriched[0]
    # Lowest slot_idx among findings for Alice is 0
    assert alice["slot_idx"] == 0


# ---------------------------------------------------------------------------
# P4: _compute_forbidden_per_slot tests
# ---------------------------------------------------------------------------


def test_compute_forbidden_per_slot_slot0_empty():
    """Slot 0 always gets an empty forbidden list so H_PRIOR is verified."""
    priors = {
        "rag_hits": ["Zhao Lusi", "Wonyoung"],
        "classifier_top_candidates": [],
    }
    result = _compute_forbidden_per_slot(priors, hypothesis_count_int=3)
    assert result[0] == [], f"Slot 0 must be empty, got {result[0]}"


def test_compute_forbidden_per_slot_slot_n_forbids_top_n():
    """Slot N forbids exactly the top-N priors in order."""
    priors = {
        "rag_hits": ["Zhao Lusi", "Wonyoung", "Karina"],
        "classifier_top_candidates": [],
    }
    result = _compute_forbidden_per_slot(priors, hypothesis_count_int=4)
    assert result[0] == []
    assert result[1] == ["Zhao Lusi"]
    assert result[2] == ["Zhao Lusi", "Wonyoung"]
    assert result[3] == ["Zhao Lusi", "Wonyoung", "Karina"]


def test_compute_forbidden_per_slot_no_priors_returns_empty_lists():
    """When no priors exist, all slots get empty forbidden lists."""
    priors = {"rag_hits": [], "classifier_top_candidates": []}
    result = _compute_forbidden_per_slot(priors, hypothesis_count_int=5)
    assert result == [[] for _ in range(5)]


def test_compute_forbidden_per_slot_caps_at_5_priors():
    """Priors are capped at 5 regardless of how many rag_hits are provided."""
    priors = {
        "rag_hits": ["A", "B", "C", "D", "E", "F", "G"],
        "classifier_top_candidates": [],
    }
    result = _compute_forbidden_per_slot(priors, hypothesis_count_int=8)
    # Slot 7 should forbid at most 5 even though 7 priors were supplied
    assert len(result[7]) <= 5
    # Specifically slot 6+ should all equal the capped 5-item list
    assert result[6] == ["A", "B", "C", "D", "E"]
    assert result[7] == ["A", "B", "C", "D", "E"]


def test_compute_forbidden_per_slot_dedupes_rag_and_classifier_overlap():
    """Overlapping names between rag_hits and classifier_top_candidates are deduped."""
    priors = {
        "rag_hits": ["Zhao Lusi", "Wonyoung"],
        "classifier_top_candidates": ["Wonyoung", "Karina"],  # Wonyoung is a dup
    }
    result = _compute_forbidden_per_slot(priors, hypothesis_count_int=4)
    # Deduped order: Zhao Lusi, Wonyoung, Karina (3 unique)
    assert result[1] == ["Zhao Lusi"]
    assert result[2] == ["Zhao Lusi", "Wonyoung"]
    assert result[3] == ["Zhao Lusi", "Wonyoung", "Karina"]


def test_compute_forbidden_per_slot_below_threshold_all_empty():
    """When hypothesis_count_int < 3 (single/paired), all slots return empty lists."""
    priors = {
        "rag_hits": ["Zhao Lusi", "Wonyoung"],
        "classifier_top_candidates": ["Karina"],
    }
    for count in (1, 2):
        result = _compute_forbidden_per_slot(priors, hypothesis_count_int=count)
        assert all(s == [] for s in result), (
            f"Expected all empty for count={count}, got {result}"
        )


def test_forbidden_per_slot_injected_into_tactician_unit_of_work():
    """Integration: each slot's unit_of_work has the correct forbidden_candidates list."""
    captured_uow: dict[int, list[str]] = {}

    phase = _make_phase("gather", hypothesis_count_policy="from_dial")
    strategy = _make_strategy([phase])

    priors = {
        "rag_hits": ["Zhao Lusi", "Wonyoung"],
        "classifier_top_candidates": [],
    }
    # competing = 3 slots
    classifier_output = {
        "task_type": "celebrity_identification",
        **priors,
    }

    async def fake_tactician(phase, unit_of_work, slot_idx):
        captured_uow[slot_idx] = unit_of_work.get("forbidden_candidates", [])
        return _make_passing_output(candidate_name=f"Candidate {slot_idx}")

    strategist = _make_strategist(strategy, hypothesis_count="competing")

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", classifier_output, fake_tactician))

    assert result.status == "completed"
    # Slot 0 must be empty (H_PRIOR verification)
    assert captured_uow[0] == [], f"Slot 0 forbidden must be empty, got {captured_uow[0]}"
    # Slot 2 must forbid exactly the top-2 priors
    assert captured_uow[2] == ["Zhao Lusi", "Wonyoung"], (
        f"Slot 2 must forbid top-2, got {captured_uow[2]}"
    )


# ---------------------------------------------------------------------------
# P5: ACH matrix tests
# ---------------------------------------------------------------------------


def test_strategist_emits_ach_matrix_in_run_result():
    """RunResult.ach_matrix is populated when the run completes with candidates."""
    phase = _make_phase("synthesize")
    strategy = _make_strategy([phase])

    async def fake_tactician(phase, unit_of_work, slot_idx):
        return {
            "findings": [
                {
                    "candidate_name": "Alice",
                    "source_class": "live_search",
                    "confidence": 0.9,
                    "evidence_snippet": "Alice live evidence",
                    "phase_id": "synthesize",
                }
            ],
            "metadata": {
                "primary_signals_count": 1,
                "actual_ru": 1,
                "hypotheses_explored": 1,
                "disconfirm_count": 0,
                "surviving_hypothesis_count": 1,
            },
            "ranked_candidates": [{"name": "Alice", "confidence": 0.9}],
        }

    strategist = _make_strategist(strategy)

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "completed"
    assert result.ach_matrix is not None, "RunResult.ach_matrix must be set on completed run"
    assert "Alice" in result.ach_matrix.scores, "ACH matrix must include score for Alice"
    assert isinstance(result.ach_matrix.cells, list)
    assert len(result.ach_matrix.cells) > 0


def test_signal_scores_derived_from_ach_matrix():
    """signal_scores values match ACH cells: consistent→match, inconsistent→mismatch."""
    from app.pipeline.strategist import _enrich_ranked_candidates, PhaseOutput

    phase_output = PhaseOutput(
        phase_id="gather",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.8,
                "evidence_snippet": "Live evidence Alice",
                "phase_id": "gather",
                "hypothesis_slot": 0,
            },
        ],
        distinct_candidate_names=["Alice"],
        metadata={},
        ranked_candidates=[],
    )

    disconfirm_output = PhaseOutput(
        phase_id="disconfirm",
        aggregated_findings=[
            {
                "candidate_name": "Bob",
                "source_class": "live_search",
                "confidence": 0.75,
                "evidence_snippet": "Bob disconfirmed",
                "phase_id": "disconfirm",
                "hypothesis_slot": 1,
            },
        ],
        distinct_candidate_names=["Bob"],
        metadata={},
        ranked_candidates=[],
    )

    raw_ranked = [
        {"name": "Alice", "confidence": 0.8},
        {"name": "Bob", "confidence": 0.5},
    ]
    enriched, matrix = _enrich_ranked_candidates(
        raw_ranked, [phase_output, disconfirm_output]
    )

    assert matrix is not None

    alice = next(c for c in enriched if c["name"] == "Alice")
    bob = next(c for c in enriched if c["name"] == "Bob")

    # Alice: live_search + conf 0.8 → primary consistent → signal_scores match
    assert alice["signal_scores"]["primary"] == "match"

    # Bob: findings are all in disconfirm phase → primary inconsistent → mismatch
    # Bob has a disconfirm finding with confidence 0.75 >= 0.5 → inconsistent
    assert bob["signal_scores"]["primary"] == "mismatch"

    # Verify matrix cell marks align
    alice_primary = next(
        c for c in matrix.cells if c.signal_id == "primary" and c.hypothesis_name == "Alice"
    )
    assert alice_primary.mark == "consistent"

    bob_primary = next(
        c for c in matrix.cells if c.signal_id == "primary" and c.hypothesis_name == "Bob"
    )
    assert bob_primary.mark == "inconsistent"


def test_ach_uses_strategy_signal_weights():
    """ACH scores reflect custom strategy signal weights, not hardcoded defaults."""
    from app.pipeline.strategist import _enrich_ranked_candidates, PhaseOutput
    from app.pipeline.ach import ACHSignal

    # Use a single signal with very high weight so we can verify score precisely
    custom_signals = [
        ACHSignal("primary", "Primary", 1.0, 0.0),
    ]

    phase_output = PhaseOutput(
        phase_id="gather",
        aggregated_findings=[
            {
                "candidate_name": "Alice",
                "source_class": "live_search",
                "confidence": 0.85,
                "evidence_snippet": "Alice is consistent",
                "phase_id": "gather",
            }
        ],
        distinct_candidate_names=["Alice"],
        metadata={},
        ranked_candidates=[],
    )

    raw_ranked = [{"name": "Alice", "confidence": 0.85}]
    enriched, matrix = _enrich_ranked_candidates(
        raw_ranked, [phase_output], ach_signals=custom_signals
    )

    assert matrix is not None
    # With weight=1.0 and consistent mark, score should be 1.0
    assert abs(matrix.scores["Alice"] - 1.0) < 0.001, (
        f"Expected score 1.0 with weight=1.0 consistent, got {matrix.scores['Alice']}"
    )
    assert enriched[0]["signal_scores"]["primary"] == "match"


# ---------------------------------------------------------------------------
# P3: Replan / recurse tests (§8.2, DEPTH_TO_REPLAN_BUDGET)
# ---------------------------------------------------------------------------

from app.pipeline.strategist import DEPTH_TO_REPLAN_BUDGET, _get_failing_check_kind


def _make_always_failing_tactician(candidate_name="Candidate X"):
    """Returns a fake tactician that always produces output failing min_primary_signals."""
    async def _fn(phase, unit_of_work, slot_idx):
        # primary_signals_count=0 → gate fails when min=99
        return {
            "findings": [{"candidate_name": candidate_name, "source_class": "web_search",
                          "confidence": 0.5, "evidence_summary": "found"}],
            "metadata": {
                "primary_signals_count": 0,
                "hypotheses_explored": 1,
                "disconfirm_count": 0,
                "surviving_hypothesis_count": 1,
                "actual_ru": 1,
            },
            "ranked_candidates": [],
        }
    return _fn


def _make_strategist_with_depth(strategy, depth):
    envelope = BudgetEnvelope(hypothesis_count="competing", depth=depth)
    return Strategist(
        strategy=strategy,
        envelope=envelope,
        run_id="run-test-p3",
        user_id="user-test-p3",
        hold_id="hold-test-p3",
    )


def test_shallow_depth_zero_replans_terminates_immediately():
    """depth=shallow → 0 replans; gate fail on first attempt terminates immediately."""
    phase = _make_phase(
        "gather",
        on_fail="replan",
        hypothesis_count_policy="fixed:1",
        checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],
    )
    strategy = _make_strategy([phase])
    strategist = _make_strategist_with_depth(strategy, "shallow")

    attempt_count = [0]

    async def fake_tactician(phase, unit_of_work, slot_idx):
        attempt_count[0] += 1
        return {
            "findings": [],
            "metadata": {"primary_signals_count": 0, "hypotheses_explored": 1,
                         "disconfirm_count": 0, "surviving_hypothesis_count": 1, "actual_ru": 1},
            "ranked_candidates": [],
        }

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    # shallow = 0 replans → terminates after 1 attempt with no replan
    assert result.status == "terminated"
    assert attempt_count[0] == 1  # exactly 1 attempt, no replan


def test_search_depth_one_replan_then_terminate():
    """depth=search → 1 replan; gate fails twice → terminates after 2 total attempts."""
    phase = _make_phase(
        "gather",
        on_fail="replan",
        hypothesis_count_policy="fixed:1",
        checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],
    )
    strategy = _make_strategy([phase])
    strategist = _make_strategist_with_depth(strategy, "search")

    attempt_count = [0]

    async def fake_tactician(phase, unit_of_work, slot_idx):
        attempt_count[0] += 1
        return {
            "findings": [],
            "metadata": {"primary_signals_count": 0, "hypotheses_explored": 1,
                         "disconfirm_count": 0, "surviving_hypothesis_count": 1, "actual_ru": 1},
            "ranked_candidates": [],
        }

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    # search=1 → 1 replan allowed → 2 total attempts
    assert result.status == "terminated"
    assert attempt_count[0] == 2


def test_deep_depth_three_replans_then_terminate():
    """depth=deep → 3 replans; gate fails 4 times → terminates after 4 total attempts."""
    phase = _make_phase(
        "gather",
        on_fail="replan",
        hypothesis_count_policy="fixed:1",
        checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],
    )
    strategy = _make_strategy([phase])
    strategist = _make_strategist_with_depth(strategy, "deep")

    attempt_count = [0]

    async def fake_tactician(phase, unit_of_work, slot_idx):
        attempt_count[0] += 1
        return {
            "findings": [],
            "metadata": {"primary_signals_count": 0, "hypotheses_explored": 1,
                         "disconfirm_count": 0, "surviving_hypothesis_count": 1, "actual_ru": 1},
            "ranked_candidates": [],
        }

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    # deep=3 → 3 replans allowed → 4 total attempts
    assert result.status == "terminated"
    assert attempt_count[0] == 4


def test_replan_with_corrective_hint_added_to_unit_of_work():
    """on_fail=replan injects corrective_hint into unit_of_work on second attempt."""
    phase = _make_phase(
        "gather",
        on_fail="replan",
        hypothesis_count_policy="fixed:1",
        checks=[{"kind": "distinct_identity_count", "params": {"min": 3}}],
    )
    strategy = _make_strategy([phase])
    strategist = _make_strategist_with_depth(strategy, "search")

    received_hints: list[str | None] = []

    async def fake_tactician(phase, unit_of_work, slot_idx):
        received_hints.append(unit_of_work.get("corrective_hint"))
        # Always fail: only 1 distinct candidate
        return {
            "findings": [{"candidate_name": "Alice", "source_class": "web_search",
                          "confidence": 0.5}],
            "metadata": {"primary_signals_count": 1, "hypotheses_explored": 1,
                         "disconfirm_count": 0, "surviving_hypothesis_count": 1, "actual_ru": 1},
            "ranked_candidates": [],
        }

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "terminated"
    # First attempt: no hint
    assert received_hints[0] is None
    # Second attempt (replan): hint present and mentions identities
    assert received_hints[1] is not None
    assert "distinct identit" in received_hints[1].lower() or "alternative" in received_hints[1].lower()


def test_swap_tactic_picks_alternative_from_catalog():
    """on_fail=swap_tactic swaps to an alternative tactic from the catalog."""
    phase = _make_phase(
        "gather",
        on_fail="swap_tactic",
        hypothesis_count_policy="fixed:1",
        checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],
    )
    strategy = _make_strategy([phase])
    strategist = _make_strategist_with_depth(strategy, "search")

    tactic_overrides_seen: list[str | None] = []

    async def fake_tactician(phase, unit_of_work, slot_idx):
        tactic_overrides_seen.append(unit_of_work.get("_tactic_override"))
        return {
            "findings": [],
            "metadata": {"primary_signals_count": 0, "hypotheses_explored": 1,
                         "disconfirm_count": 0, "surviving_hypothesis_count": 1, "actual_ru": 1},
            "ranked_candidates": [],
        }

    # Inject a fake tactics catalog with 2 gather-compatible tactics
    from app.pipeline.catalogs.schemas import Tactic, TaskSpec
    fake_tactic_a = Tactic(
        id="fake_tactic_a",
        phase_compatibility=["gather"],
        accepts={},
        produces=[TaskSpec(technique_id="web_search", params_template={}, budget_ru=1)],
        cost_class="cheap",
        required_techniques=["web_search"],
        enforcement={},
    )
    fake_tactic_b = Tactic(
        id="fake_tactic_b",
        phase_compatibility=["gather"],
        accepts={},
        produces=[TaskSpec(technique_id="web_search", params_template={}, budget_ru=1)],
        cost_class="moderate",
        required_techniques=["web_search"],
        enforcement={},
    )
    fake_catalog = {"fake_tactic_a": fake_tactic_a, "fake_tactic_b": fake_tactic_b}

    with (
        patch("app.pipeline.strategist.wallet.consume"),
        patch("app.pipeline.strategist.Strategist._pick_alternative_tactic",
              side_effect=lambda ph, used, cat: fake_tactic_b if fake_tactic_a.id not in used else None),
    ):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    # Should have tried tactic_b on second attempt before terminating
    assert result.status == "terminated"
    assert len(tactic_overrides_seen) == 2
    assert tactic_overrides_seen[0] is None   # first attempt: no override
    assert tactic_overrides_seen[1] == fake_tactic_b.id


def test_swap_tactic_returns_terminated_when_no_alternative():
    """swap_tactic with no alternatives → terminate with no_alt_tactic_available."""
    phase = _make_phase(
        "gather",
        on_fail="swap_tactic",
        hypothesis_count_policy="fixed:1",
        checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],
    )
    strategy = _make_strategy([phase])
    strategist = _make_strategist_with_depth(strategy, "deep")

    async def fake_tactician(phase, unit_of_work, slot_idx):
        return {
            "findings": [],
            "metadata": {"primary_signals_count": 0, "hypotheses_explored": 1,
                         "disconfirm_count": 0, "surviving_hypothesis_count": 1, "actual_ru": 1},
            "ranked_candidates": [],
        }

    with (
        patch("app.pipeline.strategist.wallet.consume"),
        patch("app.pipeline.strategist.Strategist._pick_alternative_tactic", return_value=None),
    ):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "terminated"
    assert result.terminate_reason == "no_alt_tactic_available"


def test_replan_succeeds_when_corrected_attempt_passes_gate():
    """Replan loop exits cleanly when the corrected attempt passes the gate."""
    phase = _make_phase(
        "gather",
        on_fail="replan",
        hypothesis_count_policy="fixed:1",
        checks=[{"kind": "min_primary_signals", "params": {"min": 1}}],
    )
    strategy = _make_strategy([phase])
    strategist = _make_strategist_with_depth(strategy, "search")

    attempt_count = [0]

    async def fake_tactician(phase, unit_of_work, slot_idx):
        attempt_count[0] += 1
        # First attempt fails (0 signals), second attempt passes (1 signal)
        signals = 1 if attempt_count[0] > 1 else 0
        return {
            "findings": [{"candidate_name": "Alice", "source_class": "web_search",
                          "confidence": 0.7}] if signals else [],
            "metadata": {"primary_signals_count": signals, "hypotheses_explored": 1,
                         "disconfirm_count": 0, "surviving_hypothesis_count": 1, "actual_ru": 1},
            "ranked_candidates": [],
        }

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "completed"
    assert attempt_count[0] == 2  # 1 fail + 1 pass


def test_replan_emits_is_phase_replan_event():
    """Replan attempt emits is.phase_replan event with correct fields."""
    phase = _make_phase(
        "gather",
        on_fail="replan",
        hypothesis_count_policy="fixed:1",
        checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],
    )
    strategy = _make_strategy([phase])
    strategist = _make_strategist_with_depth(strategy, "search")

    emitted_events: list[dict] = []

    async def fake_event_emit(payload):
        emitted_events.append(payload)

    async def fake_tactician(phase, unit_of_work, slot_idx):
        return {
            "findings": [],
            "metadata": {"primary_signals_count": 0, "hypotheses_explored": 1,
                         "disconfirm_count": 0, "surviving_hypothesis_count": 1, "actual_ru": 1},
            "ranked_candidates": [],
        }

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute(
            "query", {}, fake_tactician, event_emit=fake_event_emit
        ))

    replan_events = [e for e in emitted_events if e.get("type") == "is.phase_replan"]
    assert len(replan_events) >= 1

    evt = replan_events[0]
    assert evt["type"] == "is.phase_replan"
    assert evt["run_id"] == "run-test-p3"
    assert evt["phase_id"] == "gather"
    assert evt["attempt"] == 1
    assert evt["max_attempts"] == DEPTH_TO_REPLAN_BUDGET["search"]
    assert "reason" in evt
    assert "strategy" in evt


def test_ask_user_escalation_does_not_replan():
    """on_fail=ask_user always returns ask_user immediately — no replan loop entered."""
    phase = _make_phase(
        "extract",
        on_fail="ask_user",
        hypothesis_count_policy="fixed:1",
        checks=[{"kind": "min_primary_signals", "params": {"min": 99}}],
    )
    strategy = _make_strategy([phase])
    # Use deep so replans would be allowed if mistakenly entered
    strategist = _make_strategist_with_depth(strategy, "deep")

    attempt_count = [0]

    async def fake_tactician(phase, unit_of_work, slot_idx):
        attempt_count[0] += 1
        return {
            "findings": [],
            "metadata": {"primary_signals_count": 0, "hypotheses_explored": 1,
                         "disconfirm_count": 0, "surviving_hypothesis_count": 1, "actual_ru": 1},
            "ranked_candidates": [],
        }

    with patch("app.pipeline.strategist.wallet.consume"):
        result = run_sync(strategist.execute("query", {}, fake_tactician))

    assert result.status == "ask_user"
    assert result.user_question is not None
    # Only 1 attempt — ask_user never replans
    assert attempt_count[0] == 1


# ---------------------------------------------------------------------------
# Task 5: _select_tactic honors preferred_tactic_id
# ---------------------------------------------------------------------------


def test_select_tactic_honors_preferred_tactic_id():
    """When phase.preferred_tactic_id is set AND compatible, return it."""
    from app.pipeline.tactician import _select_tactic
    from app.pipeline.catalogs.registries.tactics.gather_default import TACTIC as GATHER_DEFAULT
    from app.pipeline.catalogs.registries.tactics.listings_gather import TACTIC as LISTINGS_GATHER

    class _MockPhase:
        id = "gather"
        preferred_tactic_id = "listings_gather"

    tactics = {"gather_default": GATHER_DEFAULT, "listings_gather": LISTINGS_GATHER}
    selected = _select_tactic(slot_idx=0, unit_of_work={}, tactics_catalog=tactics, phase=_MockPhase())
    assert selected is not None
    assert selected.id == "listings_gather"


def test_select_tactic_ignores_non_compatible_preferred():
    """If preferred_tactic_id is set but NOT compatible, fall back to existing prefs."""
    from app.pipeline.tactician import _select_tactic
    from app.pipeline.catalogs.registries.tactics.gather_default import TACTIC as GATHER_DEFAULT
    from app.pipeline.catalogs.registries.tactics.listings_gather import TACTIC as LISTINGS_GATHER

    class _MockPhase:
        id = "extract"   # preferred_tactic_id points at a gather-only tactic
        preferred_tactic_id = "listings_gather"

    tactics = {"gather_default": GATHER_DEFAULT, "listings_gather": LISTINGS_GATHER}
    selected = _select_tactic(slot_idx=0, unit_of_work={}, tactics_catalog=tactics, phase=_MockPhase())
    # extract has no compatible tactic in this stub catalog → None
    assert selected is None


def test_select_tactic_no_preferred_uses_existing_pref_logic():
    """When phase.preferred_tactic_id is None, existing slot-0 + hypothesis_first_search logic applies."""
    from app.pipeline.tactician import _select_tactic
    from app.pipeline.catalogs.registries.tactics.hypothesis_first_search import TACTIC as HFS
    # Task 8 re-bound hypothesis_first_search's phase_compatibility to gather (was legacy broaden).
    # Use phase id "gather" so the tactic is compatible.
    class _MockPhase:
        id = "gather"
        preferred_tactic_id = None

    tactics = {"hypothesis_first_search": HFS}
    selected = _select_tactic(slot_idx=1, unit_of_work={}, tactics_catalog=tactics, phase=_MockPhase())
    assert selected is not None
    # HFS is a dict; the returned object should be the same dict
    assert (selected.get("id") if isinstance(selected, dict) else selected.id) == "hypothesis_first_search"
