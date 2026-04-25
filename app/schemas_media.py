"""Pydantic models for the /v1/* media endpoints (weather, news, songs, jokes, social).

Kept in a separate module from ``app/schemas.py`` so the OSINT/profile schemas
stay uncluttered. Each response carries a ``provider`` tag (which adapter
answered) and ``fetched_at`` (UTC ISO-8601) so callers can debug + age-check.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ── shared ───────────────────────────────────────────────────────────────────


class _MediaBase(BaseModel):
    provider: str
    fetched_at: datetime


# ── weather ──────────────────────────────────────────────────────────────────


class WeatherResponse(_MediaBase):
    city: str
    condition: str | None = None
    temperature_c: float | None = None
    humidity_pct: float | None = None
    wind_kph: float | None = None
    summary: str


# ── news ─────────────────────────────────────────────────────────────────────

NewsScope = Literal["global", "country", "local"]
NewsTopic = Literal[
    "breaking",
    "tech",
    "music",
    "entertainment",
    "sports",
    "business",
    "science",
    "health",
    "politics",
    "world",
    "any",
]


class NewsItem(BaseModel):
    headline: str
    source: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    topic: NewsTopic | None = None


class NewsResponse(_MediaBase):
    scope: NewsScope
    topic: NewsTopic
    items: list[NewsItem] = Field(default_factory=list)


# ── songs ────────────────────────────────────────────────────────────────────


class SongEnrichmentResponse(_MediaBase):
    title: str
    artist: str
    album: str | None = None
    release_year: int | None = None
    genres: list[str] | None = None
    label: str | None = None
    duration_ms: int | None = None
    tags: list[str] | None = None
    trivia: str | None = None


# ── jokes ────────────────────────────────────────────────────────────────────

JokeStyle = Literal[
    "witty",
    "dad",
    "punny",
    "sarcastic",
    "observational",
    "clean",
    "any",
]


class JokeResponse(_MediaBase):
    joke: str
    style: JokeStyle
    safe: bool
    source: str | None = None


# ── social mentions ──────────────────────────────────────────────────────────

SocialPlatform = Literal["twitter", "facebook"]


class SocialMention(BaseModel):
    id: str
    platform: SocialPlatform
    author: str
    text: str
    url: str | None = None
    posted_at: datetime | None = None


class SocialMentionsResponse(_MediaBase):
    platform: SocialPlatform
    items: list[SocialMention] = Field(default_factory=list)


class SocialMentionsFetchRequest(BaseModel):
    platform: SocialPlatform
    handle: str | None = None
    oauth_token_ref: str | None = None
    since_id: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


# ── audio sourcing ────────────────────────────────────────────────────────────


class S3UploadTarget(BaseModel):
    bucket: str
    key: str
    endpoint: str
    region: str = "auto"
    access_key_id: str
    secret_access_key: str


class SongSourceRequest(BaseModel):
    title: str = Field(..., max_length=200)
    artist: str = Field(..., max_length=200)
    upload_target: S3UploadTarget | None = None
    callback_url: str | None = None


class SongSourceResult(BaseModel):
    job_id: str
    status: str  # "completed" | "failed"
    duration_sec: float | None = None
    size_bytes: int | None = None
    format: str | None = None
    object_key: str | None = None
    error: str | None = None


# ── playlist sourcing ──────────────────────────────────────────────────────────


class PlaylistSong(BaseModel):
    song_id: str
    title: str
    artist: str


class PlaylistSourceRequest(BaseModel):
    station_id: str
    songs: list[PlaylistSong]
    callback_url: str | None = None
    skip_existing: bool = True
    limit: int = Field(default=50, ge=1, le=200)


class SourcedSong(BaseModel):
    song_id: str
    r2_key: str
    audio_url: str | None = None  # Full CDN URL — preferred over r2_key


class PlaylistSourceResult(BaseModel):
    job_id: str
    status: str  # "completed" | "partial" | "failed"
    station_id: str
    total_songs: int
    sourced: int
    skipped: int
    failed: int
    songs: list[SourcedSong] = []
    errors: list[dict] = []
    error: str | None = None
