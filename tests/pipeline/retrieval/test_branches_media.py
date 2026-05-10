import asyncio
from unittest.mock import AsyncMock, patch
from app.pipeline.retrieval.tmdb_client import TMDBTitle


def _t(tmdb_id=1, title="Test", year=2025, genders=None):
    t = TMDBTitle(tmdb_id=tmdb_id, title=title, year=year, type="tv", overview="overview")
    t.top_cast = ["Actor"]
    t.top_cast_genders = genders or [1]
    return t


def test_branch_a_tagged():
    async def _run():
        from app.pipeline.retrieval.branches.media_identification import branch_character_in_universe
        with patch("app.pipeline.retrieval.branches.media_identification.search_tv",
                   new_callable=AsyncMock, return_value=[_t(1, "Silk", 2025, [1])]), \
             patch("app.pipeline.retrieval.branches.media_identification.get_top_cast",
                   new_callable=AsyncMock,
                   return_value=[{"name": "Cindy Moon", "gender": 1, "order": 0}]):
            return await branch_character_in_universe(
                {"primary": "girl", "supporting": "shotgun", "context": "spiderman"})
    result = asyncio.run(_run())
    assert all(h.branch == "character_in_universe" for h in result)


def test_branch_b_actor_connection():
    async def _run():
        from app.pipeline.retrieval.branches.media_identification import branch_actor_career
        zendaya = {"id": 505710, "name": "Zendaya", "gender": 1, "popularity": 95}
        with patch("app.pipeline.retrieval.branches.media_identification.search_franchise_cast",
                   new_callable=AsyncMock, return_value=[zendaya]), \
             patch("app.pipeline.retrieval.branches.media_identification.get_person_tv_credits",
                   new_callable=AsyncMock,
                   return_value=[_t(85552, "Euphoria", 2025, [1])]), \
             patch("app.pipeline.retrieval.branches.media_identification.get_top_cast",
                   new_callable=AsyncMock,
                   return_value=[{"name": "Zendaya", "gender": 1, "order": 0}]):
            return await branch_actor_career(
                {"primary": "girl", "supporting": "shotgun", "context": "spiderman"})
    result = asyncio.run(_run())
    assert len(result) >= 1
    assert "Zendaya" in result[0].actor_connection


def test_branch_c_tagged():
    async def _run():
        from app.pipeline.retrieval.branches.media_identification import branch_genre_signal
        with patch("app.pipeline.retrieval.branches.media_identification.search_tv",
                   new_callable=AsyncMock, return_value=[_t(209876, "Fallout", 2024, [1])]), \
             patch("app.pipeline.retrieval.branches.media_identification.get_top_cast",
                   new_callable=AsyncMock,
                   return_value=[{"name": "Ella Purnell", "gender": 1, "order": 0}]):
            return await branch_genre_signal(
                {"primary": "girl", "supporting": "man has a shotgun", "context": "spiderman"})
    result = asyncio.run(_run())
    assert all(h.branch == "genre_signal" for h in result)
