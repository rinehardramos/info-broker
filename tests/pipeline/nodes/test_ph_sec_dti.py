"""Unit tests for the PhSecDtiNode."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.pipeline.nodes.ph_sec_dti import (
    PhSecDtiNode,
    _enrich_with_officers,
    _error_item,
    _extract_between,
    _fetch_gis_officers,
    _parse_gis_officers,
    _parse_sec_html,
    _strip_tags,
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


# ---------------------------------------------------------------------------
# include_officers config schema
# ---------------------------------------------------------------------------

def test_config_schema_includes_officers_field():
    node = PhSecDtiNode()
    assert "include_officers" in node.config_schema["properties"]


def test_config_schema_include_officers_default_false():
    node = PhSecDtiNode()
    assert node.config_schema["properties"]["include_officers"]["default"] is False


# ---------------------------------------------------------------------------
# _parse_gis_officers
# ---------------------------------------------------------------------------

def test_parse_gis_officers_list_input():
    data = [
        {"name": "Juan dela Cruz", "position": "President", "nationality": "Filipino"},
        {"name": "Maria Santos", "position": "Treasurer", "nationality": "Filipino"},
    ]
    officers = _parse_gis_officers(data)
    assert len(officers) == 2
    assert officers[0]["name"] == "Juan dela Cruz"
    assert officers[0]["position"] == "President"


def test_parse_gis_officers_dict_with_officers_key():
    data = {
        "officers": [
            {"officerName": "Pedro Reyes", "designation": "Director"},
        ]
    }
    officers = _parse_gis_officers(data)
    assert len(officers) == 1
    assert officers[0]["name"] == "Pedro Reyes"
    assert officers[0]["position"] == "Director"


def test_parse_gis_officers_dict_with_data_key():
    data = {
        "data": [
            {"name": "Ana Garcia", "title": "Corporate Secretary"},
        ]
    }
    officers = _parse_gis_officers(data)
    assert len(officers) == 1
    assert officers[0]["name"] == "Ana Garcia"
    assert officers[0]["position"] == "Corporate Secretary"


def test_parse_gis_officers_skips_nameless_rows():
    data = [
        {"position": "Director"},  # no name
        {"name": "Valid Officer", "position": "Treasurer"},
    ]
    officers = _parse_gis_officers(data)
    assert len(officers) == 1
    assert officers[0]["name"] == "Valid Officer"


def test_parse_gis_officers_empty_input():
    assert _parse_gis_officers([]) == []
    assert _parse_gis_officers({}) == []


# ---------------------------------------------------------------------------
# _fetch_gis_officers
# ---------------------------------------------------------------------------

def test_fetch_gis_officers_returns_list_on_200():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"name": "Test Officer", "position": "President"},
    ]

    with patch("httpx.Client", new=_FakeClient(MagicMock(get=MagicMock(return_value=mock_response)))):
        result = _fetch_gis_officers("CS202000001")

    assert result is not None
    assert len(result) == 1


def test_fetch_gis_officers_returns_empty_list_on_404():
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("httpx.Client", new=_FakeClient(MagicMock(get=MagicMock(return_value=mock_response)))):
        result = _fetch_gis_officers("CS000000")

    assert result == []


def test_fetch_gis_officers_returns_none_on_network_error():
    mc_inner = MagicMock()
    mc_inner.get.side_effect = OSError("timeout")

    with patch("httpx.Client", new=_FakeClient(mc_inner)):
        result = _fetch_gis_officers("CS000000")

    assert result is None


# ---------------------------------------------------------------------------
# _enrich_with_officers
# ---------------------------------------------------------------------------

def test_enrich_with_officers_adds_officers_key():
    records = [
        {"company_name": "Test Corp", "registration_number": "CS202000001", "source": "sec_ph"},
    ]
    officers_data = [{"name": "Jane Doe", "position": "CEO"}]

    with patch(
        "app.pipeline.nodes.ph_sec_dti._fetch_gis_officers",
        return_value=officers_data,
    ):
        result = _enrich_with_officers(records)

    assert "officers" in result[0]
    assert result[0]["officers"] == officers_data


def test_enrich_with_officers_skips_missing_registration_number():
    records = [
        {"company_name": "No Reg Corp", "registration_number": "", "source": "sec_ph"},
    ]
    result = _enrich_with_officers(records)
    assert "officers" not in result[0]


def test_enrich_with_officers_omits_key_when_fetch_fails():
    records = [
        {"company_name": "Test Corp", "registration_number": "CS202000001", "source": "sec_ph"},
    ]
    with patch(
        "app.pipeline.nodes.ph_sec_dti._fetch_gis_officers",
        return_value=None,
    ):
        result = _enrich_with_officers(records)

    assert "officers" not in result[0]


# ---------------------------------------------------------------------------
# execute with include_officers=True end-to-end
# ---------------------------------------------------------------------------

def test_execute_with_include_officers_true():
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

    officers_data = [{"name": "Juan Cruz", "position": "President"}]

    with (
        patch("app.pipeline.nodes.ph_sec_dti._try_esparc_api", return_value=[]),
        patch("httpx.Client", new=_FakeClient(mc_inner)),
        patch(
            "app.pipeline.nodes.ph_sec_dti._fetch_gis_officers",
            return_value=officers_data,
        ),
    ):
        results = _arun(
            node.execute(
                {"include_officers": True},
                [{"company": "GREAT CORP"}],
                _ctx(),
            )
        )

    assert any(r.get("officers") == officers_data for r in results)


def test_execute_without_include_officers_no_gis_call():
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
        patch(
            "app.pipeline.nodes.ph_sec_dti._fetch_gis_officers"
        ) as mock_gis,
    ):
        results = _arun(
            node.execute(
                {"include_officers": False},
                [{"company": "GREAT CORP"}],
                _ctx(),
            )
        )

    mock_gis.assert_not_called()
    assert all("officers" not in r for r in results)
