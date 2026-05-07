"""Tests for phone OSINT node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.phone_osint import PhoneOsintNode, _lookup_numverify
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = PhoneOsintNode()
    assert node.node_type == "phone_osint"
    assert node.category == "enrich"

def test_lookup_numverify_success():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "valid": True, "number": "14155552671",
        "country_code": "US", "country_name": "United States",
        "carrier": "Verizon", "line_type": "mobile"
    }
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _lookup_numverify("+14155552671", "fake-key")
    assert result["carrier"] == "Verizon"
    assert result["line_type"] == "mobile"
    assert result["country"] == "United States"

def test_execute_with_api_key():
    with (
        patch("app.pipeline.nodes.phone_osint._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.phone_osint._lookup_numverify") as m,
    ):
        m.return_value = {"phone": "+1234", "carrier": "AT&T", "line_type": "mobile",
            "country": "US", "valid": True, "source": "numverify", "reason": "r"}
        results = _arun(PhoneOsintNode().execute({"phone": "+1234"}, [], CTX))
    assert results[0]["carrier"] == "AT&T"

def test_execute_no_key_returns_basic():
    with patch("app.pipeline.nodes.phone_osint._resolve_api_key", return_value=None):
        results = _arun(PhoneOsintNode().execute({"phone": "+14155552671"}, [], CTX))
    assert results[0]["phone"] == "+14155552671"
    assert "source" in results[0]

def test_execute_from_inputs():
    with (
        patch("app.pipeline.nodes.phone_osint._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.phone_osint._lookup_numverify") as m,
    ):
        m.return_value = {"phone": "+5678", "carrier": "T-Mo", "source": "numverify", "reason": "r"}
        results = _arun(PhoneOsintNode().execute({}, [{"phone": "+5678"}], CTX))
    assert results[0]["phone"] == "+5678"

def test_execute_no_phone_error():
    results = _arun(PhoneOsintNode().execute({}, [], CTX))
    assert results[0].get("error")
