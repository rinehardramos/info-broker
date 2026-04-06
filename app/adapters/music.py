"""Song metadata enrichment adapter for /v1/songs/enrich.

Source: MusicBrainz Web Service v2 (https://musicbrainz.org/ws/2/recording).
No API key required, but the project's User-Agent must identify the caller
per MusicBrainz ToS — set MUSICBRAINZ_USER_AGENT in the environment.

Returns whatever fields MB has: album, year, genres (from tags), label,
duration, plus a one-line ``trivia`` we can optionally synthesize from the
fields when ENABLE_LLM_TRIVIA is set (kept off by default to avoid an LLM
round-trip on every song lookup).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

from app.schemas_media import SongEnrichmentResponse
from security import safe_fetch_url

log = logging.getLogger(__name__)

MB_RECORDING_URL = "https://musicbrainz.org/ws/2/recording/"


class SongEnrichmentUnavailable(Exception):
    """Raised when MusicBrainz returns nothing usable. Route maps to 404."""


def fetch_song_enrichment(*, title: str, artist: str) -> SongEnrichmentResponse:
    if not title.strip() or not artist.strip():
        raise ValueError("title and artist required")

    user_agent = os.getenv(
        "MUSICBRAINZ_USER_AGENT",
        "playgen-info-broker/0.4 (+https://playgen.site)",
    )
    # MB query: recording:"X" AND artist:"Y", asking for releases + tags inc.
    q = f'recording:"{_escape(title)}" AND artist:"{_escape(artist)}"'
    url = (
        f"{MB_RECORDING_URL}?query={quote_plus(q)}"
        "&fmt=json&limit=1&inc=releases+tags"
    )
    try:
        resp = safe_fetch_url(
            url,
            timeout=8,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            allowed_content_types=("application/json",),
        )
    except Exception as exc:  # noqa: BLE001
        raise SongEnrichmentUnavailable(f"musicbrainz fetch failed: {exc}") from exc

    payload: dict[str, Any] = resp.json()
    recordings = payload.get("recordings") or []
    if not recordings:
        raise SongEnrichmentUnavailable("no MusicBrainz match")

    rec = recordings[0]
    releases = rec.get("releases") or []
    first_release = releases[0] if releases else {}

    album = first_release.get("title")
    release_year = _parse_year(first_release.get("date"))
    label = None
    label_info = first_release.get("label-info") or first_release.get("label")
    if isinstance(label_info, list) and label_info:
        first_label = label_info[0]
        if isinstance(first_label, dict):
            label = (first_label.get("label") or {}).get("name") or first_label.get("name")
    duration_ms = rec.get("length") if isinstance(rec.get("length"), int) else None

    raw_tags = rec.get("tags") or []
    tags = [
        t.get("name")
        for t in raw_tags
        if isinstance(t, dict) and t.get("name")
    ][:8]

    # Genres are a fuzzy subset of tags. Use a small allow-list of common
    # broad genres so DJs get clean labels rather than user-tagged noise.
    genres = [t for t in tags if _looks_like_genre(t)] or None
    if tags == []:
        tags = None

    trivia: str | None = None
    if release_year and album:
        trivia = f"Originally released on {album} in {release_year}."
    elif album:
        trivia = f"From the album {album}."
    elif release_year:
        trivia = f"First released in {release_year}."

    return SongEnrichmentResponse(
        provider="musicbrainz",
        fetched_at=datetime.now(timezone.utc),
        title=title,
        artist=artist,
        album=album,
        release_year=release_year,
        genres=genres,
        label=label,
        duration_ms=duration_ms,
        tags=tags,
        trivia=trivia,
    )


# ── helpers ──────────────────────────────────────────────────────────────────


_GENRE_HINTS = {
    "rock", "pop", "jazz", "blues", "country", "folk", "metal", "punk",
    "electronic", "hip hop", "rap", "r&b", "soul", "funk", "reggae",
    "classical", "indie", "alternative", "dance", "house", "techno",
    "ambient", "disco", "ska", "grunge",
}


def _looks_like_genre(tag: str | None) -> bool:
    if not tag:
        return False
    t = tag.strip().lower()
    return any(g in t for g in _GENRE_HINTS)


def _escape(value: str) -> str:
    """Escape MusicBrainz Lucene-style query special chars."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _parse_year(value: Any) -> int | None:
    if not isinstance(value, str) or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None
