"""Tests for crypto/blockchain tracer node."""
from __future__ import annotations
import asyncio
from unittest.mock import MagicMock, patch
from app.pipeline.nodes.crypto_tracer import CryptoTracerNode, _lookup_etherscan, _detect_chain
from app.pipeline.nodes.base import RunContext

CTX = RunContext(user_id="test", run_id="test", node_id="test")
def _arun(coro): return asyncio.run(coro)

def test_node_metadata():
    node = CryptoTracerNode()
    assert node.node_type == "crypto_tracer"
    assert node.category == "enrich"

def test_detect_chain_ethereum():
    assert _detect_chain("0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28") == "ethereum"

def test_detect_chain_bitcoin():
    assert _detect_chain("bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq") == "bitcoin"
    assert _detect_chain("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa") == "bitcoin"

def test_detect_chain_unknown():
    assert _detect_chain("not_a_wallet") == "unknown"

def test_lookup_etherscan():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": "1", "result": "1000000000000000000"}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    with patch("httpx.Client", return_value=client):
        result = _lookup_etherscan("0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28", "fake-key")
    assert result["balance_wei"] == "1000000000000000000"

def test_execute_with_key():
    with (
        patch("app.pipeline.nodes.crypto_tracer._resolve_api_key", return_value="k"),
        patch("app.pipeline.nodes.crypto_tracer._lookup_etherscan") as m,
    ):
        m.return_value = {"address": "0x123", "balance_wei": "1000", "balance_eth": "0.000000001",
            "tx_count": 5, "source": "etherscan", "reason": "r"}
        results = _arun(CryptoTracerNode().execute(
            {"wallet_address": "0x123"}, [], CTX))
    assert results[0]["balance_wei"] == "1000"

def test_execute_no_key_returns_note():
    with patch("app.pipeline.nodes.crypto_tracer._resolve_api_key", return_value=None):
        results = _arun(CryptoTracerNode().execute(
            {"wallet_address": "0x123"}, [], CTX))
    assert "source" in results[0]

def test_execute_no_address_error():
    results = _arun(CryptoTracerNode().execute({}, [], CTX))
    assert results[0].get("error")
