"""Unit tests for WorkingMemory schema, apply() merge logic, and prompt rendering."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.pipeline.runners.working_memory import (
    Fact,
    Finding,
    Hypothesis,
    HypothesisUpdate,
    MAX_OPEN_QUESTIONS,
    OpenQ,
    OpenQUpdate,
    StrategyAttempt,
    WorkingMemory,
    WorkingMemoryDelta,
    compute_next_phase,
    should_terminate,
)


def _wm(**overrides) -> WorkingMemory:
    base = {"run_id": uuid4(), "question": "test question"}
    base.update(overrides)
    return WorkingMemory(**base)


# ── Schema / serialization ────────────────────────────────────────────────────
def test_working_memory_round_trips_through_json():
    wm = _wm(turn=2, phase="test")
    wm = wm.apply(WorkingMemoryDelta(
        new_hypotheses=[Hypothesis(statement="X causes Y", confidence=0.4)],
        new_facts=[Fact(claim="founded in 2018", source_url="https://example.com",
                        verified_by="user_grade_A")],
    ))
    blob = wm.model_dump_json()
    restored = WorkingMemory.model_validate_json(blob)
    assert restored.turn == 2
    assert restored.hypotheses[0].statement == "X causes Y"
    assert restored.established_facts[0].verified_by == "user_grade_A"


def test_confidence_is_clamped_to_unit_interval():
    h = Hypothesis(statement="s", confidence=1.7)
    assert h.confidence == 1.0
    h2 = Hypothesis(statement="s", confidence=-0.3)
    assert h2.confidence == 0.0


# ── apply() merge correctness ─────────────────────────────────────────────────
def test_apply_appends_new_hypotheses_and_dedupes_by_statement():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(
        new_hypotheses=[Hypothesis(statement="Acme is in Singapore")],
    ))
    # Same statement (case-insensitive, whitespace-tolerant) should NOT duplicate.
    wm = wm.apply(WorkingMemoryDelta(
        new_hypotheses=[
            Hypothesis(statement="  ACME IS IN SINGAPORE  "),
            Hypothesis(statement="Acme raised Series B in 2024"),
        ],
    ))
    assert len(wm.hypotheses) == 2
    statements = {h.statement for h in wm.hypotheses}
    assert "Acme is in Singapore" in statements
    assert any("Series B" in s for s in statements)


def test_apply_patches_existing_hypothesis_by_id():
    wm = _wm()
    h = Hypothesis(statement="Acme is profitable", confidence=0.3)
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h]))

    wm = wm.apply(WorkingMemoryDelta(
        hypothesis_updates=[HypothesisUpdate(
            id=h.id, status="refuted", confidence=0.9,
            add_refuting_finding_ids=["f-1", "f-2"],
        )],
    ))
    assert wm.hypotheses[0].status == "refuted"
    assert wm.hypotheses[0].confidence == 0.9
    assert set(wm.hypotheses[0].refuting_finding_ids) == {"f-1", "f-2"}
    # Resolved counter must update.
    assert wm.hypotheses_resolved == 1


def test_apply_ignores_unknown_hypothesis_update_ids():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(
        hypothesis_updates=[HypothesisUpdate(id="does-not-exist", status="supported")],
    ))
    assert wm.hypotheses == []


def test_apply_dedupes_facts_by_claim():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(
        new_facts=[Fact(claim="HQ in Singapore", verified_by="registry")],
    ))
    wm = wm.apply(WorkingMemoryDelta(
        new_facts=[Fact(claim="hq in singapore  ", verified_by="user_grade_A")],
    ))
    assert len(wm.established_facts) == 1


def test_open_questions_cap_is_enforced_by_apply():
    wm = _wm()
    overflow = [OpenQ(question=f"q{i}") for i in range(MAX_OPEN_QUESTIONS + 3)]
    wm = wm.apply(WorkingMemoryDelta(new_open_questions=overflow))
    open_count = sum(1 for q in wm.open_questions if q.status == "open")
    assert open_count == MAX_OPEN_QUESTIONS


def test_open_question_status_updates_apply_to_existing():
    wm = _wm()
    q = OpenQ(question="When was it founded?")
    wm = wm.apply(WorkingMemoryDelta(new_open_questions=[q]))
    wm = wm.apply(WorkingMemoryDelta(
        open_question_updates=[OpenQUpdate(id=q.id, status="confirmed_absent")],
    ))
    assert wm.open_questions[0].status == "confirmed_absent"


def test_strategies_are_append_only_ledger():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_strategies=[
        StrategyAttempt(strategy_id="apollo_search", outcome="failed",
                        failure_reason="no api key", turn=1),
    ]))
    wm = wm.apply(WorkingMemoryDelta(new_strategies=[
        StrategyAttempt(strategy_id="apollo_search", outcome="failed",
                        failure_reason="still no api key", turn=2),
    ]))
    assert len(wm.strategies_attempted) == 2


def test_findings_total_reflects_stored_findings_not_int_hint():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="A", source_url="https://a"),
        Finding(title="B", source_url="https://b"),
    ]))
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="C", source_url="https://c"),
    ]))
    assert wm.findings_total == 3
    assert wm.distinct_sources == 3


def test_findings_dedup_by_source_url_and_title():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="Acme HQ", source_url="https://a.com"),
    ]))
    # Same title + same URL → ignored
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="acme hq", source_url="https://a.com"),
    ]))
    # Same title, different URL → kept (different observation)
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="Acme HQ", source_url="https://b.com"),
    ]))
    assert wm.findings_total == 2


def test_to_legacy_brain_result_shape():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(
        new_findings_data=[Finding(title="X", content="x body",
                                   source_url="https://x", source_tool="web_search",
                                   confidence=0.8)],
        new_hypotheses=[Hypothesis(statement="H1", status="supported", confidence=0.9)],
    ))
    legacy = wm.to_legacy_brain_result()
    assert legacy["findings"][0]["title"] == "X"
    assert legacy["findings"][0]["confidence"] == 80
    assert "H1" in legacy["summary"]
    assert legacy["tree"]["total_branches"] == 1
    assert legacy["_loop_meta"]["facts_count"] == 0


def test_apply_is_pure_does_not_mutate_source():
    wm = _wm()
    h = Hypothesis(statement="initial")
    wm_v1 = wm.apply(WorkingMemoryDelta(new_hypotheses=[h]))
    # Original wm must be untouched.
    assert wm.hypotheses == []
    assert wm_v1.hypotheses[0].statement == "initial"


# ── to_prompt_sections() ──────────────────────────────────────────────────────
def test_prompt_sections_render_all_expected_keys():
    wm = _wm()
    sections = wm.to_prompt_sections()
    assert set(sections.keys()) == {
        "current_phase", "established_facts", "open_hypotheses",
        "open_questions", "strategies_tried", "contradictions",
        "evidence_matrix", "cross_run_priors",
    }


def test_phase_section_includes_phase_specific_instructions():
    wm = _wm(phase="explore")
    explore_section = wm.to_prompt_sections()["current_phase"]
    assert "EXPLORE" in explore_section
    assert "Do NOT synthesize" in explore_section

    wm_test = _wm(phase="test")
    test_section = wm_test.to_prompt_sections()["current_phase"]
    assert "TEST" in test_section
    assert "supported" in test_section.lower()

    wm_syn = _wm(phase="synthesize")
    syn_section = wm_syn.to_prompt_sections()["current_phase"]
    assert "SYNTHESIZE" in syn_section
    assert "synthesis_summary" in syn_section


def test_empty_state_renders_none_markers():
    wm = _wm()
    sections = wm.to_prompt_sections()
    assert "(none yet)" in sections["established_facts"]
    assert "(none)" in sections["open_questions"]
    assert "(none)" in sections["strategies_tried"]


def test_populated_state_renders_facts_and_hypotheses():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(
        new_facts=[Fact(claim="HQ in Singapore", source_url="https://x.com",
                        verified_by="registry")],
        new_hypotheses=[Hypothesis(statement="Acme is profitable", confidence=0.6)],
    ))
    sections = wm.to_prompt_sections()
    assert "HQ in Singapore" in sections["established_facts"]
    assert "registry" in sections["established_facts"]
    assert "Acme is profitable" in sections["open_hypotheses"]
    assert "conf=0.60" in sections["open_hypotheses"]


def test_strategy_ledger_caps_at_last_ten_in_prompt():
    wm = _wm()
    many = [
        StrategyAttempt(strategy_id=f"s{i}", outcome="failed", turn=i)
        for i in range(15)
    ]
    wm = wm.apply(WorkingMemoryDelta(new_strategies=many))
    section = wm.to_prompt_sections()["strategies_tried"]
    # Last 10 are rendered; s0 should NOT appear, s14 should.
    assert "s14" in section
    assert "s0 " not in section  # space disambiguates from s10/s11


# ── Phase machine helpers ─────────────────────────────────────────────────────
def test_compute_next_phase_explore_to_test_at_threshold():
    wm = _wm(phase="explore")
    # 1 hypothesis → still explore
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[Hypothesis(statement="H1")]))
    assert compute_next_phase(wm) == "explore"
    # 2 hypotheses → transition to test
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[Hypothesis(statement="H2")]))
    assert compute_next_phase(wm) == "test"


def test_compute_next_phase_test_to_synthesize_when_all_resolved():
    wm = _wm(phase="test")
    h1 = Hypothesis(statement="H1")
    h2 = Hypothesis(statement="H2")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h1, h2]))
    # Both still open → stay in test
    assert compute_next_phase(wm) == "test"
    # Resolve one → still test
    wm = wm.apply(WorkingMemoryDelta(
        hypothesis_updates=[HypothesisUpdate(id=h1.id, status="supported")],
    ))
    assert compute_next_phase(wm) == "test"
    # Resolve the other → transition to synthesize
    wm = wm.apply(WorkingMemoryDelta(
        hypothesis_updates=[HypothesisUpdate(id=h2.id, status="refuted")],
    ))
    assert compute_next_phase(wm) == "synthesize"


def test_compute_next_phase_synthesize_is_terminal():
    wm = _wm(phase="synthesize")
    assert compute_next_phase(wm) == "synthesize"


def test_should_terminate_on_cancel():
    wm = _wm()
    assert should_terminate(wm, max_turns=8, cancelled=True) == "cancelled_by_user"


def test_should_terminate_on_max_turns():
    wm = _wm(turn=8)
    assert should_terminate(wm, max_turns=8, cancelled=False) == "max_turns_reached"


def test_should_terminate_after_synthesize_turn_runs():
    # Just entered synthesize this turn → not yet terminal
    wm = _wm(phase="synthesize", turn=5, phase_entered_at_turn=5)
    assert should_terminate(wm, max_turns=8, cancelled=False) is None
    # One more turn elapsed → done
    wm = _wm(phase="synthesize", turn=6, phase_entered_at_turn=5)
    assert should_terminate(wm, max_turns=8, cancelled=False) == "synthesized"


def test_should_terminate_returns_none_when_running():
    wm = _wm(phase="test", turn=3)
    assert should_terminate(wm, max_turns=8, cancelled=False) is None


# ── Slice 1.5: target picker + stagnation ─────────────────────────────────────
def test_pick_target_hypothesis_returns_none_when_no_open():
    from app.pipeline.runners.working_memory import pick_target_hypothesis
    wm = _wm()
    assert pick_target_hypothesis(wm) is None


def test_pick_target_picks_highest_confidence_open():
    from app.pipeline.runners.working_memory import pick_target_hypothesis
    wm = _wm()
    h_low  = Hypothesis(statement="A", confidence=0.3)
    h_high = Hypothesis(statement="B", confidence=0.6)
    h_mid  = Hypothesis(statement="C", confidence=0.5)
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h_low, h_high, h_mid]))
    assert pick_target_hypothesis(wm) == h_high.id


def test_pick_target_ignores_resolved_hypotheses():
    from app.pipeline.runners.working_memory import pick_target_hypothesis
    wm = _wm()
    h_done = Hypothesis(statement="X", confidence=0.9, status="supported")
    h_open = Hypothesis(statement="Y", confidence=0.4)
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h_done, h_open]))
    assert pick_target_hypothesis(wm) == h_open.id


def test_is_stagnant_in_test_requires_phase_and_idleness():
    from app.pipeline.runners.working_memory import is_stagnant_in_test
    # Wrong phase → never stagnant
    wm = _wm(phase="explore", turn=5, phase_entered_at_turn=0, last_resolved_at_turn=0)
    assert is_stagnant_in_test(wm) is False
    # In test but only just entered → not stagnant
    wm = _wm(phase="test", turn=1, phase_entered_at_turn=1, last_resolved_at_turn=1)
    assert is_stagnant_in_test(wm) is False
    # Stagnant: 2 test turns without resolution
    wm = _wm(phase="test", turn=3, phase_entered_at_turn=1, last_resolved_at_turn=0)
    assert is_stagnant_in_test(wm) is True


def test_abandon_open_hypotheses_transitions_only_opens():
    from app.pipeline.runners.working_memory import abandon_open_hypotheses
    wm = _wm()
    h_open      = Hypothesis(statement="open", status="open")
    h_supported = Hypothesis(statement="supported", status="supported")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h_open, h_supported]))
    wm2 = abandon_open_hypotheses(wm, reason="testing")
    status_by_stmt = {h.statement: h.status for h in wm2.hypotheses}
    assert status_by_stmt["open"] == "abandoned"
    assert status_by_stmt["supported"] == "supported"
    # hypotheses_resolved should now count both (abandoned counts)
    assert wm2.hypotheses_resolved == 2


def test_apply_clears_target_when_target_resolves():
    wm = _wm()
    h = Hypothesis(statement="target", confidence=0.5)
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h]))
    wm = wm.model_copy(update={"current_target_hypothesis_id": h.id})
    assert wm.current_target_hypothesis_id == h.id
    # Resolve it
    wm2 = wm.apply(WorkingMemoryDelta(
        hypothesis_updates=[HypothesisUpdate(id=h.id, status="supported")],
    ))
    assert wm2.current_target_hypothesis_id is None


def test_apply_bumps_last_resolved_at_turn_on_progress():
    wm = _wm(turn=3)
    h = Hypothesis(statement="X")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h]))
    assert wm.last_resolved_at_turn == 0
    wm = wm.model_copy(update={"turn": 5})
    wm = wm.apply(WorkingMemoryDelta(
        hypothesis_updates=[HypothesisUpdate(id=h.id, status="refuted")],
    ))
    assert wm.last_resolved_at_turn == 5


def test_apply_accepts_prefix_id_in_hypothesis_update():
    """Defense-in-depth: brain may emit truncated IDs; apply should match by prefix."""
    wm = _wm()
    h = Hypothesis(statement="X")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h]))
    # Use just the first 8 chars
    wm2 = wm.apply(WorkingMemoryDelta(
        hypothesis_updates=[HypothesisUpdate(id=h.id[:8], status="supported")],
    ))
    assert wm2.hypotheses[0].status == "supported"


def test_apply_rejects_ambiguous_prefix():
    """Prefix match must be unambiguous (single match) to apply."""
    wm = _wm()
    h1 = Hypothesis(id="aaaa1111-1111-1111-1111-111111111111", statement="A")
    h2 = Hypothesis(id="aaaa1111-2222-2222-2222-222222222222", statement="B")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h1, h2]))
    # "aaaa1111" prefix matches both → must be ignored
    wm2 = wm.apply(WorkingMemoryDelta(
        hypothesis_updates=[HypothesisUpdate(id="aaaa1111", status="supported")],
    ))
    statuses = {h.statement: h.status for h in wm2.hypotheses}
    assert statuses == {"A": "open", "B": "open"}


# ── Source-class classifier ───────────────────────────────────────────────────
def test_classify_source_uses_tool_for_registries():
    from app.pipeline.runners.working_memory import classify_source
    assert classify_source("https://example.com/x", "run_sec_edgar") == "registry"
    assert classify_source(None, "run_ph_sec_dti") == "registry"


def test_classify_source_uses_host_for_primary_official():
    from app.pipeline.runners.working_memory import classify_source
    assert classify_source("https://investors.grab.com/news", "run_web_search") == "primary_official"
    assert classify_source("https://www.sec.gov/Archives/edgar/data/x", "run_web_search") == "registry"


def test_classify_source_news_aggregator_social():
    from app.pipeline.runners.working_memory import classify_source
    assert classify_source("https://www.businesstimes.com.sg/x", "run_web_search") == "news"
    assert classify_source("https://www.macrotrends.net/y", "run_web_search") == "aggregator"
    assert classify_source("https://www.linkedin.com/in/z", "run_web_search") == "social"


def test_classify_source_falls_back_to_training_when_no_url():
    from app.pipeline.runners.working_memory import classify_source
    assert classify_source(None, "internal") == "training"
    assert classify_source(None, None) == "unknown"


def test_apply_auto_classifies_findings_when_brain_omits():
    """If the brain emits a finding without source_class, apply() must infer it
    from URL/tool — otherwise the analytic-quality signal is silently lost."""
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="Grab IR release", source_url="https://investors.grab.com/x",
                source_tool="run_web_search"),
        Finding(title="Macrotrends page", source_url="https://www.macrotrends.net/y",
                source_tool="run_web_search"),
    ]))
    by_title = {f.title: f.source_class for f in wm.findings}
    assert by_title["Grab IR release"] == "primary_official"
    assert by_title["Macrotrends page"] == "aggregator"


def test_apply_respects_brain_provided_source_class():
    """If the brain explicitly classifies, don't overwrite."""
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="A", source_url="https://example.com",
                source_tool="run_web_search", source_class="news"),
    ]))
    assert wm.findings[0].source_class == "news"


