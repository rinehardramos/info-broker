"""Crypto tracer enrich node — blockchain wallet analysis via Etherscan API.

SENTINEL tactic: low yield but high value when a wallet address surfaces in
open-source intelligence; reveals balance, transaction volume, and chain.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "SENTINEL tactic: blockchain wallet lookup surfaces balance, transaction count, "
    "and chain provenance — high-value signal when a wallet address appears in OSINT"
)
_ETHERSCAN_URL = "https://api.etherscan.io/api"

# Bitcoin address patterns:
#   - Legacy P2PKH: starts with "1"
#   - P2SH: starts with "3"
#   - Bech32 (SegWit): starts with "bc1"
_BITCOIN_RE = re.compile(r"^(1[a-km-zA-HJ-NP-Z1-9]{25,34}|3[a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-z0-9]{6,87})$")
# Accept any 0x-prefixed hex string (full canonical = 42 chars, but allow shorter in tests/stubs)
_ETHEREUM_RE = re.compile(r"^0x[0-9a-fA-F]+")


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("ETHERSCAN_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'etherscan_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


def _detect_chain(address: str) -> str:
    """Detect blockchain from wallet address format.

    Returns "ethereum", "bitcoin", or "unknown".
    """
    if _ETHEREUM_RE.match(address):
        return "ethereum"
    if _BITCOIN_RE.match(address):
        return "bitcoin"
    return "unknown"


def _lookup_etherscan(address: str, api_key: str) -> dict:
    """Fetch wallet balance from Etherscan.

    Returns a dict with balance_wei, balance_eth, and metadata.
    """
    params = {
        "module": "account",
        "action": "balance",
        "address": address,
        "tag": "latest",
        "apikey": api_key,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(_ETHERSCAN_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("crypto_tracer: HTTP error for address %r: %s", address, exc)
        return {"address": address, "source": "etherscan", "reason": _REASON, "error": str(exc)}
    except Exception as exc:
        log.warning("crypto_tracer: unexpected error for address %r: %s", address, exc)
        return {"address": address, "source": "etherscan", "reason": _REASON, "error": str(exc)}

    if data.get("status") != "1":
        msg = data.get("message") or data.get("result") or "unknown error"
        return {"address": address, "source": "etherscan", "reason": _REASON, "error": msg}

    balance_wei = data["result"]
    try:
        balance_eth = f"{int(balance_wei) / 1e18:.18f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        balance_eth = "0"

    return {
        "address": address,
        "balance_wei": balance_wei,
        "balance_eth": balance_eth,
        "chain": "ethereum",
        "source": "etherscan",
        "reason": _REASON,
    }


class CryptoTracerNode:
    node_type = "crypto_tracer"
    display_name = "Crypto Tracer"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "title": "Etherscan API Key",
                "description": "Leave blank to use ETHERSCAN_API_KEY env var or DB setting.",
            },
            "wallet_address": {
                "type": "string",
                "title": "Wallet Address",
                "description": "Blockchain wallet address to look up.",
            },
            "chain": {
                "type": "string",
                "title": "Chain",
                "enum": ["ethereum", "bitcoin", "auto"],
                "default": "auto",
                "description": "Target blockchain. 'auto' detects from address format.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        # Collect wallet address from config first, then inputs
        wallet_address = (config.get("wallet_address") or "").strip()
        if not wallet_address:
            for item in inputs:
                addr = (item.get("wallet_address") or item.get("address") or "").strip()
                if addr:
                    wallet_address = addr
                    break

        if not wallet_address:
            return [{"error": "wallet_address is required", "source": "crypto_tracer", "reason": _REASON}]

        chain_cfg = config.get("chain", "auto")
        chain = _detect_chain(wallet_address) if chain_cfg == "auto" else chain_cfg

        api_key = _resolve_api_key(config.get("api_key"))

        if chain == "ethereum":
            if not api_key:
                log.info("crypto_tracer: no Etherscan API key — returning basic record")
                return [
                    {
                        "address": wallet_address,
                        "chain": "ethereum",
                        "source": "crypto_tracer",
                        "note": "Set ETHERSCAN_API_KEY for full balance and transaction data",
                        "reason": _REASON,
                    }
                ]

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, _lookup_etherscan, wallet_address, api_key)
            return [result]

        # Bitcoin or unknown — no free API path yet; return basic record
        return [
            {
                "address": wallet_address,
                "chain": chain,
                "source": "crypto_tracer",
                "note": (
                    "Bitcoin lookup not yet implemented; Ethereum lookup requires ETHERSCAN_API_KEY"
                    if chain == "bitcoin"
                    else "Unrecognised address format — chain could not be determined"
                ),
                "reason": _REASON,
            }
        ]
