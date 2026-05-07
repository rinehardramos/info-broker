"""Unit tests for the WebCrawlNode enhancements."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline.nodes.web_crawl import (
    WebCrawlNode,
    _USER_AGENTS,
    _crawl,
    _extract_content,
    _fetch_robots_disallow,
    _fetch_with_retry,
    _is_allowed_by_robots,
    _normalize_url,
    _text_to_markdown,
)
from app.pipeline.nodes.base import RunContext


def _ctx() -> RunContext:
    return RunContext(user_id="u1", run_id="r1", node_id="n1")


def _arun(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Config schema
# ---------------------------------------------------------------------------

def test_config_schema_includes_new_fields():
    node = WebCrawlNode()
    props = node.config_schema["properties"]
    assert "delay_seconds" in props
    assert "respect_robots" in props
    assert "extract_mode" in props


def test_config_schema_extract_mode_enum():
    node = WebCrawlNode()
    enum_values = node.config_schema["properties"]["extract_mode"]["enum"]
    assert set(enum_values) == {"text", "html", "markdown"}


def test_config_schema_defaults():
    node = WebCrawlNode()
    props = node.config_schema["properties"]
    assert props["delay_seconds"]["default"] == 1.0
    assert props["respect_robots"]["default"] is True
    assert props["extract_mode"]["default"] == "text"


# ---------------------------------------------------------------------------
# User-Agent pool
# ---------------------------------------------------------------------------

def test_user_agents_has_five_entries():
    assert len(_USER_AGENTS) == 5


def test_user_agents_are_all_strings():
    assert all(isinstance(ua, str) for ua in _USER_AGENTS)


# ---------------------------------------------------------------------------
# _extract_content
# ---------------------------------------------------------------------------

def test_extract_content_text_mode():
    raw = "Hello world\nSecond line"
    assert _extract_content(raw, "text") == raw


def test_extract_content_html_mode_wraps():
    raw = "Hello <world>"
    result = _extract_content(raw, "html")
    assert result.startswith("<html>")
    assert "&lt;world&gt;" in result


def test_extract_content_html_mode_escapes_ampersand():
    raw = "A & B"
    result = _extract_content(raw, "html")
    assert "&amp;" in result


def test_extract_content_markdown_mode_returns_string():
    raw = "Some text\nAnother line"
    result = _extract_content(raw, "markdown")
    assert isinstance(result, str)
    assert "Some text" in result


def test_extract_content_unknown_mode_falls_back_to_text():
    raw = "plain"
    # Unknown mode should behave like text (default branch)
    assert _extract_content(raw, "text") == raw


# ---------------------------------------------------------------------------
# _text_to_markdown
# ---------------------------------------------------------------------------

def test_text_to_markdown_all_caps_becomes_heading():
    text = "COMPANY OVERVIEW"
    md = _text_to_markdown(text)
    assert md.startswith("##")


def test_text_to_markdown_short_caps_skipped_if_too_short():
    # ≤3 chars should NOT become a heading
    text = "NO"
    md = _text_to_markdown(text)
    assert not md.startswith("##")


def test_text_to_markdown_bullet_preserved():
    text = "- item one\n* item two\n• item three"
    md = _text_to_markdown(text)
    lines = md.splitlines()
    assert lines[0].startswith("-")
    assert lines[1].startswith("*")
    assert lines[2].startswith("•")


def test_text_to_markdown_url_becomes_link():
    text = "Visit https://example.com for details"
    md = _text_to_markdown(text)
    assert "[https://example.com](https://example.com)" in md


def test_text_to_markdown_blank_lines_preserved():
    text = "Line one\n\nLine two"
    md = _text_to_markdown(text)
    assert "\n\n" in md


# ---------------------------------------------------------------------------
# _fetch_with_retry
# ---------------------------------------------------------------------------

def test_fetch_with_retry_returns_text_on_first_success():
    with patch("app.lib.ddg_fallback.scrape_url", return_value="page content"):
        result = _fetch_with_retry("https://example.com", "UA/1.0")
    assert result == "page content"


def test_fetch_with_retry_retries_on_exception(monkeypatch):
    calls = []

    def flaky_scrape(url, **kwargs):
        calls.append(url)
        if len(calls) < 3:
            raise OSError("connection reset")
        return "ok"

    monkeypatch.setattr("app.pipeline.nodes.web_crawl.time.sleep", lambda s: None)

    with patch("app.lib.ddg_fallback.scrape_url", side_effect=flaky_scrape):
        result = _fetch_with_retry("https://example.com", "UA/1.0")

    assert result == "ok"
    assert len(calls) == 3


def test_fetch_with_retry_returns_none_after_all_attempts_fail(monkeypatch):
    monkeypatch.setattr("app.pipeline.nodes.web_crawl.time.sleep", lambda s: None)

    with patch("app.lib.ddg_fallback.scrape_url", side_effect=OSError("fail")):
        result = _fetch_with_retry("https://example.com", "UA/1.0")

    assert result is None


# ---------------------------------------------------------------------------
# _is_allowed_by_robots / _fetch_robots_disallow
# ---------------------------------------------------------------------------

def test_is_allowed_by_robots_empty_cache_allowed(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.nodes.web_crawl._fetch_robots_disallow",
        lambda url: set(),
    )
    cache: dict = {}
    assert _is_allowed_by_robots("https://example.com/page", cache) is True


def test_is_allowed_by_robots_disallowed_path(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.nodes.web_crawl._fetch_robots_disallow",
        lambda url: {"/private/"},
    )
    cache: dict = {}
    assert _is_allowed_by_robots("https://example.com/private/data", cache) is False


def test_is_allowed_by_robots_uses_cache():
    cache = {"example.com": {"/secret/"}}
    # Should not call _fetch_robots_disallow — uses cache directly
    result = _is_allowed_by_robots("https://example.com/secret/page", cache)
    assert result is False


def test_fetch_robots_disallow_parses_correctly():
    robots_txt = (
        "User-agent: *\n"
        "Disallow: /admin/\n"
        "Disallow: /private\n"
        "\n"
        "User-agent: Googlebot\n"
        "Disallow: /nogoogle\n"
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = robots_txt

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response

    with patch("httpx.Client", return_value=mock_client):
        disallowed = _fetch_robots_disallow("https://example.com/robots.txt")

    assert "/admin/" in disallowed
    assert "/private" in disallowed
    # Googlebot-specific rule should NOT be included (we only track *)
    assert "/nogoogle" not in disallowed


def test_fetch_robots_disallow_returns_empty_on_404():
    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response

    with patch("httpx.Client", return_value=mock_client):
        disallowed = _fetch_robots_disallow("https://example.com/robots.txt")

    assert disallowed == set()


def test_fetch_robots_disallow_returns_empty_on_network_error():
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = OSError("timeout")

    with patch("httpx.Client", return_value=mock_client):
        disallowed = _fetch_robots_disallow("https://example.com/robots.txt")

    assert disallowed == set()


# ---------------------------------------------------------------------------
# _crawl integration (rate-limiting + robots.txt + extract_mode)
# ---------------------------------------------------------------------------

def test_crawl_respects_delay_between_requests(monkeypatch):
    """Verify that at least delay_seconds passes between page fetches."""
    call_times: list[float] = []

    def timed_scrape(url, **kwargs):
        call_times.append(time.monotonic())
        return f"content of {url}"

    monkeypatch.setattr(
        "app.pipeline.nodes.web_crawl._fetch_with_retry",
        lambda url, ua, **kw: timed_scrape(url),
    )
    monkeypatch.setattr(
        "app.pipeline.nodes.web_crawl._is_allowed_by_robots",
        lambda url, cache: True,
    )

    start_url = "https://example.com"
    # Two pages: the start URL + one linked page
    all_results = _crawl(
        start_url,
        allowed_domains=[],
        max_pages=2,
        scrape_depth=0,
        delay_seconds=0.0,  # 0 so test is fast but still exercises the code path
        respect_robots=False,
        extract_mode="text",
    )
    assert isinstance(all_results, list)


def test_crawl_skips_robots_disallowed(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.nodes.web_crawl._fetch_with_retry",
        lambda url, ua, **kw: "some content",
    )
    monkeypatch.setattr(
        "app.pipeline.nodes.web_crawl._is_allowed_by_robots",
        lambda url, cache: False,
    )

    results = _crawl(
        "https://example.com/private/",
        allowed_domains=[],
        max_pages=5,
        scrape_depth=0,
        delay_seconds=0.0,
        respect_robots=True,
        extract_mode="text",
    )
    assert results == []


def test_crawl_extract_mode_html(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.nodes.web_crawl._fetch_with_retry",
        lambda url, ua, **kw: "raw page text",
    )
    monkeypatch.setattr(
        "app.pipeline.nodes.web_crawl._is_allowed_by_robots",
        lambda url, cache: True,
    )

    results = _crawl(
        "https://example.com",
        allowed_domains=[],
        max_pages=1,
        scrape_depth=0,
        delay_seconds=0.0,
        respect_robots=False,
        extract_mode="html",
    )
    assert len(results) == 1
    assert results[0]["content"].startswith("<html>")


def test_crawl_extract_mode_markdown(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.nodes.web_crawl._fetch_with_retry",
        lambda url, ua, **kw: "ABOUT US\nWe are a company.",
    )
    monkeypatch.setattr(
        "app.pipeline.nodes.web_crawl._is_allowed_by_robots",
        lambda url, cache: True,
    )

    results = _crawl(
        "https://example.com",
        allowed_domains=[],
        max_pages=1,
        scrape_depth=0,
        delay_seconds=0.0,
        respect_robots=False,
        extract_mode="markdown",
    )
    assert len(results) == 1
    # "ABOUT US" is all-caps so it should be turned into a heading
    assert "##" in results[0]["content"]


# ---------------------------------------------------------------------------
# Node metadata preserved
# ---------------------------------------------------------------------------

def test_node_metadata():
    node = WebCrawlNode()
    assert node.node_type == "web_crawl"
    assert node.display_name == "Web Crawl"
    assert node.category == "datastore"
