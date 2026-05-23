"""Input sanitization helpers.

Use sanitize_user_input on user-submitted free-text BEFORE persisting.
Never apply to scraped HTML, LLM completions, or any research artifact —
those must be stored raw and sanitized at render time on the frontend.
"""
from __future__ import annotations

import bleach

DEFAULT_MAX_LENGTH = 4000


def sanitize_user_input(value: str | None, max_length: int = DEFAULT_MAX_LENGTH) -> str:
    """Strip all HTML tags and truncate. Idempotent.

    - Removes all tags and attributes (whitelist is empty).
    - strip=True removes tag bodies that look like dangling HTML.
    - Truncation is applied AFTER cleaning so the cap reflects stored size.
    """
    if value is None:
        return ""
    cleaned = bleach.clean(value, tags=[], attributes={}, strip=True)
    return cleaned[:max_length]


# ---------------------------------------------------------------------------
# Gate-result detail sanitization (spec: 2026-05-22-gather-ask-user-diagnostic)
# ---------------------------------------------------------------------------

_MAX_DETAIL_STRING_LEN = 120


def _is_safe_string(s: str) -> bool:
    """Reject strings that look like absolute file paths (PII / internal layout)."""
    if s.startswith("/") or (len(s) >= 2 and s[1] == ":" and s[2:3] in ("\\", "/")):
        return False
    return True


def _sanitize_value(v):
    """Return v sanitized, or None if v should be dropped entirely."""
    if isinstance(v, bool):  # bool is int subclass — check first
        return v
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        if not _is_safe_string(v):
            return None
        return v[:_MAX_DETAIL_STRING_LEN]
    if isinstance(v, list):
        cleaned = [_sanitize_value(x) for x in v]
        return [x for x in cleaned if x is not None]
    if isinstance(v, dict):
        # One level deep only; nested dicts are stripped of their dict children.
        out = {}
        for k, val in v.items():
            if not isinstance(k, str):
                continue
            if isinstance(val, dict):
                # second-level dict — drop
                continue
            sv = _sanitize_value(val)
            if sv is not None:
                out[k] = sv
        return out
    return None  # Exceptions, custom objects, etc. all fall through to here


def sanitize_check_detail(detail: dict | None) -> dict:
    """Deny-by-default sanitizer for `GateResult.failing_check_detail`.

    Allowed value types: int, float, bool, str (≤120 chars, no absolute paths),
    list of allowed, dict of allowed (one level deep only — nested dicts dropped).
    Everything else is dropped. See spec §Sanitization contract.
    """
    if detail is None:
        return {}
    result = {}
    for k, v in detail.items():
        if not isinstance(k, str):
            continue
        sv = _sanitize_value(v)
        if sv is not None:
            result[k] = sv
    return result
