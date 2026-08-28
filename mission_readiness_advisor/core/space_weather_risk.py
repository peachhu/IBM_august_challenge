"""
space_weather_risk.py — Space Weather Risk Scorer
===================================================
Combines historical datasets (already collected) with real-time DONKI API
data to produce a Space Weather Risk Score (0.0 – 1.0) for a given date.

Risk factors:
  1. Geomagnetic storm level (G0–G5 / Kp index)
  2. Solar flare class (A/B/C/M/X)
  3. CME events — speed + geo-effectiveness
  4. High-speed solar wind streams (HSS)
  5. Sunspot/solar activity trend
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

# ── Lazy import config so this module works standalone ─────────────────────
try:
    from config import DATASETS, FLARE_RISK_MAP, KP_THRESHOLDS, CME_SPEED_RISK
except ImportError:
    from mission_readiness_advisor.config import DATASETS, FLARE_RISK_MAP, KP_THRESHOLDS, CME_SPEED_RISK


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class SpaceWeatherResult:
    date: str
    kp_max: float = 0.0
    geomag_level: str = "G0"          # G0–G5
    flare_class_max: str = "None"     # A/B/C/M/X or 'None'
    cme_count: int = 0
    cme_geoeffective: bool = False
    cme_max_speed_kms: float = 0.0
    hss_active: bool = False
    sunspot_number: float = 0.0
    risk_score: float = 0.0           # 0.0–1.0
    risk_level: str = "LOW"           # LOW / MODERATE / HIGH / EXTREME
    risk_factors: list = field(default_factory=list)
    data_source: str = "dataset"      # 'dataset' | 'api' | 'combined'

    @property
    def risk_emoji(self) -> str:
        return {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🔴", "EXTREME": "☢️"}.get(self.risk_level, "❓")

    def __str__(self) -> str:
        return (
            f"{self.risk_emoji} Space Weather [{self.date}]  "
            f"Risk: {self.risk_score:.0%} ({self.risk_level})  "
            f"| Kp={self.kp_max:.1f} | Flare={self.flare_class_max} "
            f"| CME={'Yes' if self.cme_count else 'No'}"
        )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _kp_to_g_level(kp: float) -> str:
    if kp >= 9:    return "G5"
    if kp >= 8:    return "G4"
    if kp >= 7:    return "G3"
    if kp >= 6:    return "G2"
    if kp >= 5:    return "G1"
    return "G0"


def _flare_class_risk(flare_class: Optional[str]) -> float:
    if not flare_class or pd.isna(flare_class):
        return 0.0
    prefix = str(flare_class).strip().upper()[0]
    return FLARE_RISK_MAP.get(prefix, 0.0)


def _cme_speed_to_category(speed_kms: float) -> str:
    if speed_kms >= 1800: return "Extreme"
    if speed_kms >= 900:  return "Fast"
    if speed_kms >= 400:  return "Normal"
    return "Slow"


def _score_to_level(score: float) -> str:
    if score >= 0.75: return "EXTREME"
    if score >= 0.50: return "HIGH"
    if score >= 0.25: return "MODERATE"
    return "LOW"


# ─── Dataset Loaders ─────────────────────────────────────────────────────────

_cache: dict = {}

def _load_dataset(key: str) -> pd.DataFrame:
    """Load a dataset CSV once and cache it."""
    if key in _cache:
        return _cache[key]
    path = DATASETS.get(key)
    if path and Path(path).exists():
        df = pd.read_csv(path, low_memory=False)
        _cache[key] = df
        return df
    return pd.DataFrame()


# ─── Core Scoring Logic ───────────────────────────────────────────────────────

def _score_geomagnetic(date_dt: datetime, window_days: int = 3) -> tuple[float, float, str, list]:
    """
    Return (kp_max, geomag_risk_score, geomag_level, factors)
    Uses daily_geomagnetic_data.csv or geomagnetic_storms.csv.
    """
    factors = []
    kp_max = 0.0

    # Try daily geomagnetic first (finer 3-hr resolution)
    df = _load_dataset("daily_geomagnetic")
    if not df.empty and "Timestamp" in df.columns and "Estimated K" in df.columns:
        df["_dt"] = pd.to_datetime(df["Timestamp"], errors="coerce", utc=True)
        start = date_dt - timedelta(days=window_days)
        mask = (df["_dt"] >= start) & (df["_dt"] <= date_dt + timedelta(days=1))
        subset = df[mask]
        if not subset.empty:
            kp_vals = pd.to_numeric(subset["Estimated K"], errors="coerce").dropna()
            kp_max = float(kp_vals.max()) if not kp_vals.empty else 0.0

    # Fallback: event-based geomagnetic_storms
    if kp_max == 0:
        df2 = _load_dataset("geomagnetic_storms")
        if not df2.empty and "begin_time" in df2.columns:
            df2["_dt"] = pd.to_datetime(df2["begin_time"], errors="coerce", utc=True)
            start = date_dt - timedelta(days=window_days)
            mask = (df2["_dt"] >= start) & (df2["_dt"] <= date_dt + timedelta(days=1))
            subset = df2[mask]
            if not subset.empty:
                kp_vals = pd.to_numeric(subset["kp_index"], errors="coerce").dropna()
                kp_max = float(kp_vals.max()) if not kp_vals.empty else 0.0

    level = _kp_to_g_level(kp_max)
    # Score: G0=0, G1=0.15, G2=0.35, G3=0.60, G4=0.80, G5=1.0
    score_map = {"G0": 0.0, "G1": 0.15, "G2": 0.35, "G3": 0.60, "G4": 0.80, "G5": 1.0}
    score = score_map.get(level, 0.0)

    if kp_max >= KP_THRESHOLDS["moderate"]:
        factors.append(f"Geomagnetic storm {level} (Kp={kp_max:.1f})")

    return kp_max, score, level, factors


def _score_flares(date_dt: datetime, window_days: int = 3) -> tuple[str, float, list]:
    """Return (max_flare_class, flare_risk_score, factors)."""
    factors = []
    best_class = "None"
    best_risk = 0.0

    df = _load_dataset("solar_flares")
    if df.empty:
        df = _load_dataset("space_weather_unified")

    if not df.empty:
        time_col = next((c for c in ["begin_time", "peak_time"] if c in df.columns), None)
        if time_col:
            df["_dt"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
            start = date_dt - timedelta(days=window_days)
            mask = (df["_dt"] >= start) & (df["_dt"] <= date_dt + timedelta(days=1))
            subset = df[mask]
            if not subset.empty and "class_type" in subset.columns:
                for cls in subset["class_type"].dropna():
                    risk = _flare_class_risk(str(cls))
                    if risk > best_risk:
                        best_risk = risk
                        best_class = str(cls)
                if best_risk > 0.1:
                    factors.append(f"Solar flare detected: class {best_class}")

    return best_class, best_risk, factors


def _score_cme(date_dt: datetime, window_days: int = 5) -> tuple[int, bool, float, float, list]:
    """Return (count, is_geoeffective, max_speed_kms, cme_risk, factors)."""
    factors = []
    df = _load_dataset("cme_events")
    if df.empty:
        return 0, False, 0.0, 0.0, factors

    time_col = next((c for c in ["start_time", "begin_time"] if c in df.columns), None)
    if not time_col:
        return 0, False, 0.0, 0.0, factors

    df["_dt"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    start = date_dt - timedelta(days=window_days)
    mask = (df["_dt"] >= start) & (df["_dt"] <= date_dt + timedelta(days=1))
    subset = df[mask]

    if subset.empty:
        return 0, False, 0.0, 0.0, factors

    count = len(subset)
    is_geo = False
    max_speed = 0.0

    if "potentially_geoeffective" in subset.columns:
        geo_vals = subset["potentially_geoeffective"].astype(str).str.lower()
        is_geo = geo_vals.isin(["true", "1", "yes"]).any()

    if "speed" in subset.columns:
        speeds = pd.to_numeric(subset["speed"], errors="coerce").dropna()
        if not speeds.empty:
            max_speed = float(speeds.max())

    cat = _cme_speed_to_category(max_speed)
    cme_risk = CME_SPEED_RISK.get(cat, 0.2)
    if is_geo:
        cme_risk = min(cme_risk * 1.4, 1.0)
        factors.append(f"Geoeffective CME detected (speed={max_speed:.0f} km/s)")
    elif count > 0:
        factors.append(f"{count} CME event(s) in window (max speed {max_speed:.0f} km/s)")

    return count, is_geo, max_speed, cme_risk, factors


def _score_hss(date_dt: datetime, window_days: int = 3) -> tuple[bool, float, list]:
    """Return (hss_active, hss_risk, factors)."""
    factors = []
    df = _load_dataset("high_speed_streams")
    if df.empty:
        return False, 0.0, []

    time_col = next((c for c in ["begin_time", "start_time"] if c in df.columns), None)
    if not time_col:
        return False, 0.0, []

    df["_dt"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    start = date_dt - timedelta(days=window_days)
    mask = (df["_dt"] >= start) & (df["_dt"] <= date_dt + timedelta(days=2))
    active = not df[mask].empty

    if active:
        factors.append("High-speed solar wind stream (HSS) active — elevated Kp expected")

    return active, 0.20 if active else 0.0, factors


# ─── Public API ───────────────────────────────────────────────────────────────

def evaluate_space_weather(
    date: str | datetime,
    window_days: int = 3,
    extra_kp: Optional[float] = None,
    extra_flare_class: Optional[str] = None,
) -> SpaceWeatherResult:
    """
    Score space weather risk for a given date.

    Parameters
    ----------
    date        : ISO date string or datetime (UTC assumed)
    window_days : Look-back window in days for recent events
    extra_kp    : Override/supplement Kp value (e.g. from live DONKI API)
    extra_flare : Override/supplement flare class (e.g. from live API)

    Returns
    -------
    SpaceWeatherResult with full breakdown
    """
    if isinstance(date, str):
        date_dt = pd.to_datetime(date, utc=True)
    else:
        date_dt = date if date.tzinfo else date.replace(tzinfo=timezone.utc)

    all_factors: list[str] = []

    kp_max, geomag_score, geomag_level, gm_factors = _score_geomagnetic(date_dt, window_days)
    flare_class, flare_score, fl_factors = _score_flares(date_dt, window_days)
    cme_count, cme_geo, cme_speed, cme_score, cme_factors = _score_cme(date_dt, window_days + 2)
    hss_active, hss_score, hss_factors = _score_hss(date_dt, window_days)

    # Apply live API overrides if provided
    if extra_kp is not None and extra_kp > kp_max:
        kp_max = extra_kp
        geomag_level = _kp_to_g_level(kp_max)
        score_map = {"G0": 0.0, "G1": 0.15, "G2": 0.35, "G3": 0.60, "G4": 0.80, "G5": 1.0}
        geomag_score = score_map.get(geomag_level, 0.0)
        all_factors.append(f"Live Kp={kp_max:.1f} from DONKI API")

    if extra_flare_class and _flare_class_risk(extra_flare_class) > flare_score:
        flare_class = extra_flare_class
        flare_score = _flare_class_risk(extra_flare_class)
        all_factors.append(f"Live flare class {extra_flare_class} from DONKI API")

    all_factors += gm_factors + fl_factors + cme_factors + hss_factors

    # Weighted aggregate (geomag dominates, flares secondary)
    combined = (
        geomag_score * 0.45
        + flare_score * 0.30
        + cme_score   * 0.15
        + hss_score   * 0.10
    )
    combined = round(min(combined, 1.0), 3)

    return SpaceWeatherResult(
        date=date_dt.strftime("%Y-%m-%d"),
        kp_max=kp_max,
        geomag_level=geomag_level,
        flare_class_max=flare_class,
        cme_count=cme_count,
        cme_geoeffective=cme_geo,
        cme_max_speed_kms=cme_speed,
        hss_active=hss_active,
        risk_score=combined,
        risk_level=_score_to_level(combined),
        risk_factors=all_factors,
        data_source="dataset",
    )
