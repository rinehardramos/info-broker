"""Tests for the /v1/* media endpoints (broker-PR-1: cache + weather)."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.adapters.weather import WeatherUnavailable, fetch_weather
from app.lib.cache import TTLCache, cache_key
from app.main import app
from app.routers import media as media_router

API_KEY = "test-broker-key"


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    monkeypatch.setenv("INFO_BROKER_API_KEY", API_KEY)
    yield


@pytest.fixture(autouse=True)
def _reset_weather_cache():
    media_router._weather_cache.clear()
    yield
    media_router._weather_cache.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _fake_response(payload: dict | str, content_type: str = "application/json") -> SimpleNamespace:
    text = json.dumps(payload) if isinstance(payload, dict) else payload
    return SimpleNamespace(
        text=text,
        json=lambda: json.loads(text),
        headers={"Content-Type": content_type},
    )


# ── TTLCache unit tests ──────────────────────────────────────────────────────


class TestTTLCache:
    def test_get_returns_none_for_missing_key(self):
        cache: TTLCache[str] = TTLCache(default_ttl=10)
        assert cache.get("missing") is None

    def test_set_then_get_round_trips(self):
        cache: TTLCache[str] = TTLCache(default_ttl=10)
        cache.set("k", "v")
        assert cache.get("k") == "v"

    def test_expired_entries_return_none_and_get_evicted(self):
        cache: TTLCache[str] = TTLCache(default_ttl=0.05)
        cache.set("k", "v")
        time.sleep(0.06)
        assert cache.get("k") is None
        assert len(cache) == 0

    def test_lru_bound_evicts_oldest(self):
        cache: TTLCache[int] = TTLCache(default_ttl=10, max_entries=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # evicts "a"
        assert cache.get("a") is None
        assert cache.get("d") == 4
        assert len(cache) == 3

    def test_get_touches_lru_order(self):
        cache: TTLCache[int] = TTLCache(default_ttl=10, max_entries=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.get("a")  # makes "a" the most recent
        cache.set("d", 4)  # should evict "b" now, not "a"
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_purge_expired_returns_count(self):
        cache: TTLCache[int] = TTLCache(default_ttl=0.05)
        cache.set("a", 1)
        cache.set("b", 2)
        time.sleep(0.06)
        assert cache.purge_expired() == 2

    def test_invalid_ttl_rejected(self):
        with pytest.raises(ValueError):
            TTLCache(default_ttl=0)
        with pytest.raises(ValueError):
            TTLCache(default_ttl=10, max_entries=0)


class TestCacheKey:
    def test_string_parts_lowercased_and_stripped(self):
        assert cache_key("Weather", " Manila ") == ("weather", "manila")

    def test_none_parts_preserved(self):
        assert cache_key("weather", None, "ph") == ("weather", None, "ph")

    def test_numeric_parts_preserved(self):
        assert cache_key("weather", 14.6, 120.98) == ("weather", 14.6, 120.98)


# ── weather adapter unit tests ───────────────────────────────────────────────


class TestWeatherAdapterOpenWeatherMap:
    def test_happy_path_parses_temperature_and_units(self, monkeypatch):
        monkeypatch.setenv("OPENWEATHER_API_KEY", "fake-owm-key")
        payload = {
            "name": "Manila",
            "weather": [{"description": "light rain", "main": "Rain"}],
            "main": {"temp": 28.5, "humidity": 80},
            "wind": {"speed": 5.0},  # m/s
        }
        with patch(
            "app.adapters.weather.safe_fetch_url",
            return_value=_fake_response(payload),
        ) as mock_fetch:
            result = fetch_weather(city="Manila", country_code="PH")

        assert result.provider == "openweathermap"
        assert result.city == "Manila"
        assert result.condition == "light rain"
        assert result.temperature_c == 28.5
        assert result.humidity_pct == 80.0
        assert result.wind_kph == 18.0  # 5 m/s * 3.6
        assert "Manila" in result.summary
        # Python round() is banker's rounding so 28.5 → 28; either is acceptable.
        assert "28°C" in result.summary or "29°C" in result.summary
        # URL was built with appid + units=metric + q=Manila,PH
        assert mock_fetch.call_count == 1
        called_url = mock_fetch.call_args.args[0]
        assert "appid=fake-owm-key" in called_url
        assert "units=metric" in called_url
        assert "Manila" in called_url

    def test_lat_lon_takes_precedence_over_city(self, monkeypatch):
        monkeypatch.setenv("OPENWEATHER_API_KEY", "k")
        payload = {"name": "Somewhere", "weather": [{}], "main": {"temp": 20}, "wind": {}}
        with patch(
            "app.adapters.weather.safe_fetch_url",
            return_value=_fake_response(payload),
        ) as mock_fetch:
            fetch_weather(city=None, lat=14.6, lon=120.98)
        called_url = mock_fetch.call_args.args[0]
        assert "lat=14.6" in called_url
        assert "lon=120.98" in called_url

    def test_owm_failure_falls_back_to_ddg(self, monkeypatch):
        monkeypatch.setenv("OPENWEATHER_API_KEY", "k")
        ddg_payload = {"AbstractText": "Manila weather: 30°C and humid"}

        call_log: list[str] = []

        def fake(url: str, **kwargs):
            call_log.append(url)
            if "openweathermap" in url:
                raise RuntimeError("upstream 500")
            return _fake_response(ddg_payload)

        with patch("app.adapters.weather.safe_fetch_url", side_effect=fake):
            result = fetch_weather(city="Manila")

        assert result.provider == "duckduckgo"
        assert result.temperature_c == 30.0
        assert "Manila" in result.summary
        assert any("openweathermap" in u for u in call_log)
        assert any("duckduckgo" in u for u in call_log)


class TestWeatherAdapterDuckDuckGo:
    def test_no_api_key_uses_ddg_directly(self, monkeypatch):
        monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
        payload = {"AbstractText": "Tokyo weather: 18°C clear"}
        with patch(
            "app.adapters.weather.safe_fetch_url",
            return_value=_fake_response(payload),
        ):
            result = fetch_weather(city="Tokyo")
        assert result.provider == "duckduckgo"
        assert result.temperature_c == 18.0

    def test_fahrenheit_converted_to_celsius(self, monkeypatch):
        monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
        payload = {"AbstractText": "Phoenix weather: 100°F sunny"}
        with patch(
            "app.adapters.weather.safe_fetch_url",
            return_value=_fake_response(payload),
        ):
            result = fetch_weather(city="Phoenix")
        # 100F → 37.8C
        assert result.temperature_c == 37.8

    def test_empty_abstract_raises_unavailable(self, monkeypatch):
        monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
        with patch(
            "app.adapters.weather.safe_fetch_url",
            return_value=_fake_response({"AbstractText": "", "Abstract": "", "Answer": ""}),
        ):
            with pytest.raises(WeatherUnavailable):
                fetch_weather(city="Nowhere")

    def test_missing_inputs_raise_value_error(self):
        with pytest.raises(ValueError):
            fetch_weather(city=None)


# ── /v1/weather route integration tests ─────────────────────────────────────


class TestWeatherRoute:
    def test_missing_api_key_returns_401(self, client):
        r = client.get("/v1/weather", params={"city": "Manila"})
        assert r.status_code == 401

    def test_wrong_api_key_returns_401(self, client):
        r = client.get(
            "/v1/weather",
            params={"city": "Manila"},
            headers={"X-API-Key": "wrong"},
        )
        assert r.status_code == 401

    def test_missing_city_and_coords_returns_400(self, client):
        r = client.get("/v1/weather", headers={"X-API-Key": API_KEY})
        assert r.status_code == 400

    def test_happy_path_returns_weather(self, client, monkeypatch):
        monkeypatch.setenv("OPENWEATHER_API_KEY", "k")
        payload = {
            "name": "Manila",
            "weather": [{"description": "sunny"}],
            "main": {"temp": 30, "humidity": 70},
            "wind": {"speed": 3},
        }
        with patch(
            "app.adapters.weather.safe_fetch_url",
            return_value=_fake_response(payload),
        ):
            r = client.get(
                "/v1/weather",
                params={"city": "Manila", "country_code": "PH"},
                headers={"X-API-Key": API_KEY},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["city"] == "Manila"
        assert body["temperature_c"] == 30
        assert body["provider"] == "openweathermap"

    def test_second_call_hits_the_cache(self, client, monkeypatch):
        monkeypatch.setenv("OPENWEATHER_API_KEY", "k")
        payload = {
            "name": "Manila",
            "weather": [{"description": "sunny"}],
            "main": {"temp": 30},
            "wind": {},
        }
        with patch(
            "app.adapters.weather.safe_fetch_url",
            return_value=_fake_response(payload),
        ) as mock_fetch:
            r1 = client.get(
                "/v1/weather",
                params={"city": "Manila"},
                headers={"X-API-Key": API_KEY},
            )
            r2 = client.get(
                "/v1/weather",
                params={"city": "Manila"},
                headers={"X-API-Key": API_KEY},
            )
        assert r1.status_code == r2.status_code == 200
        # Upstream called exactly once even though we hit the route twice.
        assert mock_fetch.call_count == 1

    def test_provider_outage_returns_503(self, client, monkeypatch):
        monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
        with patch(
            "app.adapters.weather.safe_fetch_url",
            side_effect=RuntimeError("ddg down"),
        ):
            r = client.get(
                "/v1/weather",
                params={"city": "Manila"},
                headers={"X-API-Key": API_KEY},
            )
        assert r.status_code == 503
