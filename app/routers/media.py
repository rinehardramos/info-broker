"""/v1/* media endpoints used by playgen-dj for script generation.

Each handler:
  - is rate-limited via slowapi (per-API-key bucket)
  - is gated by ``require_api_key``
  - reads/writes a per-endpoint TTL cache before/after touching upstreams
  - maps adapter exceptions to consistent HTTP error codes
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.adapters.music import SongEnrichmentUnavailable, fetch_song_enrichment
from app.adapters.news import NewsUnavailable, fetch_news
from app.adapters.weather import WeatherUnavailable, fetch_weather
from app.deps import require_api_key
from app.lib.cache import TTLCache, cache_key
from app.lib.rate_limit import limiter
from app.schemas_media import (
    NewsResponse,
    NewsScope,
    NewsTopic,
    SongEnrichmentResponse,
    WeatherResponse,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["media"])

# 10 min weather TTL — keeps repeat DJ jobs from hammering OpenWeatherMap.
_weather_cache: TTLCache[WeatherResponse] = TTLCache(default_ttl=600, max_entries=512)
# 15 min news TTL — fresh enough for "current events" while still cutting load.
_news_cache: TTLCache[NewsResponse] = TTLCache(default_ttl=900, max_entries=512)
# 7 day song-enrichment TTL — recording metadata is effectively immutable.
_song_cache: TTLCache[SongEnrichmentResponse] = TTLCache(
    default_ttl=7 * 24 * 3600, max_entries=4096
)


@router.get(
    "/weather",
    response_model=WeatherResponse,
    summary="Current weather for a city or lat/lon",
)
@limiter.limit("60/minute")
def get_weather(
    request: Request,
    response: Response,
    city: str | None = Query(default=None, max_length=100),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    _api_key: str = Depends(require_api_key),
) -> WeatherResponse:
    if not city and (lat is None or lon is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="city or lat+lon required",
        )

    key = cache_key("weather", city, country_code, lat, lon)
    cached = _weather_cache.get(key)
    if cached is not None:
        return cached

    try:
        result = fetch_weather(
            city=city, country_code=country_code, lat=lat, lon=lon
        )
    except WeatherUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"weather unavailable: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("weather adapter crashed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="weather provider error",
        ) from exc

    _weather_cache.set(key, result)
    return result


@router.get(
    "/news",
    response_model=NewsResponse,
    summary="Top news headlines, optionally scoped + filtered by topic",
)
@limiter.limit("60/minute")
def get_news(
    request: Request,
    response: Response,
    scope: NewsScope = Query(default="global"),
    topic: NewsTopic = Query(default="any"),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=10, ge=1, le=50),
    _api_key: str = Depends(require_api_key),
) -> NewsResponse:
    if scope in ("country", "local") and not country_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="country_code required when scope is 'country' or 'local'",
        )

    key = cache_key("news", scope, topic, country_code, query, limit)
    cached = _news_cache.get(key)
    if cached is not None:
        return cached

    try:
        result = fetch_news(
            scope=scope,
            topic=topic,
            country_code=country_code,
            query=query,
            limit=limit,
        )
    except NewsUnavailable as exc:
        # The bundled fallback should make this practically unreachable, but
        # keep the explicit branch for forensics.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"news unavailable: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("news adapter crashed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="news provider error",
        ) from exc

    _news_cache.set(key, result)
    return result


@router.get(
    "/songs/enrich",
    response_model=SongEnrichmentResponse,
    summary="Enrich a (title, artist) pair with album/year/genre/trivia from MusicBrainz",
)
@limiter.limit("120/minute")
def get_song_enrichment(
    request: Request,
    response: Response,
    title: str = Query(..., max_length=200),
    artist: str = Query(..., max_length=200),
    _api_key: str = Depends(require_api_key),
) -> SongEnrichmentResponse:
    key = cache_key("song", title, artist)
    cached = _song_cache.get(key)
    if cached is not None:
        return cached

    try:
        result = fetch_song_enrichment(title=title, artist=artist)
    except SongEnrichmentUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no enrichment found: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("song enrichment crashed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="enrichment provider error",
        ) from exc

    _song_cache.set(key, result)
    return result
