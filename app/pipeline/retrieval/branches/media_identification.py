"""Media identification retrieval branches.

Three parallel TMDB search strategies for resolving vague media queries:
  A. character_in_universe  — search by franchise character/universe keywords
  B. actor_career           — search via known franchise actor's recent credits
  C. genre_signal           — broad genre + demographic search, franchise-blind
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.pipeline.retrieval.multi_branch import BranchHit

log = logging.getLogger(__name__)


async def branch_character_in_universe(signals: dict) -> list["BranchHit"]:
    """Branch A: search for titles tied to a franchise character or universe."""
    from app.pipeline.retrieval.multi_branch import BranchHit
    from app.pipeline.retrieval.tmdb_client import search_tv, get_top_cast

    context = signals.get("context", "")
    primary = signals.get("primary", "")
    query = f"{context} {primary}".strip()
    if not query:
        return []

    titles = await search_tv(query)
    hits: list[BranchHit] = []
    for t in titles:
        cast = await get_top_cast(t.tmdb_id, "tv")
        hits.append(BranchHit(
            title=t.title,
            year=t.year,
            type="tv",
            tmdb_id=t.tmdb_id,
            top_billed_cast=[c.get("name", "") for c in cast],
            top_billed_genders=[c.get("gender", 0) for c in cast],
            overview=t.overview,
            source="tmdb",
            branch="character_in_universe",
        ))
    return hits


async def branch_actor_career(signals: dict) -> list["BranchHit"]:
    """Branch B: find recent titles from actors known for the source franchise."""
    from app.pipeline.retrieval.multi_branch import BranchHit
    from app.pipeline.retrieval.tmdb_client import search_franchise_cast, get_person_tv_credits

    context = signals.get("context", "")
    franchise_titles = [context] if context else []
    if not franchise_titles:
        return []

    people = await search_franchise_cast(franchise_titles)
    hits: list[BranchHit] = []
    for person in people[:3]:
        person_id = person.get("id")
        if not person_id:
            continue
        credits = await get_person_tv_credits(person_id)
        for t in credits:
            hits.append(BranchHit(
                title=t.title,
                year=t.year,
                type="tv",
                tmdb_id=t.tmdb_id,
                top_billed_cast=[person.get("name", "")],
                top_billed_genders=[person.get("gender", 0)],
                overview=t.overview,
                source="tmdb",
                branch="actor_career",
                actor_connection=person.get("name"),
            ))
    return hits


async def branch_genre_signal(signals: dict) -> list["BranchHit"]:
    """Branch C: genre + demographic search without franchise assumptions."""
    from app.pipeline.retrieval.multi_branch import BranchHit
    from app.pipeline.retrieval.tmdb_client import search_tv

    primary = signals.get("primary", "")
    supporting = signals.get("supporting", "")
    query = f"{primary} {supporting}".strip()
    if not query:
        return []

    titles = await search_tv(query)
    hits: list[BranchHit] = []
    for t in titles:
        hits.append(BranchHit(
            title=t.title,
            year=t.year,
            type="tv",
            tmdb_id=t.tmdb_id,
            top_billed_cast=[],
            top_billed_genders=[],
            overview=t.overview,
            source="tmdb",
            branch="genre_signal",
        ))
    return hits
