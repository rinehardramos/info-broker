"""Unit tests for app/pipeline/ach.py — P5 ACH module.

All tests are pure: no LLM calls, no IO, no DB.
"""
from __future__ import annotations

import pytest

from app.pipeline.ach import (
    ACHSignal,
    ACHCell,
    ACHMatrix,
    compute_ach_matrix,
    ach_matrix_to_signal_scores,
    DEFAULT_ACH_SIGNALS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signals(
    primary_weight: float = 0.40,
    primary_penalty: float = 0.30,
    supporting_weight: float = 0.25,
    supporting_penalty: float = 0.15,
    medium_weight: float = 0.15,
    medium_penalty: float = 0.25,
    recency_weight: float = 0.10,
    recency_penalty: float = 0.10,
    live_weight: float = 0.10,
    live_penalty: float = 0.05,
) -> list[ACHSignal]:
    return [
        ACHSignal("primary", "Primary subject match", primary_weight, primary_penalty),
        ACHSignal("supporting", "Supporting detail match", supporting_weight, supporting_penalty),
        ACHSignal("medium", "Medium type match", medium_weight, medium_penalty),
        ACHSignal("recency", "Recency match", recency_weight, recency_penalty),
        ACHSignal("live_source", "Has live source", live_weight, live_penalty),
    ]


def _live_finding(candidate: str, confidence: float = 0.8, phase_id: str = "broaden") -> dict:
    return {
        "candidate_name": candidate,
        "source_class": "live_search",
        "confidence": confidence,
        "evidence_snippet": f"Live evidence for {candidate}",
        "source_url": f"https://example.com/{candidate.lower().replace(' ', '-')}",
        "phase_id": phase_id,
        "hypothesis_slot": 0,
    }


def _disconfirm_finding(candidate: str, confidence: float = 0.7) -> dict:
    return {
        "candidate_name": candidate,
        "source_class": "live_search",
        "confidence": confidence,
        "evidence_snippet": f"Disconfirm evidence for {candidate}",
        "phase_id": "red_team",
        "hypothesis_slot": 0,
    }


def _rag_finding(candidate: str) -> dict:
    return {
        "candidate_name": candidate,
        "source_class": "prior_research",
        "confidence": 0.5,
        "evidence_snippet": f"RAG evidence for {candidate}",
        "phase_id": "broaden",
    }


# ---------------------------------------------------------------------------
# test_compute_ach_all_consistent_returns_max_score
# ---------------------------------------------------------------------------

def test_compute_ach_all_consistent_returns_max_score():
    """When all signals are consistent for a hypothesis, score should be maximum (1.0)."""
    signals = _make_signals()
    hypothesis = "Wonyoung"
    f = _live_finding(hypothesis, confidence=0.9)

    # All signal marks will be computed from these findings; provide enough
    # coverage: live_search covers primary, supporting, live_source
    # broaden phase covers medium (with media_identification strategy)
    # no date → recency will be neutral (0.5 not 1.0), so we add a dated finding
    dated_finding = {
        **f,
        "date": "2025-06-01",
        "signals_matched": ["supporting"],
    }

    matrix = compute_ach_matrix(
        hypothesis_names=[hypothesis],
        findings_by_candidate={hypothesis: [dated_finding]},
        disconfirm_findings_by_candidate={hypothesis: []},
        signals=signals,
        phase_outputs=[],
        strategy_id="media_identification",
    )

    score = matrix.scores[hypothesis]
    # primary=consistent(1.0)*0.40, supporting=consistent(1.0)*0.25,
    # medium=neutral(0.5)*0.15 (no phase_outputs), recency=consistent(1.0)*0.10,
    # live_source=consistent(1.0)*0.10
    # total positive = 0.40+0.25+0.075+0.10+0.10 = 0.925, no penalties
    assert score > 0.85, f"Expected near-max score, got {score}"


# ---------------------------------------------------------------------------
# test_compute_ach_inconsistent_applies_penalty
# ---------------------------------------------------------------------------

def test_compute_ach_inconsistent_applies_penalty():
    """Inconsistent marks reduce score by weight + penalty_on_mismatch."""
    signals = [
        ACHSignal("primary", "Primary", 0.40, 0.30),
    ]
    hypothesis = "Zhao Lusi"
    disconfirm = _disconfirm_finding(hypothesis, confidence=0.7)

    matrix = compute_ach_matrix(
        hypothesis_names=[hypothesis],
        findings_by_candidate={hypothesis: [disconfirm]},
        disconfirm_findings_by_candidate={hypothesis: [disconfirm]},
        signals=signals,
        phase_outputs=[],
    )

    score = matrix.scores[hypothesis]
    # primary inconsistent: cell_value=0.0 → 0.0*0.40 = 0.0
    # penalty = 0.30
    # final = max(0, 0.0 - 0.30) = 0.0
    assert score == 0.0, f"Expected 0.0 after penalty, got {score}"

    primary_cell = next(c for c in matrix.cells if c.signal_id == "primary")
    assert primary_cell.mark == "inconsistent"


# ---------------------------------------------------------------------------
# test_compute_ach_unknown_neutral_no_score_change
# ---------------------------------------------------------------------------

def test_compute_ach_unknown_neutral_no_score_change():
    """Unknown/neutral marks produce 0.5 × weight (no penalty, no full credit)."""
    signals = [
        ACHSignal("primary", "Primary", 0.40, 0.30),
    ]
    hypothesis = "Unknown Person"

    # No findings → unknown mark
    matrix = compute_ach_matrix(
        hypothesis_names=[hypothesis],
        findings_by_candidate={hypothesis: []},
        disconfirm_findings_by_candidate={hypothesis: []},
        signals=signals,
        phase_outputs=[],
    )

    score = matrix.scores[hypothesis]
    # unknown → cell_value=0.5 → 0.5*0.40 = 0.20, no penalty
    assert abs(score - 0.20) < 0.001, f"Expected 0.20 for unknown, got {score}"

    primary_cell = next(c for c in matrix.cells if c.signal_id == "primary")
    assert primary_cell.mark == "unknown"


# ---------------------------------------------------------------------------
# test_compute_ach_empty_hypothesis_list
# ---------------------------------------------------------------------------

def test_compute_ach_empty_hypothesis_list():
    """Empty hypothesis list returns matrix with empty cells and scores."""
    matrix = compute_ach_matrix(
        hypothesis_names=[],
        findings_by_candidate={},
        disconfirm_findings_by_candidate={},
        signals=_make_signals(),
        phase_outputs=[],
    )

    assert matrix.hypotheses == []
    assert matrix.cells == []
    assert matrix.scores == {}


# ---------------------------------------------------------------------------
# test_compute_ach_zhao_lusi_vs_wonyoung_canned
# ---------------------------------------------------------------------------

def test_compute_ach_zhao_lusi_vs_wonyoung_canned():
    """Canned 2-hypothesis matrix: Wonyoung outranks Zhao Lusi.

    Wonyoung: has live evidence on primary signal + recent date.
    Zhao Lusi: has disconfirm evidence → inconsistent primary mark.
    """
    signals = _make_signals()

    wonyoung_finding = {
        "candidate_name": "Wonyoung",
        "source_class": "live_search",
        "confidence": 0.85,
        "evidence_snippet": "IVE Wonyoung promotional image with curling iron",
        "source_url": "https://example.com/wonyoung-ad",
        "phase_id": "broaden",
        "date": "2025-03-01",
        "signals_matched": ["supporting"],
    }

    zhao_disconfirm = {
        "candidate_name": "Zhao Lusi",
        "source_class": "live_search",
        "confidence": 0.75,
        "evidence_snippet": "Zhao Lusi mole placement does not match ad description",
        "phase_id": "red_team",
    }

    matrix = compute_ach_matrix(
        hypothesis_names=["Wonyoung", "Zhao Lusi"],
        findings_by_candidate={
            "Wonyoung": [wonyoung_finding],
            "Zhao Lusi": [zhao_disconfirm],
        },
        disconfirm_findings_by_candidate={
            "Wonyoung": [],
            "Zhao Lusi": [zhao_disconfirm],
        },
        signals=signals,
        phase_outputs=[],
        strategy_id="media_identification",
    )

    wonyoung_score = matrix.scores["Wonyoung"]
    zhao_score = matrix.scores["Zhao Lusi"]

    assert wonyoung_score > zhao_score, (
        f"Wonyoung ({wonyoung_score:.3f}) should outrank Zhao Lusi ({zhao_score:.3f})"
    )

    # Wonyoung primary should be consistent
    wy_primary = next(
        c for c in matrix.cells
        if c.signal_id == "primary" and c.hypothesis_name == "Wonyoung"
    )
    assert wy_primary.mark == "consistent"

    # Zhao Lusi primary should be inconsistent
    zl_primary = next(
        c for c in matrix.cells
        if c.signal_id == "primary" and c.hypothesis_name == "Zhao Lusi"
    )
    assert zl_primary.mark == "inconsistent"


# ---------------------------------------------------------------------------
# test_ach_matrix_to_signal_scores_mapping
# ---------------------------------------------------------------------------

def test_ach_matrix_to_signal_scores_mapping():
    """ach_matrix_to_signal_scores maps consistent→match, inconsistent→mismatch, neutral→unknown."""
    signals = [
        ACHSignal("primary", "Primary", 0.40, 0.30),
        ACHSignal("supporting", "Supporting", 0.25, 0.15),
        ACHSignal("medium", "Medium", 0.15, 0.25),
    ]

    cells = [
        ACHCell("primary", "Alice", "consistent", None, None),
        ACHCell("supporting", "Alice", "inconsistent", None, None),
        ACHCell("medium", "Alice", "neutral", None, None),
    ]

    matrix = ACHMatrix(
        signals=signals,
        hypotheses=["Alice"],
        cells=cells,
        scores={"Alice": 0.5},
    )

    signal_scores = ach_matrix_to_signal_scores(matrix, "Alice")

    assert signal_scores["primary"] == "match"
    assert signal_scores["supporting"] == "mismatch"
    assert signal_scores["medium"] == "unknown"


# ---------------------------------------------------------------------------
# test_ach_matrix_cells_count
# ---------------------------------------------------------------------------

def test_ach_matrix_cells_count():
    """Matrix always has exactly len(signals) × len(hypotheses) cells."""
    signals = _make_signals()  # 5 signals
    hypotheses = ["Alice", "Bob", "Charlie"]  # 3 hypotheses

    f_alice = _live_finding("Alice")
    f_bob = _rag_finding("Bob")

    matrix = compute_ach_matrix(
        hypothesis_names=hypotheses,
        findings_by_candidate={
            "Alice": [f_alice],
            "Bob": [f_bob],
            "Charlie": [],
        },
        disconfirm_findings_by_candidate={h: [] for h in hypotheses},
        signals=signals,
        phase_outputs=[],
    )

    assert len(matrix.cells) == len(signals) * len(hypotheses), (
        f"Expected {len(signals) * len(hypotheses)} cells, got {len(matrix.cells)}"
    )


# ---------------------------------------------------------------------------
# test_ach_disconfirm_below_confidence_threshold_not_inconsistent
# ---------------------------------------------------------------------------

def test_ach_disconfirm_below_confidence_threshold_not_inconsistent():
    """Disconfirm findings with confidence < 0.5 do not trigger inconsistent mark."""
    signals = [ACHSignal("primary", "Primary", 0.40, 0.30)]
    hypothesis = "Alice"

    low_conf_disconfirm = {
        "candidate_name": hypothesis,
        "source_class": "live_search",
        "confidence": 0.3,  # below 0.5 threshold
        "evidence_snippet": "Weak disconfirm",
        "phase_id": "red_team",
    }

    matrix = compute_ach_matrix(
        hypothesis_names=[hypothesis],
        findings_by_candidate={hypothesis: []},
        disconfirm_findings_by_candidate={hypothesis: [low_conf_disconfirm]},
        signals=signals,
        phase_outputs=[],
    )

    primary_cell = next(c for c in matrix.cells if c.signal_id == "primary")
    assert primary_cell.mark != "inconsistent", (
        f"Low-confidence disconfirm should not produce inconsistent mark, got {primary_cell.mark}"
    )


# ---------------------------------------------------------------------------
# test_ach_default_signals_used_when_none_provided
# ---------------------------------------------------------------------------

def test_ach_default_signals_used_when_none_provided():
    """compute_ach_matrix uses DEFAULT_ACH_SIGNALS when signals=[] is passed."""
    matrix = compute_ach_matrix(
        hypothesis_names=["Alice"],
        findings_by_candidate={"Alice": []},
        disconfirm_findings_by_candidate={"Alice": []},
        signals=[],
        phase_outputs=[],
    )

    assert len(matrix.signals) == len(DEFAULT_ACH_SIGNALS)
    assert len(matrix.cells) == len(DEFAULT_ACH_SIGNALS)


# ---------------------------------------------------------------------------
# test_ach_score_clamped_to_zero_on_heavy_penalty
# ---------------------------------------------------------------------------

def test_ach_score_clamped_to_zero_on_heavy_penalty():
    """Score is clamped to 0.0 even if penalties exceed raw score."""
    signals = [
        ACHSignal("primary", "Primary", 0.10, 2.0),  # massive penalty
    ]
    hypothesis = "Bad Candidate"
    disconfirm = _disconfirm_finding(hypothesis, confidence=0.9)

    matrix = compute_ach_matrix(
        hypothesis_names=[hypothesis],
        findings_by_candidate={hypothesis: [disconfirm]},
        disconfirm_findings_by_candidate={hypothesis: [disconfirm]},
        signals=signals,
        phase_outputs=[],
    )

    assert matrix.scores[hypothesis] >= 0.0, "Score must never go negative"
    assert matrix.scores[hypothesis] == 0.0


# ---------------------------------------------------------------------------
# test_ach_consistent_mark_carries_evidence_finding_id
# ---------------------------------------------------------------------------

def test_ach_consistent_mark_carries_evidence_finding_id():
    """A consistent mark should carry the source_url as evidence_finding_id."""
    signals = [ACHSignal("primary", "Primary", 0.40, 0.30)]
    hypothesis = "Wonyoung"
    url = "https://example.com/wonyoung-live"
    f = {
        "candidate_name": hypothesis,
        "source_class": "live_search",
        "confidence": 0.9,
        "evidence_snippet": "Live evidence",
        "source_url": url,
        "phase_id": "broaden",
    }

    matrix = compute_ach_matrix(
        hypothesis_names=[hypothesis],
        findings_by_candidate={hypothesis: [f]},
        disconfirm_findings_by_candidate={hypothesis: []},
        signals=signals,
        phase_outputs=[],
    )

    primary_cell = next(c for c in matrix.cells if c.signal_id == "primary")
    assert primary_cell.mark == "consistent"
    assert primary_cell.evidence_finding_id == url