def test_legacy_brain_result_includes_source_class_counts():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="A", source_url="https://investors.grab.com/x", source_tool="run_web_search"),
        Finding(title="B", source_url="https://www.businesstimes.com.sg/y", source_tool="run_web_search"),
        Finding(title="C", source_url="https://www.macrotrends.net/z", source_tool="run_web_search"),
    ]))
    legacy = wm.to_legacy_brain_result()
    sc = legacy["_loop_meta"]["source_class_counts"]
    assert sc == {"primary_official": 1, "news": 1, "aggregator": 1}
    # Each legacy finding also exposes source_class for UI per-row tagging
    assert {f["source_class"] for f in legacy["findings"]} == {"primary_official", "news", "aggregator"}


# ── Contradictions ────────────────────────────────────────────────────────────
def test_apply_appends_new_contradictions_and_dedupes_by_statement_pair():
    from app.pipeline.runners.working_memory import Contradiction
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_contradictions=[
        Contradiction(statement_a="net loss US$105M (GAAP)",
                      statement_b="net loss US$158M (IFRS)"),
    ]))
    assert len(wm.contradictions) == 1
    # Same pair (case-insensitive) → ignored
    wm = wm.apply(WorkingMemoryDelta(new_contradictions=[
        Contradiction(statement_a="NET LOSS US$105M (GAAP)",
                      statement_b="net loss US$158M (IFRS)"),
    ]))
    assert len(wm.contradictions) == 1
    # Reversed pair → also ignored
    wm = wm.apply(WorkingMemoryDelta(new_contradictions=[
        Contradiction(statement_a="net loss US$158M (IFRS)",
                      statement_b="net loss US$105M (GAAP)"),
    ]))
    assert len(wm.contradictions) == 1


