"""Joke adapter for /v1/jokes.

Provider chain:
  1. JokeAPI v2 (https://v2.jokeapi.dev) — free, no key, supports category +
     blacklist filtering. Mapped to broker-side ``style`` enum.
  2. icanhazdadjoke (https://icanhazdadjoke.com) — free, no key, dad jokes only.
  3. Bundled fallback list (data/fallback_jokes.json) — last resort, never 503.

Safety
  ``safe=true`` (default) enforces JokeAPI's blacklist flags
  (nsfw,religious,political,racist,sexist,explicit). A joke with any of those
  flags MUST NOT reach a live radio broadcast.
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas_media import JokeResponse, JokeStyle
from security import safe_fetch_url

log = logging.getLogger(__name__)

JOKEAPI_BASE_DEFAULT = "https://v2.jokeapi.dev"
DAD_JOKE_URL = "https://icanhazdadjoke.com/"

_FALLBACK_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "fallback_jokes.json"

# style → JokeAPI category
_STYLE_CATEGORY = {
    "witty": "Misc",
    "punny": "Pun",
    "sarcastic": "Misc",
    "observational": "Misc",
    "clean": "Any",
    "any": "Any",
    "dad": None,  # routes to icanhazdadjoke instead
}

_BLACKLIST_FLAGS = "nsfw,religious,political,racist,sexist,explicit"


class JokeUnavailable(Exception):
    """Raised only when even the bundled file is unreadable."""


def fetch_joke(*, style: JokeStyle = "any", safe: bool = True) -> JokeResponse:
    if style == "dad":
        try:
            return _fetch_dad_joke(safe=safe)
        except Exception as exc:  # noqa: BLE001
            log.warning("dad joke provider failed (%s)", exc)
        return _fetch_bundled(style=style, safe=safe)

    try:
        return _fetch_jokeapi(style=style, safe=safe)
    except Exception as exc:  # noqa: BLE001
        log.warning("JokeAPI failed (%s); trying dad joke", exc)

    try:
        return _fetch_dad_joke(safe=safe)
    except Exception as exc:  # noqa: BLE001
        log.warning("dad joke fallback failed (%s); using bundled", exc)

    return _fetch_bundled(style=style, safe=safe)


# ── JokeAPI ──────────────────────────────────────────────────────────────────


def _fetch_jokeapi(*, style: JokeStyle, safe: bool) -> JokeResponse:
    base = os.getenv("JOKEAPI_BASE_URL", JOKEAPI_BASE_DEFAULT).rstrip("/")
    category = _STYLE_CATEGORY.get(style, "Any")
    params: list[str] = ["type=single", "format=json"]
    if safe:
        params.append("safe-mode")
        params.append(f"blacklistFlags={_BLACKLIST_FLAGS}")
    url = f"{base}/joke/{category}?{'&'.join(params)}"

    resp = safe_fetch_url(
        url, timeout=6, allowed_content_types=("application/json",)
    )
    payload: dict[str, Any] = resp.json()
    if payload.get("error"):
        raise JokeUnavailable(f"JokeAPI error: {payload.get('message')}")

    text = (payload.get("joke") or "").strip()
    if not text:
        raise JokeUnavailable("JokeAPI returned no joke text")

    # Defense in depth: if the API somehow returns a flagged joke, drop it.
    flags = payload.get("flags") or {}
    if safe and isinstance(flags, dict):
        for blocked in _BLACKLIST_FLAGS.split(","):
            if flags.get(blocked):
                raise JokeUnavailable(f"JokeAPI returned a {blocked} joke despite safe-mode")

    return JokeResponse(
        provider="jokeapi",
        fetched_at=datetime.now(timezone.utc),
        joke=text,
        style=style,
        safe=safe,
        source="jokeapi.dev",
    )


# ── icanhazdadjoke ───────────────────────────────────────────────────────────


def _fetch_dad_joke(*, safe: bool) -> JokeResponse:
    resp = safe_fetch_url(
        DAD_JOKE_URL,
        timeout=6,
        headers={
            "Accept": "application/json",
            "User-Agent": "playgen-info-broker (+https://playgen.site)",
        },
        allowed_content_types=("application/json",),
    )
    payload: dict[str, Any] = resp.json()
    text = (payload.get("joke") or "").strip()
    if not text:
        raise JokeUnavailable("icanhazdadjoke returned empty joke")
    return JokeResponse(
        provider="icanhazdadjoke",
        fetched_at=datetime.now(timezone.utc),
        joke=text,
        style="dad",
        safe=safe,
        source="icanhazdadjoke.com",
    )


# ── Bundled fallback ─────────────────────────────────────────────────────────


def _fetch_bundled(*, style: JokeStyle, safe: bool) -> JokeResponse:
    if not _FALLBACK_PATH.exists():
        raise JokeUnavailable(f"fallback file missing: {_FALLBACK_PATH}")
    try:
        data = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JokeUnavailable(f"fallback file unreadable: {exc}") from exc

    items: list[str] = data.get("items") or []
    if not items:
        raise JokeUnavailable("fallback file empty")
    return JokeResponse(
        provider="bundled-fallback",
        fetched_at=datetime.now(timezone.utc),
        joke=random.choice(items),  # noqa: S311 — entertainment, not crypto
        style=style,
        safe=safe,
        source=None,
    )
