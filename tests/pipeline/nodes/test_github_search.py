"""Tests for GitHub search node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.github_search import GithubSearchNode, _search_repos
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = GithubSearchNode()
    assert node.node_type == "github_search"
    assert node.category == "source"

def test_search_repos_returns_results():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"items": [
        {"full_name": "user/repo", "description": "A repo", "html_url": "https://github.com/user/repo",
         "stargazers_count": 100, "language": "Python", "updated_at": "2026-01-01"},
    ]}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        results = _search_repos("OSINT tool", None, 10)
    assert len(results) == 1
    assert results[0]["full_name"] == "user/repo"
    assert results[0]["stars"] == 100

def test_execute_searches():
    with patch("app.pipeline.nodes.github_search._search_repos") as m:
        m.return_value = [{"full_name": "x/y", "url": "https://github.com/x/y", "stars": 50, "source": "github_search"}]
        results = _arun(GithubSearchNode().execute({"query": "osint"}, [], CTX))
    assert results[0]["full_name"] == "x/y"

def test_execute_no_query():
    results = _arun(GithubSearchNode().execute({}, [], CTX))
    assert results[0].get("error")
