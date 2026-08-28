"""
donki_client.py — NASA DONKI (Space Weather Database of Notifications, etc.) Client
=====================================================================================
Fetches real-time space weather data from https://api.nasa.gov/DONKI/
Free API key at https://api.nasa.gov/

Endpoints used:
  /FLR  — Solar Flares
  /GST  — Geomagnetic Storms
  /CME  — Coronal Mass Ejections
  /HSS  — High Speed Streams
  /notifications — Summary notifications
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import requests

try:
    from config import NASA_API_KEY
except ImportError:
    from mission_readiness_advisor.config import NASA_API_KEY

_DONKI_BASE = "https://api.nasa.gov/DONKI"
_TIMEOUT = 12  # seconds


# ─── Helper ──────────────────────────────────────────────────────────────────

def _date_range(target_date: str | datetime,
                look_back_days: int = 7,
                look_ahead_days: int = 3) -> tuple[str, str]:
    if isinstance(target_date, str):
        dt = datetime.fromisoformat(target_date.split("T")[0])
    else:
        dt = target_date
    start = (dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    end = (dt + timedelta(days=look_ahead_days)).strftime("%Y-%m-%d")
    return start, end


def _get(endpoint: str, params: dict, api_key: str) -> list | dict | None:
    params["api_key"] = api_key or NASA_API_KEY
    try:
        resp = requests.get(
            f"{_DONKI_BASE}/{endpoint}",
            params=params,
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"[DONKI] {endpoint} → HTTP {resp.status_code}")
        return None
    except Exception as exc:
        print(f"[DONKI] {endpoint} request failed: {exc}")
        return None


# ─── Flares ───────────────────────────────────────────────────────────────────

def get_flares(target_date: str | datetime,
               look_back_days: int = 7,
               api_key: str = "") -> list[dict]:
    """Return list of solar flare events near the target date."""
    start, end = _date_range(target_date, look_back_days, look_ahead_days=1)
    raw = _get("FLR", {"startDate": start, "endDate": end}, api_key)
    if not raw:
        return []
    return [
        {
            "event_id": f.get("flrID", ""),
            "begin_time": f.get("beginTime", ""),
            "peak_time": f.get("peakTime", ""),
            "class_type": f.get("classType", ""),
            "source_location": f.get("sourceLocation", ""),
            "active_region": f.get("activeRegionNum"),
        }
        for f in raw
    ]


def get_max_flare_class(target_date: str | datetime,
                        look_back_days: int = 7,
                        api_key: str = "") -> Optional[str]:
    """Return the highest flare class string found (e.g. 'X2.3'), or None."""
    flares = get_flares(target_date, look_back_days, api_key)
    if not flares:
        return None
    _rank = {"X": 5, "M": 4, "C": 3, "B": 2, "A": 1}
    best = None
    best_rank = 0
    for f in flares:
        cls = str(f.get("class_type", "")).strip().upper()
        if cls and cls[0] in _rank and _rank[cls[0]] > best_rank:
            best_rank = _rank[cls[0]]
            best = cls
    return best


# ─── Geomagnetic Storms ───────────────────────────────────────────────────────

def get_geomagnetic_storms(target_date: str | datetime,
                           look_back_days: int = 7,
                           api_key: str = "") -> list[dict]:
    """Return list of GST events near the target date."""
    start, end = _date_range(target_date, look_back_days, look_ahead_days=1)
    raw = _get("GST", {"startDate": start, "endDate": end}, api_key)
    if not raw:
        return []
    events = []
    for g in raw:
        kp_list = g.get("allKpIndex", []) or []
        kp_max = max((float(k.get("kpIndex", 0)) for k in kp_list), default=0.0)
        events.append({
            "event_id": g.get("gstID", ""),
            "begin_time": g.get("startTime", ""),
            "kp_max": kp_max,
            "source": "DONKI",
        })
    return events


def get_max_kp(target_date: str | datetime,
               look_back_days: int = 7,
               api_key: str = "") -> float:
    """Return the maximum Kp index found in the window, or 0.0."""
    storms = get_geomagnetic_storms(target_date, look_back_days, api_key)
    if not storms:
        return 0.0
    return max(s.get("kp_max", 0.0) for s in storms)


# ─── CME Events ───────────────────────────────────────────────────────────────

def get_cme_events(target_date: str | datetime,
                   look_back_days: int = 10,
                   api_key: str = "") -> list[dict]:
    """Return CME analysis events near the target date."""
    start, end = _date_range(target_date, look_back_days, look_ahead_days=3)
    raw = _get("CMEAnalysis", {"startDate": start, "endDate": end, "mostAccurateOnly": "true"}, api_key)
    if not raw:
        return []
    events = []
    for c in raw:
        events.append({
            "time": c.get("time21_5", "") or c.get("startTime", ""),
            "speed": float(c.get("speed") or 0),
            "latitude": c.get("latitude"),
            "longitude": c.get("longitude"),
            "half_angle": c.get("halfAngle"),
            "type": c.get("type", ""),
            "note": c.get("note", ""),
        })
    return events


# ─── High Speed Streams ───────────────────────────────────────────────────────

def get_hss_events(target_date: str | datetime,
                   look_back_days: int = 5,
                   api_key: str = "") -> list[dict]:
    """Return HSS (high-speed stream) events near the target date."""
    start, end = _date_range(target_date, look_back_days, look_ahead_days=2)
    raw = _get("HSS", {"startDate": start, "endDate": end}, api_key)
    if not raw:
        return []
    return [
        {
            "event_id": h.get("hssID", ""),
            "begin_time": h.get("eventTime", ""),
            "note": h.get("note", ""),
        }
        for h in raw
    ]


# ─── Combined Live Snapshot ───────────────────────────────────────────────────

def get_live_space_weather(target_date: str | datetime,
                           api_key: str = "") -> dict:
    """
    Single convenience call — returns a dict with the most important
    live values extracted from DONKI, ready to feed into space_weather_risk.
    """
    return {
        "kp_max": get_max_kp(target_date, look_back_days=7, api_key=api_key),
        "flare_class": get_max_flare_class(target_date, look_back_days=7, api_key=api_key),
        "cme_events": get_cme_events(target_date, look_back_days=10, api_key=api_key),
        "hss_active": len(get_hss_events(target_date, look_back_days=5, api_key=api_key)) > 0,
    }
