"""Rate limiter wired to the FastAPI app via slowapi.

Per-API-key (falls back to client IP) bucket — keeps the broker from being
DoS-amplified into MusicBrainz / OpenWeatherMap / NewsAPI.

Limits are intentionally generous on the read endpoints (60/min) and tighter
on the social-mention POST (because each call costs an upstream OAuth quota).
Override per-route in the route decorator.
"""
from __future__ import annotations

import os

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

# Disable limiting under test: the suite makes hundreds of requests from a
# single client IP (one bucket), which trips the 60/minute default and causes
# flaky `429`s unrelated to the code under test. conftest sets DISABLE_RATE_LIMIT=1
# before importing the app. (Does not affect prod, where the env var is unset.)
_RATE_LIMIT_ENABLED = os.getenv("DISABLE_RATE_LIMIT") != "1"


def _key_func(request: Request) -> str:
    """Bucket by API key when present, else by client IP.

    The auth dependency runs *after* the limiter, so we cannot rely on it to
    have validated the key yet. We just read the header.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"key:{api_key}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=_key_func,
    default_limits=["60/minute"],
    storage_uri="memory://",
    headers_enabled=True,
    enabled=_RATE_LIMIT_ENABLED,
)
