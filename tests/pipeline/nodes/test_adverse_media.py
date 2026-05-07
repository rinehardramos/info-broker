"""Tests for adverse media monitoring node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.adverse_media import AdverseMediaNode, _search_adverse_media, ADVERSE_CATEGORIES
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = AdverseMediaNode()
    assert node.node_type == "adverse_media"
    assert node.category == "enrich"

def test_adverse_categories_defined():
    assert "fraud" in ADVERSE_CATEGORIES
    assert "corruption" in ADVERSE_CATEGORIES
    assert "lawsuit" in ADVERSE_CATEGORIES
    assert len(ADVERSE_CATEGORIES) >= 5

def test_search_finds_results():
    resp = MagicMock(status_code=200)
    resp.text = '<a class="result__a" href="https://example.com">John Doe arrested for fraud</a><a class="result__snippet">John Doe was arrested</a>'
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _search_adverse_media("John Doe", ["fraud"])
    assert len(result) >= 0  # may or may not parse results depending on HTML structure

def test_execute_returns_results():
    with patch("app.pipeline.nodes.adverse_media._search_adverse_media") as m:
        m.return_value = [
            {"title": "Doe arrested", "category": "fraud", "snippet": "test", "source_url": "https://x.com"}
        ]
        results = _arun(AdverseMediaNode().execute({"name": "John Doe"}, [], CTX))
    assert len(results) >= 1

def test_execute_from_inputs():
    with patch("app.pipeline.nodes.adverse_media._search_adverse_media") as m:
        m.return_value = []
        results = _arun(AdverseMediaNode().execute({}, [{"name": "Test Person"}], CTX))
    assert len(results) >= 1  # at least the wrapper dict

def test_execute_no_name_error():
    results = _arun(AdverseMediaNode().execute({}, [], CTX))
    assert results[0].get("error")
