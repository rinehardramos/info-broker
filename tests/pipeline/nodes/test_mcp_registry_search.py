"""Tests for MCP registry search node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.mcp_registry_search import MCPRegistrySearchNode, _search_mcp_registry
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = MCPRegistrySearchNode()
    assert node.node_type == "mcp_registry_search"
    assert node.category == "source"

def test_search_returns_results():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"servers": [
        {"name": "github-mcp", "description": "GitHub MCP server", "url": "https://github.com/mcp/github",
         "tools": ["search_repos", "get_issues"], "category": "developer"},
    ]}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        results = _search_mcp_registry("github", 5)
    assert len(results) >= 1
    assert results[0]["name"] == "github-mcp"

def test_execute_searches():
    with patch("app.pipeline.nodes.mcp_registry_search._search_mcp_registry") as m:
        m.return_value = [{"name": "test-mcp", "description": "A test server", "source": "mcp_registry_search"}]
        results = _arun(MCPRegistrySearchNode().execute({"query": "test"}, [], CTX))
    assert results[0]["name"] == "test-mcp"

def test_execute_no_query():
    results = _arun(MCPRegistrySearchNode().execute({}, [], CTX))
    assert results[0].get("error")
