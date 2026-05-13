"""Signed webhook delivery with exponential backoff retry."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import uuid

import httpx

from app.routers.v3.db import execute, fetch_one

log = logging.getLogger(__name__)

_RETRY_DELAYS = [5, 30, 300, 1800, 7200]   # 5s, 30s, 5min, 30min, 2h


def _sign_payload(run_id: str, status: str, timestamp: int) -> str:
    """HMAC-SHA256 signature over run_id:status:timestamp."""
    secret = os.getenv("WEBHOOK_SECRET", "dev-secret")
    msg = f"{run_id}:{status}:{timestamp}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _record_attempt(delivery_id: str, run_id: str, url: str, attempt: int,
                    status_code: int | None, error: str | None) -> None:
    try:
        execute(
            """INSERT INTO webhook_deliveries
               (id, run_id, attempt, url, status_code, error, delivered_at)
               VALUES (%s, %s, %s, %s, %s, %s, now())
               ON CONFLICT DO NOTHING""",
            (delivery_id, run_id, attempt, url, status_code, error),
        )
    except Exception as exc:
        log.warning("Failed to record webhook delivery: %s", exc)


async def deliver_webhook(run_id: str, payload: dict, callback_url: str) -> None:
    """POST signed webhook to callback_url with retry. Non-blocking — fire and forget."""
    asyncio.create_task(_deliver_with_retry(run_id, payload, callback_url))


async def _deliver_with_retry(run_id: str, payload: dict, callback_url: str) -> None:
    timestamp = int(time.time())
    status = payload.get("status", "unknown")
    signature = _sign_payload(run_id, status, timestamp)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Timestamp": str(timestamp),
    }
    body = json.dumps(payload)
    delivery_id = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=10) as client:
        for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
            try:
                resp = await client.post(callback_url, content=body, headers=headers)
                _record_attempt(delivery_id, run_id, callback_url, attempt, resp.status_code, None)
                if resp.status_code < 500:
                    log.info("Webhook delivered run=%s attempt=%d status=%d", run_id, attempt, resp.status_code)
                    return
                log.warning("Webhook 5xx run=%s attempt=%d status=%d", run_id, attempt, resp.status_code)
            except Exception as exc:
                _record_attempt(delivery_id, run_id, callback_url, attempt, None, str(exc)[:200])
                log.warning("Webhook error run=%s attempt=%d: %s", run_id, attempt, exc)

            if attempt < len(_RETRY_DELAYS):
                await asyncio.sleep(delay)

    log.error("Webhook exhausted retries run=%s url=%s", run_id, callback_url)
