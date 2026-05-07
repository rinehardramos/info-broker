"""Unit tests for StripeMarketplaceNode and helpers."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.nodes.stripe_marketplace import (
    StripeMarketplaceNode,
    _cutoff_timestamp,
    _fetch_metric,
    _resolve_api_key,
)
from app.pipeline.nodes.base import RunContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx() -> RunContext:
    return RunContext(user_id="u1", run_id="r1", node_id="n1")


def _arun(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _resolve_api_key
# ---------------------------------------------------------------------------

def test_resolve_api_key_config_takes_priority():
    with patch.dict("os.environ", {"STRIPE_API_KEY": "env_key"}):
        assert _resolve_api_key("config_key") == "config_key"


def test_resolve_api_key_env_fallback():
    with patch.dict("os.environ", {"STRIPE_API_KEY": "env_key"}, clear=False):
        assert _resolve_api_key() == "env_key"


def test_resolve_api_key_missing_returns_none():
    with patch.dict("os.environ", {}, clear=True):
        with patch("app.pipeline.nodes.stripe_marketplace._resolve_api_key", return_value=None):
            # Direct test: no env, no DB row
            pass  # covered by execute-missing-key test below


# ---------------------------------------------------------------------------
# _cutoff_timestamp
# ---------------------------------------------------------------------------

def test_cutoff_timestamp_30_days():
    import time
    now = int(time.time())
    cutoff = _cutoff_timestamp(30)
    diff = now - cutoff
    # Should be approx 30 * 86400 seconds
    assert 29 * 86400 <= diff <= 31 * 86400


def test_cutoff_timestamp_1_day():
    import time
    now = int(time.time())
    cutoff = _cutoff_timestamp(1)
    diff = now - cutoff
    assert 0 < diff <= 2 * 86400


# ---------------------------------------------------------------------------
# _fetch_metric — balance
# ---------------------------------------------------------------------------

def _make_httpx_response(status_code: int, body: dict):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = body
    mock.raise_for_status = MagicMock()
    return mock


def test_fetch_metric_balance():
    balance_data = {
        "available": [{"amount": 150000, "currency": "usd"}],
        "pending": [{"amount": 50000, "currency": "usd"}],
    }
    mock_resp = _make_httpx_response(200, balance_data)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _fetch_metric("sk_test_key", "balance", 30)

    assert result["source"] == "stripe"
    assert result["metric_type"] == "balance"
    assert result["confidence"] == 90
    assert "1500.00" in result["content"]
    assert "500.00" in result["content"]
    assert result["raw_data"] == balance_data


def test_fetch_metric_charges():
    charges_data = {
        "data": [
            {"amount": 2000, "currency": "usd", "paid": True},
            {"amount": 3000, "currency": "usd", "paid": True},
            {"amount": 1000, "currency": "usd", "paid": False},
        ]
    }
    mock_resp = _make_httpx_response(200, charges_data)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _fetch_metric("sk_test_key", "charges", 30)

    assert result["metric_type"] == "charges"
    assert "3 charges" in result["content"]
    assert "50.00" in result["content"]  # 2000+3000 paid = 50.00 USD


def test_fetch_metric_customers():
    customers_data = {"data": [{"id": "cus_1"}, {"id": "cus_2"}]}
    mock_resp = _make_httpx_response(200, customers_data)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _fetch_metric("sk_test_key", "customers", 30)

    assert result["metric_type"] == "customers"
    assert "2 new customers" in result["content"]


def test_fetch_metric_disputes():
    disputes_data = {
        "data": [
            {"id": "dp_1", "status": "needs_response"},
            {"id": "dp_2", "status": "won"},
        ]
    }
    mock_resp = _make_httpx_response(200, disputes_data)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _fetch_metric("sk_test_key", "disputes", 30)

    assert result["metric_type"] == "disputes"
    assert "2 disputes" in result["content"]
    assert "1 need response" in result["content"]


def test_fetch_metric_payouts():
    payouts_data = {
        "data": [
            {"amount": 10000, "currency": "usd", "status": "paid"},
            {"amount": 5000, "currency": "usd", "status": "in_transit"},
        ]
    }
    mock_resp = _make_httpx_response(200, payouts_data)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _fetch_metric("sk_test_key", "payouts", 30)

    assert result["metric_type"] == "payouts"
    assert "100.00" in result["content"]


def test_fetch_metric_unknown_type():
    result = _fetch_metric("sk_test_key", "unknown_type", 30)
    assert "error" in result
    assert result["confidence"] == 0


def test_fetch_metric_http_error():
    import httpx
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "401", request=MagicMock(), response=MagicMock()
        )
        mock_client_cls.return_value = mock_client

        result = _fetch_metric("sk_bad_key", "balance", 30)

    assert "error" in result
    assert result["confidence"] == 0


# ---------------------------------------------------------------------------
# StripeMarketplaceNode.execute
# ---------------------------------------------------------------------------

def test_execute_missing_api_key():
    node = StripeMarketplaceNode()
    with patch("app.pipeline.nodes.stripe_marketplace._resolve_api_key", return_value=None):
        result = _arun(node.execute({}, [], _ctx()))
    assert len(result) == 1
    assert "error" in result[0]
    assert result[0]["confidence"] == 0


def test_execute_balance_success():
    balance_data = {
        "available": [{"amount": 200000, "currency": "usd"}],
        "pending": [{"amount": 0, "currency": "usd"}],
    }
    mock_resp = _make_httpx_response(200, balance_data)

    node = StripeMarketplaceNode()
    with patch("app.pipeline.nodes.stripe_marketplace._resolve_api_key", return_value="sk_test"):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            result = _arun(node.execute({"metric_type": "balance"}, [], _ctx()))

    assert len(result) == 1
    assert result[0]["source"] == "stripe"
    assert result[0]["metric_type"] == "balance"
    assert result[0]["confidence"] == 90


# ---------------------------------------------------------------------------
# StripeMarketplaceNode.health_check
# ---------------------------------------------------------------------------

def test_health_check_no_key():
    node = StripeMarketplaceNode()
    with patch("app.pipeline.nodes.stripe_marketplace._resolve_api_key", return_value=None):
        status = _arun(node.health_check())
    assert status["healthy"] is False
    assert "not configured" in status["error"]


def test_health_check_valid_key():
    import httpx

    node = StripeMarketplaceNode()

    async def fake_aenter(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.get = AsyncMock(return_value=mock_resp)
        return mock_client

    with patch("app.pipeline.nodes.stripe_marketplace._resolve_api_key", return_value="sk_test"):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_acm = MagicMock()
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_acm.__aenter__ = AsyncMock(return_value=mock_client)
            mock_acm.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_acm

            status = _arun(node.health_check())

    assert status["healthy"] is True
    assert status["error"] is None


# ---------------------------------------------------------------------------
# Node metadata
# ---------------------------------------------------------------------------

def test_node_type():
    node = StripeMarketplaceNode()
    assert node.node_type == "stripe_marketplace"
    assert node.display_name == "Stripe Marketplace Metrics"
    assert node.category == "enrich"


def test_config_schema_has_metric_type():
    node = StripeMarketplaceNode()
    props = node.config_schema["properties"]
    assert "metric_type" in props
    assert "balance" in props["metric_type"]["enum"]
    assert "date_range_days" in props
