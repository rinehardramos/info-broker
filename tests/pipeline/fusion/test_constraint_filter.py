import asyncio
from unittest.mock import AsyncMock, patch
from app.pipeline.fusion.constraint_filter import (
    passes_lead_constraint, extract_primary_signal, PrimarySignal,
)


def test_girl_is_female():
    assert extract_primary_signal("girl").gender == "female"


def test_unknown_word():
    assert extract_primary_signal("detective").gender == "unknown"


def test_spider_noir_blocked():
    async def _run():
        with patch("app.pipeline.fusion.constraint_filter.get_top_cast",
                   new_callable=AsyncMock,
                   return_value=[{"name": "Nicolas Cage", "gender": 2, "order": 0}]):
            return await passes_lead_constraint(
                "Spider-Noir", 12345, "tv",
                PrimarySignal(entity="girl", gender="female", role="lead"))
    result = asyncio.run(_run())
    assert result.passed is False
    assert "Nicolas Cage" in result.reason


def test_euphoria_passes():
    async def _run():
        with patch("app.pipeline.fusion.constraint_filter.get_top_cast",
                   new_callable=AsyncMock,
                   return_value=[{"name": "Zendaya", "gender": 1, "order": 0}]):
            return await passes_lead_constraint(
                "Euphoria", 85552, "tv",
                PrimarySignal(entity="girl", gender="female", role="lead"))
    result = asyncio.run(_run())
    assert result.passed is True


def test_no_tmdb_id_passes():
    result = asyncio.run(passes_lead_constraint(
        "Unknown", None, "tv",
        PrimarySignal(entity="girl", gender="female", role="lead")))
    assert result.passed is True
    assert "unverified" in str(result.evidence)


def test_unknown_gender_always_passes():
    result = asyncio.run(passes_lead_constraint(
        "Any", 99, "tv",
        PrimarySignal(entity="detective", gender="unknown", role="lead")))
    assert result.passed is True


def test_spider_noir_scores_low():
    from app.pipeline.fusion.scorecard import query_explanatory_score
    candidate = {"title": "Spider-Noir", "year": 2026,
                 "top_billed_genders": [2], "overview": "1930s detective shotgun",
                 "branches": ["character_in_universe"]}
    score = query_explanatory_score(
        candidate, {"primary": "girl", "supporting": "shotgun", "context": "spiderman"})
    assert score <= 0.55  # PRIMARY fails (no +0.40)


def test_euphoria_scores_high():
    import datetime
    from app.pipeline.fusion.scorecard import query_explanatory_score
    candidate = {"title": "Euphoria", "year": datetime.date.today().year,
                 "top_billed_genders": [1], "overview": "teen drama violence gun scenes",
                 "branches": ["actor_career", "genre_signal"]}
    score = query_explanatory_score(
        candidate, {"primary": "girl", "supporting": "shotgun", "context": "spiderman"})
    assert score >= 0.55  # PRIMARY +0.40, recency +0.10, multi-branch +0.10
