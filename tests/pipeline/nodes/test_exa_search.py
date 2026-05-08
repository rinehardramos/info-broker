"""Tests for Exa neural search node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.exa_search import ExaSearchNode, _search_exa
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = ExaSearchNode()
    assert node.node_type == "exa_search"
    assert node.category == "source"

def test_search_returns_results():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"results": [
        {"title": "Neural Search Paper", "url": "https://example.com/paper",
         "text": "This paper explores...", "score": 0.92,
         "publishedDate": "2025-06-01"},
    ]}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.post.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        results = _search_exa("neural search techniques", "fake-key", 5)
    assert len(results) == 1
    assert results[0]["title"] == "Neural Search Paper"
    assert results[0]["score"] == 0.92

def test_execute_with_key():
    with (
        patch("app.pipeline.nodes.exa_search._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.exa_search._search_exa") as m,
    ):
        m.return_value = [{"title": "A", "url": "https://a.com", "source": "exa_search"}]
        results = _arun(ExaSearchNode().execute({"query": "test"}, [], CTX))
    assert results[0]["title"] == "A"

def test_execute_no_key():
    with patch("app.pipeline.nodes.exa_search._resolve_api_key", return_value=None):
        results = _arun(ExaSearchNode().execute({"query": "test"}, [], CTX))
    assert results[0].get("error")

def test_execute_no_query():
    results = _arun(ExaSearchNode().execute({}, [], CTX))
    assert results[0].get("error")
