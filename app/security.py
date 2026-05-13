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
