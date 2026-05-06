"""Unit tests for the PhSecDtiNode."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.pipeline.nodes.ph_sec_dti import (
    PhSecDtiNode,
    _parse_sec_html,
    _strip_tags,
    _extract_between,
    _error_item,
)
from app.pipeline.nodes.base import RunContext


def _ctx() -> RunContext:
    return RunContext(user_id="u1", run_id="r1", node_id="n1")


def _arun(coro):
    return asyncio.run(coro)


class _FakeClient:
    def __init__(self, inner: MagicMock):
        self._inner = inner

    def __call__(self, **kwargs):
        return self

    def __enter__(self):
        return self._inner

    def __exit__(self, *a):
        return False


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def test_strip_tags_basic():
    assert _strip_tags("<b>Hello</b> <em>World</em>") == "Hello World"


def test_strip_tags_nested():
    assert _strip_tags("<td><a href='x'>Company Name</a></td>") == "Company Name"


def test_strip_tags_empty():
    assert _strip_tags("") == ""


def test_extract_between_basic():
    html = "<td>First</td><td>Second</td>"
    assert _extract_between(html, "<td", "</td>") == ["First", "Second"]


def test_extract_between_empty():
    assert _extract_between("<tr></tr>", "<td", "</td>") == []


def test_parse_sec_html_finds_company():
    html = """
    <table>
      <tr><th>Company Name</th><th>SEC Number</th><th>Status</th></tr>
      <tr>
        <td>ACME TECHNOLOGY INC</td>
        <td>CS201900001</td>
        <td>ACTIVE</td>
      </tr>
    </table>
    """
    results = _parse_sec_html(html, "ACME TECHNOLOGY")
    assert len(results) >= 1
    r = results[0]
    assert r["company_name"] == "ACME TECHNOLOGY INC"
    assert r["registration_number"] == "CS201900001"
    assert r["status"] == "ACTIVE"
    assert r["source"] == "sec_ph"


def test_parse_sec_html_skips_header_rows():
    html = "<tr><th>Company</th><th>Number</th></tr>"
    assert _parse_sec_html(html, "anything") == []


def test_parse_sec_html_no_match_when_different_company():
    html = """
    <tr>
      <td>COMPLETELY DIFFERENT CO</td>
      <td>CS000001</td>
      <td>ACTIVE</td>
    </tr>
    """
    assert _parse_sec_html(html, "ACME") == []


def test_error_item_shape():
    item = _error_item("Test Corp", "HTTP 503")
    assert item["company_name"] == "Test Corp"
    assert item["source"] == "sec_ph"
    assert item["error"] == "HTTP 503"
    assert "reason" in item


# ---------------------------------------------------------------------------
# PhSecDtiNode.execute
# ---------------------------------------------------------------------------

def test_execute_skips_empty_query():
    node = PhSecDtiNode()
    results = _arun(node.execute({}, [{"query": ""}], _ctx()))
    assert results == []


def test_execute_skips_items_with_no_relevant_field():
    node = PhSecDtiNode()
    results = _arun(node.execute({}, [{"score": 5}], _ctx()))
    assert results == []


def test_execute_returns_error_item_on_http_failure():
    node = PhSecDtiNode()
    mc_inner = MagicMock()
    mc_inner.get.return_value.status_code = 503
    with (
        patch("app.pipeline.nodes.ph_sec_dti._try_esparc_api", return_value=[]),
        patch("httpx.Client", new=_FakeClient(mc_inner)),
    ):
        results = _arun(node.execute({"search_type": "company_name"}, [{"company": "Any Corp"}], _ctx()))
    assert len(results) >= 1
    assert results[0]["source"] == "sec_ph"


def test_execute_uses_company_field():
    node = PhSecDtiNode()
    html_body = """
    <tr>
      <td>GREAT CORP INC</td>
      <td>CS202000099</td>
      <td>ACTIVE</td>
    </tr>
    """
    mc_inner = MagicMock()
    mc_inner.get.return_value.status_code = 200
    mc_inner.get.return_value.text = html_body
    with (
        patch("app.pipeline.nodes.ph_sec_dti._try_esparc_api", return_value=[]),
        patch("httpx.Client", new=_FakeClient(mc_inner)),
    ):
        results = _arun(node.execute({}, [{"company": "GREAT CORP"}], _ctx()))
    assert any(r["source"] == "sec_ph" for r in results)


# ---------------------------------------------------------------------------
# Node metadata
# ---------------------------------------------------------------------------

def test_node_metadata():
    node = PhSecDtiNode()
    assert node.node_type == "ph_sec_dti"
    assert node.display_name == "PH SEC/DTI Registry"
    assert node.category == "enrich"
    assert "search_type" in node.config_schema["properties"]
