"""Tests for email enumerator node."""
from __future__ import annotations
import asyncio
from unittest.mock import patch
from app.pipeline.nodes.email_enumerator import EmailEnumeratorNode, _generate_candidates
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    assert EmailEnumeratorNode().node_type == "email_enumerator"

def test_generate_basic():
    cands = _generate_candidates("John", "Doe", ["gmail.com"])
    assert "john.doe@gmail.com" in cands
    assert "johndoe@gmail.com" in cands
    assert "j.doe@gmail.com" in cands
    assert "jdoe@gmail.com" in cands
    assert "doe.john@gmail.com" in cands

def test_generate_multi_provider():
    cands = _generate_candidates("Jane", "Smith", ["gmail.com", "yahoo.com"])
    gmail = sum(1 for c in cands if c.endswith("@gmail.com"))
    yahoo = sum(1 for c in cands if c.endswith("@yahoo.com"))
    assert gmail > 0 and gmail == yahoo

def test_generate_defaults():
    cands = _generate_candidates("A", "B", [])
    assert any(c.endswith("@gmail.com") for c in cands)

def test_execute_verifies():
    with patch("app.pipeline.nodes.email_enumerator._verify_email") as m:
        m.side_effect = lambda e, t: e == "john.doe@gmail.com"
        results = _arun(EmailEnumeratorNode().execute(
            {"first_name": "John", "last_name": "Doe",
             "providers": ["gmail.com"], "max_candidates": 10}, [], CTX))
    verified = [r for r in results if r.get("exists") is True]
    assert len(verified) >= 1

def test_execute_from_inputs():
    with patch("app.pipeline.nodes.email_enumerator._verify_email", return_value=None):
        results = _arun(EmailEnumeratorNode().execute(
            {}, [{"first_name": "Alice", "last_name": "Wonder"}], CTX))
    assert len(results) >= 1
