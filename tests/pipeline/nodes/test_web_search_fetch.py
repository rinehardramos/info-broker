"""Unit tests for the WebSearchFetchNode."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.pipeline.nodes.web_search_fetch import WebSearchFetchNode, _fetch_page_text, _html_to_text
from app.pipeline.nodes.base import RunContext
from app.search_engine.plugins.base import PluginResult

CTX = RunContext(user_id="test", run_id="test", node_id="test")


def _arun(coro):
    return asyncio.run(coro)


def _make_result(title: str, url: str, snippet: str) -> PluginResult:
    return PluginResult(
        title=title,
        url=url,
        snippet=snippet,
        full_text=None,
        published_at=None,
        source_name="ddg",
    )


def _make_ddg_mock(results: list[PluginResult]) -> MagicMock:
    """Return a mock DdgPlugin whose search() coroutine returns results."""
    mock_plugin = MagicMock()
    mock_plugin.search = AsyncMock(return_value=results)
    MockDdg = MagicMock(return_value=mock_plugin)
    return MockDdg, mock_plugin


class _FakeHttpxClient:
    """Replaces httpx.Client as a context manager for _fetch_page_text."""

    def __init__(self, inner: MagicMock):
        self._inner = inner

    def __call__(self, **kwargs):
        return self

    def __enter__(self):
        return self._inner

    def __exit__(self, *a):
        return False


# ---------------------------------------------------------------------------
# _html_to_text helper
# ---------------------------------------------------------------------------

def test_html_to_text_strips_tags():
    html = "<html><body><h1>Hello</h1><p>World</p></body></html>"
    text = _html_to_text(html)
    assert "Hello" in text
    assert "World" in text
    assert "<" not in text
    assert ">" not in text


def test_html_to_text_removes_script_blocks():
    html = "<html><script>alert('xss')</script><p>Safe content</p></html>"
    text = _html_to_text(html)
    assert "xss" not in text
    assert "Safe content" in text


def test_html_to_text_decodes_entities():
    html = "<p>&amp; &lt; &gt; &quot; &#39; &nbsp;</p>"
    text = _html_to_text(html)
    assert "&" in text
    assert "<" in text
    assert ">" in text


# ---------------------------------------------------------------------------
# Node metadata
# ---------------------------------------------------------------------------

def test_node_metadata():
    node = WebSearchFetchNode()
    assert node.node_type == "web_search_fetch"
    assert node.display_name == "Web Search & Fetch"
    assert node.category == "enrich"
    props = node.config_schema["properties"]
    assert "max_results" in props
    assert "fetch_content" in props
    assert "search_engine" in props


# ---------------------------------------------------------------------------
# test_execute_search_only — fetch_content=False, returns snippets only
# ---------------------------------------------------------------------------

def test_execute_search_only():
    node = WebSearchFetchNode()
    search_results = [
        _make_result("Result One", "https://example.com/1", "First snippet"),
        _make_result("Result Two", "https://example.com/2", "Second snippet"),
    ]
    MockDdg, mock_plugin = _make_ddg_mock(search_results)

    with patch("app.search_engine.plugins.ddg.DdgPlugin", MockDdg):
        results = _arun(node.execute(
            {"max_results": 5, "fetch_content": False},
            [{"query": "Philippines IT companies"}],
            CTX,
        ))

    # search was called with the query
    mock_plugin.search.assert_called_once()
    call_args = mock_plugin.search.call_args
    assert "Philippines IT companies" in call_args[0]

    assert len(results) == 2
    assert results[0]["title"] == "Result One"
    assert results[0]["snippet"] == "First snippet"
    assert results[0]["url"] == "https://example.com/1"
    assert results[0]["query"] == "Philippines IT companies"
    assert results[0]["source"] == "web_search"
    # fetch_content=False — no "content" key injected
    assert "content" not in results[0]


# ---------------------------------------------------------------------------
# test_execute_with_content_fetch — fetch_content=True
# ---------------------------------------------------------------------------

def test_execute_with_content_fetch():
    node = WebSearchFetchNode()
    search_results = [
        _make_result("Page A", "https://example.com/a", "snippet a"),
    ]
    MockDdg, _ = _make_ddg_mock(search_results)

    mc = MagicMock()
    mc.get.return_value = MagicMock(
        status_code=200,
        text="<html><body><p>Full page content</p></body></html>",
        raise_for_status=MagicMock(),
    )

    with (
        patch("app.search_engine.plugins.ddg.DdgPlugin", MockDdg),
        patch("httpx.Client", new=_FakeHttpxClient(mc)),
    ):
        results = _arun(node.execute(
            {"fetch_content": True},
            [{"query": "test query"}],
            CTX,
        ))

    assert len(results) == 1
    assert "content" in results[0]
    assert "Full page content" in results[0]["content"]


# ---------------------------------------------------------------------------
# test_execute_handles_fetch_error — one URL fails, others succeed
# ---------------------------------------------------------------------------

def test_execute_handles_fetch_error():
    """When fetching one URL raises, the entry gets content='' and processing continues."""
    node = WebSearchFetchNode()
    search_results = [
        _make_result("Good Page", "https://example.com/good", "good snippet"),
        _make_result("Bad Page", "https://example.com/bad", "bad snippet"),
    ]
    MockDdg, _ = _make_ddg_mock(search_results)

    def _selective_get(url, **kwargs):
        if "bad" in url:
            raise Exception("Connection refused")
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "<p>Good content</p>"
        resp.raise_for_status = MagicMock()
        return resp

    mc = MagicMock()
    mc.get.side_effect = _selective_get

    with (
        patch("app.search_engine.plugins.ddg.DdgPlugin", MockDdg),
        patch("httpx.Client", new=_FakeHttpxClient(mc)),
    ):
        results = _arun(node.execute(
            {"fetch_content": True},
            [{"query": "test"}],
            CTX,
        ))

    assert len(results) == 2
    good = next(r for r in results if r["title"] == "Good Page")
    bad = next(r for r in results if r["title"] == "Bad Page")
    assert "Good content" in good["content"]
    assert bad["content"] == ""


# ---------------------------------------------------------------------------
# test_execute_empty_query — inputs with no usable query field → empty output
# ---------------------------------------------------------------------------

def test_execute_empty_query():
    node = WebSearchFetchNode()
    MockDdg, mock_plugin = _make_ddg_mock([])

    with patch("app.search_engine.plugins.ddg.DdgPlugin", MockDdg):
        results = _arun(node.execute(
            {},
            [{"irrelevant_field": "value"}],
            CTX,
        ))

    mock_plugin.search.assert_not_called()
    assert results == []


def test_execute_no_inputs_returns_empty():
    node = WebSearchFetchNode()
    MockDdg, mock_plugin = _make_ddg_mock([])

    with patch("app.search_engine.plugins.ddg.DdgPlugin", MockDdg):
        results = _arun(node.execute({}, [], CTX))

    mock_plugin.search.assert_not_called()
    assert results == []


# ---------------------------------------------------------------------------
# test_execute_uses_message_and_title_as_query_fallback
# ---------------------------------------------------------------------------

def test_execute_uses_message_as_query():
    node = WebSearchFetchNode()
    search_results = [_make_result("R", "https://x.com", "s")]
    MockDdg, mock_plugin = _make_ddg_mock(search_results)

    with patch("app.search_engine.plugins.ddg.DdgPlugin", MockDdg):
        results = _arun(node.execute(
            {},
            [{"message": "find me something"}],
            CTX,
        ))

    call_query = mock_plugin.search.call_args[0][0]
    assert call_query == "find me something"
    assert len(results) == 1


def test_execute_uses_title_as_query_last_resort():
    node = WebSearchFetchNode()
    search_results = [_make_result("R", "https://x.com", "s")]
    MockDdg, mock_plugin = _make_ddg_mock(search_results)

    with patch("app.search_engine.plugins.ddg.DdgPlugin", MockDdg):
        results = _arun(node.execute(
            {},
            [{"title": "My Company Title"}],
            CTX,
        ))

    call_query = mock_plugin.search.call_args[0][0]
    assert call_query == "My Company Title"
    assert len(results) == 1


# ---------------------------------------------------------------------------
# test_execute_multiple_inputs — one query per input item
# ---------------------------------------------------------------------------

def test_execute_multiple_inputs():
    node = WebSearchFetchNode()

    call_count = 0
    async def _mock_search(query, *, max_results=5):
        nonlocal call_count
        call_count += 1
        return [_make_result(f"Result for {query}", "https://x.com", "s")]

    mock_plugin = MagicMock()
    mock_plugin.search = _mock_search
    MockDdg = MagicMock(return_value=mock_plugin)

    with patch("app.search_engine.plugins.ddg.DdgPlugin", MockDdg):
        results = _arun(node.execute(
            {},
            [{"query": "query A"}, {"query": "query B"}],
            CTX,
        ))

    assert call_count == 2
    assert len(results) == 2
    queries_used = {r["query"] for r in results}
    assert queries_used == {"query A", "query B"}
