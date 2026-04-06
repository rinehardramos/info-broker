"""Weather adapter for the /v1/weather endpoint.

Provider chain:
  1. OpenWeatherMap (paid, requires OPENWEATHER_API_KEY)
  2. DuckDuckGo Instant Answer (free, no key)

Both fetches go through ``security.safe_fetch_url`` which enforces:
  - http(s) only
  - no SSRF (loopback / RFC1918 / metadata IPs blocked at DNS time)
  - response body capped (default 512 KiB)
  - redirects disabled

The result is cached for 10 minutes per (city, country_code) tuple by the
caller (route handler) so repeated DJ jobs do not hammer upstream.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from app.schemas_media import WeatherResponse
from security import safe_fetch_url

log = logging.getLogger(__name__)

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
DDG_URL = "https://api.duckduckgo.com/"


class WeatherUnavailable(Exception):
    """Raised when no provider can answer. Route handler maps to 503."""


def fetch_weather(
    *,
    city: str | None,
    country_code: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> WeatherResponse:
    """Try OpenWeatherMap first, fall back to DDG, raise if neither answered.

    Either ``city`` or both ``lat``+``lon`` must be supplied. ``country_code``
    disambiguates duplicate city names ("Manila, PH" vs "Manila, US").
    """
    if not city and (lat is None or lon is None):
        raise ValueError("city or lat+lon required")

    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if api_key:
        try:
            return _fetch_openweathermap(api_key, city, country_code, lat, lon)
        except Exception as exc:  # noqa: BLE001 — fallback chain by design
            log.warning("OpenWeatherMap failed (%s); falling back to DDG", exc)

    if city:
        try:
            return _fetch_duckduckgo(city)
        except Exception as exc:  # noqa: BLE001
            log.warning("DuckDuckGo weather failed (%s)", exc)

    raise WeatherUnavailable("no weather provider returned a usable result")


# ── OpenWeatherMap ───────────────────────────────────────────────────────────


def _fetch_openweathermap(
    api_key: str,
    city: str | None,
    country_code: str | None,
    lat: float | None,
    lon: float | None,
) -> WeatherResponse:
    params: list[str] = [f"appid={api_key}", "units=metric"]
    if lat is not None and lon is not None:
        params += [f"lat={lat}", f"lon={lon}"]
    elif city:
        q = city if not country_code else f"{city},{country_code}"
        params.append(f"q={_url_quote(q)}")

    url = f"{OPENWEATHER_URL}?{'&'.join(params)}"
    resp = safe_fetch_url(
        url,
        timeout=8,
        allowed_content_types=("application/json",),
    )
    payload: dict[str, Any] = resp.json()

    weather = (payload.get("weather") or [{}])[0]
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    name = payload.get("name") or city or "Unknown"

    condition = weather.get("description") or weather.get("main")
    temp_c = _to_float(main.get("temp"))
    humidity = _to_float(main.get("humidity"))
    wind_ms = _to_float(wind.get("speed"))
    wind_kph = round(wind_ms * 3.6, 1) if wind_ms is not None else None

    summary_bits = [name]
    if condition:
        summary_bits.append(condition)
    if temp_c is not None:
        summary_bits.append(f"{round(temp_c)}°C")
    summary = ", ".join(summary_bits)

    return WeatherResponse(
        provider="openweathermap",
        fetched_at=datetime.now(timezone.utc),
        city=name,
        condition=condition,
        temperature_c=temp_c,
        humidity_pct=humidity,
        wind_kph=wind_kph,
        summary=summary,
    )


# ── DuckDuckGo Instant Answer fallback ───────────────────────────────────────

# DDG returns a one-line "Abstract" / "AbstractText" / "Answer" containing the
# weather summary. We extract a temperature in C or F if present.
_DDG_TEMP_RE = re.compile(r"(-?\d{1,3}(?:\.\d+)?)\s*°?\s*([CF])", re.IGNORECASE)


def _fetch_duckduckgo(city: str) -> WeatherResponse:
    q = f"weather in {city} today"
    url = f"{DDG_URL}?q={_url_quote(q)}&format=json&no_html=1&skip_disambig=1"
    resp = safe_fetch_url(
        url,
        timeout=6,
        allowed_content_types=("application/json", "application/x-javascript"),
    )
    # DDG sometimes returns application/x-javascript wrapping JSON. Parse leniently.
    text = resp.text.strip()
    if text.startswith("ddg_spice_") or not text.startswith("{"):
        text = text[text.find("{") : text.rfind("}") + 1]
    try:
        payload: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WeatherUnavailable(f"DDG returned non-JSON ({exc})") from exc

    summary = (
        payload.get("AbstractText")
        or payload.get("Abstract")
        or payload.get("Answer")
        or ""
    ).strip()
    if not summary:
        raise WeatherUnavailable("DDG returned empty abstract")

    temp_c: float | None = None
    if (m := _DDG_TEMP_RE.search(summary)) is not None:
        value = float(m.group(1))
        unit = m.group(2).upper()
        temp_c = value if unit == "C" else round((value - 32) * 5 / 9, 1)

    return WeatherResponse(
        provider="duckduckgo",
        fetched_at=datetime.now(timezone.utc),
        city=city,
        condition=None,
        temperature_c=temp_c,
        humidity_pct=None,
        wind_kph=None,
        summary=summary,
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _url_quote(value: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(value)
