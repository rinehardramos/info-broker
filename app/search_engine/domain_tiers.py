from __future__ import annotations

from urllib.parse import urlparse

_DOMAIN_TIERS: dict[str, float] = {
    # Tier 1 (1.0)
    "reuters.com": 1.0, "apnews.com": 1.0, "wikipedia.org": 1.0,
    "who.int": 1.0, "un.org": 1.0, "gov.uk": 1.0, "nasa.gov": 1.0,
    "nih.gov": 1.0, "cdc.gov": 1.0, "nature.com": 1.0, "science.org": 1.0,
    # Tier 2 (0.8)
    "bbc.com": 0.8, "bbc.co.uk": 0.8, "nytimes.com": 0.8,
    "washingtonpost.com": 0.8, "theguardian.com": 0.8, "economist.com": 0.8,
    "ft.com": 0.8, "bloomberg.com": 0.8, "wsj.com": 0.8, "cnn.com": 0.8,
    "aljazeera.com": 0.8, "npr.org": 0.8, "pbs.org": 0.8,
    "arstechnica.com": 0.8, "techcrunch.com": 0.8, "wired.com": 0.8,
    # Tier 3 (0.6)
    "medium.com": 0.6, "substack.com": 0.6, "reddit.com": 0.6,
    "stackoverflow.com": 0.6, "github.com": 0.6, "news.ycombinator.com": 0.6,
}
DEFAULT_SCORE = 0.4


def _extract_root_domain(hostname: str) -> str:
    parts = hostname.lower().rstrip(".").split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "gov", "ac", "edu"):
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return hostname.lower()


def get_domain_reliability(url_or_domain: str | None) -> float:
    if not url_or_domain:
        return DEFAULT_SCORE
    if "://" in url_or_domain:
        parsed = urlparse(url_or_domain)
        hostname = parsed.hostname or ""
    else:
        hostname = url_or_domain
    if not hostname:
        return DEFAULT_SCORE
    root = _extract_root_domain(hostname)
    return _DOMAIN_TIERS.get(root, DEFAULT_SCORE)
