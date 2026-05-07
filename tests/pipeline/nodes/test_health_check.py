"""Unit tests for the plugin health check system."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from app.pipeline.nodes.apify_actor import ApifyActorNode
from app.pipeline.nodes.apify_mcp import ApifyMcpNode
from app.pipeline.nodes.linkedin_profile import LinkedInProfileNode
from app.pipeline.nodes.base import HealthStatus


def _arun(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# HealthStatus TypedDict
# ---------------------------------------------------------------------------

def test_health_status_typeddict_keys():
    status = HealthStatus(
        healthy=True,
        error=None,
        requires_key="APIFY_API_TOKEN",
        setup_url="/settings",
        setup_instructions=None,
    )
    assert status["healthy"] is True
    assert status["error"] is None
    assert status["requires_key"] == "APIFY_API_TOKEN"
    assert status["setup_url"] == "/settings"
    assert status["setup_instructions"] is None


def test_health_status_unhealthy():
    status = HealthStatus(
        healthy=False,
        error="key not configured",
        requires_key="APIFY_API_TOKEN",
        setup_url="/settings",
        setup_instructions="Add token in Settings.",
    )
    assert status["healthy"] is False
    assert status["error"] == "key not configured"


# ---------------------------------------------------------------------------
# ApifyActorNode.health_check
# ---------------------------------------------------------------------------

def test_apify_actor_health_check_no_key():
    node = ApifyActorNode()
    with patch("app.pipeline.nodes.apify_actor._resolve_api_key", side_effect=RuntimeError("no key")):
        result = _arun(node.health_check())
    assert result["healthy"] is False
    assert result["requires_key"] == "APIFY_API_TOKEN"
    assert result["error"] is not None


def test_apify_actor_health_check_with_invalid_key():
    """When key exists but Apify returns 401, should be unhealthy."""
    node = ApifyActorNode()

    mock_resp = MagicMock()
    mock_resp.status_code = 401

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="bad-key"),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = _arun(node.health_check())
    assert result["healthy"] is False
    assert "401" in result["error"]


def test_apify_actor_health_check_with_valid_key():
    """When key exists and Apify returns 200, should be healthy."""
    node = ApifyActorNode()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="good-key"),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = _arun(node.health_check())
    assert result["healthy"] is True
    assert result["error"] is None


# ---------------------------------------------------------------------------
# ApifyMcpNode.health_check
# ---------------------------------------------------------------------------

def test_apify_mcp_health_check_no_key():
    node = ApifyMcpNode()
    with patch("app.pipeline.nodes.apify_actor._resolve_api_key", side_effect=RuntimeError("no key")):
        result = _arun(node.health_check())
    assert result["healthy"] is False
    assert result["requires_key"] == "APIFY_API_TOKEN"
    assert result["error"] is not None


def test_apify_mcp_health_check_with_key():
    node = ApifyMcpNode()
    with patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"):
        result = _arun(node.health_check())
    assert result["healthy"] is True
    assert result["error"] is None


# ---------------------------------------------------------------------------
# LinkedInProfileNode.health_check
# ---------------------------------------------------------------------------

def test_linkedin_profile_health_check_no_key():
    node = LinkedInProfileNode()
    with patch("app.pipeline.nodes.apify_actor._resolve_api_key", side_effect=RuntimeError("no key")):
        result = _arun(node.health_check())
    assert result["healthy"] is False
    assert result["requires_key"] == "APIFY_API_TOKEN"
    assert result["error"] is not None


def test_linkedin_profile_health_check_with_key():
    node = LinkedInProfileNode()
    with patch("app.pipeline.nodes.apify_actor._resolve_api_key", return_value="fake-key"):
        result = _arun(node.health_check())
    assert result["healthy"] is True
    assert result["error"] is None


# ---------------------------------------------------------------------------
# Nodes without health_check have no health_check attribute
# ---------------------------------------------------------------------------

def test_ddg_search_has_no_health_check():
    from app.pipeline.nodes.ddg_search import DdgSearchNode
    node = DdgSearchNode()
    assert not hasattr(node, "health_check")


def test_wikipedia_has_no_health_check():
    from app.pipeline.nodes.wikipedia_api import WikipediaApiNode
    node = WikipediaApiNode()
    assert not hasattr(node, "health_check")


# ---------------------------------------------------------------------------
# get_healthy_nodes helper
# ---------------------------------------------------------------------------

def test_get_healthy_nodes_excludes_agent_input_and_is(monkeypatch):
    """get_healthy_nodes must never include agent_input or intelligent_search."""
    from app.routers.v3.pipelines import get_healthy_nodes

    monkeypatch.setattr(
        "app.routers.v3.pipelines._is_node_enabled",
        lambda nt: True,
    )
    monkeypatch.setattr(
        "app.pipeline.nodes.apify_actor._resolve_api_key",
        lambda: "fake-key",
    )

    result = _arun(get_healthy_nodes())
    node_types = [r["node_type"] for r in result]
    assert "agent_input" not in node_types
    assert "intelligent_search" not in node_types


def test_get_healthy_nodes_excludes_unhealthy(monkeypatch):
    """Nodes whose health_check returns healthy=False must be excluded."""
    from app.routers.v3.pipelines import get_healthy_nodes, _health_cache

    _health_cache.clear()

    monkeypatch.setattr(
        "app.routers.v3.pipelines._is_node_enabled",
        lambda nt: True,
    )
    monkeypatch.setattr(
        "app.pipeline.nodes.apify_actor._resolve_api_key",
        lambda: (_ for _ in ()).throw(RuntimeError("no key")),
    )

    result = _arun(get_healthy_nodes())
    node_types = [r["node_type"] for r in result]
    assert "apify_actor" not in node_types
    assert "apify_mcp" not in node_types
    assert "linkedin_profile" not in node_types


def test_get_healthy_nodes_result_shape(monkeypatch):
    """Each entry must have the required keys."""
    from app.routers.v3.pipelines import get_healthy_nodes, _health_cache

    _health_cache.clear()

    monkeypatch.setattr(
        "app.routers.v3.pipelines._is_node_enabled",
        lambda nt: True,
    )
    monkeypatch.setattr(
        "app.pipeline.nodes.apify_actor._resolve_api_key",
        lambda: "fake-key",
    )

    result = _arun(get_healthy_nodes())
    assert len(result) > 0
    for entry in result:
        assert "node_type" in entry
        assert "mcp_tool_name" in entry
        assert "display_name" in entry
        assert "params" in entry
        assert entry["mcp_tool_name"] == f"run_{entry['node_type']}"
