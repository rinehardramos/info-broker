"""Fused retriever — orchestrates 5 signals in parallel and merges via RRF."""

from __future__ import annotations

import asyncio
import logging

from app.memory.models import MemoryResult
from app.memory.rrf import reciprocal_rank_fusion
from app.memory.signals import (
    bm25_search,
    entity_search,
    feedback_search,
    semantic_search,
    temporal_search,
)

log = logging.getLogger(__name__)

_SIGNAL_NAMES = ["semantic", "bm25", "entity", "temporal", "feedback"]


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
    return fused[:limit]
