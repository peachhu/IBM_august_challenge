"""
lcc_rules.py — Launch Commit Criteria (LCC) Rule Engine
========================================================
Based on the Kennedy Space Center Launch Weather Rules (45th Space Wing)
and general Eastern/Western Range commit criteria used by NASA & SpaceX.

Each rule returns a RuleResult with:
  - violated (bool): True if this condition would prevent/delay launch
  - name (str):      Short rule identifier
  - description (str): Human-readable explanation
  - severity (str):  'SCRUB' | 'CAUTION' | 'OK'
  - measured_value:  The actual measured quantity
  - limit_value:     The threshold that was checked
"""

from dataclasses import dataclass, field
from typing import Optional


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class RuleResult:
    name: str
    description: str
    severity: str            # 'SCRUB' | 'CAUTION' | 'OK'
    violated: bool
    measured_value: float = 0.0
    limit_value: float = 0.0
    unit: str = ""

    def __str__(self) -> str:
        icon = "🔴" if self.severity == "SCRUB" else ("🟡" if self.severity == "CAUTION" else "🟢")
        return (
            f"{icon} [{self.severity}] {self.name}: "
            f"{self.measured_value:.1f}{self.unit} "
            f"({'>' if self.measured_value > self.limit_value else '<='} limit {self.limit_value:.1f}{self.unit})"
        )


@dataclass
class LCCResult:
    rules: list = field(default_factory=list)

    @property
    def is_scrub(self) -> bool:
        return any(r.severity == "SCRUB" and r.violated for r in self.rules)

    @property
    def is_caution(self) -> bool:
        return any(r.severity == "CAUTION" and r.violated for r in self.rules)

    @property
    def scrub_rules(self) -> list:
        return [r for r in self.rules if r.severity == "SCRUB" and r.violated]

    @property
    def caution_rules(self) -> list:
        return [r for r in self.rules if r.severity == "CAUTION" and r.violated]

    @property
    def risk_score(self) -> float:
        """
        Compute weather risk score 0.0–1.0 from rule violations.
        SCRUB rules contribute 0.6–1.0, CAUTION rules contribute 0.2–0.4.
        """
        if not self.rules:
            return 0.0
        scrub_count = len(self.scrub_rules)
        caution_count = len(self.caution_rules)
        # Cap: even one SCRUB = at least 0.60 risk
        base = min(scrub_count * 0.35 + caution_count * 0.12, 1.0)
        if scrub_count >= 1:
            base = max(base, 0.60)
        return round(base, 3)

    @property
    def summary(self) -> str:
        if self.is_scrub:
            reasons = "; ".join(r.name for r in self.scrub_rules)
            return f"⛔ SCRUB — {reasons}"
        if self.is_caution:
            reasons = "; ".join(r.name for r in self.caution_rules)
            return f"⚠️ CAUTION — {reasons}"
        return "✅ All LCC rules satisfied"

    @property
    def violated_descriptions(self) -> list[str]:
        return [r.description for r in self.rules if r.violated]


# ─── Individual Rule Checks ───────────────────────────────────────────────────

def check_surface_winds(wind_speed_knots: float,
                        gust_knots: Optional[float] = None) -> RuleResult:
    """Rule: Surface winds shall not exceed 30 knots (KSC)."""
    limit = 30.0
    effective = max(wind_speed_knots, gust_knots or 0)
    violated = effective > limit
    return RuleResult(
        name="Surface Winds",
        description=f"Surface wind speed {effective:.1f} kt exceeds {limit:.0f} kt limit" if violated
                    else f"Surface winds {effective:.1f} kt — within limit",
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=effective,
        limit_value=limit,
        unit=" kt",
    )


def check_wind_shear(low_level_shear_knots: Optional[float] = None,
                     upper_level_shear_knots: Optional[float] = None) -> RuleResult:
    """Rule: Low-level wind shear > 20 kts between 0-3000 ft is a scrub condition."""
    limit = 20.0
    value = max(
        low_level_shear_knots or 0.0,
        upper_level_shear_knots or 0.0,
    )
    violated = value > limit
    return RuleResult(
        name="Wind Shear",
        description=f"Wind shear {value:.1f} kt exceeds {limit:.0f} kt limit" if violated
                    else f"Wind shear {value:.1f} kt — within limit",
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=value,
        limit_value=limit,
        unit=" kt",
    )


def check_visibility(visibility_miles: float) -> RuleResult:
    """Rule: Visibility shall be at least 3 statute miles at launch."""
    limit = 3.0
    violated = visibility_miles < limit
    return RuleResult(
        name="Visibility",
        description=f"Visibility {visibility_miles:.1f} mi below {limit:.0f} mi minimum" if violated
                    else f"Visibility {visibility_miles:.1f} mi — OK",
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=visibility_miles,
        limit_value=limit,
        unit=" mi",
    )


def check_precipitation(is_raining: bool,
                        precipitation_mm_per_hour: float = 0.0) -> RuleResult:
    """Rule: No heavy precipitation (>= 4 mm/hr) in the flight path."""
    limit = 4.0
    violated = is_raining and precipitation_mm_per_hour >= limit
    caution = is_raining and 0 < precipitation_mm_per_hour < limit
    return RuleResult(
        name="Precipitation",
        description=(
            f"Heavy precipitation {precipitation_mm_per_hour:.1f} mm/hr at launch site" if violated
            else f"Light precipitation present — monitor" if caution
            else "No precipitation"
        ),
        severity="SCRUB" if violated else ("CAUTION" if caution else "OK"),
        violated=violated or caution,
        measured_value=precipitation_mm_per_hour,
        limit_value=limit,
        unit=" mm/hr",
    )


