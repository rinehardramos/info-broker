"""Tests for OpenAlex academic search node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.openalex_search import OpenAlexSearchNode, _search_works
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = OpenAlexSearchNode()
    assert node.node_type == "openalex_search"
    assert node.category == "source"

def test_search_works_returns_papers():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"results": [
        {"id": "W123", "title": "A Study on AI", "publication_year": 2025,
         "doi": "10.1234/test", "cited_by_count": 42,
         "authorships": [{"author": {"display_name": "John Doe"}}],
         "primary_location": {"source": {"display_name": "Nature"}}},
    ]}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        results = _search_works("artificial intelligence", 5)
    assert len(results) == 1
    assert results[0]["title"] == "A Study on AI"
    assert results[0]["citations"] == 42

def test_execute_searches():
    with patch("app.pipeline.nodes.openalex_search._search_works") as m:
        m.return_value = [{"title": "Paper", "citations": 10, "source": "openalex_search"}]
        results = _arun(OpenAlexSearchNode().execute({"query": "CRISPR"}, [], CTX))
    assert results[0]["title"] == "Paper"

def test_execute_no_query():
    results = _arun(OpenAlexSearchNode().execute({}, [], CTX))
    assert results[0].get("error")
