"""Tests for multi-engine meta-search node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from app.pipeline.nodes.multi_search import (
    MultiSearchNode, _search_ddg, _search_serper, _dedup_results, _rank_by_consensus,
)
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = MultiSearchNode()
    assert node.node_type == "multi_search"
    assert node.category == "source"
    assert "query" in node.config_schema["properties"]
    assert "engines" in node.config_schema["properties"]

def test_search_ddg_returns_results():
    with patch("app.pipeline.nodes.multi_search._ddg_search_impl") as m:
        m.return_value = [
            {"title": "A", "url": "https://a.com", "snippet": "desc a"},
            {"title": "B", "url": "https://b.com", "snippet": "desc b"},
        ]
        results = _search_ddg("test query", 5)
    assert len(results) == 2
    assert all(r["engine"] == "ddg" for r in results)

def test_search_serper_returns_results():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"organic": [
        {"title": "C", "link": "https://c.com", "snippet": "desc c"},
    ]}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.post.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        results = _search_serper("test query", "fake-key", 5)
    assert len(results) == 1
    assert results[0]["url"] == "https://c.com"
    assert results[0]["engine"] == "serper"

def test_dedup_merges_same_url():
    results = [
        {"title": "A", "url": "https://a.com/page", "snippet": "s1", "engine": "ddg"},
        {"title": "A Page", "url": "https://a.com/page", "snippet": "s2", "engine": "serper"},
        {"title": "B", "url": "https://b.com", "snippet": "s3", "engine": "ddg"},
    ]
    deduped = _dedup_results(results)
    assert len(deduped) == 2
    a = next(r for r in deduped if "a.com" in r["url"])
    assert len(a["engines"]) == 2

def test_dedup_normalizes_trailing_slash():
    results = [
        {"title": "A", "url": "https://a.com/page/", "snippet": "s1", "engine": "ddg"},
        {"title": "A", "url": "https://a.com/page", "snippet": "s2", "engine": "serper"},
    ]
    deduped = _dedup_results(results)
    assert len(deduped) == 1
    assert deduped[0]["consensus_score"] == 2

def test_rank_by_consensus():
    results = [
        {"url": "a.com", "engines": ["ddg"], "consensus_score": 1},
        {"url": "b.com", "engines": ["ddg", "serper", "brave"], "consensus_score": 3},
        {"url": "c.com", "engines": ["ddg", "serper"], "consensus_score": 2},
    ]
    ranked = _rank_by_consensus(results)
    assert ranked[0]["url"] == "b.com"
    assert ranked[1]["url"] == "c.com"
    assert ranked[2]["url"] == "a.com"

def test_execute_with_ddg_only():
    with patch("app.pipeline.nodes.multi_search._search_ddg") as m:
        m.return_value = [{"title": "A", "url": "https://a.com", "snippet": "s", "engine": "ddg"}]
        results = _arun(MultiSearchNode().execute(
            {"query": "test", "engines": ["ddg"]}, [], CTX))
    assert len(results) >= 1
    assert results[0]["source"] == "multi_search"

def test_execute_no_query_error():
    results = _arun(MultiSearchNode().execute({}, [], CTX))
    assert results[0].get("error")
