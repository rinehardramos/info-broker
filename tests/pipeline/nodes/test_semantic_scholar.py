"""Tests for Semantic Scholar search node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.semantic_scholar import SemanticScholarNode, _search_papers
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = SemanticScholarNode()
    assert node.node_type == "semantic_scholar"
    assert node.category == "source"

def test_search_papers_returns_results():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"data": [
        {"paperId": "abc123", "title": "Deep Learning Survey",
         "year": 2025, "citationCount": 500, "abstract": "A comprehensive survey...",
         "authors": [{"name": "Jane Smith"}],
         "externalIds": {"DOI": "10.5555/test"}},
    ]}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        results = _search_papers("deep learning", 5)
    assert len(results) == 1
    assert results[0]["title"] == "Deep Learning Survey"
    assert results[0]["citations"] == 500

def test_execute_searches():
    with patch("app.pipeline.nodes.semantic_scholar._search_papers") as m:
        m.return_value = [{"title": "Paper", "citations": 10, "source": "semantic_scholar"}]
        results = _arun(SemanticScholarNode().execute({"query": "transformers"}, [], CTX))
    assert results[0]["title"] == "Paper"

def test_execute_no_query():
    results = _arun(SemanticScholarNode().execute({}, [], CTX))
    assert results[0].get("error")
