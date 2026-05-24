"""Regression tests for the MCP run_web_crawl URL-argument parsing (issue #110).

The brain often passes ``urls`` as a single bare URL or a comma/whitespace list
rather than a JSON array string. ``json.loads`` raised JSONDecodeError on the
bare-URL form *before any HTTP call*. _parse_url_arg tolerates all forms.
"""
from __future__ import annotations

import pytest

mcp_server = pytest.importorskip("mcp_server.server")
_parse_url_arg = mcp_server._parse_url_arg


def test_json_array_string():
    assert _parse_url_arg('["https://a.com", "https://b.com"]') == [
        "https://a.com",
        "https://b.com",
    ]


def test_bare_url_no_longer_crashes():
    # This input previously raised json.JSONDecodeError before any HTTP call.
    assert _parse_url_arg("https://example.com") == ["https://example.com"]


def test_json_quoted_single_url():
    assert _parse_url_arg('"https://example.com"') == ["https://example.com"]


def test_comma_separated():
    assert _parse_url_arg("https://a.com, https://b.com") == [
        "https://a.com",
        "https://b.com",
    ]


def test_whitespace_separated():
    assert _parse_url_arg("https://a.com  https://b.com") == [
        "https://a.com",
        "https://b.com",
    ]


def test_blank_entries_dropped():
    assert _parse_url_arg('["https://a.com", "", "  "]') == ["https://a.com"]


def test_empty_string_returns_empty_list():
    assert _parse_url_arg("") == []