def test_contradiction_update_with_winner_implicitly_resolves():
    from app.pipeline.runners.working_memory import Contradiction, ContradictionUpdate
    wm = _wm()
    c = Contradiction(statement_a="A", statement_b="B")
    wm = wm.apply(WorkingMemoryDelta(new_contradictions=[c]))
    wm = wm.apply(WorkingMemoryDelta(contradiction_updates=[
        ContradictionUpdate(id=c.id, winner="both",
                            resolution_note="Different framings, both true"),
    ]))
    after = wm.contradictions[0]
    assert after.status == "resolved"
    assert after.winner == "both"
    assert "Different framings" in after.resolution_note


def test_open_contradictions_helper_counts_only_open():
    from app.pipeline.runners.working_memory import (
        Contradiction, ContradictionUpdate, open_contradictions,
    )
    wm = _wm()
    c1 = Contradiction(statement_a="A1", statement_b="B1")
    c2 = Contradiction(statement_a="A2", statement_b="B2")
    wm = wm.apply(WorkingMemoryDelta(new_contradictions=[c1, c2]))
    assert open_contradictions(wm) == 2
    wm = wm.apply(WorkingMemoryDelta(contradiction_updates=[
        ContradictionUpdate(id=c1.id, winner="a", resolution_note="x"),
    ]))
    assert open_contradictions(wm) == 1


