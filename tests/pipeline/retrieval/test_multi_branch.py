import asyncio
from unittest.mock import AsyncMock, patch
from app.pipeline.retrieval.multi_branch import (
    BranchHit, BranchEvidence, prefetch_branches, BRANCH_QUOTA,
)


def _hit(title: str, branch: str) -> BranchHit:
    return BranchHit(title=title, year=2025, type="tv", tmdb_id=None,
                     top_billed_cast=["Zendaya"], top_billed_genders=[1],
                     overview="test", source="tmdb", branch=branch)


def test_returns_all_three_branches():
    async def _run():
        with patch("app.pipeline.retrieval.branches.media_identification.branch_character_in_universe",
                   new_callable=AsyncMock, return_value=[_hit("Silk", "character_in_universe")]), \
             patch("app.pipeline.retrieval.branches.media_identification.branch_actor_career",
                   new_callable=AsyncMock, return_value=[_hit("Euphoria S3", "actor_career")]), \
             patch("app.pipeline.retrieval.branches.media_identification.branch_genre_signal",
                   new_callable=AsyncMock, return_value=[_hit("Fallout", "genre_signal")]):
            return await prefetch_branches(
                {"primary": "girl", "supporting": "shotgun", "context": "spiderman"},
                "media_identification")
    result = asyncio.run(_run())
    assert set(result.branches.keys()) == {"character_in_universe", "actor_career", "genre_signal"}
    assert result.balanced is True


def test_caps_at_quota():
    async def _run():
        many = [_hit(f"T{i}", "character_in_universe") for i in range(20)]
        with patch("app.pipeline.retrieval.branches.media_identification.branch_character_in_universe",
                   new_callable=AsyncMock, return_value=many), \
             patch("app.pipeline.retrieval.branches.media_identification.branch_actor_career",
                   new_callable=AsyncMock, return_value=[]), \
             patch("app.pipeline.retrieval.branches.media_identification.branch_genre_signal",
                   new_callable=AsyncMock, return_value=[]):
            return await prefetch_branches(
                {"primary": "girl", "supporting": "", "context": "spiderman"},
                "media_identification")
    result = asyncio.run(_run())
    assert len(result.branches["character_in_universe"]) == BRANCH_QUOTA
    assert result.balanced is False


def test_non_media_returns_empty():
    result = asyncio.run(
        prefetch_branches({"primary": "company"}, "person")
    )
    assert result.branches == {}
    assert result.balanced is True


def test_to_prompt_block_has_all_branches():
    evidence = BranchEvidence(branches={
        "character_in_universe": [_hit("Silk", "character_in_universe")],
        "actor_career": [_hit("Euphoria S3", "actor_career")],
        "genre_signal": [_hit("Fallout", "genre_signal")],
    }, balanced=True)
    block = evidence.to_prompt_block()
    assert "Branch A" in block and "Branch B" in block and "Branch C" in block
    assert "Silk" in block and "Euphoria S3" in block
    assert "YOU MUST produce" in block
