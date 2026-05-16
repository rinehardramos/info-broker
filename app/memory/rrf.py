"""Reciprocal Rank Fusion (RRF) for multi-signal memory retrieval."""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from app.memory.models import MemoryResult

# ---------------------------------------------------------------------------
# Grade-boost integration (Enhancement 3.1)
# ---------------------------------------------------------------------------

_GRADE_MULTIPLIER: dict[str, float] = {
    "A": 1.5,
    "B": 1.2,
    "C": 1.0,
    "D": 0.4,
}


def apply_grade_boost(
    results: list[MemoryResult],
    grades_map: dict[str, str],
) -> list[MemoryResult]:
    """Apply per-finding grade multipliers to RRF scores.

    Args:
        results:    List of fused MemoryResult objects (scores already computed).
        grades_map: Mapping of finding ref -> best grade letter ('A'–'D').
                    Build this by querying findings_grades and taking the
                    max-boost grade (A > B > C > D) from all available grades.
                    Ungraded findings are not present in the map (neutral ×1.0).

    Returns:
        New list with scores adjusted and re-sorted descending.
        The original list is not mutated.
    """
    if not grades_map:
        return results

    boosted: list[MemoryResult] = []
    for r in results:
        multiplier = _GRADE_MULTIPLIER.get(grades_map.get(r.ref, ""), 1.0)
        if multiplier == 1.0:
            boosted.append(r)
        else:
            boosted.append(replace(r, score=r.score * multiplier))

    boosted.sort(key=lambda r: r.score, reverse=True)
    return boosted


def reciprocal_rank_fusion(
    signal_results: Sequence[Sequence[MemoryResult]],
    k: int = 60,
    feedback_boost: float = 0.1,
    feedback_penalty: float = 0.2,
    signal_names: list[str] | None = None,
) -> list[MemoryResult]:
    """Fuse multiple ranked result lists using Reciprocal Rank Fusion.

    For each result in each signal list:
        rrf_score = 1 / (k + rank + 1)   (rank is 0-based)

    Scores are summed across signals for the same ref (dedup by ref).
    Feedback adjustments are applied after fusion:
        user_score == +1 -> add feedback_boost
        user_score == -1 -> subtract feedback_penalty

    Per-signal scores are stored in result.signals using signal_names
    (falls back to "signal_0", "signal_1", ... when not provided).

    Returns results sorted by total score descending.
    """
    if not signal_results:
        return []

    # Accumulated RRF scores per ref
    accumulated_scores: dict[str, float] = {}
    # Per-signal scores per ref
    per_signal_scores: dict[str, dict[str, float]] = {}
    # First-seen MemoryResult object for each ref (for metadata)
    first_seen: dict[str, MemoryResult] = {}

    for signal_idx, results in enumerate(signal_results):
        name = signal_names[signal_idx] if signal_names and signal_idx < len(signal_names) else f"signal_{signal_idx}"
        for rank, result in enumerate(results):
            rrf_score = 1.0 / (k + rank + 1)
            ref = result.ref

            if ref not in first_seen:
                first_seen[ref] = result
                accumulated_scores[ref] = 0.0
                per_signal_scores[ref] = {}

            accumulated_scores[ref] += rrf_score
            per_signal_scores[ref][name] = rrf_score

    if not first_seen:
        return []

    fused: list[MemoryResult] = []
    for ref, base_result in first_seen.items():
        total = accumulated_scores[ref]

        # Apply user feedback
        if base_result.user_score == 1:
            total += feedback_boost
        elif base_result.user_score == -1:
            total -= feedback_penalty

        fused_result = replace(
            base_result,
            score=total,
            signals=per_signal_scores[ref],
        )
        fused.append(fused_result)

    fused.sort(key=lambda r: r.score, reverse=True)
    return fused
