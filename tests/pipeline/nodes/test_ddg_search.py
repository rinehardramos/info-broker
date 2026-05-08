"""Tests for DdgSearchNode — web, images, videos, news search modes."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline.nodes.base import RunContext
from app.pipeline.nodes.ddg_search import DdgSearchNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx() -> RunContext:
    return RunContext(user_id="u1", run_id="run-1", node_id="n1")


def _arun(coro):
    return asyncio.run(coro)


_INPUT = [{"query": "test query"}]


def _make_mock_ddgs(return_attr: str, return_value: list):
    """Build a DDGS context-manager mock that returns return_value from return_attr."""
    instance = MagicMock()
    instance.__enter__ = lambda s: s
    instance.__exit__ = MagicMock(return_value=False)
    getattr(instance, return_attr).return_value = return_value
    mock_cls = MagicMock(return_value=instance)
    return mock_cls, instance


# ---------------------------------------------------------------------------
# Config schema tests
# ---------------------------------------------------------------------------

def test_ddg_config_has_search_type():
    node = DdgSearchNode()
    props = node.config_schema.get("properties", {})
    assert "search_type" in props


def test_ddg_search_type_enum():
    node = DdgSearchNode()
    enum_vals = node.config_schema["properties"]["search_type"].get("enum", [])
    assert set(enum_vals) == {"web", "images", "videos", "news"}


def test_ddg_search_type_default_web():
    node = DdgSearchNode()
    default = node.config_schema["properties"]["search_type"].get("default")
    assert default == "web"


# ---------------------------------------------------------------------------
# Web search (default) — DDGS.text() called
# ---------------------------------------------------------------------------

def test_ddg_web_search_calls_text():
    node = DdgSearchNode()
    mock_cls, instance = _make_mock_ddgs(
        "text",
        [{"title": "Web Result", "href": "https://example.com", "body": "snippet text"}],
    )

    with patch("app.search_engine.plugins.ddg.DDGS", mock_cls):
        results = _arun(node.execute({}, _INPUT, _ctx()))

    instance.text.assert_called_once()
    assert len(results) == 1
    assert results[0]["title"] == "Web Result"
    assert results[0]["url"] == "https://example.com"
    assert results[0]["source"] == "ddg"


def test_ddg_explicit_web_search_type_calls_text():
    node = DdgSearchNode()
    mock_cls, instance = _make_mock_ddgs(
        "text",
        [{"title": "Web Result", "href": "https://example.com", "body": "snippet"}],
    )

    with patch("app.search_engine.plugins.ddg.DDGS", mock_cls):
        results = _arun(node.execute({"search_type": "web"}, _INPUT, _ctx()))

    instance.text.assert_called_once()
    instance.images.assert_not_called()
    instance.videos.assert_not_called()
    instance.news.assert_not_called()


# ---------------------------------------------------------------------------
# Images search — DDGS.images() called
# ---------------------------------------------------------------------------

def test_ddg_search_type_images():
    node = DdgSearchNode()
    mock_cls, instance = _make_mock_ddgs(
        "images",
        [
            {
                "title": "Cool Image",
                "image": "https://cdn.example.com/img.jpg",
                "thumbnail": "https://cdn.example.com/thumb.jpg",
                "url": "https://example.com/page",
            }
        ],
    )

    with patch("app.search_engine.plugins.ddg.DDGS", mock_cls):
        results = _arun(node.execute({"search_type": "images"}, _INPUT, _ctx()))

    instance.images.assert_called_once()
    instance.text.assert_not_called()
    assert len(results) == 1
    assert results[0]["title"] == "Cool Image"
    assert results[0]["image"] == "https://cdn.example.com/img.jpg"
    assert results[0]["thumbnail"] == "https://cdn.example.com/thumb.jpg"
    assert results[0]["url"] == "https://example.com/page"
    assert results[0]["source"] == "ddg"
    assert results[0]["search_type"] == "images"


# ---------------------------------------------------------------------------
# Videos search — DDGS.videos() called
# ---------------------------------------------------------------------------

def test_ddg_search_type_videos():
    node = DdgSearchNode()
    mock_cls, instance = _make_mock_ddgs(
        "videos",
        [
            {
                "title": "Great Video",
                "content": "https://video.example.com/v.mp4",
                "publisher": "ExampleTV",
                "url": "https://video.example.com/watch",
            }
        ],
    )

    with patch("app.search_engine.plugins.ddg.DDGS", mock_cls):
        results = _arun(node.execute({"search_type": "videos"}, _INPUT, _ctx()))

    instance.videos.assert_called_once()
    instance.text.assert_not_called()
    assert len(results) == 1
    assert results[0]["title"] == "Great Video"
    assert results[0]["content"] == "https://video.example.com/v.mp4"
    assert results[0]["publisher"] == "ExampleTV"
    assert results[0]["url"] == "https://video.example.com/watch"
    assert results[0]["source"] == "ddg"
    assert results[0]["search_type"] == "videos"


# ---------------------------------------------------------------------------
# News search — DDGS.news() called
# ---------------------------------------------------------------------------

def test_ddg_search_type_news():
    node = DdgSearchNode()
    mock_cls, instance = _make_mock_ddgs(
        "news",
        [
            {
                "title": "Breaking News",
                "body": "Something happened today.",
                "date": "2026-05-07T10:00:00",
                "url": "https://news.example.com/article",
                "source": "ExampleNews",
            }
        ],
    )

    with patch("app.search_engine.plugins.ddg.DDGS", mock_cls):
        results = _arun(node.execute({"search_type": "news"}, _INPUT, _ctx()))

    instance.news.assert_called_once()
    instance.text.assert_not_called()
    assert len(results) == 1
    assert results[0]["title"] == "Breaking News"
    assert results[0]["snippet"] == "Something happened today."
    assert results[0]["date"] == "2026-05-07T10:00:00"
    assert results[0]["url"] == "https://news.example.com/article"
    assert results[0]["news_source"] == "ExampleNews"
    assert results[0]["source"] == "ddg"
    assert results[0]["search_type"] == "news"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_ddg_skips_empty_query():
    node = DdgSearchNode()
    results = _arun(node.execute({"search_type": "news"}, [{"query": ""}], _ctx()))
    assert results == []


def test_ddg_multiple_inputs_images():
    node = DdgSearchNode()
    mock_cls, instance = _make_mock_ddgs(
        "images",
        [{"title": "Img", "image": "https://i.example.com/1.jpg", "thumbnail": "", "url": "https://example.com"}],
    )

    inputs = [{"query": "cats"}, {"query": "dogs"}]
    with patch("app.search_engine.plugins.ddg.DDGS", mock_cls):
        results = _arun(node.execute({"search_type": "images"}, inputs, _ctx()))

    assert instance.images.call_count == 2
    assert len(results) == 2
