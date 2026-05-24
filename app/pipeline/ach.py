"""ACH (Analysis of Competing Hypotheses) scoring module — P5.

Pure module: no LLM calls, no IO.  Computes the full Heuer ACH matrix from
existing finding data.

Design ref: docs/intelligence/three-tier-brain-architecture.md §14 (ACH appendix)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

ACHMark = Literal["consistent", "inconsistent", "neutral", "unknown"]

# Source classes that carry "live" authority for primary/supporting signals
_LIVE_SOURCE_CLASSES = frozenset({"live_search", "primary_official"})

# Phase ids whose findings are treated as disconfirm evidence.
# Legacy id red_team is kept for historical DB rows; allowlist 2026-05-23.
# The 2026-05-23 taxonomy rename means new rows use disconfirm.
_DISCONFIRM_PHASE_IDS = frozenset({"red_team", "disconfirm"})  # allowlist 2026-05-23: legacy phase id for historical research_trails rows

# Years within which a finding's date field is considered "recent"
_RECENCY_YEARS = 2


@dataclass
class ACHSignal:
    id: str           # "primary", "supporting", "medium", "recency", custom
    label: str
    weight: float     # 0.0 .. 1.0; sum of weights typically ≈ 1.0
    penalty_on_mismatch: float  # additional penalty beyond losing the weight


@dataclass
class ACHCell:
    signal_id: str
    hypothesis_name: str
    mark: ACHMark
    evidence_finding_id: str | None  # which finding produced this mark
    notes: str | None


@dataclass
class ACHMatrix:
    signals: list[ACHSignal]
    hypotheses: list[str]   # ordered, top-ranked first
    cells: list[ACHCell]    # len = len(signals) × len(hypotheses)
    scores: dict[str, float]  # hypothesis_name → final score 0.0..1.0


def _cell_value(mark: ACHMark) -> float:
    """Per Heuer: consistent=1.0, neutral=0.5, unknown=0.5, inconsistent=0.0."""
    if mark == "consistent":
        return 1.0
    if mark == "inconsistent":
        return 0.0
    # neutral or unknown
    return 0.5


def _mark_primary(
    candidate_findings: list[dict],
    disconfirm_findings: list[dict],
) -> tuple[ACHMark, str | None]:
    """
    Determine ACH mark for the 'primary' signal:
      - consistent: any finding with live source_class AND confidence >= 0.6
      - inconsistent: any disconfirm finding AND confidence >= 0.5
      - neutral: finding mentions candidate but no confirm/disconfirm
      - unknown: no relevant finding
    """
    best_finding_id: str | None = None

    for f in disconfirm_findings:
        conf = float(f.get("confidence", 0.0))
        if conf >= 0.5:
            finding_id = f.get("source_url") or f.get("evidence_snippet", "")[:40] or None
            return "inconsistent", finding_id

    for f in candidate_findings:
        source_class = f.get("source_class", "")
        conf = float(f.get("confidence", 0.0))
        if source_class in _LIVE_SOURCE_CLASSES and conf >= 0.6:
            finding_id = f.get("source_url") or f.get("evidence_snippet", "")[:40] or None
            return "consistent", finding_id

    if candidate_findings:
        return "neutral", None

    return "unknown", None


def _mark_supporting(
    candidate_findings: list[dict],
) -> tuple[ACHMark, str | None]:
    """
    Determine ACH mark for the 'supporting' signal.
    Uses findings that have signals_matched set (indicating supporting context).
    Falls back to any live-source finding with confidence >= 0.6.
    """
    supporting = [f for f in candidate_findings if f.get("signals_matched")]

    for f in supporting:
        source_class = f.get("source_class", "")
        conf = float(f.get("confidence", 0.0))
        if source_class in _LIVE_SOURCE_CLASSES and conf >= 0.6:
            finding_id = f.get("source_url") or f.get("evidence_snippet", "")[:40] or None
            return "consistent", finding_id

    if supporting:
        return "neutral", None

    # Fall back to any candidate finding with live + high confidence
    for f in candidate_findings:
        source_class = f.get("source_class", "")
        conf = float(f.get("confidence", 0.0))
        if source_class in _LIVE_SOURCE_CLASSES and conf >= 0.6:
            finding_id = f.get("source_url") or f.get("evidence_snippet", "")[:40] or None
            return "consistent", finding_id

    if candidate_findings:
        return "neutral", None

    return "unknown", None


def _mark_medium(
    candidate_findings: list[dict],
    phase_outputs: list,
    strategy_id: str = "",
) -> tuple[ACHMark, str | None]:
    """
    Determine ACH mark for the 'medium' signal.
    Consistent if strategy is media_identification AND any finding from the
    gather phase has a live source_class.
    """
    # Collect phase_id from phase_outputs metadata
    gather_finding_ids: set[str] = set()
    for po in phase_outputs:
        if hasattr(po, "phase_id") and po.phase_id == "gather":
            for f in po.aggregated_findings:
                url = f.get("source_url") or ""
                if url:
                    gather_finding_ids.add(url)

    if "media_identification" in strategy_id:
        for f in candidate_findings:
            phase_id = f.get("phase_id", "")
            source_class = f.get("source_class", "")
            if phase_id == "gather" and source_class in _LIVE_SOURCE_CLASSES:
                finding_id = f.get("source_url") or f.get("evidence_snippet", "")[:40] or None
                return "consistent", finding_id

    if candidate_findings:
        return "neutral", None

    return "unknown", None


def _mark_recency(
    candidate_findings: list[dict],
) -> tuple[ACHMark, str | None]:
    """
    Determine ACH mark for the 'recency' signal.
    Consistent if any finding has a date field within _RECENCY_YEARS.
    """
    now_year = datetime.now(tz=timezone.utc).year

    for f in candidate_findings:
        date_val = f.get("date")
        if date_val:
            try:
                year = int(str(date_val)[:4])
                if now_year - year <= _RECENCY_YEARS:
                    finding_id = f.get("source_url") or f.get("evidence_snippet", "")[:40] or None
                    return "consistent", finding_id
            except (TypeError, ValueError):
                pass

    if candidate_findings:
        return "neutral", None

    return "unknown", None


def _mark_live_source(
    candidate_findings: list[dict],
) -> tuple[ACHMark, str | None]:
    """
    Determine ACH mark for the 'live_source' signal.
    Consistent if any finding has a live source_class.
    """
    for f in candidate_findings:
        if f.get("source_class", "") in _LIVE_SOURCE_CLASSES:
            finding_id = f.get("source_url") or f.get("evidence_snippet", "")[:40] or None
            return "consistent", finding_id

    if candidate_findings:
        return "neutral", None

    return "unknown", None


def _mark_for_signal(
    signal_id: str,
    candidate_findings: list[dict],
    disconfirm_findings: list[dict],
    phase_outputs: list,
    strategy_id: str = "",
) -> tuple[ACHMark, str | None]:
    """Dispatch mark computation to the correct signal handler."""
    if signal_id == "primary":
        return _mark_primary(candidate_findings, disconfirm_findings)
    if signal_id == "supporting":
        return _mark_supporting(candidate_findings)
    if signal_id == "medium":
        return _mark_medium(candidate_findings, phase_outputs, strategy_id)
    if signal_id == "recency":
        return _mark_recency(candidate_findings)
    if signal_id == "live_source":
        return _mark_live_source(candidate_findings)
    # Custom/unknown signal: fall back to primary logic
    return _mark_primary(candidate_findings, disconfirm_findings)


# Default signals used when no strategy-level ach_signals are provided
DEFAULT_ACH_SIGNALS: list[ACHSignal] = [
    ACHSignal(id="primary", label="Primary subject match", weight=0.40, penalty_on_mismatch=0.30),
    ACHSignal(id="supporting", label="Supporting detail match", weight=0.25, penalty_on_mismatch=0.15),
    ACHSignal(id="medium", label="Medium type match", weight=0.15, penalty_on_mismatch=0.25),
    ACHSignal(id="recency", label="Recency match", weight=0.10, penalty_on_mismatch=0.10),
    ACHSignal(id="live_source", label="Has live source", weight=0.10, penalty_on_mismatch=0.05),
]


def compute_ach_matrix(
    hypothesis_names: list[str],
    findings_by_candidate: dict[str, list[dict]],
    disconfirm_findings_by_candidate: dict[str, list[dict]],
    signals: list[ACHSignal],
    phase_outputs: list,
    strategy_id: str = "",
) -> ACHMatrix:
    """Compute full ACH per Heuer methodology.

    Per Heuer: for each (signal, hypothesis) cell:
      - consistent: finding directly supports hypothesis on this signal
      - inconsistent: disconfirm finding contradicts on this signal
      - neutral: finding mentions but doesn't take a side
      - unknown: no relevant finding

    Score per hypothesis:
      score = sum_over_signals(signal.weight * cell_value(mark))
              - sum_over_signals(signal.penalty * (mark == 'inconsistent'))

    Where cell_value:
      consistent → 1.0
      neutral → 0.5
      unknown → 0.5 (no penalty, no boost)
      inconsistent → 0.0

    Args:
        hypothesis_names: ordered list of candidate/hypothesis names.
        findings_by_candidate: candidate → list of supporting findings.
        disconfirm_findings_by_candidate: candidate → list of disconfirm findings.
        signals: ordered list of ACHSignal objects to score.
        phase_outputs: list of PhaseOutput objects (for medium/recency context).
        strategy_id: strategy id string for medium-type signal scoping.

    Returns:
        ACHMatrix with populated cells and scores.
    """
    if not signals:
        signals = DEFAULT_ACH_SIGNALS

    cells: list[ACHCell] = []
    scores: dict[str, float] = {}

    for hypothesis in hypothesis_names:
        candidate_findings = findings_by_candidate.get(hypothesis, [])
        disconfirm_findings = disconfirm_findings_by_candidate.get(hypothesis, [])

        raw_score = 0.0
        penalty = 0.0

        for signal in signals:
            mark, evidence_id = _mark_for_signal(
                signal_id=signal.id,
                candidate_findings=candidate_findings,
                disconfirm_findings=disconfirm_findings,
                phase_outputs=phase_outputs,
                strategy_id=strategy_id,
            )

            cells.append(ACHCell(
                signal_id=signal.id,
                hypothesis_name=hypothesis,
                mark=mark,
                evidence_finding_id=evidence_id,
                notes=None,
            ))

            raw_score += signal.weight * _cell_value(mark)
            if mark == "inconsistent":
                penalty += signal.penalty_on_mismatch

        final_score = max(0.0, min(1.0, raw_score - penalty))
        scores[hypothesis] = final_score

    return ACHMatrix(
        signals=signals,
        hypotheses=list(hypothesis_names),
        cells=cells,
        scores=scores,
    )


def ach_matrix_to_signal_scores(
    matrix: ACHMatrix,
    hypothesis_name: str,
) -> dict[str, str]:
    """Derive the legacy signal_scores dict from ACH matrix cells.

    Maps:
      consistent → "match"
      inconsistent → "mismatch"
      neutral / unknown → "unknown"

    This preserves backward compatibility with the UI-P3 RankedCandidate type.
    """
    scores: dict[str, str] = {}
    for cell in matrix.cells:
        if cell.hypothesis_name != hypothesis_name:
            continue
        if cell.mark == "consistent":
            scores[cell.signal_id] = "match"
        elif cell.mark == "inconsistent":
            scores[cell.signal_id] = "mismatch"
        else:
            scores[cell.signal_id] = "unknown"
    return scores


def ach_matrix_to_dict(matrix: ACHMatrix) -> dict:
    """Serialize an ACHMatrix to a JSON-safe dict for event emission."""
    return {
        "signals": [
            {
                "id": s.id,
                "label": s.label,
                "weight": s.weight,
                "penalty_on_mismatch": s.penalty_on_mismatch,
            }
            for s in matrix.signals
        ],
        "hypotheses": matrix.hypotheses,
        "cells": [
            {
                "signal_id": c.signal_id,
                "hypothesis_name": c.hypothesis_name,
                "mark": c.mark,
                "evidence_finding_id": c.evidence_finding_id,
                "notes": c.notes,
            }
            for c in matrix.cells
        ],
        "scores": matrix.scores,
    }
