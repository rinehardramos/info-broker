"""Admiralty source classification and intelligence confidence ratings."""

from __future__ import annotations

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
