import asyncio
from unittest.mock import AsyncMock, patch


def _arun(coro):
    return asyncio.run(coro)


def test_search_tv_returns_titles():
    from app.pipeline.retrieval.tmdb_client import search_tv
    mock_data = {"results": [{"id": 85552, "name": "Euphoria",
                               "first_air_date": "2025-01-01", "overview": "A teen drama"}]}
    with patch("app.pipeline.retrieval.tmdb_client._resolve_key", return_value="test-key"), \
         patch("app.pipeline.retrieval.tmdb_client._get",
               new_callable=AsyncMock, return_value=mock_data):
        results = _arun(search_tv("euphoria", year_gte=2024))
    assert len(results) == 1
    assert results[0].tmdb_id == 85552
    assert results[0].type == "tv"


def test_get_top_cast_sorted_by_order():
    from app.pipeline.retrieval.tmdb_client import get_top_cast
    mock_data = {"cast": [
        {"id": 1, "name": "Zendaya", "gender": 1, "order": 0},
        {"id": 2, "name": "Eric Dane", "gender": 2, "order": 1},
    ]}
    with patch("app.pipeline.retrieval.tmdb_client._resolve_key", return_value="test-key"), \
         patch("app.pipeline.retrieval.tmdb_client._get",
               new_callable=AsyncMock, return_value=mock_data):
        cast = _arun(get_top_cast(85552, media_type="tv"))
    assert cast[0]["name"] == "Zendaya"
    assert cast[0]["gender"] == 1


def test_no_api_key_returns_empty():
    from app.pipeline.retrieval.tmdb_client import search_tv
    with patch("app.pipeline.retrieval.tmdb_client._resolve_key", return_value=None):
        results = _arun(search_tv("anything", year_gte=2024))
    assert results == []
