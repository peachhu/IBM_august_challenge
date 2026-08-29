"""
risk_engine.py — Mission Readiness Risk Aggregation Engine
===========================================================
Combines three risk dimensions into a single Mission Readiness Score:

  1. Weather Risk        — from LCC rule engine
  2. Space Weather Risk  — from space_weather_risk scorer
  3. Historical Risk     — from mission history / launch library

Output is a MissionRiskReport with:
  - overall_score (0.0–1.0)
  - recommendation: GO | CAUTION | NO-GO
  - per-dimension breakdown
  - key risk factors for LLM explanation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

try:
    from config import RISK_WEIGHTS
    from core.lcc_rules import LCCResult, evaluate_lcc
    from core.space_weather_risk import SpaceWeatherResult, evaluate_space_weather
    from api_clients.weather_client import WeatherForecast, WeatherSnapshot, get_weather_for_site
    from api_clients.donki_client import get_live_space_weather
    from api_clients.mission_history import historical_scrub_risk
except ImportError:
    from mission_readiness_advisor.config import RISK_WEIGHTS
    from mission_readiness_advisor.core.lcc_rules import LCCResult, evaluate_lcc
    from mission_readiness_advisor.core.space_weather_risk import SpaceWeatherResult, evaluate_space_weather
    from mission_readiness_advisor.api_clients.weather_client import WeatherForecast, WeatherSnapshot, get_weather_for_site
    from mission_readiness_advisor.api_clients.donki_client import get_live_space_weather
    from mission_readiness_advisor.api_clients.mission_history import historical_scrub_risk


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class DimensionScore:
    name: str
    score: float           # 0.0–1.0
    weight: float          # contribution weight
    weighted: float        # score * weight
    level: str             # LOW / MODERATE / HIGH / EXTREME
    summary: str
    factors: list = field(default_factory=list)


@dataclass
class MissionRiskReport:
    mission_date: str
    site_name: str
    overall_score: float           # 0.0–1.0
    recommendation: str            # GO | CAUTION | NO-GO
    confidence: str                # HIGH | MEDIUM | LOW (data quality indicator)
    dimensions: list = field(default_factory=list)    # list[DimensionScore]
    key_factors: list = field(default_factory=list)   # top risk factors
    lcc_result: Optional[LCCResult] = None
    space_weather: Optional[SpaceWeatherResult] = None
    weather_snapshot: Optional[WeatherSnapshot] = None
    historical: Optional[dict] = None
    generated_at: str = ""

    # ── Derived ──────────────────────────────────────────────────────────────
    @property
    def delay_probability_pct(self) -> int:
        """Overall score expressed as an integer percentage."""
        return round(self.overall_score * 100)

    @property
    def recommendation_emoji(self) -> str:
        return {"GO": "🟢", "CAUTION": "🟡", "NO-GO": "🔴"}.get(self.recommendation, "❓")

    @property
    def headline(self) -> str:
        prob = self.delay_probability_pct
        rec = self.recommendation
        kf = self.key_factors[:2]
        reason = " — " + "; ".join(kf) if kf else ""
        return f"{self.recommendation_emoji} {rec}  |  Delay Risk: {prob}%{reason}"

    def dimension_by_name(self, name: str) -> Optional[DimensionScore]:
        return next((d for d in self.dimensions if d.name == name), None)


# ─── Score → Level Mapping ────────────────────────────────────────────────────

def _level(score: float) -> str:
    if score >= 0.75: return "EXTREME"
    if score >= 0.50: return "HIGH"
    if score >= 0.25: return "MODERATE"
    return "LOW"


def _recommendation(score: float, lcc: Optional[LCCResult] = None) -> str:
    """
    Decision logic:
    - Any SCRUB-level LCC violation → NO-GO regardless of score
    - score >= 0.65 → NO-GO
    - score >= 0.35 → CAUTION
    - else → GO
    """
    if lcc and lcc.is_scrub:
        return "NO-GO"
    if score >= 0.65:
        return "NO-GO"
    if score >= 0.35:
        return "CAUTION"
    return "GO"


# ─── Core Engine ─────────────────────────────────────────────────────────────

def evaluate_mission_readiness(
    mission_date: str,
    site_key: str,
    site_config: dict,
    # ── optional overrides (for real-time / test scenarios) ──
    weather_snapshot: Optional[WeatherSnapshot] = None,
    space_weather_result: Optional[SpaceWeatherResult] = None,
    history_data: Optional[dict] = None,
    use_live_donki: bool = True,
    nasa_api_key: str = "",
    owm_api_key: str = "",
) -> MissionRiskReport:
    """
    Full mission readiness evaluation.

    Parameters
    ----------
    mission_date    : Target launch date (YYYY-MM-DD or ISO string)
    site_key        : Display name of site (from LAUNCH_SITES)
    site_config     : Site dict {lat, lon, ll2_name, ...}
    weather_snapshot: Pre-fetched weather (skip OWM call if provided)
    space_weather_result: Pre-computed space weather (skip dataset load if provided)
    history_data    : Pre-loaded historical scrub data
    use_live_donki  : If True, supplement dataset risk with live DONKI API
    nasa_api_key    : Override NASA API key
    owm_api_key     : Override OWM API key
    """

    # ── 1. Weather ──────────────────────────────────────────────────────────
    if weather_snapshot is None:
        forecast = get_weather_for_site(site_config, api_key=owm_api_key)
        weather_snapshot = forecast.current

    wx = weather_snapshot
    lcc = evaluate_lcc(
        wind_speed_knots=wx.wind_speed_knots,
        gust_knots=wx.wind_gust_knots,
        visibility_miles=wx.visibility_miles,
        temperature_c=wx.temperature_c,
        humidity_pct=wx.humidity_pct,
        is_raining=wx.is_raining,
        precipitation_mm_per_hour=wx.precipitation_mm_per_hour,
        lightning_within_10nm=wx.has_lightning,
        lightning_last_30min=wx.has_lightning,
    )
    wx_score = lcc.risk_score
    wx_factors = [r.description for r in lcc.rules if r.violated]
    wx_dim = DimensionScore(
        name="Weather",
        score=wx_score,
        weight=RISK_WEIGHTS["weather"],
        weighted=wx_score * RISK_WEIGHTS["weather"],
        level=_level(wx_score),
        summary=lcc.summary,
        factors=wx_factors,
    )

    # ── 2. Space Weather ─────────────────────────────────────────────────────
    if space_weather_result is None:
        extra_kp = None
        extra_flare = None
        if use_live_donki:
            live = get_live_space_weather(mission_date, api_key=nasa_api_key)
            extra_kp = live.get("kp_max")
            extra_flare = live.get("flare_class")
        space_weather_result = evaluate_space_weather(
            mission_date,
            extra_kp=extra_kp,
            extra_flare_class=extra_flare,
        )

    sw = space_weather_result
    sw_dim = DimensionScore(
        name="Space Weather",
        score=sw.risk_score,
        weight=RISK_WEIGHTS["space_weather"],
        weighted=sw.risk_score * RISK_WEIGHTS["space_weather"],
        level=sw.risk_level,
        summary=str(sw),
        factors=sw.risk_factors,
    )

    # ── 3. Historical ────────────────────────────────────────────────────────
    if history_data is None:
        target_month = None
        try:
            target_month = datetime.fromisoformat(mission_date.split("T")[0]).month
        except Exception:
            pass
        history_data = historical_scrub_risk(
            site_config.get("ll2_name", site_key),
            target_month=target_month,
        )

    hist_score = min(
        history_data.get("scrub_rate", 0.10)
        + max(history_data.get("seasonal_modifier", 0.0), 0.0),
        1.0,
    )
    hist_dim = DimensionScore(
        name="Historical",
        score=hist_score,
        weight=RISK_WEIGHTS["historical"],
        weighted=hist_score * RISK_WEIGHTS["historical"],
        level=_level(hist_score),
        summary=history_data.get("notes", ""),
        factors=[history_data.get("notes", "")] if history_data.get("notes") else [],
    )

    # ── 4. Aggregate ─────────────────────────────────────────────────────────
    overall = round(wx_dim.weighted + sw_dim.weighted + hist_dim.weighted, 3)
    rec = _recommendation(overall, lcc)

    # Confidence: how much real-time / verified data did we get?
    # FIXED (Bug #5): "dataset" (static historical CSV, not live) previously
    # counted the same as "api"/"combined" (live NASA DONKI). A dataset-only
    # run could show HIGH confidence even with zero live data. Only live or
    # combined sources count as a strong signal now; "dataset" alone does not.
    data_flags = [
        wx.source != "mock",
        sw.data_source in ("api", "combined"),
        history_data.get("data_source") == "launch_library_2",
    ]
    conf_map = {3: "HIGH", 2: "MEDIUM", 1: "LOW", 0: "LOW"}
    confidence = conf_map[sum(data_flags)]

    # Key factors: gather top violated items across dimensions
    key_factors = (
        [r.description for r in lcc.scrub_rules]
        + [r.description for r in lcc.caution_rules]
        + [f for f in sw.risk_factors if f]
    )
    if hist_score >= 0.25:
        key_factors.append(
            f"Historical scrub rate at {site_key}: {hist_score:.0%}"
        )
    key_factors = key_factors[:5]  # top 5

    report = MissionRiskReport(
        mission_date=mission_date,
        site_name=site_key,
        overall_score=overall,
        recommendation=rec,
        confidence=confidence,
        dimensions=[wx_dim, sw_dim, hist_dim],
        key_factors=key_factors,
        lcc_result=lcc,
        space_weather=sw,
        weather_snapshot=wx,
        historical=history_data,
        generated_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    return report