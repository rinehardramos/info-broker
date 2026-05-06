"""Unit tests for the ClutchGoodfirmsNode."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.pipeline.nodes.clutch_goodfirms import (
    ClutchGoodfirmsNode,
    _fetch_clutch,
    _fetch_goodfirms,
    _parse_clutch_html,
    _parse_goodfirms_html,
)
from app.pipeline.nodes.base import RunContext


def _ctx() -> RunContext:
    return RunContext(user_id="u1", run_id="r1", node_id="n1")


def _arun(coro):
    return asyncio.run(coro)


def _ok_resp(html: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.text = html
    resp.raise_for_status = MagicMock()
    return resp


class _FakeClient:
    """Replaces httpx.Client as a context manager."""

    def __init__(self, inner: MagicMock):
        self._inner = inner

    def __call__(self, **kwargs):
        return self

    def __enter__(self):
        return self._inner

    def __exit__(self, *a):
        return False


# ---------------------------------------------------------------------------
# Node metadata
# ---------------------------------------------------------------------------

def test_node_metadata():
    node = ClutchGoodfirmsNode()
    assert node.node_type == "clutch_goodfirms"
    assert node.display_name == "Clutch/GoodFirms Reviews"
    assert node.category == "enrich"
    props = node.config_schema["properties"]
    assert "platform" in props
    assert "location" in props
    assert "service_type" in props
    assert "max_results" in props


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

_CLUTCH_HTML = """
<ul>
  <li class="provider-row">
    <h3>Acme IT Solutions</h3>
    <a href="/profile/acme-it-solutions" class="company_info">Acme IT Solutions</a>
    <span class="location-flag">Manila, Philippines</span>
    <span class="focus-item">IT Services</span>
    4.9 rating, 32 reviews
  </li>
  <li class="provider-row">
    <h3>Beta Software PH</h3>
    <a href="/profile/beta-software-ph" class="company_info">Beta Software PH</a>
    <span class="location-flag">Cebu, Philippines</span>
    5.0 rating, 15 reviews
  </li>
</ul>
"""

_GOODFIRMS_HTML = """
<div class="company-box">
  <h4>GoodFirm Corp</h4>
  <a href="/it-companies/goodfirm-corp">GoodFirm Corp</a>
  <span class="location">Makati, Philippines</span>
  4.8 rating, 20 reviews
</div>
</div>
"""


def test_parse_clutch_html_returns_companies():
    results = _parse_clutch_html(_CLUTCH_HTML, "https://clutch.co/it-services/philippines")
    assert len(results) == 2
    assert results[0]["company"] == "Acme IT Solutions"
    assert results[0]["source"] == "clutch"
    assert results[1]["company"] == "Beta Software PH"
    assert results[1]["source"] == "clutch"


def test_parse_goodfirms_html_returns_companies():
    results = _parse_goodfirms_html(_GOODFIRMS_HTML)
    assert len(results) >= 1
    assert results[0]["company"] == "GoodFirm Corp"
    assert results[0]["source"] == "goodfirms"


def test_parse_clutch_html_empty_returns_empty():
    results = _parse_clutch_html("<html><body>No results</body></html>", "https://clutch.co")
    assert results == []


# ---------------------------------------------------------------------------
# test_execute_clutch_search
# ---------------------------------------------------------------------------

def test_execute_clutch_search():
    node = ClutchGoodfirmsNode()
    mc = MagicMock()
    mc.get.return_value = _ok_resp(_CLUTCH_HTML)

    with patch("httpx.Client", new=_FakeClient(mc)):
        results = _arun(node.execute(
            {"platform": "clutch", "location": "Philippines", "service_type": "IT Services"},
            [],
            _ctx(),
        ))

    # Verify the Clutch base URL was hit
    call_url = mc.get.call_args[0][0]
    assert "clutch.co" in call_url
    assert isinstance(results, list)
    for r in results:
        assert r.get("source") == "clutch"


# ---------------------------------------------------------------------------
# test_execute_goodfirms_search
# ---------------------------------------------------------------------------

def test_execute_goodfirms_search():
    node = ClutchGoodfirmsNode()
    mc = MagicMock()
    mc.get.return_value = _ok_resp(_GOODFIRMS_HTML)

    with patch("httpx.Client", new=_FakeClient(mc)):
        results = _arun(node.execute(
            {"platform": "goodfirms", "location": "Philippines"},
            [],
            _ctx(),
        ))

    call_url = mc.get.call_args[0][0]
    assert "goodfirms.co" in call_url
    assert isinstance(results, list)
    for r in results:
        assert r.get("source") == "goodfirms"


# ---------------------------------------------------------------------------
# test_execute_both_platforms
# ---------------------------------------------------------------------------

def test_execute_both_platforms():
    node = ClutchGoodfirmsNode()
    mc = MagicMock()

    # Return Clutch HTML for the first call, GoodFirms HTML for the second
    mc.get.side_effect = [
        _ok_resp(_CLUTCH_HTML),
        _ok_resp(_GOODFIRMS_HTML),
    ]

    with patch("httpx.Client", new=_FakeClient(mc)):
        results = _arun(node.execute(
            {"platform": "both", "location": "Philippines", "max_results": 50},
            [],
            _ctx(),
        ))

    assert mc.get.call_count == 2
    sources = {r.get("source") for r in results}
    assert "clutch" in sources
    assert "goodfirms" in sources


# ---------------------------------------------------------------------------
# test_execute_handles_scrape_error
# ---------------------------------------------------------------------------

def test_execute_handles_scrape_error():
    """A connection error from httpx should produce an error entry, not raise."""
    node = ClutchGoodfirmsNode()
    mc = MagicMock()
    mc.get.side_effect = Exception("Connection refused")

    with patch("httpx.Client", new=_FakeClient(mc)):
        results = _arun(node.execute(
            {"platform": "clutch"},
            [],
            _ctx(),
        ))

    assert len(results) == 1
    assert "error" in results[0]
    assert results[0]["source"] == "clutch"


def test_execute_both_platforms_one_fails():
    """When Clutch fails and GoodFirms succeeds, partial results are returned."""
    node = ClutchGoodfirmsNode()
    mc = MagicMock()
    mc.get.side_effect = [
        Exception("Clutch timeout"),
        _ok_resp(_GOODFIRMS_HTML),
    ]

    with patch("httpx.Client", new=_FakeClient(mc)):
        results = _arun(node.execute(
            {"platform": "both"},
            [],
            _ctx(),
        ))

    assert any(r.get("source") == "goodfirms" for r in results)
    assert any("error" in r and r.get("source") == "clutch" for r in results)
