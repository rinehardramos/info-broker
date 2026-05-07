"""Tests for reverse identity lookup node."""
from __future__ import annotations
import asyncio
from unittest.mock import patch
from app.pipeline.nodes.reverse_lookup import ReverseLookupNode, _detect_type
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = ReverseLookupNode()
    assert node.node_type == "reverse_lookup"
    assert node.category == "enrich"

def test_detect_email():
    assert _detect_type("john@example.com") == "email"

def test_detect_phone():
    assert _detect_type("09171234567") == "phone"

def test_detect_username():
    assert _detect_type("johndoe42") == "username"

def test_execute_auto_detects():
    with patch("app.pipeline.nodes.reverse_lookup._web_search_reverse") as m:
        m.return_value = {"query": "a@b.com", "query_type": "email",
            "identities": [], "source": "web_search", "reason": "r"}
        results = _arun(ReverseLookupNode().execute({"query": "a@b.com"}, [], CTX))
    assert results[0]["query_type"] == "email"

def test_execute_from_inputs():
    with patch("app.pipeline.nodes.reverse_lookup._web_search_reverse") as m:
        m.return_value = {"query": "x@y.com", "query_type": "email",
            "identities": [{"name": "Test", "platform": "linkedin", "confidence": 70}],
            "source": "web_search", "reason": "r"}
        results = _arun(ReverseLookupNode().execute({}, [{"email": "x@y.com"}], CTX))
    assert results[0]["identities"][0]["name"] == "Test"

def test_execute_no_query_error():
    results = _arun(ReverseLookupNode().execute({}, [], CTX))
    assert results[0].get("error")