def test_synthesize_phase_blocked_until_contradictions_resolved():
    """compute_next_phase must keep us in TEST if open contradictions exist,
    even when all hypotheses are resolved."""
    from app.pipeline.runners.working_memory import (
        Contradiction, ContradictionUpdate, compute_next_phase,
    )
    wm = _wm(phase="test")
    # Two resolved hypotheses + one open contradiction → still test
    h1 = Hypothesis(statement="H1", status="supported")
    h2 = Hypothesis(statement="H2", status="refuted")
    c = Contradiction(statement_a="A", statement_b="B")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h1, h2], new_contradictions=[c]))
    assert compute_next_phase(wm) == "test"
    # Resolve the contradiction → synthesize unblocks
    wm = wm.apply(WorkingMemoryDelta(contradiction_updates=[
        ContradictionUpdate(id=c.id, winner="both", resolution_note="ok"),
    ]))
    assert compute_next_phase(wm) == "synthesize"


# ── Falsification condition on Hypothesis ─────────────────────────────────────
def test_hypothesis_falsification_condition_round_trips():
    h = Hypothesis(statement="X", falsification_condition="evidence that not-X")
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h]))
    blob = wm.model_dump_json()
    restored = WorkingMemory.model_validate_json(blob)
    assert restored.hypotheses[0].falsification_condition == "evidence that not-X"


