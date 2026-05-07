"""Tests for document search (Google Dorking) node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.document_search import DocumentSearchNode, _build_dork_queries
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = DocumentSearchNode()
    assert node.node_type == "document_search"
    assert node.category == "source"

def test_build_dork_queries_with_name():
    queries = _build_dork_queries("John Doe", None, ["pdf", "docx"])
    assert any("filetype:pdf" in q for q in queries)
    assert any("John Doe" in q for q in queries)

def test_build_dork_queries_with_site():
    queries = _build_dork_queries("report", "acme.com", ["pdf"])
    assert any("site:acme.com" in q for q in queries)

def test_execute_returns_results():
    with patch("app.pipeline.nodes.document_search._run_dork_search") as m:
        m.return_value = [
            {"title": "John Doe CV", "url": "https://example.com/cv.pdf",
             "filetype": "pdf", "snippet": "curriculum vitae"}
        ]
        results = _arun(DocumentSearchNode().execute(
            {"query": "John Doe", "filetypes": ["pdf"]}, [], CTX))
    assert len(results) >= 1
    assert results[0]["filetype"] == "pdf"

def test_execute_from_inputs():
    with patch("app.pipeline.nodes.document_search._run_dork_search") as m:
        m.return_value = []
        results = _arun(DocumentSearchNode().execute(
            {}, [{"query": "Test Person"}], CTX))
    assert len(results) >= 1

def test_execute_no_query_error():
    results = _arun(DocumentSearchNode().execute({}, [], CTX))
    assert results[0].get("error")
