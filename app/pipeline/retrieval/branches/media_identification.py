"""Three retrieval branches for media_identification queries.

A (character_in_universe): female character IS in Spider-Man universe
B (actor_career):          actress FROM Spider-Man films, different new series
C (genre_signal):          female lead + gritty action, franchise-blind
"""
from __future__ import annotations

import asyncio
import logging

from app.pipeline.retrieval.multi_branch import BranchHit, BRANCH_QUOTA
from app.pipeline.retrieval.tmdb_client import (
    TMDBTitle, search_tv, get_top_cast, get_person_tv_credits, search_franchise_cast,
)

log = logging.getLogger(__name__)

_YEAR_GTE = 2024
_SPIDER_MAN_FRANCHISE = [
    "Spider-Man: No Way Home",
    "Spider-Man: Across the Spider-Verse",
    "Spider-Man: Beyond the Spider-Verse",
    "Madame Web",
    "Kraven the Hunter",
]


def _to_hit(title: TMDBTitle, branch: str, cast: list[dict] | None = None,
            actor_connection: str | None = None) -> BranchHit:
    names   = [c.get("name", "") for c in (cast or [])][:3]
    genders = [c.get("gender", 0) for c in (cast or [])][:3]
    return BranchHit(
        title=title.title, year=title.year, type=title.type,
        tmdb_id=title.tmdb_id, top_billed_cast=names, top_billed_genders=genders,
        overview=title.overview, source="tmdb", branch=branch,
        actor_connection=actor_connection,
    )


async def branch_character_in_universe(signals: dict) -> list[BranchHit]:
    """Branch A: female character IS in Spider-Man universe."""
    context = signals.get("context", "spiderman")
    queries = [
        f"{context} female lead series",
        f"new {context} series girl protagonist",
        "spider woman silk series 2025",
    ]
    results_lists = await asyncio.gather(
        *[search_tv(q, year_gte=_YEAR_GTE) for q in queries], return_exceptions=True)
    hits: list[BranchHit] = []
    seen: set[int] = set()
    for results in results_lists:
        if isinstance(results, Exception):
            continue
        for title in results:
            if title.tmdb_id and title.tmdb_id not in seen:
                seen.add(title.tmdb_id)
                cast = await get_top_cast(title.tmdb_id, media_type="tv")
                hits.append(_to_hit(title, "character_in_universe", cast))
                if len(hits) >= BRANCH_QUOTA:
                    return hits
    return hits[:BRANCH_QUOTA]


async def branch_actor_career(signals: dict) -> list[BranchHit]:
    """Branch B: actress FROM Spider-Man films in a DIFFERENT new series."""
    franchise_cast = await search_franchise_cast(_SPIDER_MAN_FRANCHISE)
    if not franchise_cast:
        return []
    credits_lists = await asyncio.gather(
        *[get_person_tv_credits(p["id"], year_gte=_YEAR_GTE) for p in franchise_cast[:5]],
        return_exceptions=True,
    )
    hits: list[BranchHit] = []
    for person, credits in zip(franchise_cast[:5], credits_lists):
        if isinstance(credits, Exception):
            continue
        for credit in credits[:2]:
            if credit.tmdb_id:
                cast = await get_top_cast(credit.tmdb_id, media_type="tv")
                hits.append(_to_hit(
                    credit, "actor_career", cast,
                    actor_connection=f"{person.get('name', '')} (from Spider-Man franchise)",
                ))
        if len(hits) >= BRANCH_QUOTA:
            break
    return hits[:BRANCH_QUOTA]


async def branch_genre_signal(signals: dict) -> list[BranchHit]:
    """Branch C: female lead + gritty action, franchise-blind."""
    primary = signals.get("primary", "girl")
    queries = [
        f"new series {primary} protagonist gritty action drama 2025",
        "new series young woman lead thriller 2025",
        "2025 streaming series female lead action drama",
    ]
    results_lists = await asyncio.gather(
        *[search_tv(q, year_gte=_YEAR_GTE) for q in queries], return_exceptions=True)
    hits: list[BranchHit] = []
    seen: set[int] = set()
    for results in results_lists:
        if isinstance(results, Exception):
            continue
        for title in results:
            if title.tmdb_id and title.tmdb_id not in seen:
                seen.add(title.tmdb_id)
                cast = await get_top_cast(title.tmdb_id, media_type="tv")
                hits.append(_to_hit(title, "genre_signal", cast))
                if len(hits) >= BRANCH_QUOTA:
                    return hits
    return hits[:BRANCH_QUOTA]