def test_hypothesis_render_warns_when_falsification_condition_missing():
    wm = _wm(phase="test")
    h = Hypothesis(statement="vague claim", falsification_condition="")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h]))
    section = wm.to_prompt_sections()["open_hypotheses"]
    assert "too vague" in section


def test_hypothesis_render_shows_falsification_condition_when_present():
    wm = _wm(phase="test")
    h = Hypothesis(statement="claim",
                   falsification_condition="audited filing showing positive net income")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h]))
    section = wm.to_prompt_sections()["open_hypotheses"]
    assert "refuted by" in section
    assert "audited filing" in section


# ── ACH evidence matrix ──────────────────────────────────────────────────────
def test_apply_merges_evidence_scores_keyed_by_pair():
    from app.pipeline.runners.working_memory import EvidenceScore
    wm = _wm()
    h = Hypothesis(statement="H1")
    f = Finding(title="F1", source_url="https://x")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h], new_findings_data=[f]))
    wm = wm.apply(WorkingMemoryDelta(new_evidence_scores=[
        EvidenceScore(finding_id=f.id, hypothesis_id=h.id,
                      consistency="consistent", note="affirms"),
    ]))
    assert len(wm.evidence_matrix) == 1
    assert wm.evidence_matrix[0].consistency == "consistent"
    # Re-score same pair → overwrites, not duplicates
    wm = wm.apply(WorkingMemoryDelta(new_evidence_scores=[
        EvidenceScore(finding_id=f.id, hypothesis_id=h.id,
                      consistency="inconsistent", note="actually refutes"),
    ]))
    assert len(wm.evidence_matrix) == 1
    assert wm.evidence_matrix[0].consistency == "inconsistent"


def test_apply_drops_evidence_scores_with_unknown_ids():
    from app.pipeline.runners.working_memory import EvidenceScore
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_evidence_scores=[
        EvidenceScore(finding_id="ghost-finding", hypothesis_id="ghost-hyp",
                      consistency="consistent"),
    ]))
    assert wm.evidence_matrix == []


def test_apply_supports_prefix_ids_in_evidence_scores():
    from app.pipeline.runners.working_memory import EvidenceScore
    wm = _wm()
    h = Hypothesis(statement="H1")
    f = Finding(title="F1", source_url="https://x")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h], new_findings_data=[f]))
    wm = wm.apply(WorkingMemoryDelta(new_evidence_scores=[
        EvidenceScore(finding_id=f.id[:8], hypothesis_id=h.id[:8],
                      consistency="consistent"),
    ]))
    assert len(wm.evidence_matrix) == 1
    # Stored under full ids, not the short forms
    assert wm.evidence_matrix[0].finding_id == f.id
    assert wm.evidence_matrix[0].hypothesis_id == h.id


def test_count_inconsistencies_helper():
    from app.pipeline.runners.working_memory import EvidenceScore, count_inconsistencies
    wm = _wm()
    h = Hypothesis(statement="H1")
    f1 = Finding(title="F1", source_url="https://1")
    f2 = Finding(title="F2", source_url="https://2")
    f3 = Finding(title="F3", source_url="https://3")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h], new_findings_data=[f1, f2, f3]))
    wm = wm.apply(WorkingMemoryDelta(new_evidence_scores=[
        EvidenceScore(finding_id=f1.id, hypothesis_id=h.id, consistency="inconsistent"),
        EvidenceScore(finding_id=f2.id, hypothesis_id=h.id, consistency="consistent"),
        EvidenceScore(finding_id=f3.id, hypothesis_id=h.id, consistency="inconsistent"),
    ]))
    assert count_inconsistencies(wm, h.id) == 2


def test_is_diagnostic_finding():
    """A finding is diagnostic if it's consistent for some hypothesis AND inconsistent for another."""
    from app.pipeline.runners.working_memory import EvidenceScore, is_diagnostic
    wm = _wm()
    h_a = Hypothesis(statement="A")
    h_b = Hypothesis(statement="B")
    f = Finding(title="F", source_url="https://x")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h_a, h_b], new_findings_data=[f]))
    # Only one hypothesis scored → not diagnostic yet
    wm = wm.apply(WorkingMemoryDelta(new_evidence_scores=[
        EvidenceScore(finding_id=f.id, hypothesis_id=h_a.id, consistency="consistent"),
    ]))
    assert is_diagnostic(wm, f.id) is False
    # Score for the second hypothesis with opposite consistency → diagnostic
    wm = wm.apply(WorkingMemoryDelta(new_evidence_scores=[
        EvidenceScore(finding_id=f.id, hypothesis_id=h_b.id, consistency="inconsistent"),
    ]))
    assert is_diagnostic(wm, f.id) is True


