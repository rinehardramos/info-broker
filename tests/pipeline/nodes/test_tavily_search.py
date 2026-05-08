"""Tests for Tavily AI search node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.tavily_search import TavilySearchNode, _search_tavily
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = TavilySearchNode()
    assert node.node_type == "tavily_search"
    assert node.category == "source"

def test_search_returns_results():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"results": [
        {"title": "Result 1", "url": "https://example.com", "content": "Detailed content", "score": 0.95},
    ]}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.post.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        results = _search_tavily("test query", "fake-key", 5)
    assert len(results) == 1
    assert results[0]["title"] == "Result 1"
    assert results[0]["relevance_score"] == 0.95

def test_execute_with_key():
    with (
        patch("app.pipeline.nodes.tavily_search._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.tavily_search._search_tavily") as m,
    ):
        m.return_value = [{"title": "A", "url": "https://a.com", "content": "c", "source": "tavily_search"}]
        results = _arun(TavilySearchNode().execute({"query": "test"}, [], CTX))
    assert results[0]["title"] == "A"

def test_execute_no_key():
    with patch("app.pipeline.nodes.tavily_search._resolve_api_key", return_value=None):
        results = _arun(TavilySearchNode().execute({"query": "test"}, [], CTX))
    assert results[0].get("error")

def test_execute_no_query():
    results = _arun(TavilySearchNode().execute({}, [], CTX))
    assert results[0].get("error")
