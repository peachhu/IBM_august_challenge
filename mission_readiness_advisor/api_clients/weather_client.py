"""
weather_client.py — OpenWeatherMap API Client
=============================================
Fetches current and 5-day forecast weather for a launch site.
Falls back gracefully when the API key is missing/invalid.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests

try:
    from config import OWM_API_KEY
except ImportError:
    from mission_readiness_advisor.config import OWM_API_KEY

_OWM_BASE = "https://api.openweathermap.org/data/2.5"
_REQUEST_TIMEOUT = 10  # seconds


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class WeatherSnapshot:
    timestamp: str = ""
    temperature_c: float = 22.0
    humidity_pct: float = 60.0
    pressure_hpa: float = 1013.0
    wind_speed_ms: float = 0.0
    wind_gust_ms: Optional[float] = None
    wind_direction_deg: float = 0.0
    visibility_m: float = 10000.0
    weather_main: str = "Clear"       # e.g. "Rain", "Thunderstorm", "Clouds"
    weather_description: str = "clear sky"
    cloud_cover_pct: float = 0.0
    rain_1h_mm: float = 0.0
    rain_3h_mm: float = 0.0
    snow_1h_mm: float = 0.0
    source: str = "api"               # 'api' | 'mock'

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def wind_speed_knots(self) -> float:
        return self.wind_speed_ms * 1.94384

    @property
    def wind_gust_knots(self) -> Optional[float]:
        return self.wind_gust_ms * 1.94384 if self.wind_gust_ms else None

    @property
    def visibility_miles(self) -> float:
        return self.visibility_m * 0.000621371

    @property
    def precipitation_mm_per_hour(self) -> float:
        """Best estimate of hourly precipitation rate."""
        if self.rain_1h_mm > 0:
            return self.rain_1h_mm
        if self.rain_3h_mm > 0:
            return self.rain_3h_mm / 3.0
        return 0.0

    @property
    def is_raining(self) -> bool:
        return self.weather_main in ("Rain", "Drizzle", "Thunderstorm") or self.rain_1h_mm > 0

    @property
    def has_lightning(self) -> bool:
        return self.weather_main == "Thunderstorm"


@dataclass
class WeatherForecast:
    site_name: str = ""
    lat: float = 0.0
    lon: float = 0.0
    current: Optional[WeatherSnapshot] = None
    hourly: list = field(default_factory=list)   # list[WeatherSnapshot]
    fetched_at: str = ""
    error: str = ""


# ─── Internal Parsers ─────────────────────────────────────────────────────────

def _parse_snapshot(entry: dict, source: str = "api") -> WeatherSnapshot:
    main = entry.get("main", {})
    wind = entry.get("wind", {})
    weather_list = entry.get("weather", [{}])
    rain = entry.get("rain", {})
    snow = entry.get("snow", {})
    clouds = entry.get("clouds", {})

    ts = entry.get("dt_txt", "") or (
        datetime.utcfromtimestamp(entry.get("dt", 0)).strftime("%Y-%m-%d %H:%M UTC")
    )

    return WeatherSnapshot(
        timestamp=ts,
        temperature_c=main.get("temp", 22.0) - 273.15 if main.get("temp", 0) > 200 else main.get("temp", 22.0),
        humidity_pct=main.get("humidity", 60.0),
        pressure_hpa=main.get("pressure", 1013.0),
        wind_speed_ms=wind.get("speed", 0.0),
        wind_gust_ms=wind.get("gust"),
        wind_direction_deg=wind.get("deg", 0.0),
        visibility_m=min(entry.get("visibility", 10000), 10000),
        weather_main=weather_list[0].get("main", "Clear"),
        weather_description=weather_list[0].get("description", ""),
        cloud_cover_pct=clouds.get("all", 0.0),
        rain_1h_mm=rain.get("1h", 0.0),
        rain_3h_mm=rain.get("3h", 0.0),
        snow_1h_mm=snow.get("1h", 0.0),
        source=source,
    )


# ─── API Calls ────────────────────────────────────────────────────────────────

def get_current_weather(lat: float, lon: float, api_key: str = "") -> Optional[WeatherSnapshot]:
    """Fetch current weather from OWM /weather endpoint."""
    key = api_key or OWM_API_KEY
    if not key:
        return None
    try:
        resp = requests.get(
            f"{_OWM_BASE}/weather",
            params={"lat": lat, "lon": lon, "appid": key, "units": "metric"},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return _parse_snapshot(resp.json())
    except Exception as exc:
        print(f"[WeatherClient] current weather failed: {exc}")
        return None


def get_forecast(lat: float, lon: float,
                 api_key: str = "",
                 site_name: str = "") -> WeatherForecast:
    """
    Fetch 5-day / 3-hour forecast from OWM /forecast endpoint.
    Returns a WeatherForecast object with .current and .hourly populated.
    """
    key = api_key or OWM_API_KEY
    forecast = WeatherForecast(
        site_name=site_name, lat=lat, lon=lon,
        fetched_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    if not key:
        forecast.error = "OWM_API_KEY not set — using mock data"
        forecast.current = _mock_snapshot()
        forecast.hourly = [_mock_snapshot(i) for i in range(1, 9)]
        return forecast

    try:
        resp = requests.get(
            f"{_OWM_BASE}/forecast",
            params={"lat": lat, "lon": lon, "appid": key, "units": "metric", "cnt": 40},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        entries = data.get("list", [])
        if entries:
            forecast.current = _parse_snapshot(entries[0])
            forecast.hourly = [_parse_snapshot(e) for e in entries[1:]]
    except Exception as exc:
        forecast.error = str(exc)
        forecast.current = _mock_snapshot()
        forecast.hourly = [_mock_snapshot(i) for i in range(1, 9)]

    return forecast


# ─── Mock / Fallback ──────────────────────────────────────────────────────────

def _mock_snapshot(offset_slots: int = 0) -> WeatherSnapshot:
    """Return a safe-to-launch mock weather snapshot for demo/testing."""
    return WeatherSnapshot(
        timestamp=f"2025-01-01 {offset_slots * 3 % 24:02d}:00 UTC",
        temperature_c=24.0,
        humidity_pct=65.0,
        pressure_hpa=1013.0,
        wind_speed_ms=5.0,
        wind_direction_deg=90.0,
        visibility_m=9999.0,
        weather_main="Clear",
        weather_description="clear sky (demo mode)",
        cloud_cover_pct=5.0,
        source="mock",
    )


def get_weather_for_site(site: dict, api_key: str = "") -> WeatherForecast:
    """
    Convenience wrapper that accepts a site dict from config.LAUNCH_SITES.
    Usage: get_weather_for_site(LAUNCH_SITES["Kennedy Space Center (KSC), FL"])
    """
    return get_forecast(
        lat=site["lat"],
        lon=site["lon"],
        api_key=api_key,
        site_name=site.get("ll2_name", ""),
    )
