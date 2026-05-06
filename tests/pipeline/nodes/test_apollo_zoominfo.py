"""Unit tests for the ApolloZoominfoNode."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.pipeline.nodes.apollo_zoominfo import (
    ApolloZoominfoNode,
    _call_apollo,
    _map_person,
    _map_company,
)
from app.pipeline.nodes.base import RunContext


def _ctx() -> RunContext:
    return RunContext(user_id="u1", run_id="r1", node_id="n1")


def _arun(coro):
    return asyncio.run(coro)


def _ok_resp(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _err_resp(code: int, msg: str = "") -> MagicMock:
    import httpx
    resp = MagicMock()
    resp.status_code = code
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        msg or f"HTTP {code}", request=MagicMock(), response=resp
    )
    return resp


class _FakeClient:
    """Replaces httpx.Client; each call returns self as context manager."""

    def __init__(self, inner: MagicMock):
        self._inner = inner

    def __call__(self, **kwargs):
        return self

    def __enter__(self):
        return self._inner

    def __exit__(self, *a):
        return False


# ---------------------------------------------------------------------------
# _map_person / _map_company
# ---------------------------------------------------------------------------

def test_map_person_full():
    item = {
        "name": "Jane Doe",
        "title": "CTO",
        "organization": {"name": "Acme Corp"},
        "email": "jane@example.com",
        "linkedin_url": "li.example.com/in/janedoe",
        "phone_numbers": [{"raw_number": "+63-[REDACTED:us-phone:12ch:hash=c6d4d6eb]"}],
    }
    r = _map_person(item)
    assert r["name"] == "Jane Doe"
    assert r["title"] == "CTO"
    assert r["company"] == "Acme Corp"
    assert r["email"] == "jane@example.com"
    assert r["source"] == "apollo"
    assert "reason" in r


def test_map_person_minimal():
    r = _map_person({"first_name": "John", "last_name": "Smith"})
    assert r["name"] == "John Smith"
    assert r["company"] == ""
    assert r["source"] == "apollo"


def test_map_company():
    item = {"name": "TechStart PH", "industry": "Software", "num_employees": 50}
    r = _map_company(item)
    assert r["name"] == "TechStart PH"
    assert r["industry"] == "Software"
    assert r["employees"] == 50
    assert r["source"] == "apollo"


# ---------------------------------------------------------------------------
# _call_apollo
# ---------------------------------------------------------------------------

def test_call_apollo_people_success():
    payload = {
        "people": [
            {"name": "Alice", "title": "CEO", "organization": {"name": "Foo Inc"}},
            {"name": "Bob", "title": "CTO", "organization": {"name": "Bar LLC"}},
        ]
    }
    mc = MagicMock()
    mc.post.return_value = _ok_resp(payload)
    with patch("httpx.Client", new=_FakeClient(mc)):
        results = _call_apollo("test-key", "people", {})
    assert len(results) == 2
    assert results[0]["source"] == "apollo"


def test_call_apollo_companies_success():
    mc = MagicMock()
    mc.post.return_value = _ok_resp({"organizations": [{"name": "CloudPH"}, {"name": "DataPH"}]})
    with patch("httpx.Client", new=_FakeClient(mc)):
        results = _call_apollo("test-key", "companies", {})
    assert len(results) == 2
    assert results[0]["source"] == "apollo"


def test_call_apollo_http_error():
    mc = MagicMock()
    mc.post.return_value = _err_resp(429, "429 Too Many Requests")
    with patch("httpx.Client", new=_FakeClient(mc)):
        results = _call_apollo("test-key", "people", {})
    assert len(results) == 1
    assert "error" in results[0]
    assert results[0]["source"] == "apollo"


def test_call_apollo_network_error():
    mc = MagicMock()
    mc.post.side_effect = Exception("DNS failure")
    with patch("httpx.Client", new=_FakeClient(mc)):
        results = _call_apollo("test-key", "people", {})
    assert len(results) == 1
    assert "error" in results[0]


# ---------------------------------------------------------------------------
# ApolloZoominfoNode.execute
# ---------------------------------------------------------------------------

def test_execute_no_api_key():
    node = ApolloZoominfoNode()
    with patch("app.pipeline.nodes.apollo_zoominfo._resolve_api_key", return_value=None):
        results = _arun(node.execute({}, [], _ctx()))
    assert len(results) == 1
    assert "error" in results[0]
    assert results[0]["source"] == "apollo"


def test_execute_invalid_json_filters():
    node = ApolloZoominfoNode()
    mc = MagicMock()
    mc.post.return_value = _ok_resp({"people": [{"name": "Test User"}]})
    with (
        patch("app.pipeline.nodes.apollo_zoominfo._resolve_api_key", return_value="fake-key"),
        patch("httpx.Client", new=_FakeClient(mc)),
    ):
        results = _arun(node.execute({"filters": "NOT_VALID_JSON"}, [{"company": "Acme"}], _ctx()))
    assert isinstance(results, list)


def test_execute_merges_input_company():
    node = ApolloZoominfoNode()
    mc = MagicMock()
    mc.post.return_value = _ok_resp({"people": [{"name": "SME Owner", "organization": {"name": "Local Biz"}}]})
    with (
        patch("app.pipeline.nodes.apollo_zoominfo._resolve_api_key", return_value="fake-key"),
        patch("httpx.Client", new=_FakeClient(mc)),
    ):
        _arun(node.execute({"search_type": "people"}, [{"company": "Local Biz"}], _ctx()))
    call_json = mc.post.call_args[1].get("json", {})
    assert call_json.get("q_organization_name") == "Local Biz"


# ---------------------------------------------------------------------------
# Node metadata
# ---------------------------------------------------------------------------

def test_node_metadata():
    node = ApolloZoominfoNode()
    assert node.node_type == "apollo_zoominfo"
    assert node.display_name == "Apollo/ZoomInfo Enrichment"
    assert node.category == "enrich"
    props = node.config_schema["properties"]
    assert "api_key" in props
    assert "search_type" in props
    assert "filters" in props