def check_lightning(lightning_within_10nm: bool = False,
                    lightning_last_30min: bool = False) -> RuleResult:
    """Rule: No lightning within 10 nautical miles of launch pad, 30-min clearance required."""
    violated = lightning_within_10nm or lightning_last_30min
    return RuleResult(
        name="Lightning",
        description="Lightning detected within 10 NM — 30-min clearance required" if violated
                    else "No lightning within 10 NM",
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=1.0 if violated else 0.0,
        limit_value=0.0,
        unit="",
    )


def check_cloud_ceiling(cloud_ceiling_ft: Optional[float] = None) -> RuleResult:
    """Rule: Cloud ceiling shall not be below 6,000 ft for vehicle electrostatics."""
    if cloud_ceiling_ft is None:
        # unknown — treat as caution
        return RuleResult(
            name="Cloud Ceiling",
            description="Cloud ceiling data unavailable — treat as caution",
            severity="CAUTION",
            violated=True,
            measured_value=0.0,
            limit_value=6000.0,
            unit=" ft",
        )
    limit = 6000.0
    violated = cloud_ceiling_ft < limit
    return RuleResult(
        name="Cloud Ceiling",
        description=f"Cloud ceiling {cloud_ceiling_ft:.0f} ft below {limit:.0f} ft minimum" if violated
                    else f"Cloud ceiling {cloud_ceiling_ft:.0f} ft — OK",
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=cloud_ceiling_ft,
        limit_value=limit,
        unit=" ft",
    )


def check_temperature(temperature_c: float) -> RuleResult:
    """Rule: Temperature must be between -0.6°C (31°F) and 43.3°C (110°F) at pad."""
    low_limit, high_limit = -0.6, 43.3
    violated = temperature_c < low_limit or temperature_c > high_limit
    return RuleResult(
        name="Temperature",
        description=f"Temperature {temperature_c:.1f}°C outside range [{low_limit}°C – {high_limit}°C]"
                    if violated else f"Temperature {temperature_c:.1f}°C — within range",
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=temperature_c,
        limit_value=high_limit,
        unit="°C",
    )


def check_humidity(humidity_pct: float) -> RuleResult:
    """Rule: Relative humidity > 95% is a caution; condensation risk."""
    limit = 95.0
    violated = humidity_pct > limit
    return RuleResult(
        name="Humidity",
        description=f"Humidity {humidity_pct:.0f}% exceeds {limit:.0f}% caution level" if violated
                    else f"Humidity {humidity_pct:.0f}% — OK",
        severity="CAUTION" if violated else "OK",
        violated=violated,
        measured_value=humidity_pct,
        limit_value=limit,
        unit="%",
    )


def check_anvil_cloud(anvil_cloud_present: bool = False) -> RuleResult:
    """Rule: Anvil clouds (cumulonimbus anvil) within 10 NM = scrub."""
    return RuleResult(
        name="Anvil Cloud",
        description="Anvil cloud within 10 NM of launch corridor — electrostatic hazard" if anvil_cloud_present
                    else "No anvil cloud detected",
        severity="SCRUB" if anvil_cloud_present else "OK",
        violated=anvil_cloud_present,
        measured_value=1.0 if anvil_cloud_present else 0.0,
        limit_value=0.0,
        unit="",
    )


# ─── Full LCC Evaluation ──────────────────────────────────────────────────────

def evaluate_lcc(
    wind_speed_knots: float = 0.0,
    gust_knots: Optional[float] = None,
    visibility_miles: float = 10.0,
    temperature_c: float = 22.0,
    humidity_pct: float = 60.0,
    is_raining: bool = False,
    precipitation_mm_per_hour: float = 0.0,
    lightning_within_10nm: bool = False,
    lightning_last_30min: bool = False,
    cloud_ceiling_ft: Optional[float] = None,
    wind_shear_knots: Optional[float] = None,
    anvil_cloud: bool = False,
) -> LCCResult:
    """
    Run all LCC rules and return a combined LCCResult.

    Parameters
    ----------
    wind_speed_knots        : Surface sustained wind speed at launch pad (knots)
    gust_knots              : Gust speed (knots) — uses max(sustained, gust)
    visibility_miles        : Horizontal visibility (statute miles)
    temperature_c           : Temperature at pad (Celsius)
    humidity_pct            : Relative humidity (0–100)
    is_raining              : True if precipitation is occurring
    precipitation_mm_per_hour: Precipitation rate (mm/hr)
    lightning_within_10nm   : True if lightning detected within 10 NM
    lightning_last_30min    : True if lightning occurred in last 30 min
    cloud_ceiling_ft        : Lowest cloud ceiling (feet AGL); None = unknown
    wind_shear_knots        : Max wind shear between layers (knots)
    anvil_cloud             : True if anvil cloud (Cb) within 10 NM

    Returns
    -------
    LCCResult with all rule outcomes and aggregate risk score.
    """
    result = LCCResult()
    result.rules = [
        check_surface_winds(wind_speed_knots, gust_knots),
        check_visibility(visibility_miles),
        check_temperature(temperature_c),
        check_precipitation(is_raining, precipitation_mm_per_hour),
        check_lightning(lightning_within_10nm, lightning_last_30min),
        check_humidity(humidity_pct),
        check_cloud_ceiling(cloud_ceiling_ft),
        check_anvil_cloud(anvil_cloud),
    ]
    if wind_shear_knots is not None:
        result.rules.append(check_wind_shear(wind_shear_knots))
    return result
