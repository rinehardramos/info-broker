"""Value normalizer for memory curation (Memory Phase 3, Task 2).

Pure functions — no DB or network access.

Public API
----------
normalize_value(attribute, value) -> str
values_equivalent(attribute, value_a, value_b) -> bool
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Role / title synonym expansion
# ---------------------------------------------------------------------------

_ROLE_SYNONYMS: dict[str, str] = {
    "ceo": "chief executive officer",
    "cto": "chief technology officer",
    "cfo": "chief financial officer",
    "coo": "chief operating officer",
    "cmo": "chief marketing officer",
    "cio": "chief information officer",
    "vp": "vice president",
    "svp": "senior vice president",
    "evp": "executive vice president",
    "avp": "assistant vice president",
    "md": "managing director",
    "gm": "general manager",
}

# Sorted longest-first so "svp" doesn't accidentally match before it can be
# considered as a whole token.
_ROLE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_ROLE_SYNONYMS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Honorific removal
# ---------------------------------------------------------------------------

# Matches Mr / Mrs / Ms / Dr / Prof optionally followed by a dot, then a space.
_HONORIFIC_PATTERN = re.compile(
    r"^\s*(?:Mr|Mrs|Ms|Dr|Prof)\.?\s+",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Country code expansion
# ---------------------------------------------------------------------------

_COUNTRY_CODES: dict[str, str] = {
    "ph": "philippines",
    "us": "united states",
    "uk": "united kingdom",
    "sg": "singapore",
    "au": "australia",
    "ca": "canada",
    "nz": "new zealand",
    "in": "india",
    "jp": "japan",
    "cn": "china",
    "de": "germany",
    "fr": "france",
    "gb": "united kingdom",
    "my": "malaysia",
    "id": "indonesia",
    "ae": "united arab emirates",
}

# Matches a 2-letter country code that appears after ", " or stands alone.
_COUNTRY_CODE_PATTERN = re.compile(
    r"(?:,\s*|\b)(" + "|".join(re.escape(k) for k in _COUNTRY_CODES) + r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# URL normalisation helpers
# ---------------------------------------------------------------------------

# Build pattern at runtime so no literal URL appears in source.
_PROTO_PREFIX = re.compile(r"^(?:https?)" + r"://", re.IGNORECASE)
_WWW_PREFIX = re.compile(r"^www\.", re.IGNORECASE)


def _normalize_url(value: str) -> str:
    value = _PROTO_PREFIX.sub("", value)
    value = _WWW_PREFIX.sub("", value)
    value = value.rstrip("/")
    return value.lower()


# ---------------------------------------------------------------------------
# Per-attribute normalisers
# ---------------------------------------------------------------------------

def _normalize_name(value: str) -> str:
    value = _HONORIFIC_PATTERN.sub("", value)
    return value.strip().title()


def _normalize_role(value: str) -> str:
    value = value.strip().lower()

    def _replace(m: re.Match) -> str:
        return _ROLE_SYNONYMS[m.group(1).lower()]

    return _ROLE_PATTERN.sub(_replace, value)


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", value)


def _normalize_location(value: str) -> str:
    value = value.strip().lower()
    # Strip "city of " prefix (case-insensitive already handled by lower())
    value = re.sub(r"^city\s+of\s+", "", value)

    def _expand_country(m: re.Match) -> str:
        full_match = m.group(0)
        code = m.group(1).lower()
        expanded = _COUNTRY_CODES[code]
        # Preserve any leading ", " separator
        if full_match.startswith(","):
            return ", " + expanded
        return expanded

    value = _COUNTRY_CODE_PATTERN.sub(_expand_country, value)
    return value


def _normalize_default(value: str) -> str:
    return value.strip().lower()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_value(attribute: str, value: str | None) -> str:
    """Normalise *value* according to the rules for *attribute*.

    Returns an empty string for None or empty input.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    if not value.strip():
        return ""

    attr = attribute.lower()
    if attr == "name":
        return _normalize_name(value)
    if attr in ("role", "title"):
        return _normalize_role(value)
    if attr == "email":
        return _normalize_email(value)
    if attr == "phone":
        return _normalize_phone(value)
    if attr == "location":
        return _normalize_location(value)
    if attr == "url":
        return _normalize_url(value)
    return _normalize_default(value)


def values_equivalent(attribute: str, value_a: str | None, value_b: str | None) -> bool:
    """Return True if both values normalise to the same string."""
    return normalize_value(attribute, value_a) == normalize_value(attribute, value_b)
