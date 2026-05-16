"""Fused retriever — orchestrates 5 signals in parallel and merges via RRF."""

from __future__ import annotations

import asyncio
import logging

from app.memory.models import MemoryResult
from app.memory.rrf import reciprocal_rank_fusion, apply_grade_boost
from app.memory.signals import (
    bm25_search,
    entity_search,
    feedback_search,
    semantic_search,
    skill_search,
    temporal_search,
)

log = logging.getLogger(__name__)

_SIGNAL_NAMES = ["semantic", "bm25", "entity", "temporal", "feedback"]


_GRADE_PRIORITY = {"A": 4, "B": 3, "C": 2, "D": 1}


def _load_grades_map(user_id: str) -> dict[str, str]:
    """Return finding_id -> best-grade letter for findings graded by any user.

    "Best" means the grade with the highest boost multiplier (A > B > C > D).
    Uses a simple per-finding MAX based on priority ordering.
    Returns an empty dict on any DB error so retrieval degrades gracefully.
    """
    try:
        from app.routers.v3.db import fetch_all
        rows = fetch_all(
            "SELECT finding_id, grade FROM findings_grades",
            (),
        )
        grades_map: dict[str, str] = {}
        for row in rows:
            fid = row["finding_id"]
            g = row["grade"]
            existing = grades_map.get(fid)
            if existing is None or _GRADE_PRIORITY.get(g, 0) > _GRADE_PRIORITY.get(existing, 0):
                grades_map[fid] = g
        return grades_map
    except Exception:
        return {}


def _track_access(run_ids: list[str]) -> None:
    """Batch-update last_accessed_at for accessed observations (1-hour debounce)."""
    if not run_ids:
        return
    try:
        from app.routers.v3.db import execute
        # Update entity_observations linked to these run_ids
        # Only update if last_accessed_at is null or >1 hour ago (debounce)
        placeholders = ",".join(["%s"] * len(run_ids))
        execute(
            f"""UPDATE entity_observations
                SET last_accessed_at = now()
                WHERE source_run_id IN ({placeholders})
                  AND (last_accessed_at IS NULL OR last_accessed_at < now() - interval '1 hour')""",
            tuple(run_ids),
        )
    except Exception:
        pass  # Non-critical, don't break retrieval


async def fused_retrieve(
    query: str,
    limit: int = 20,
    time_filter: tuple | None = None,
    entity_types: list[str] | None = None,
    user_id: str | None = None,
) -> list[MemoryResult]:
    """Run all 5 retrieval signals in parallel and fuse results via RRF.

    Args:
        query: The search query string.
        limit: Maximum number of results to return.
        time_filter: Optional (from_dt, to_dt) tuple forwarded to temporal_search.
        entity_types: Reserved for future entity-type filtering.
        user_id: Reserved for future per-user scoping.

    Returns:
        Up to `limit` MemoryResult objects sorted by fused RRF score descending.
    """
    raw = await asyncio.gather(
        semantic_search(query),
        bm25_search(query),
        entity_search(query),
        temporal_search(query, time_filter=time_filter),
        feedback_search(query),
        return_exceptions=True,
    )

    clean: list[list[MemoryResult]] = []
    for name, result in zip(_SIGNAL_NAMES, raw):
        if isinstance(result, Exception):
            log.warning("Signal '%s' raised an exception: %s", name, result)
            clean.append([])
        else:
            clean.append(result)

    fused = reciprocal_rank_fusion(
        clean,
        k=60,
        signal_names=_SIGNAL_NAMES,
    )
    # Apply user grade boosts if a user_id was supplied
    if user_id:
        grades_map = _load_grades_map(user_id)
        fused = apply_grade_boost(fused, grades_map)

    results = fused[:limit]

    # Track access for lifecycle management
    _track_access([r.run_id for r in results if r.run_id])

    return results


async def fused_retrieve_with_skills(
    query: str,
    limit: int = 20,
    skill_limit: int = 3,
    time_filter: tuple | None = None,
) -> tuple[list[MemoryResult], list[MemoryResult]]:
    """Run 6 signals: 5 finding signals + 1 skill signal.

    Returns (findings, skills) as separate lists.
    """
    signal_results = await asyncio.gather(
        semantic_search(query, limit=50),
        bm25_search(query, limit=50),
        entity_search(query, limit=30),
        temporal_search(query, limit=30, time_filter=time_filter),
        feedback_search(query, limit=50),
        skill_search(query, limit=skill_limit),
        return_exceptions=True,
    )

    # Separate skills (index 5) from findings (indices 0-4)
    skill_results: list[MemoryResult] = (
        signal_results[5]
        if not isinstance(signal_results[5], Exception)
        else []
    )

    finding_signals: list[list[MemoryResult]] = []
    for i, result in enumerate(signal_results[:5]):
        if isinstance(result, Exception):
            log.warning("Signal %s failed: %s", _SIGNAL_NAMES[i], result)
            finding_signals.append([])
        else:
            finding_signals.append(result)

    fused_findings = reciprocal_rank_fusion(
        finding_signals,
        k=60,
        signal_names=_SIGNAL_NAMES,
    )

    return fused_findings[:limit], skill_results
