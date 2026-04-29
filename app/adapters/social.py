"""Social media adapter — Twitter v2 mentions + Facebook page feed.

API base URLs are read from env vars (see README for values).
Both methods return an empty response on error — graceful degradation.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

log = logging.getLogger(__name__)


def _twitter_base() -> str:
    v = os.getenv("TWITTER_API_BASE")
    if not v:
        raise RuntimeError("TWITTER_API_BASE env var not set")
    return v.rstrip("/")


def _facebook_base() -> str:
    v = os.getenv("FACEBOOK_API_BASE")
    if not v:
        raise RuntimeError("FACEBOOK_API_BASE env var not set")
    return v.rstrip("/")


@dataclass
class SocialMention:
    id: str
    text: str
    author_id: str | None = None
    created_at: str | None = None
    platform: str = "twitter"


@dataclass
class SocialMentionsResponse:
    platform: str
    handle: str
    mentions: list[SocialMention] = field(default_factory=list)
    error: str | None = None


def _resolve_token(ref: str) -> str:
    import re
    if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", ref, re.I):
        from app.lib.token_vault import fetch
        return fetch(ref)
    return ref


def _twitter_user_id(handle: str, bearer: str) -> str | None:
    try:
        r = httpx.get(
            f"{_twitter_base()}/users/by/username/{handle}",
            headers={"Authorization": f"Bearer {bearer}"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("data", {}).get("id")
    except Exception as exc:
        log.warning("twitter user lookup failed handle=%s: %s", handle, exc)
        return None


def fetch_mentions(
    platform: str,
    handle: str,
    oauth_token_ref: str,
    since_id: str | None = None,
    limit: int = 20,
) -> SocialMentionsResponse:
    try:
        token = _resolve_token(oauth_token_ref)
    except KeyError:
        return SocialMentionsResponse(platform=platform, handle=handle, error="token not found")
    except Exception as exc:
        return SocialMentionsResponse(platform=platform, handle=handle, error=str(exc))

    if platform == "twitter":
        return _twitter_mentions(handle, token, since_id, limit)
    if platform == "facebook":
        return _facebook_feed(handle, token, limit)
    return SocialMentionsResponse(platform=platform, handle=handle, error=f"unsupported: {platform!r}")


def _twitter_mentions(handle: str, bearer: str, since_id: str | None, limit: int) -> SocialMentionsResponse:
    user_id = _twitter_user_id(handle, bearer)
    if not user_id:
        return SocialMentionsResponse(platform="twitter", handle=handle, error="user not found")
    params: dict = {"max_results": min(limit, 100), "tweet.fields": "created_at,author_id"}
    if since_id:
        params["since_id"] = since_id
    try:
        r = httpx.get(
            f"{_twitter_base()}/users/{user_id}/mentions",
            headers={"Authorization": f"Bearer {bearer}"},
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        return SocialMentionsResponse(
            platform="twitter", handle=handle,
            mentions=[
                SocialMention(id=t["id"], text=t.get("text", ""),
                              author_id=t.get("author_id"), created_at=t.get("created_at"),
                              platform="twitter")
                for t in (r.json().get("data") or [])
            ],
        )
    except Exception as exc:
        log.warning("twitter mentions failed handle=%s: %s", handle, exc)
        return SocialMentionsResponse(platform="twitter", handle=handle, error=str(exc))


def _facebook_feed(handle: str, token: str, limit: int) -> SocialMentionsResponse:
    try:
        r = httpx.get(
            f"{_facebook_base()}/{handle}/feed",
            params={"fields": "id,message,created_time,from", "limit": min(limit, 100)},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        r.raise_for_status()
        return SocialMentionsResponse(
            platform="facebook", handle=handle,
            mentions=[
                SocialMention(id=p["id"], text=p.get("message", ""),
                              author_id=(p.get("from") or {}).get("id"),
                              created_at=p.get("created_time"), platform="facebook")
                for p in (r.json().get("data") or [])
            ],
        )
    except Exception as exc:
        log.warning("facebook feed failed handle=%s: %s", handle, exc)
        return SocialMentionsResponse(platform="facebook", handle=handle, error=str(exc))
