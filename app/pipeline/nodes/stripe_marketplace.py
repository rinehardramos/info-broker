"""Stripe Marketplace Metrics node — fetch financial data from the Stripe API."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_BASE_URL = "https://api.stripe.com"


def _resolve_api_key(config_key: str | None = None) -> str | None:
    """Config value takes priority, then env var, then DB setting."""
    if config_key:
        return config_key
    key = os.getenv("STRIPE_API_KEY")
    if key:
        return key
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one(
            "SELECT value FROM core_settings WHERE key = 'stripe_api_key'", ()
        )
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    return None


class StripeMarketplaceNode:
    node_type = "stripe_marketplace"
    display_name = "Stripe Marketplace Metrics"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "metric_type": {
                "type": "string",
                "title": "Metric Type",
                "enum": ["balance", "charges", "customers", "disputes", "payouts"],
                "default": "balance",
            },
            "date_range_days": {
                "type": "integer",
                "title": "Date Range (days)",
                "default": 30,
                "minimum": 1,
                "maximum": 365,
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        import asyncio

        api_key = _resolve_api_key(config.get("api_key"))
        if not api_key:
            return [{
                "source": "stripe",
                "error": "Stripe API key not configured. Set STRIPE_API_KEY in .env or Settings.",
                "title": "Stripe: missing API key",
                "content": "Configure your Stripe API key to fetch marketplace metrics.",
                "confidence": 0,
            }]

        metric_type = config.get("metric_type", "balance")
        date_range_days = int(config.get("date_range_days", 30))

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, _fetch_metric, api_key, metric_type, date_range_days
        )
        return [result]

    async def health_check(self) -> "HealthStatus":
        from app.pipeline.nodes.base import HealthStatus

        _SETUP = (
            "1. Log in to your Stripe Dashboard\n"
            "2. Go to Developers > API Keys\n"
            "3. Copy your Secret key\n"
            "4. Paste in Settings > API Keys > Stripe"
        )

        api_key = _resolve_api_key()
        if not api_key:
            return HealthStatus(
                healthy=False,
                error="Stripe API key not configured",
                requires_key="STRIPE_API_KEY",
                setup_url="https://dashboard.stripe.com/apikeys",
                setup_instructions=_SETUP,
            )

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{_BASE_URL}/v1/balance",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            if resp.status_code == 200:
                return HealthStatus(
                    healthy=True, error=None, requires_key=None,
                    setup_url=None, setup_instructions=None,
                )
            return HealthStatus(
                healthy=False,
                error=f"Stripe returned HTTP {resp.status_code}",
                requires_key="STRIPE_API_KEY",
                setup_url="https://dashboard.stripe.com/apikeys",
                setup_instructions=_SETUP,
            )
        except Exception as exc:
            return HealthStatus(
                healthy=False,
                error=str(exc),
                requires_key="STRIPE_API_KEY",
                setup_url="https://dashboard.stripe.com/apikeys",
                setup_instructions=_SETUP,
            )


def _cutoff_timestamp(days: int) -> int:
    """Return a Unix timestamp for `days` ago."""
    return int(time.time()) - days * 86400


def _fetch_metric(api_key: str, metric_type: str, date_range_days: int) -> dict:
    """Synchronous Stripe API call — run in executor."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "info-broker/1.0",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            if metric_type == "balance":
                resp = client.get(f"{_BASE_URL}/v1/balance", headers=headers)
                resp.raise_for_status()
                data = resp.json()
                available = data.get("available", [])
                pending = data.get("pending", [])
                total_available = sum(b.get("amount", 0) for b in available)
                total_pending = sum(b.get("amount", 0) for b in pending)
                currency = available[0].get("currency", "usd").upper() if available else "USD"
                return {
                    "source": "stripe",
                    "metric_type": "balance",
                    "title": f"Stripe Balance ({currency})",
                    "content": (
                        f"Available: {total_available / 100:.2f} {currency} | "
                        f"Pending: {total_pending / 100:.2f} {currency}"
                    ),
                    "url": "https://dashboard.stripe.com/balance",
                    "confidence": 90,
                    "raw_data": data,
                }

            elif metric_type == "charges":
                gte = _cutoff_timestamp(date_range_days)
                resp = client.get(
                    f"{_BASE_URL}/v1/charges",
                    params={"limit": 100, "created[gte]": gte},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("data", [])
                total = sum(c.get("amount", 0) for c in items if c.get("paid"))
                currency = items[0].get("currency", "usd").upper() if items else "USD"
                return {
                    "source": "stripe",
                    "metric_type": "charges",
                    "title": f"Stripe Charges (last {date_range_days}d)",
                    "content": (
                        f"{len(items)} charges | Total paid: {total / 100:.2f} {currency}"
                    ),
                    "url": "https://dashboard.stripe.com/payments",
                    "confidence": 90,
                    "raw_data": data,
                }

            elif metric_type == "customers":
                gte = _cutoff_timestamp(date_range_days)
                resp = client.get(
                    f"{_BASE_URL}/v1/customers",
                    params={"limit": 100, "created[gte]": gte},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("data", [])
                return {
                    "source": "stripe",
                    "metric_type": "customers",
                    "title": f"Stripe Customers (last {date_range_days}d)",
                    "content": f"{len(items)} new customers in the past {date_range_days} days",
                    "url": "https://dashboard.stripe.com/customers",
                    "confidence": 90,
                    "raw_data": data,
                }

            elif metric_type == "disputes":
                resp = client.get(
                    f"{_BASE_URL}/v1/disputes",
                    params={"limit": 100},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("data", [])
                open_count = sum(1 for d in items if d.get("status") == "needs_response")
                return {
                    "source": "stripe",
                    "metric_type": "disputes",
                    "title": "Stripe Disputes",
                    "content": (
                        f"{len(items)} disputes total | {open_count} need response"
                    ),
                    "url": "https://dashboard.stripe.com/disputes",
                    "confidence": 90,
                    "raw_data": data,
                }

            elif metric_type == "payouts":
                gte = _cutoff_timestamp(date_range_days)
                resp = client.get(
                    f"{_BASE_URL}/v1/payouts",
                    params={"limit": 100, "created[gte]": gte},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("data", [])
                total = sum(p.get("amount", 0) for p in items if p.get("status") == "paid")
                currency = items[0].get("currency", "usd").upper() if items else "USD"
                return {
                    "source": "stripe",
                    "metric_type": "payouts",
                    "title": f"Stripe Payouts (last {date_range_days}d)",
                    "content": (
                        f"{len(items)} payouts | Total paid out: {total / 100:.2f} {currency}"
                    ),
                    "url": "https://dashboard.stripe.com/balance/overview",
                    "confidence": 90,
                    "raw_data": data,
                }

            else:
                return {
                    "source": "stripe",
                    "metric_type": metric_type,
                    "error": f"Unknown metric_type: {metric_type!r}",
                    "title": "Stripe: unknown metric",
                    "content": "",
                    "confidence": 0,
                }

    except httpx.HTTPStatusError as exc:
        log.warning("stripe_marketplace: HTTP error for %r: %s", metric_type, exc)
        return {
            "source": "stripe",
            "metric_type": metric_type,
            "error": str(exc),
            "title": f"Stripe {metric_type} — HTTP error",
            "content": str(exc),
            "confidence": 0,
        }
    except Exception as exc:
        log.warning("stripe_marketplace: unexpected error for %r: %s", metric_type, exc)
        return {
            "source": "stripe",
            "metric_type": metric_type,
            "error": str(exc),
            "title": f"Stripe {metric_type} — error",
            "content": str(exc),
            "confidence": 0,
        }
