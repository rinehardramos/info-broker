"""Tests for HIBP breach lookup node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.hibp_lookup import HibpLookupNode, _fetch_hibp_api
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = HibpLookupNode()
    assert node.node_type == "hibp_lookup"
    assert node.category == "enrich"

def test_fetch_api_breached():
    resp = MagicMock(status_code=200)
    resp.json.return_value = [
        {"Name": "LinkedIn", "BreachDate": "2021-06-22", "DataClasses": ["Email addresses"]},
    ]
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _fetch_hibp_api("t@x.com", "key")
    assert result["breached"] is True
    assert result["breaches"][0]["name"] == "LinkedIn"

def test_fetch_api_not_breached():
    resp = MagicMock(status_code=404)
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _fetch_hibp_api("c@x.com", "key")
    assert result["breached"] is False

def test_execute_uses_api():
    with (
        patch("app.pipeline.nodes.hibp_lookup._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.hibp_lookup._fetch_hibp_api") as m,
    ):
        m.return_value = {"email": "t@x.com", "breached": True,
            "breaches": [{"name": "T", "date": "2023", "data_classes": []}],
            "source": "hibp_api", "reason": "r"}
        results = _arun(HibpLookupNode().execute({"email": "t@x.com"}, [], CTX))
    assert results[0]["breached"] is True

def test_execute_fallback_no_key():
    with (
        patch("app.pipeline.nodes.hibp_lookup._resolve_api_key", return_value=None),
        patch("app.pipeline.nodes.hibp_lookup._fetch_hibp_web") as m,
    ):
        m.return_value = {"email": "t@x.com", "breached": None,
            "breaches": [], "source": "web_search", "reason": "r"}
        results = _arun(HibpLookupNode().execute({"email": "t@x.com"}, [], CTX))
    assert results[0]["source"] == "web_search"

def test_execute_from_inputs():
    with (
        patch("app.pipeline.nodes.hibp_lookup._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.hibp_lookup._fetch_hibp_api") as m,
    ):
        m.return_value = {"email": "a@b.com", "breached": False,
            "breaches": [], "source": "hibp_api", "reason": "r"}
        results = _arun(HibpLookupNode().execute({}, [{"email": "a@b.com"}], CTX))
    assert results[0]["email"] == "a@b.com"
