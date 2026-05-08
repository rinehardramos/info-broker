"""Tests for Serper Google SERP search node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.serper_search import SerperSearchNode, _search_serper
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = SerperSearchNode()
    assert node.node_type == "serper_search"
    assert node.category == "source"

def test_search_returns_results():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"organic": [
        {"title": "Result 1", "link": "https://example.com", "snippet": "A snippet"},
    ]}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.post.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        results = _search_serper("test query", "fake-key", 10)
    assert len(results) == 1
    assert results[0]["title"] == "Result 1"

def test_execute_with_key():
    with (
        patch("app.pipeline.nodes.serper_search._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.serper_search._search_serper") as m,
    ):
        m.return_value = [{"title": "A", "url": "https://a.com", "snippet": "s", "source": "serper_search"}]
        results = _arun(SerperSearchNode().execute({"query": "test"}, [], CTX))
    assert results[0]["title"] == "A"

def test_execute_no_key():
    with patch("app.pipeline.nodes.serper_search._resolve_api_key", return_value=None):
        results = _arun(SerperSearchNode().execute({"query": "test"}, [], CTX))
    assert results[0].get("error")

def test_execute_no_query():
    results = _arun(SerperSearchNode().execute({}, [], CTX))
    assert results[0].get("error")
