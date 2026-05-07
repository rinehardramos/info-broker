"""Tests for username enumerator node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.username_enumerator import UsernameEnumeratorNode, _check_platform, PLATFORMS
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = UsernameEnumeratorNode()
    assert node.node_type == "username_enumerator"
    assert node.category == "enrich"

def test_platforms_defined():
    assert len(PLATFORMS) >= 8
    assert any(p["name"] == "github" for p in PLATFORMS)
    assert any(p["name"] == "twitter" for p in PLATFORMS)

def test_check_platform_found():
    resp = MagicMock(status_code=200)
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _check_platform("johndoe", {"name": "github", "url_pattern": "https://github.com/{}", "check": "status_200"})
    assert result["exists"] is True
    assert result["platform"] == "github"

def test_check_platform_not_found():
    resp = MagicMock(status_code=404)
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _check_platform("johndoe", {"name": "github", "url_pattern": "https://github.com/{}", "check": "status_200"})
    assert result["exists"] is False

def test_execute_checks_platforms():
    with patch("app.pipeline.nodes.username_enumerator._check_platform") as m:
        m.return_value = {"platform": "github", "url": "https://github.com/johndoe", "exists": True}
        results = _arun(UsernameEnumeratorNode().execute(
            {"username": "johndoe", "platforms": ["github"]}, [], CTX))
    assert len(results) >= 1
    assert results[0]["exists"] is True

def test_execute_from_inputs():
    with patch("app.pipeline.nodes.username_enumerator._check_platform") as m:
        m.return_value = {"platform": "github", "url": "x", "exists": False}
        results = _arun(UsernameEnumeratorNode().execute(
            {}, [{"username": "testuser"}], CTX))
    assert len(results) >= 1

def test_execute_no_username_error():
    results = _arun(UsernameEnumeratorNode().execute({}, [], CTX))
    assert results[0].get("error")
