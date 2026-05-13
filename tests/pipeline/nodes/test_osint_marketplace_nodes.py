"""Tests for OSINT marketplace datastore nodes: FullContact, Intelligence X, Clearbit, Pipl."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.pipeline.nodes.base import RunContext


class FakeCtx(RunContext):
    def __init__(self):
        super().__init__(user_id="u1", run_id="r1", node_id="n1")


def _arun(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# FullContact
# ---------------------------------------------------------------------------

def test_fullcontact_returns_error_without_key():
    from app.pipeline.nodes.fullcontact_enrich import FullContactEnrichNode
    node = FullContactEnrichNode()
    with patch("app.pipeline.nodes.fullcontact_enrich._resolve_api_key", return_value=None):
        result = _arun(node.execute({"query": "test@example.com"}, [], FakeCtx()))
    assert len(result) == 1 and "error" in result[0]


def test_fullcontact_node_metadata():
    from app.pipeline.nodes.fullcontact_enrich import FullContactEnrichNode
    node = FullContactEnrichNode()
    assert node.node_type == "fullcontact_enrich"
    assert node.category == "datastore"
    assert "lookup_type" in node.config_schema["properties"]


def test_fullcontact_map_person():
    from app.pipeline.nodes.fullcontact_enrich import _map_person
    data = {
        "fullName": "Jane Doe",
        "details": {
            "emails": [{"value": "jane@example.com"}],
            "phones": [{"value": "+1-555-0100"}],
            "profiles": {"linkedin": {"url": "linkedin.com/in/janedoe"}},
        },
        "gender": "Female",
        "location": "Manila, PH",
    }
    r = _map_person(data)
    assert r["name"] == "Jane Doe"
    assert r["email"] == "jane@example.com"
    assert r["source"] == "fullcontact"
    assert "reason" in r


def test_fullcontact_map_company():
    from app.pipeline.nodes.fullcontact_enrich import _map_company
    data = {"name": "Acme Corp", "website": "acme.com", "category": "Software", "employees": 200}
    r = _map_company(data)
    assert r["name"] == "Acme Corp"
    assert r["source"] == "fullcontact"


def test_fullcontact_build_payload_email():
    from app.pipeline.nodes.fullcontact_enrich import _build_payload
    p = _build_payload({"email": "foo@bar.com"}, "email")
    assert p == {"email": "foo@bar.com"}


def test_fullcontact_build_payload_domain():
    from app.pipeline.nodes.fullcontact_enrich import _build_payload
    p = _build_payload({"query": "example.com"}, "domain")
    assert p == {"domain": "example.com"}


def test_fullcontact_http_error():
    from app.pipeline.nodes.fullcontact_enrich import _call_fullcontact
    import httpx

    class _FakeClient:
        def __call__(self, **kw):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, *a, **kw):
            resp = MagicMock()
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401", request=MagicMock(), response=MagicMock()
            )
            return resp

    with patch("httpx.Client", new=_FakeClient()):
        result = _call_fullcontact("fake-key", {"email": "x@y.com"}, False)
    assert "error" in result
    assert result["source"] == "fullcontact"


# ---------------------------------------------------------------------------
# Intelligence X
# ---------------------------------------------------------------------------

def test_intelligence_x_returns_error_without_key():
    from app.pipeline.nodes.intelligence_x import IntelligenceXNode
    node = IntelligenceXNode()
    with patch("app.pipeline.nodes.intelligence_x._resolve_api_key", return_value=None):
        result = _arun(node.execute({"query": "test@example.com"}, [], FakeCtx()))
    assert len(result) == 1 and "error" in result[0]


def test_intelligence_x_node_metadata():
    from app.pipeline.nodes.intelligence_x import IntelligenceXNode
    node = IntelligenceXNode()
    assert node.node_type == "intelligence_x"
    assert node.category == "datastore"


def test_intelligence_x_map_record():
    from app.pipeline.nodes.intelligence_x import _map_record
    record = {"name": "paste_abc.txt", "bucket": "pastes", "date": "2024-01-01", "size": 1024}
    r = _map_record(record, "victim@example.com")
    assert r["bucket"] == "pastes"
    assert r["source"] == "intelligence_x"
    assert "reason" in r


def test_intelligence_x_http_error():
    from app.pipeline.nodes.intelligence_x import _search_intelx
    import httpx

    class _FakeClient:
        def __call__(self, **kw):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, *a, **kw):
            resp = MagicMock()
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock()
            )
            return resp

    with patch("httpx.Client", new=_FakeClient()):
        result = _search_intelx("fake-key", "query", 5, [])
    assert len(result) == 1 and "error" in result[0]


# ---------------------------------------------------------------------------
# Clearbit
# ---------------------------------------------------------------------------

def test_clearbit_returns_error_without_key():
    from app.pipeline.nodes.clearbit_enrich import ClearbitEnrichNode
    node = ClearbitEnrichNode()
    with patch("app.pipeline.nodes.clearbit_enrich._resolve_api_key", return_value=None):
        result = _arun(node.execute({"query": "example.com"}, [], FakeCtx()))
    assert len(result) == 1 and "error" in result[0]


def test_clearbit_node_metadata():
    from app.pipeline.nodes.clearbit_enrich import ClearbitEnrichNode
    node = ClearbitEnrichNode()
    assert node.node_type == "clearbit_enrich"
    assert node.category == "datastore"
    assert "lookup_type" in node.config_schema["properties"]


def test_clearbit_map_person():
    from app.pipeline.nodes.clearbit_enrich import _map_person
    data = {
        "name": {"fullName": "Bob Smith"},
        "email": "bob@corp.com",
        "employment": {"title": "VP Sales", "name": "CorpCo"},
        "location": "Makati, PH",
    }
    r = _map_person(data)
    assert r["name"] == "Bob Smith"
    assert r["title"] == "VP Sales"
    assert r["source"] == "clearbit"


def test_clearbit_map_company():
    from app.pipeline.nodes.clearbit_enrich import _map_company
    data = {
        "name": "StartupPH",
        "domain": "startupph.com",
        "category": {"industry": "Technology"},
        "metrics": {"employees": 50},
    }
    r = _map_company(data)
    assert r["industry"] == "Technology"
    assert r["employees"] == 50
    assert r["source"] == "clearbit"


def test_clearbit_build_params_domain():
    from app.pipeline.nodes.clearbit_enrich import _build_params
    p = _build_params({"query": "example.com"}, "domain")
    assert p == {"domain": "example.com"}


def test_clearbit_http_error():
    from app.pipeline.nodes.clearbit_enrich import _call_clearbit
    import httpx

    class _FakeClient:
        def __call__(self, **kw):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get(self, *a, **kw):
            resp = MagicMock()
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock()
            )
            return resp

    with patch("httpx.Client", new=_FakeClient()):
        result = _call_clearbit("fake-key", {"email": "x@y.com"}, False)
    assert "error" in result
    assert result["source"] == "clearbit"


# ---------------------------------------------------------------------------
# Pipl
# ---------------------------------------------------------------------------

def test_pipl_returns_error_without_key():
    from app.pipeline.nodes.pipl_search import PiplSearchNode
    node = PiplSearchNode()
    with patch("app.pipeline.nodes.pipl_search._resolve_api_key", return_value=None):
        result = _arun(node.execute({"query": "john@example.com"}, [], FakeCtx()))
    assert len(result) == 1 and "error" in result[0]


def test_pipl_node_metadata():
    from app.pipeline.nodes.pipl_search import PiplSearchNode
    node = PiplSearchNode()
    assert node.node_type == "pipl_search"
    assert node.category == "datastore"


def test_pipl_build_search_spec_email():
    from app.pipeline.nodes.pipl_search import _build_search_spec
    spec = _build_search_spec({"query": "john@example.com"})
    assert spec == {"email": "john@example.com"}


def test_pipl_build_search_spec_name():
    from app.pipeline.nodes.pipl_search import _build_search_spec
    spec = _build_search_spec({"name": "John Smith", "location": "Manila"})
    assert spec["first_name"] == "John"
    assert spec["last_name"] == "Smith"
    assert spec["raw_address"] == "Manila"


def test_pipl_build_search_spec_raw_name():
    from app.pipeline.nodes.pipl_search import _build_search_spec
    spec = _build_search_spec({"query": "Bathala"})
    assert spec == {"raw_name": "Bathala"}


def test_pipl_map_person():
    from app.pipeline.nodes.pipl_search import _map_person
    person = {
        "names": [{"display": "Maria Santos", "first": "Maria", "last": "Santos"}],
        "emails": [{"address": "maria@santos.ph"}],
        "phones": [{"display": "+63 917 000 0001"}],
        "jobs": [{"title": "Manager", "organization": "BPO Corp"}],
        "addresses": [{"display": "Quezon City, PH"}],
        "usernames": [],
        "images": [],
    }
    r = _map_person(person)
    assert r["name"] == "Maria Santos"
    assert r["source"] == "pipl"
    assert "reason" in r


def test_pipl_http_error():
    from app.pipeline.nodes.pipl_search import _call_pipl
    import httpx

    class _FakeClient:
        def __call__(self, **kw):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get(self, *a, **kw):
            resp = MagicMock()
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "402", request=MagicMock(), response=MagicMock()
            )
            return resp

    with patch("httpx.Client", new=_FakeClient()):
        result = _call_pipl("fake-key", {"raw_name": "Test User"}, "")
    assert len(result) == 1 and "error" in result[0]


# ---------------------------------------------------------------------------
# Cross-cutting: all nodes must have category == "datastore"
# ---------------------------------------------------------------------------

def test_all_nodes_have_datastore_category():
    from app.pipeline.nodes.fullcontact_enrich import FullContactEnrichNode
    from app.pipeline.nodes.intelligence_x import IntelligenceXNode
    from app.pipeline.nodes.clearbit_enrich import ClearbitEnrichNode
    from app.pipeline.nodes.pipl_search import PiplSearchNode
    for cls in [FullContactEnrichNode, IntelligenceXNode, ClearbitEnrichNode, PiplSearchNode]:
        assert cls.category == "datastore", f"{cls.__name__} category should be datastore"
