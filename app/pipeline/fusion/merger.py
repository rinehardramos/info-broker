from __future__ import annotations
import re


def _normalize_title(title: str) -> set[str]:
    stopwords = {"the", "a", "an", "and", "or", "in", "on", "at", "of", "for",
                 "to", "with", "by", "is", "are", "was", "were"}
    tokens = re.findall(r"[a-z0-9]+", title.lower())
    return {t for t in tokens if t not in stopwords and len(t) > 1}


def _findings_similar(a: dict, b: dict) -> bool:
    """Return True if two findings refer to the same source.

    Identical URL is an exact match. Title word-overlap >= 0.7 is a near-match.
    """
    url_a = (a.get("url") or "").strip().rstrip("/")
    url_b = (b.get("url") or "").strip().rstrip("/")
    if url_a and url_b and url_a == url_b:
        return True
    tokens_a = _normalize_title(a.get("title") or "")
    tokens_b = _normalize_title(b.get("title") or "")
    if not tokens_a or not tokens_b:
        return False
    overlap = tokens_a & tokens_b
    shorter = min(len(tokens_a), len(tokens_b))
    return len(overlap) / shorter >= 0.7


def merge_research_results(fast: dict, thorough: dict, query: str) -> dict:
    """Merge fast and thorough IS research results.

    Fast findings are marked confirmed_by_thorough=True when a similar
    finding exists in the thorough run. Thorough-only findings are appended
    with phase='thorough' and confirmed_by_thorough=True.
    """
    fast_findings = list(fast.get("findings") or [])
    thorough_findings = list(thorough.get("findings") or [])

    merged: list[dict] = []
    for ff in fast_findings:
        confirmed = any(_findings_similar(ff, tf) for tf in thorough_findings)
        merged.append({**ff, "phase": "fast", "confirmed_by_thorough": confirmed})

    for tf in thorough_findings:
        if not any(_findings_similar(tf, ff) for ff in fast_findings):
            merged.append({**tf, "phase": "thorough", "confirmed_by_thorough": True})

    confirmed_count = sum(1 for f in merged if f.get("confirmed_by_thorough"))
    return {
        **thorough,
        "findings": merged,
        "fast_count": len(fast_findings),
        "thorough_count": len(thorough_findings),
        "merged_count": len(merged),
        "confirmed_count": confirmed_count,
    }
