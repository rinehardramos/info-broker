"""Admiralty source classification and intelligence confidence ratings."""

from __future__ import annotations

import re
from collections import defaultdict

# NATO Admiralty Source Reliability (A-F)
# A = Completely Reliable, B = Usually Reliable, C = Fairly Reliable
# D = Not Usually Reliable, E = Unreliable, F = Cannot Be Judged
SOURCE_RATINGS: dict[str, str] = {
    # A — Government / Official registries
    "ph_sec_dti": "A",
    "opencorporates": "A",
    "sec_edgar": "A",
    "ph_bir": "A",
    "polish_krs": "A",
    "pep_sanctions_screen": "A",
    # B — Professional platforms / Technical verification
    "linkedin_profile": "B",
    "linkedin_navigator": "B",
    "apollo_zoominfo": "B",
    "hibp_lookup": "B",
    "smtp_verifier": "B",
    "hunter_io": "B",
    "whois_lookup": "B",
    "shodan_search": "B",
    "phone_osint": "B",
    # C — Social media / News
    "facebook_pages": "C",
    "instagram_profile": "C",
    "twitter_search": "C",
    "google_news": "C",
    "adverse_media": "C",
    "clutch_goodfirms": "C",
    "glassdoor_reviews": "C",
    "messaging_check": "C",
    # D — Generic web / Unverified
    "ddg_search": "D",
    "web_crawl": "D",
    "web_search_fetch": "D",
    "document_search": "D",
    "username_enumerator": "D",
    "reverse_lookup": "D",
    "wikipedia_api": "D",
    # E — High deception risk (rated D as closest valid bucket)
    "crypto_tracer": "D",
    "face_search": "D",
    "exif_extractor": "D",
}


def rate_source(source_tool: str) -> str:
    """Return Admiralty reliability rating (A-F) for a source tool."""
    clean = source_tool.replace("run_", "")
    return SOURCE_RATINGS.get(clean, "F")


def confidence_to_stix(confidence: int) -> int:
    """Map a 0-100 confidence value to STIX 2.1 scale (capped 0-100)."""
    return max(0, min(100, confidence))


def admiralty_info_credibility(corroboration_count: int) -> int:
    """
    Map corroboration count to Admiralty information credibility (1-6).
    0 sources = 6 (Cannot be judged)
    1 source  = 3 (Possibly true)
    2 sources = 2 (Probably true)
    3+ sources = 1 (Confirmed)
    """
    if corroboration_count >= 3:
        return 1
    elif corroboration_count == 2:
        return 2
    elif corroboration_count == 1:
        return 3
    return 6


def track_corroboration(findings: list[dict]) -> list[dict]:
    """Enrich findings with corroboration tracking.

    For each finding, identifies how many OTHER findings from DIFFERENT sources
    share significant content overlap (shared entities/keywords).

    Adds to each finding:
    - corroboration_count: number of unique sources confirming similar content
    - corroboration_level: "uncorroborated" (1 source), "corroborated" (2), "multi_source" (3+)
    - credibility: Admiralty info credibility (1-6) based on corroboration
    """
    if not findings:
        return []

    _STOP = {
        "this", "that", "with", "from", "they", "their", "have", "been",
        "were", "which", "about", "would", "could", "should", "found",
        "search", "result",
    }

    def _extract_tokens(text: str) -> set[str]:
        words = re.findall(r'\b[a-zA-Z0-9@._-]{4,}\b', text.lower())
        return {w for w in words if w not in _STOP}

    indexed = []
    for f in findings:
        text = (f.get("title", "") + " " + f.get("content", "")).strip()
        tokens = _extract_tokens(text)
        source = f.get("source", f.get("source_tool", "unknown"))
        indexed.append({"finding": f, "tokens": tokens, "source": source})

    results = []
    for i, item in enumerate(indexed):
        corroborating_sources: set[str] = set()
        for j, other in enumerate(indexed):
            if i == j:
                continue
            if other["source"] == item["source"]:
                continue  # Same source doesn't count
            overlap = item["tokens"] & other["tokens"]
            # High-specificity tokens (emails, domains) count as corroboration on their own.
            # Generic tokens require at least 3 to reduce false positives.
            high_spec = {t for t in overlap if "@" in t or t.count(".") >= 1}
            if len(overlap) >= 3 or len(high_spec) >= 1:
                corroborating_sources.add(other["source"])

        count = len(corroborating_sources) + 1  # +1 for self
        if count >= 3:
            level = "multi_source"
        elif count == 2:
            level = "corroborated"
        else:
            level = "uncorroborated"

        results.append({
            **item["finding"],
            "corroboration_count": count,
            "corroboration_level": level,
            "credibility": admiralty_info_credibility(count),
        })

    return results
