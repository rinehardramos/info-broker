"""News adapter for the /v1/news endpoint.

Provider chain:
  1. NewsAPI.org (paid, requires NEWSAPI_KEY)
  2. DuckDuckGo Instant Answer / news search (free, no key)
  3. Hard-coded evergreen fallback list (data/fallback_news.json) so the
     endpoint never 503s — a dead news feed should never block a DJ script.

Scope semantics
  - global  : worldwide top headlines (NewsAPI /v2/top-headlines?language=en
              + category) or NewsAPI /v2/everything when topic=any.
  - country : top headlines for the supplied country_code + category.
  - local   : top headlines for country_code, post-filtered by ``query``
              (typically the station's city) so a station in Manila gets
              Manila-flavoured headlines.

Topic semantics — broker-side enum that maps to NewsAPI's category enum:
  breaking → general          tech         → technology
  music    → entertainment    entertainment→ entertainment
  sports   → sports           business     → business
  science  → science          health       → health
  politics → general (+query "politics")
  world    → general (omit country)
  any      → no category

Cache key includes (scope, topic, country_code, query, limit) so different
slices don't collide.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from app.lib.ddg_fallback import ddg_fallback_summary, ddg_search
from app.schemas_media import NewsItem, NewsResponse, NewsScope, NewsTopic
from security import safe_fetch_url

log = logging.getLogger(__name__)

NEWSAPI_TOP = "https://newsapi.org/v2/top-headlines"
NEWSAPI_EVERYTHING = "https://newsapi.org/v2/everything"
DDG_URL = "https://api.duckduckgo.com/"

# Topic → (NewsAPI category | None, optional extra query keyword)
_TOPIC_MAP: dict[NewsTopic, tuple[str | None, str | None]] = {
    "breaking": ("general", None),
    "tech": ("technology", None),
    "music": ("entertainment", "music"),
    "entertainment": ("entertainment", None),
    "sports": ("sports", None),
    "business": ("business", None),
    "science": ("science", None),
    "health": ("health", None),
    "politics": ("general", "politics"),
    "world": ("general", None),  # plus we omit country_code below
    "any": (None, None),
}

_FALLBACK_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "fallback_news.json"


class NewsUnavailable(Exception):
    """Raised only when even the fallback file is missing/empty."""


def fetch_news(
    *,
    scope: NewsScope = "global",
    topic: NewsTopic = "any",
    country_code: str | None = None,
    query: str | None = None,
    limit: int = 10,
) -> NewsResponse:
    """Try NewsAPI → DDG → bundled fallback. Always returns a NewsResponse."""
    limit = max(1, min(int(limit), 50))
    api_key = os.getenv("NEWSAPI_KEY", "").strip()

    if api_key:
        try:
            return _fetch_newsapi(api_key, scope, topic, country_code, query, limit)
        except Exception as exc:  # noqa: BLE001 — fallback chain by design
            log.warning("NewsAPI failed (%s); falling back to DDG", exc)

    try:
        return _fetch_duckduckgo(scope, topic, country_code, query, limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("DDG Instant Answer failed (%s); trying DDG web scrape", exc)

    try:
        return _fetch_ddg_scrape(scope, topic, country_code, query, limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("DDG scrape failed (%s); falling back to bundled list", exc)

    return _fetch_bundled(scope, topic, limit)


def _fetch_ddg_scrape(
    scope: NewsScope,
    topic: NewsTopic,
    country_code: str | None,
    query: str | None,
    limit: int,
) -> NewsResponse:
    """Final network tier: DDG web search → headlines from result titles."""
    q_parts: list[str] = ["latest news"]
    if topic != "any":
        q_parts.append(topic)
    if scope == "local" and query:
        q_parts.append(query)
    elif scope == "country" and country_code:
        q_parts.append(country_code)
    search_q = " ".join(q_parts)

    hits = ddg_search(search_q, max_results=limit * 2)
    items: list[NewsItem] = []
    for hit in hits:
        headline = hit.get("title", "").strip()
        if not headline:
            continue
        items.append(
            NewsItem(
                headline=headline,
                source="DuckDuckGo",
                url=hit.get("url"),
                topic=topic if topic != "any" else None,
            )
        )
        if len(items) >= limit:
            break

    if not items:
        raise NewsUnavailable("DDG web search returned no results")

    return NewsResponse(
        provider="ddg-scrape",
        fetched_at=datetime.now(timezone.utc),
        scope=scope,
        topic=topic,
        items=items,
    )


# ── NewsAPI ──────────────────────────────────────────────────────────────────


def _fetch_newsapi(
    api_key: str,
    scope: NewsScope,
    topic: NewsTopic,
    country_code: str | None,
    query: str | None,
    limit: int,
) -> NewsResponse:
    category, extra_q = _TOPIC_MAP[topic]
    params: list[str] = [f"apiKey={api_key}", f"pageSize={limit}"]

    if topic == "any" and scope == "global":
        # Use /v2/everything for the "global anything" case so we get a wide net.
        url_base = NEWSAPI_EVERYTHING
        params += ["language=en", "sortBy=publishedAt"]
        q_terms: list[str] = []
        if query:
            q_terms.append(query)
        if extra_q:
            q_terms.append(extra_q)
        if q_terms:
            params.append(f"q={quote_plus(' '.join(q_terms))}")
        else:
            params.append("q=top")  # NewsAPI requires q on /everything
    else:
        url_base = NEWSAPI_TOP
        params.append("language=en")
        if category:
            params.append(f"category={category}")
        if scope in ("country", "local") and country_code:
            params.append(f"country={country_code.lower()}")
        # world: explicitly do NOT pin to a country
        q_terms = []
        if scope == "local" and query:
            q_terms.append(query)
        if extra_q:
            q_terms.append(extra_q)
        if q_terms:
            params.append(f"q={quote_plus(' '.join(q_terms))}")

    url = f"{url_base}?{'&'.join(params)}"
    resp = safe_fetch_url(
        url, timeout=8, allowed_content_types=("application/json",)
    )
    payload: dict[str, Any] = resp.json()
    articles = payload.get("articles") or []

    items: list[NewsItem] = []
    for art in articles[:limit]:
        title = (art.get("title") or "").strip()
        if not title or title == "[Removed]":
            continue
        items.append(
            NewsItem(
                headline=title,
                source=(art.get("source") or {}).get("name"),
                url=art.get("url"),
                published_at=_parse_iso(art.get("publishedAt")),
                topic=topic if topic != "any" else None,
            )
        )

    if not items:
        raise NewsUnavailable("NewsAPI returned no usable articles")

    return NewsResponse(
        provider="newsapi",
        fetched_at=datetime.now(timezone.utc),
        scope=scope,
        topic=topic,
        items=items,
    )


# ── DuckDuckGo fallback ──────────────────────────────────────────────────────


def _fetch_duckduckgo(
    scope: NewsScope,
    topic: NewsTopic,
    country_code: str | None,
    query: str | None,
    limit: int,
) -> NewsResponse:
    q_parts: list[str] = ["latest news"]
    if topic != "any":
        q_parts.append(topic)
    if scope == "local" and query:
        q_parts.append(query)
    elif scope == "country" and country_code:
        q_parts.append(country_code)

    q = " ".join(q_parts)
    url = f"{DDG_URL}?q={quote_plus(q)}&format=json&no_html=1&skip_disambig=1"
    resp = safe_fetch_url(
        url,
        timeout=6,
        allowed_content_types=("application/json", "application/x-javascript"),
    )
    text = resp.text.strip()
    if not text.startswith("{"):
        text = text[text.find("{") : text.rfind("}") + 1]
    try:
        payload: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NewsUnavailable(f"DDG returned non-JSON ({exc})") from exc

    related = payload.get("RelatedTopics") or []
    items: list[NewsItem] = []
    for entry in related:
        if not isinstance(entry, dict):
            continue
        text_field = entry.get("Text")
        if not text_field:
            continue
        items.append(
            NewsItem(
                headline=text_field.strip(),
                source="DuckDuckGo",
                url=entry.get("FirstURL"),
                topic=topic if topic != "any" else None,
            )
        )
        if len(items) >= limit:
            break

    if not items:
        raise NewsUnavailable("DDG returned no related topics")

    return NewsResponse(
        provider="duckduckgo",
        fetched_at=datetime.now(timezone.utc),
        scope=scope,
        topic=topic,
        items=items,
    )


# ── Bundled evergreen fallback ───────────────────────────────────────────────


def _fetch_bundled(scope: NewsScope, topic: NewsTopic, limit: int) -> NewsResponse:
    """Last-resort source so the endpoint never 503s."""
    if not _FALLBACK_PATH.exists():
        raise NewsUnavailable(f"fallback file missing: {_FALLBACK_PATH}")
    try:
        data = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise NewsUnavailable(f"fallback file unreadable: {exc}") from exc

    raw_items = data.get("items") or []
    items = [
        NewsItem(
            headline=str(it.get("headline", "")).strip(),
            source=it.get("source"),
            topic=topic if topic != "any" else None,
        )
        for it in raw_items[:limit]
        if it.get("headline")
    ]
    return NewsResponse(
        provider="bundled-fallback",
        fetched_at=datetime.now(timezone.utc),
        scope=scope,
        topic=topic,
        items=items,
    )


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
