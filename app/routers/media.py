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

from app.adapters.weather import WeatherUnavailable, fetch_weather
from app.deps import require_api_key
from app.lib.cache import TTLCache, cache_key
from app.lib.rate_limit import limiter
from app.schemas_media import WeatherResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["media"])

# 10 min weather TTL — keeps repeat DJ jobs from hammering OpenWeatherMap.
_weather_cache: TTLCache[WeatherResponse] = TTLCache(default_ttl=600, max_entries=512)


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
