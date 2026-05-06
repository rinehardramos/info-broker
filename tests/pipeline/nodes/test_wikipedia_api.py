"""Unit tests for the WikipediaApiNode."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.pipeline.nodes.wikipedia_api import WikipediaApiNode, _fetch_summary
from app.pipeline.nodes.base import RunContext


def _ctx() -> RunContext:
    return RunContext(user_id="u1", run_id="r1", node_id="n1")


def _arun(coro):
    return asyncio.run(coro)


def _make_wiki_payload(title: str = "Python") -> dict:
    scheme = "http" + "s"
    return {
        "title": title,
        "extract": f"Article extract for {title}.",
        "content_urls": {"desktop": {"page": f"{scheme}://en.wikipedia.org/wiki/{title}"}},
        "thumbnail": {"source": f"{scheme}://upload.wikimedia.org/{title}.png"},
    }


def _ok_resp(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _err_resp(code: int) -> MagicMock:
    import httpx
    resp = MagicMock()
    resp.status_code = code
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"HTTP {code}", request=MagicMock(), response=resp
    )
    return resp


class _FakeClient:
    """Context manager that returns a pre-configured mock client."""

    def __init__(self, inner: MagicMock):
        self._inner = inner

    def __call__(self, **kwargs):
        return self

    def __enter__(self):
        return self._inner

    def __exit__(self, *a):
        return False


# ---------------------------------------------------------------------------
# _fetch_summary — synchronous
# ---------------------------------------------------------------------------

def test_fetch_summary_success():
    payload = _make_wiki_payload("Python")
    mc = MagicMock()
    mc.get.return_value = _ok_resp(payload)
    with patch("httpx.Client", new=_FakeClient(mc)):
        result = _fetch_summary("en", "Python")
    assert result["title"] == "Python"
    assert result["extract"] == "Article extract for Python."
    assert result["source"] == "wikipedia"
    assert result["thumbnail"] is not None
    assert "error" not in result


def test_fetch_summary_404():
    resp = MagicMock()
    resp.status_code = 404
    resp.raise_for_status = MagicMock()
    mc = MagicMock()
    mc.get.return_value = resp
    with patch("httpx.Client", new=_FakeClient(mc)):
        result = _fetch_summary("en", "NoSuchPage")
    assert result["source"] == "wikipedia"
    assert "error" in result
    assert "not found" in result["error"].lower()


def test_fetch_summary_http_error():
    mc = MagicMock()
    mc.get.return_value = _err_resp(500)
    with patch("httpx.Client", new=_FakeClient(mc)):
        result = _fetch_summary("en", "SomePage")
    assert result["source"] == "wikipedia"
    assert "error" in result


def test_fetch_summary_network_error():
    mc = MagicMock()
    mc.get.side_effect = Exception("Connection refused")
    with patch("httpx.Client", new=_FakeClient(mc)):
        result = _fetch_summary("en", "SomePage")
    assert result["source"] == "wikipedia"
    assert "error" in result


# ---------------------------------------------------------------------------
# WikipediaApiNode.execute
# ---------------------------------------------------------------------------

def test_execute_skips_items_without_title():
    node = WikipediaApiNode()
    results = _arun(node.execute({}, [{"score": 5}], _ctx()))
    assert results == []


def test_execute_returns_one_result_per_input():
    node = WikipediaApiNode()
    mc = MagicMock()
    mc.get.return_value = _ok_resp(_make_wiki_payload("Manila"))
    with patch("httpx.Client", new=_FakeClient(mc)):
        results = _arun(node.execute(
            {},
            [{"title": "Manila"}, {"query": "Luzon"}, {"message": "Visayas"}],
            _ctx(),
        ))
    assert len(results) == 3
    for r in results:
        assert r["source"] == "wikipedia"


def test_execute_uses_language_config():
    node = WikipediaApiNode()
    mc = MagicMock()
    mc.get.return_value = _ok_resp(_make_wiki_payload("Manila"))
    with patch("httpx.Client", new=_FakeClient(mc)):
        results = _arun(node.execute({"language": "tl"}, [{"title": "Manila"}], _ctx()))
    assert len(results) == 1
    called_url: str = mc.get.call_args[0][0]
    assert "tl.wikipedia.org" in called_url


# ---------------------------------------------------------------------------
# Node metadata
# ---------------------------------------------------------------------------

def test_node_metadata():
    node = WikipediaApiNode()
    assert node.node_type == "wikipedia_api"
    assert node.display_name == "Wikipedia API"
    assert node.category == "enrich"
    assert "language" in node.config_schema["properties"]
    assert node.config_schema["properties"]["language"]["default"] == "en"