def test_ach_ranking_prefers_fewest_inconsistencies():
    """ACH's load-bearing rule: rank by fewest inconsistencies, not most consistencies."""
    from app.pipeline.runners.working_memory import EvidenceScore, ach_ranking
    wm = _wm()
    h_winner = Hypothesis(statement="0 inc / 1 con")
    h_loser  = Hypothesis(statement="1 inc / 5 con")
    f1 = Finding(title="F1", source_url="https://1")
    f2 = Finding(title="F2", source_url="https://2")
    f3 = Finding(title="F3", source_url="https://3")
    f4 = Finding(title="F4", source_url="https://4")
    f5 = Finding(title="F5", source_url="https://5")
    f6 = Finding(title="F6", source_url="https://6")
    wm = wm.apply(WorkingMemoryDelta(
        new_hypotheses=[h_winner, h_loser],
        new_findings_data=[f1, f2, f3, f4, f5, f6],
    ))
    wm = wm.apply(WorkingMemoryDelta(new_evidence_scores=[
        # h_winner: 0 inconsistent, 1 consistent
        EvidenceScore(finding_id=f1.id, hypothesis_id=h_winner.id, consistency="consistent"),
        # h_loser: 1 inconsistent, 5 consistent
        EvidenceScore(finding_id=f1.id, hypothesis_id=h_loser.id, consistency="inconsistent"),
        EvidenceScore(finding_id=f2.id, hypothesis_id=h_loser.id, consistency="consistent"),
        EvidenceScore(finding_id=f3.id, hypothesis_id=h_loser.id, consistency="consistent"),
        EvidenceScore(finding_id=f4.id, hypothesis_id=h_loser.id, consistency="consistent"),
        EvidenceScore(finding_id=f5.id, hypothesis_id=h_loser.id, consistency="consistent"),
        EvidenceScore(finding_id=f6.id, hypothesis_id=h_loser.id, consistency="consistent"),
    ]))
    ranking = ach_ranking(wm)
    # h_winner first despite having only 1 consistency
    assert ranking[0][0] == h_winner.id
    assert ranking[0][1] == 0   # 0 inconsistencies
    assert ranking[1][0] == h_loser.id
    assert ranking[1][1] == 1   # 1 inconsistency


def test_render_evidence_matrix_shows_ranking_and_diagnostic_star():
    from app.pipeline.runners.working_memory import EvidenceScore
    wm = _wm(phase="test")
    h_a = Hypothesis(statement="A")
    h_b = Hypothesis(statement="B")
    f = Finding(title="F", source_url="https://x")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h_a, h_b], new_findings_data=[f]))
    wm = wm.apply(WorkingMemoryDelta(new_evidence_scores=[
        EvidenceScore(finding_id=f.id, hypothesis_id=h_a.id, consistency="consistent"),
        EvidenceScore(finding_id=f.id, hypothesis_id=h_b.id, consistency="inconsistent"),
    ]))
    section = wm.to_prompt_sections()["evidence_matrix"]
    assert "EVIDENCE MATRIX" in section
    assert "FEWEST inconsistencies" in section
    assert "DIAGNOSTIC FINDINGS" in section
    # The "A" hypothesis should be marked favored (0 inc, 1 con)
    assert "favored" in section


def test_apply_auto_derives_evidence_scores_from_hypothesis_links():
    """Matrix should populate as a byproduct of hypothesis testing, even when
    the brain doesn't emit explicit evidence_scores. Supporting → consistent;
    refuting → inconsistent."""
    wm = _wm()
    h = Hypothesis(statement="H1")
    f_support = Finding(title="supports", source_url="https://a")
    f_refute  = Finding(title="refutes",  source_url="https://b")
    wm = wm.apply(WorkingMemoryDelta(
        new_hypotheses=[h],
        new_findings_data=[f_support, f_refute],
    ))
    # Brain emits a hypothesis_update with supporting + refuting findings,
    # but NO explicit evidence_scores.
    wm = wm.apply(WorkingMemoryDelta(
        hypothesis_updates=[HypothesisUpdate(
            id=h.id, status="supported",
            add_supporting_finding_ids=[f_support.id],
            add_refuting_finding_ids=[f_refute.id],
        )],
    ))
    cells = {(s.finding_id, s.hypothesis_id): s for s in wm.evidence_matrix}
    assert cells[(f_support.id, h.id)].consistency == "consistent"
    assert cells[(f_refute.id,  h.id)].consistency == "inconsistent"
    # Derived note marks origin so we can audit
    assert "derived" in cells[(f_support.id, h.id)].note


def test_brain_provided_score_overrides_derivation():
    from app.pipeline.runners.working_memory import EvidenceScore
    wm = _wm()
    h = Hypothesis(statement="H1")
    f = Finding(title="F", source_url="https://x")
    wm = wm.apply(WorkingMemoryDelta(new_hypotheses=[h], new_findings_data=[f]))
    # Brain explicitly says inconsistent
    wm = wm.apply(WorkingMemoryDelta(
        new_evidence_scores=[EvidenceScore(
            finding_id=f.id, hypothesis_id=h.id,
            consistency="inconsistent", note="brain says no",
        )],
        # ...but also lists it as a supporting finding (which would derive 'consistent')
        hypothesis_updates=[HypothesisUpdate(
            id=h.id, add_supporting_finding_ids=[f.id],
        )],
    ))
    # Brain's explicit score wins over the derivation
    cell = next(s for s in wm.evidence_matrix
                if s.finding_id == f.id and s.hypothesis_id == h.id)
    assert cell.consistency == "inconsistent"
    assert "brain says no" in cell.note


