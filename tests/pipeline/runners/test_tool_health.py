"""Unit tests for app.pipeline.runners.tool_health."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.pipeline.runners.tool_health import (
    _tool_name_to_node,
    is_unhealthy,
    missing_key,
    technique_health,
)


# ---------------------------------------------------------------------------
# _tool_name_to_node mapping
# ---------------------------------------------------------------------------

def test_run_prefix_strips_to_node():
    assert _tool_name_to_node("run_hunter_io") == "hunter_io"
    assert _tool_name_to_node("run_apollo_search") == "apollo_search"
    assert _tool_name_to_node("run_phone_osint") == "phone_osint"
    assert _tool_name_to_node("run_pipl_search") == "pipl_search"
    assert _tool_name_to_node("run_opencorporates") == "opencorporates"
    assert _tool_name_to_node("run_whois_lookup") == "whois_lookup"
    assert _tool_name_to_node("run_web_search") == "web_search"


def test_apify_actor_run_maps_to_apify_actor():
    assert _tool_name_to_node("apify_actor_run") == "apify_actor"


def test_get_past_research_maps_to_none():
    # no backing node → always healthy
    assert _tool_name_to_node("get_past_research") is None


def test_unknown_tool_name_falls_back_to_strip():
    # Generic fallback: strip run_ prefix
    assert _tool_name_to_node("run_some_future_tool") == "some_future_tool"


def test_no_run_prefix_unknown_returns_none():
    # Can't map — return None (treat healthy)
    assert _tool_name_to_node("totally_unknown") is None


# ---------------------------------------------------------------------------
# technique_health — cache-empty → None (treat healthy)
# ---------------------------------------------------------------------------

def test_technique_health_empty_cache_returns_none():
    """When the health cache has no entry for a node, return None (treat as healthy)."""
    with patch("app.routers.v3.pipelines._health_cache", {}):
        result = technique_health("hunter_email_search")
    assert result is None


# ---------------------------------------------------------------------------
# technique_health — cache populated with requires_key
# ---------------------------------------------------------------------------

def test_technique_health_returns_unhealthy_when_cache_says_requires_key():
    """When cache says requires_key, technique_health returns the HealthStatus dict."""
    fake_status = {
        "healthy": False,
        "error": "HUNTER_API_KEY not set",
        "requires_key": "HUNTER_API_KEY",
        "setup_url": "/settings",
        "setup_instructions": None,
    }
    fake_cache = {"hunter_io": (time.time(), fake_status)}
    with patch("app.routers.v3.pipelines._health_cache", fake_cache):
        result = technique_health("hunter_email_search")
    assert result is not None
    assert result["healthy"] is False
    assert result["requires_key"] == "HUNTER_API_KEY"


def test_is_unhealthy_true_when_requires_key():
    fake_status = {
        "healthy": False,
        "error": "HUNTER_API_KEY not set",
        "requires_key": "HUNTER_API_KEY",
        "setup_url": None,
        "setup_instructions": None,
    }
    fake_cache = {"hunter_io": (time.time(), fake_status)}
    with patch("app.routers.v3.pipelines._health_cache", fake_cache):
        assert is_unhealthy("hunter_email_search") is True


def test_is_unhealthy_false_when_cache_empty():
    """Cache miss → not unhealthy (best-effort, don't over-suppress)."""
    with patch("app.routers.v3.pipelines._health_cache", {}):
        assert is_unhealthy("hunter_email_search") is False


def test_missing_key_returns_key_name():
    fake_status = {
        "healthy": False,
        "error": "HUNTER_API_KEY not set",
        "requires_key": "HUNTER_API_KEY",
        "setup_url": None,
        "setup_instructions": None,
    }
    fake_cache = {"hunter_io": (time.time(), fake_status)}
    with patch("app.routers.v3.pipelines._health_cache", fake_cache):
        assert missing_key("hunter_email_search") == "HUNTER_API_KEY"


def test_missing_key_returns_none_when_healthy():
    fake_status = {
        "healthy": True,
        "error": None,
        "requires_key": None,
        "setup_url": None,
        "setup_instructions": None,
    }
    fake_cache = {"hunter_io": (time.time(), fake_status)}
    with patch("app.routers.v3.pipelines._health_cache", fake_cache):
        assert missing_key("hunter_email_search") is None


def test_technique_health_stale_cache_returns_none():
    """A stale cache entry (beyond TTL) should be treated as unknown → None."""
    fake_status = {
        "healthy": False,
        "error": "key missing",
        "requires_key": "HUNTER_API_KEY",
        "setup_url": None,
        "setup_instructions": None,
    }
    # timestamp far in the past (3600s old)
    stale_time = time.time() - 3600
    fake_cache = {"hunter_io": (stale_time, fake_status)}
    with patch("app.routers.v3.pipelines._health_cache", fake_cache):
        result = technique_health("hunter_email_search")
    assert result is None


def test_is_unhealthy_apify_listings_search_cache_miss():
    """apify_listings_search maps to apify_actor; cache miss → not unhealthy."""
    with patch("app.routers.v3.pipelines._health_cache", {}):
        assert is_unhealthy("apify_listings_search") is False
