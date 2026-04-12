from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from app.search_engine.domain_tiers import get_domain_reliability

W_RELEVANCE = 0.4
W_FRESHNESS = 0.3
W_RELIABILITY = 0.3


def relevance_score(query: str, title_and_snippet: str) -> float:
    query_tokens = set(re.findall(r"\w+", query.lower()))
    result_tokens = set(re.findall(r"\w+", title_and_snippet.lower()))
    if not query_tokens:
        return 0.0
    overlap = query_tokens & result_tokens
    token_score = len(overlap) / len(query_tokens)
    substring_boost = 0.1 if query.lower() in title_and_snippet.lower() else 0.0
    return min(1.0, token_score + substring_boost)


def freshness_score(published_at: datetime | None) -> float:
    if published_at is None:
        return 0.3
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - published_at).total_seconds() / 86400)
    return round(math.exp(-0.1 * age_days), 4)


def score_result(
    *,
    query: str,
    title: str,
    snippet: str,
    url: str | None,
    published_at: datetime | None,
) -> dict[str, float]:
    rel = relevance_score(query, f"{title} {snippet}")
    fresh = freshness_score(published_at)
    reliability = get_domain_reliability(url)
    composite = (W_RELEVANCE * rel) + (W_FRESHNESS * fresh) + (W_RELIABILITY * reliability)
    return {
        "relevance": round(rel, 3),
        "freshness": round(fresh, 3),
        "source_reliability": round(reliability, 3),
        "composite": round(composite, 3),
    }