# ── Cross-run priors ──────────────────────────────────────────────────────────
def test_cross_run_priors_render_empty_when_absent():
    wm = _wm()
    section = wm.to_prompt_sections()["cross_run_priors"]
    assert "no semantically-related" in section


def test_cross_run_priors_render_graded_first():
    wm = _wm()
    wm = wm.model_copy(update={"cross_run_priors": [
        {"ref": "r1", "title": "Ungraded prior", "content": "x", "score": 0.5,
         "user_score": 0, "source": "semantic"},
        {"ref": "r2", "title": "GRADED A prior", "content": "y", "score": 0.7,
         "user_score": 1, "source": "feedback"},
    ]})
    section = wm.to_prompt_sections()["cross_run_priors"]
    # GRADED entries come first and carry the ✓ marker
    g_idx = section.find("GRADED")
    u_idx = section.find("Ungraded prior")
    assert g_idx < u_idx
    assert "GRADED A prior" in section
    assert "1 user-graded" in section


def test_cross_run_priors_round_trip_through_wm_json():
    wm = _wm()
    wm = wm.model_copy(update={"cross_run_priors": [
        {"ref": "r1", "title": "T", "content": "C", "score": 0.42,
         "user_score": 1, "source": "feedback", "run_id": "abc"},
    ]})
    restored = WorkingMemory.model_validate_json(wm.model_dump_json())
    assert restored.cross_run_priors[0]["title"] == "T"
    assert restored.cross_run_priors[0]["user_score"] == 1


def test_should_terminate_synthesize_wins_over_max_turns():
    """If both synthesize-ran and max_turns conditions apply on the same turn,
    the synthesize signal should win — the run produced a real answer."""
    from app.pipeline.runners.working_memory import should_terminate
    wm = _wm(phase="synthesize", turn=8, phase_entered_at_turn=7)
    assert should_terminate(wm, max_turns=8, cancelled=False) == "synthesized"


# ── Deception scoring integration ─────────────────────────────────────────────
def test_apply_scores_findings_with_deception_signals():
    """When two findings share the same title+content but list different
    sources, source_echo should fire (an astroturfing-style signal)."""
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="Acme is profitable!",
                content="Acme reported record FY profits.",
                source_url="https://a.com",
                source_tool="serper"),
        Finding(title="Acme is profitable!",  # identical title+content
                content="Acme reported record FY profits.",
                source_url="https://b.com",
                source_tool="brave"),
    ]))
    # Both findings get the source_echo flag because their (title,content)
    # appears from multiple distinct source tools.
    for f in wm.findings:
        assert "source_echo" in f.deception_flags, f"missing source_echo on {f.title}: {f.deception_flags}"
        assert f.deception_risk > 0.0


def test_apply_recomputes_deception_on_each_merge():
    """A finding that appears risk-free on its own should pick up source_echo
    later when a duplicate-from-different-source arrives."""
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="Solo finding", content="text", source_url="https://a", source_tool="x"),
    ]))
    assert wm.findings[0].deception_risk == 0.0
    # Add a duplicate from a different source
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="Solo finding", content="text", source_url="https://b", source_tool="y"),
    ]))
    # First finding now flagged retroactively
    by_url = {f.source_url: f for f in wm.findings}
    assert "source_echo" in by_url["https://a"].deception_flags


def test_low_source_diversity_flag_fires_when_all_findings_from_one_tool():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title=f"F{i}", source_url=f"https://x/{i}", source_tool="ddg")
        for i in range(3)
    ]))
    # All findings have the same source_tool → low_source_diversity fires
    assert all("low_source_diversity" in f.deception_flags for f in wm.findings)


def test_legacy_brain_result_surfaces_deception_per_finding_and_summary():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="Echo A", content="dupe", source_url="https://a", source_tool="serper"),
        Finding(title="Echo A", content="dupe", source_url="https://b", source_tool="brave"),
    ]))
    legacy = wm.to_legacy_brain_result()
    for f in legacy["findings"]:
        assert "deception_risk" in f
        assert "deception_flags" in f
    assert legacy["_loop_meta"]["deception_flagged_count"] == 2


def test_finding_deception_round_trips_through_json():
    wm = _wm()
    wm = wm.apply(WorkingMemoryDelta(new_findings_data=[
        Finding(title="A", source_url="https://x", source_tool="t"),
        Finding(title="A", source_url="https://y", source_tool="u"),  # echo
    ]))
    blob = wm.model_dump_json()
    restored = WorkingMemory.model_validate_json(blob)
    risks = [f.deception_risk for f in restored.findings]
    flags = [f.deception_flags for f in restored.findings]
    assert all(r > 0 for r in risks)
    assert all("source_echo" in fl for fl in flags)


