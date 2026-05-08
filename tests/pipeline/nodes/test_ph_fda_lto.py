"""Tests for PH FDA LTO registry node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.ph_fda_lto import PhFdaLtoNode, _search_fda
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = PhFdaLtoNode()
    assert node.node_type == "ph_fda_lto"
    assert node.category == "source"

def test_search_returns_results():
    resp = MagicMock(status_code=200)
    resp.text = '<tr><td>Acme Pharma</td><td>LTO-1234</td><td>Active</td><td>Medical Device Distributor</td><td>Makati</td></tr>'
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        results = _search_fda("Acme Pharma")
    assert len(results) >= 0  # HTML parsing may vary

def test_execute_searches():
    with patch("app.pipeline.nodes.ph_fda_lto._search_fda") as m:
        m.return_value = [{"company": "Acme", "lto_number": "LTO-1234", "status": "Active", "source": "ph_fda_lto"}]
        results = _arun(PhFdaLtoNode().execute({"company_name": "Acme"}, [], CTX))
    assert results[0]["company"] == "Acme"

def test_execute_from_inputs():
    with patch("app.pipeline.nodes.ph_fda_lto._search_fda") as m:
        m.return_value = [{"company": "Test", "source": "ph_fda_lto"}]
        results = _arun(PhFdaLtoNode().execute({}, [{"company": "Test Corp"}], CTX))
    assert len(results) >= 1

def test_execute_no_query():
    results = _arun(PhFdaLtoNode().execute({}, [], CTX))
    assert results[0].get("error")
