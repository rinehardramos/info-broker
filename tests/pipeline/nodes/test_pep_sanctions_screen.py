"""Tests for PEP/sanctions screening node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.pep_sanctions_screen import PepSanctionsScreenNode, _search_opensanctions, _search_web_fallback
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = PepSanctionsScreenNode()
    assert node.node_type == "pep_sanctions_screen"
    assert node.category == "enrich"

def test_opensanctions_match():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"responses": {"default": {"results": [
        {"id": "Q123", "caption": "John Doe", "datasets": ["us_ofac_sdn"],
         "properties": {"topics": [["sanction"]]}}
    ]}}}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _search_opensanctions("John Doe", "fake-key")
    assert result["matched"] is True
    assert len(result["matches"]) == 1

def test_opensanctions_no_match():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"responses": {"default": {"results": []}}}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _search_opensanctions("Clean Person", "fake-key")
    assert result["matched"] is False

def test_execute_uses_api():
    with (
        patch("app.pipeline.nodes.pep_sanctions_screen._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.pep_sanctions_screen._search_opensanctions") as m,
    ):
        m.return_value = {"name": "John", "matched": False, "matches": [], "source": "opensanctions", "reason": "r"}
        results = _arun(PepSanctionsScreenNode().execute({"name": "John"}, [], CTX))
    assert results[0]["matched"] is False

def test_execute_fallback_no_key():
    with (
        patch("app.pipeline.nodes.pep_sanctions_screen._resolve_api_key", return_value=None),
        patch("app.pipeline.nodes.pep_sanctions_screen._search_web_fallback") as m,
    ):
        m.return_value = {"name": "John", "matched": None, "matches": [], "source": "web_search", "reason": "r"}
        results = _arun(PepSanctionsScreenNode().execute({"name": "John"}, [], CTX))
    assert results[0]["source"] == "web_search"

def test_execute_no_name_error():
    results = _arun(PepSanctionsScreenNode().execute({}, [], CTX))
    assert results[0].get("error")