# ── Tool gating per phase ─────────────────────────────────────────────────────
def test_allowed_tools_for_phase_explore_is_search_only():
    from app.pipeline.runners.working_memory import allowed_tools_for_phase
    tools = allowed_tools_for_phase("explore")
    assert any("run_web_search" in t for t in tools)
    assert any("run_wikipedia_api" in t for t in tools)
    # Fetch + registry lookups are NOT available in explore
    assert not any("run_web_search_fetch" in t for t in tools)
    assert not any("run_sec_edgar" in t for t in tools)


def test_allowed_tools_for_phase_test_adds_verification_tools():
    from app.pipeline.runners.working_memory import allowed_tools_for_phase
    tools = allowed_tools_for_phase("test")
    # Test has everything explore has
    assert any("run_web_search" in t for t in tools)
    # ...plus the verification tools
    assert any("run_web_search_fetch" in t for t in tools)
    assert any("run_sec_edgar" in t for t in tools)
    assert any("run_linkedin_profile_search" in t for t in tools)


def test_allowed_tools_for_phase_synthesize_is_essentially_empty():
    """Synthesize must force the brain to use accumulated findings — only
    ask_user remains for clarifications."""
    from app.pipeline.runners.working_memory import allowed_tools_for_phase
    tools = allowed_tools_for_phase("synthesize")
    assert len(tools) == 1
    assert tools[0].endswith("ask_user")
    # No research tools at all
    assert not any("run_web_search" in t for t in tools)
    assert not any("run_sec_edgar" in t for t in tools)


def test_allowed_tools_for_phase_unknown_falls_back_to_explore():
    """Defensive: never blank-allowlist a real run."""
    from app.pipeline.runners.working_memory import allowed_tools_for_phase
    unknown = allowed_tools_for_phase("xyzzy")
    explore = allowed_tools_for_phase("explore")
    assert unknown == explore


def test_allowed_tools_are_qualified_with_mcp_prefix():
    """The CLI's --allowedTools expects fully-qualified names."""
    from app.pipeline.runners.working_memory import allowed_tools_for_phase
    for tool in allowed_tools_for_phase("test"):
        assert tool.startswith("mcp__info-broker-mcp__"), tool


# ── Category-driven tool gating ──────────────────────────────────────────────
def test_unknown_mcp_tool_is_denied_by_default():
    """A tool not registered in MCP_TOOL_CATEGORIES is silently DENIED in
    every phase. Explicit opt-in is safer than accidental opt-out."""
    from app.pipeline.runners.working_memory import (
        allowed_tools_for_phase, MCP_TOOL_CATEGORIES,
    )
    for phase in ("explore", "test", "synthesize"):
        tools = allowed_tools_for_phase(phase)
        assert not any("hypothetical_brand_new_tool" in t for t in tools)
    # And the tool isn't in the registry
    assert "hypothetical_brand_new_tool" not in MCP_TOOL_CATEGORIES


def test_new_tool_added_to_category_inherits_phase_gating():
    """If a new tool is added to MCP_TOOL_CATEGORIES with category='source',
    it automatically appears in EXPLORE and TEST allowlists (no per-phase
    code change needed)."""
    from app.pipeline.runners.working_memory import (
        allowed_tools_for_phase, MCP_TOOL_CATEGORIES,
    )
    fake_tool = "run_fake_new_search_engine"
    MCP_TOOL_CATEGORIES[fake_tool] = "source"
    try:
        explore = allowed_tools_for_phase("explore")
        test_phase = allowed_tools_for_phase("test")
        synth = allowed_tools_for_phase("synthesize")
        assert any(fake_tool in t for t in explore)
        assert any(fake_tool in t for t in test_phase)
        # Synthesize never allows source tools
        assert not any(fake_tool in t for t in synth)
    finally:
        del MCP_TOOL_CATEGORIES[fake_tool]


def test_env_deny_tools_overrides_all_phases(monkeypatch):
    """IS_DENY_TOOLS env var hard-blocks specific tools regardless of phase —
    incident-response lever without a code change."""
    from app.pipeline.runners.working_memory import allowed_tools_for_phase
    # Without override, run_web_search is in explore
    pre = allowed_tools_for_phase("explore")
    assert any("run_web_search" in t for t in pre)
    # With override, it disappears
    monkeypatch.setenv("IS_DENY_TOOLS", "run_web_search")
    post = allowed_tools_for_phase("explore")
    assert not any(t.endswith("__run_web_search") for t in post)


def test_destination_and_meta_tools_never_allowed_in_loop_phases():
    """The loop should never call export or admin tools; those are
    user-driven actions, not brain-driven."""
    from app.pipeline.runners.working_memory import allowed_tools_for_phase
    for phase in ("explore", "test", "synthesize"):
        tools = allowed_tools_for_phase(phase)
        assert not any("export_research" in t for t in tools)
        assert not any("log_cycle" in t for t in tools)
        assert not any("save_pipeline" in t for t in tools)


def test_phase_allowlist_dict_stays_in_sync_with_derived_view():
    """Backwards-compat alias PHASE_TOOL_ALLOWLIST is derived from the
    category map — it must always agree with allowed_tools_for_phase."""
    from app.pipeline.runners.working_memory import (
        allowed_tools_for_phase, PHASE_TOOL_ALLOWLIST,
    )
    for phase, bare_names in PHASE_TOOL_ALLOWLIST.items():
        qualified = allowed_tools_for_phase(phase)
        # Each bare name appears in the qualified list
        for name in bare_names:
            assert any(t.endswith("__" + name) for t in qualified)
