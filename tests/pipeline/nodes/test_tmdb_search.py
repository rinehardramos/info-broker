"""Tests for TMDB search node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.tmdb_search import TmdbSearchNode, _search_multi
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = TmdbSearchNode()
    assert node.node_type == "tmdb_search"
    assert node.category == "source"

def test_search_multi_returns_results():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"results": [
        {"id": 123, "media_type": "movie", "title": "Test Movie",
         "overview": "A test movie", "release_date": "2025-01-01", "vote_average": 7.5},
    ]}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        results = _search_multi("test movie", "fake-key", 10)
    assert len(results) == 1
    assert results[0]["title"] == "Test Movie"
    assert results[0]["media_type"] == "movie"

def test_execute_with_key():
    with (
        patch("app.pipeline.nodes.tmdb_search._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.tmdb_search._search_multi") as m,
    ):
        m.return_value = [{"title": "Film", "media_type": "movie", "source": "tmdb_search"}]
        results = _arun(TmdbSearchNode().execute({"query": "film"}, [], CTX))
    assert results[0]["title"] == "Film"

def test_execute_no_key():
    with patch("app.pipeline.nodes.tmdb_search._resolve_api_key", return_value=None):
        results = _arun(TmdbSearchNode().execute({"query": "test"}, [], CTX))
    assert results[0].get("error")

def test_execute_no_query():
    results = _arun(TmdbSearchNode().execute({}, [], CTX))
    assert results[0].get("error")
