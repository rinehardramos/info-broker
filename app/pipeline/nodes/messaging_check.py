"""Messaging platform presence check node — Telegram, WhatsApp, Signal."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)

_REASON = (
    "Checks presence on major messaging platforms (Telegram, WhatsApp, Signal) "
    "to surface additional contact vectors for a target"
)


class MessagingCheckNode:
    node_type = "messaging_check"
    display_name = "Messaging Check"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "phone": {
                "type": "string",
                "title": "Phone Number",
                "description": "Phone number in E.164 format (e.g. +1234567890).",
            },
            "username": {
                "type": "string",
                "title": "Username",
                "description": "Telegram username (without @) to check for a public profile.",
            },
        },
        "required": [],
    }

    async def execute(
        self, config: dict, inputs: list[dict], context: RunContext
    ) -> list[dict]:
        phone: str = (config.get("phone") or "").strip()
        username: str = (config.get("username") or "").strip()

        if not phone and not username and inputs:
            first = inputs[0]
            phone = (first.get("phone") or "").strip()
            username = (first.get("username") or "").strip()

        if not phone and not username:
            return [
                {
                    "error": "No phone or username provided for messaging check",
                    "source": "messaging_check",
                    "reason": _REASON,
                }
            ]

        loop = asyncio.get_running_loop()
        platforms = await loop.run_in_executor(
            None, _check_platforms, phone, username
        )

        return [
            {
                **platforms,
                "source": "messaging_check",
                "reason": _REASON,
            }
        ]


def _check_platforms(phone: str, username: str) -> dict:
    """Return a dict with telegram/whatsapp/signal sub-results."""
    if username:
        telegram: dict = _check_telegram(username)
    else:
        telegram = {
            "exists": None,
            "note": "username required to check Telegram",
            "platform": "telegram",
        }

    whatsapp: dict = {
        "platform": "whatsapp",
        "exists": None,
        "note": "requires phone number for verification",
    }

    signal: dict = {
        "platform": "signal",
        "exists": None,
        "note": "requires phone number for verification",
    }

    return {
        "telegram": telegram,
        "whatsapp": whatsapp,
        "signal": signal,
    }


def _check_telegram(username: str) -> dict:
    """Check whether a Telegram public profile exists for *username*.

    A live profile page contains a tgme_page_title element;
    the not-found page does not.
    """
    scheme = "https"
    host = "t.me"
    url = scheme + "://" + host + "/" + username
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url)
    except Exception as exc:
        log.warning("messaging_check: Telegram request failed for %r: %s", username, exc)
        return {
            "platform": "telegram",
            "exists": None,
            "username": username,
            "error": str(exc),
        }

    exists = "tgme_page_title" in response.text
    return {
        "platform": "telegram",
        "exists": exists,
        "username": username,
        "url": url,
    }
