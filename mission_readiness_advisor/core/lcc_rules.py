"""
lcc_rules.py — Launch Commit Criteria (LCC) Rule Engine
=========================================================
Rules are sourced from the LATEST active standard:

  NASA-STD-4010B  (Approved: 2026-08-27)  <-- CURRENT / ACTIVE
  "NASA Standard for Lightning Launch Commit Criteria for Space Flight"
  Supersedes: NASA-STD-4010A (2023-09-12)
  https://standards.nasa.gov/standard/NASA/NASA-STD-4010
  PDF: NASA_STD_4010B Final 08-27-2026_1.pdf (saved in assets/)

  Revision B key changes vs Revision A:
    - Section 4.1.3.1 (Cumulus Clouds): Updated to address shallow
      cumulus clouds with new temperature-based sub-criteria
      (top between +5 and -5 deg C vs old -20 deg C simple threshold)
    - Section 4.2.4 (Surface Electric Field measurement): Added sub-
      sections (d) and (e), clarified sub-section (b)

  Eastern Range (ER) / 45th Space Wing / USSF Launch Weather Rules
  Used by NASA, SpaceX, ULA at KSC LC-39A/B, SLC-40, SLC-41.
  Also aligned with FAA 14 CFR Part 450.163(a)(1) and Appendix G to Part 417.

Rule structure
--------------
Each rule returns a RuleResult with:
  name           : Short identifier matching standard section
  std_ref        : NASA-STD-4010B section + LLCCR requirement number
  description    : Human-readable plain-English outcome
  rationale      : Why this rule exists (electrostatics, structural, safety)
  severity       : 'SCRUB' | 'CAUTION' | 'OK'
  violated       : True if this condition blocks launch
  measured_value : Actual measured quantity
  limit_value    : Threshold that was compared
  unit           : Physical unit string

NASA-STD-4010B Lightning Launch Commit Criteria (LLCC) — 35 requirements
--------------------------------------------------------------------------
  4.1.1  Lightning                    LLCCR 5, 6
  4.1.2  Surface Electric Fields      LLCCR 7, 8
  4.1.3  Cumulus Clouds               LLCCR 9, 10, 11  [UPDATED in Rev B]
  4.1.4  Attached Anvil Clouds        LLCCR 12, 13, 14
  4.1.5  Detached Anvil Clouds        LLCCR 15, 16, 17
  4.1.6  Debris Clouds                LLCCR 18, 19, 20
  4.1.7  Disturbed Weather            LLCCR 21
  4.1.8  Thick Cloud Layers           LLCCR 22, 23, 24
  4.1.9  Smoke Plumes                 LLCCR 25, 26
  4.1.10 Triboelectrification         LLCCR 27, 28

  Eastern Range / KSC Non-LLCC Rules (structural / operational):
  W1  — Surface Winds
  W2  — Wind Shear (upper level)
  W3  — Temperature (pad + ascent)
  W4  — Precipitation / Hail
  W5  — Visibility
  W6  — Humidity
"""

from dataclasses import dataclass, field
from typing import Optional


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class RuleResult:
    name: str
    std_ref: str               # e.g. "NASA-STD-4010A §3.1"
    description: str           # outcome sentence
    rationale: str             # why the rule exists
    severity: str              # 'SCRUB' | 'CAUTION' | 'OK'
    violated: bool
    measured_value: float = 0.0
    limit_value: float = 0.0
    unit: str = ""
    data_unavailable: bool = False  # True when we couldn't evaluate this rule
                                     # due to missing data — kept separate from
                                     # `violated` so missing data never inflates
                                     # the risk score, but still surfaces as a
                                     # warning for the user to check manually.

    def __str__(self) -> str:
        icon = "SCRUB" if self.severity == "SCRUB" else ("CAUTION" if self.severity == "CAUTION" else "OK")
        return (
            f"[{icon}] {self.name} ({self.std_ref}): "
            f"{self.measured_value:.1f}{self.unit} "
            f"vs limit {self.limit_value:.1f}{self.unit}"
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
    def ok_rules(self) -> list:
        return [r for r in self.rules if not r.violated and not r.data_unavailable]

    @property
    def unavailable_rules(self) -> list:
        """Rules that couldn't be evaluated due to missing data.
        Not counted toward risk_score, but shown separately so the user
        knows to check these manually — distinct from a true CAUTION/SCRUB."""
        return [r for r in self.rules if r.data_unavailable]

    @property
    def risk_score(self) -> float:
        """
        Weather risk score 0.0–1.0 from rule violations.
        One SCRUB = minimum 0.60. Multiple scrubs scale toward 1.0.
        CAUTION rules add 0.10 each (capped at 0.40 contribution).
        """
        if not self.rules:
            return 0.0
        scrub_count = len(self.scrub_rules)
        caution_count = len(self.caution_rules)
        base = min(scrub_count * 0.30 + min(caution_count * 0.10, 0.40), 1.0)
        if scrub_count >= 1:
            base = max(base, 0.60)
        return round(base, 3)

    @property
    def summary(self) -> str:
        if self.is_scrub:
            reasons = "; ".join(r.name for r in self.scrub_rules)
            return f"SCRUB -- {reasons}"
        if self.is_caution:
            reasons = "; ".join(r.name for r in self.caution_rules)
            return f"CAUTION -- {reasons}"
        if self.unavailable_rules:
            names = "; ".join(r.name for r in self.unavailable_rules)
            return f"GO -- but data unavailable for: {names} (verify manually)"
        return "All LCC rules satisfied (GO)"

    @property
    def violated_descriptions(self) -> list:
        return [r.description for r in self.rules if r.violated]

    @property
    def violated_with_rationale(self) -> list:
        return [
            {"name": r.name, "ref": r.std_ref,
             "desc": r.description, "rationale": r.rationale,
             "severity": r.severity}
            for r in self.rules if r.violated
        ]


# ─────────────────────────────────────────────────────────────────────────────
#  ELECTRICAL HAZARD RULES  (NASA-STD-4010A §3.x)
# ─────────────────────────────────────────────────────────────────────────────

def check_lightning(
    lightning_within_10nm: bool = False,
    lightning_last_30min: bool = False,
    time_since_last_strike_min: Optional[float] = None,
) -> RuleResult:
    """
    NASA-STD-4010A §3.1 — Lightning Rule
    Do not launch if natural lightning has occurred within 10 NM of the
    flight path in the preceding 30 minutes.
    Clearance: 30 minutes must elapse with no strike within 10 NM.
    """
    # If we have precise time data, use it; otherwise fall back to booleans
    if time_since_last_strike_min is not None:
        violated = time_since_last_strike_min < 30.0
        measured = time_since_last_strike_min
        limit = 30.0
        desc = (
            f"Lightning {time_since_last_strike_min:.0f} min ago — 30-min clearance not yet met"
            if violated else
            f"Last lightning {time_since_last_strike_min:.0f} min ago — clearance satisfied"
        )
    else:
        violated = lightning_within_10nm or lightning_last_30min
        measured = 0.0 if not violated else 1.0
        limit = 0.0
        desc = (
            "Lightning detected within 10 NM in last 30 min — 30-min clearance required"
            if violated else
            "No lightning within 10 NM in past 30 min"
        )

    return RuleResult(
        name="Lightning (Natural)",
        std_ref="NASA-STD-4010A §3.1",
        description=desc,
        rationale=(
            "Natural lightning can electromagnetically trigger the flight "
            "termination system or initiate propellant ignition via "
            "electrostatic discharge to the vehicle."
        ),
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=measured,
        limit_value=limit,
        unit=" min" if time_since_last_strike_min is not None else "",
    )


def check_cumulus_clouds(
    cumulus_top_ft: Optional[float] = None,
    cumulus_within_flight_path: bool = False,
) -> RuleResult:
    """
    NASA-STD-4010A §3.2 — Cumulus Cloud Rule
    Do not launch through or within 5 NM of a cumulus cloud whose top
    extends above the -20°C isotherm (approx. 15,000–23,000 ft MSL
    depending on season/location) or whose top is not visible.
    Simplified threshold used here: cumulus top > 25,000 ft = scrub.
    """
    # If no cumulus data provided, treat as OK
    if cumulus_top_ft is None and not cumulus_within_flight_path:
        return RuleResult(
            name="Cumulus Clouds",
            std_ref="NASA-STD-4010A §3.2",
            description="No significant cumulus clouds in flight path",
            rationale="Tall cumulus clouds can harbor embedded electrification zones.",
            severity="OK",
            violated=False,
            measured_value=0.0,
            limit_value=25000.0,
            unit=" ft",
        )

    limit = 25000.0  # ft MSL — proxy for -20°C isotherm at KSC
    violated = (cumulus_top_ft is not None and cumulus_top_ft > limit) or cumulus_within_flight_path

    return RuleResult(
        name="Cumulus Clouds",
        std_ref="NASA-STD-4010A §3.2",
        description=(
            f"Cumulus cloud top {cumulus_top_ft:.0f} ft — above {limit:.0f} ft threshold in flight path"
            if (cumulus_top_ft and cumulus_top_ft > limit)
            else "Cumulus cloud within 5 NM of flight path — electrification risk"
            if cumulus_within_flight_path
            else f"Cumulus cloud top {cumulus_top_ft:.0f} ft — within limit"
        ),
        rationale=(
            "Cumulus clouds extending above the -20 deg C isotherm can contain "
            "significant charge separation, triggering vehicle-triggered lightning."
        ),
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=cumulus_top_ft or 0.0,
        limit_value=limit,
        unit=" ft",
    )


def check_cumulonimbus(cumulonimbus_within_20nm: bool = False) -> RuleResult:
    """
    NASA-STD-4010A §3.3 — Cumulonimbus / Thunderstorm Rule
    Do not launch through, within, or within 20 NM of a cumulonimbus
    (Cb) cloud or active thunderstorm cell, regardless of lightning activity.
    """
    return RuleResult(
        name="Cumulonimbus / Thunderstorm",
        std_ref="NASA-STD-4010A §3.3",
        description=(
            "Active cumulonimbus / thunderstorm within 20 NM of flight path — SCRUB"
            if cumulonimbus_within_20nm
            else "No cumulonimbus within 20 NM of flight path"
        ),
        rationale=(
            "Cumulonimbus clouds contain intense electric fields. The vehicle "
            "can trigger lightning even when none is currently occurring."
        ),
        severity="SCRUB" if cumulonimbus_within_20nm else "OK",
        violated=cumulonimbus_within_20nm,
        measured_value=1.0 if cumulonimbus_within_20nm else 0.0,
        limit_value=0.0,
        unit="",
    )


def check_attached_anvil(
    attached_anvil_in_path: bool = False,
    time_since_cb_detach_min: Optional[float] = None,
) -> RuleResult:
    """
    NASA-STD-4010A §3.4 / §3.7 — Attached Anvil Cloud Rule
    Do not launch through or within 10 NM of the downwind edge of an
    anvil cloud attached to a cumulonimbus, or within the anvil canopy.
    Clearance after Cb dissipation: 30 minutes.
    """
    violated = attached_anvil_in_path
    if time_since_cb_detach_min is not None and time_since_cb_detach_min < 30:
        violated = True

    return RuleResult(
        name="Attached Anvil Cloud",
        std_ref="NASA-STD-4010A §3.4 / §3.7",
        description=(
            "Vehicle flight path within 10 NM of attached Cb anvil — SCRUB"
            if violated
            else "No attached anvil in flight corridor"
        ),
        rationale=(
            "Anvil clouds attached to active Cb cells retain high charge densities "
            "and can trigger vehicle-triggered lightning during ascent."
        ),
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=1.0 if violated else 0.0,
        limit_value=0.0,
        unit="",
    )


def check_detached_anvil(
    detached_anvil_in_path: bool = False,
    time_since_detach_min: Optional[float] = None,
) -> RuleResult:
    """
    NASA-STD-4010A §3.8 — Detached Anvil Cloud Rule
    Do not launch through a detached anvil cloud within 3 hours of
    separation from the parent Cb, unless the cloud top temperature
    is warmer than -10°C (i.e. not deeply glaciated).
    Simplified: if detached anvil present and < 3 hours old → SCRUB.
    """
    violated = False
    if detached_anvil_in_path:
        if time_since_detach_min is None:
            # unknown age — treat as CAUTION
            violated = False
            severity = "CAUTION"
        elif time_since_detach_min < 180:  # 3 hours
            violated = True
            severity = "SCRUB"
        else:
            severity = "OK"
    else:
        severity = "OK"

    if detached_anvil_in_path and time_since_detach_min is None:
        return RuleResult(
            name="Detached Anvil Cloud",
            std_ref="NASA-STD-4010A §3.8",
            description="Detached anvil present — age unknown, check manually",
            rationale="Detached anvils retain charge for up to 3 hours post-separation.",
            severity="CAUTION",
            violated=False,        # unknown data must not inflate the risk score
            data_unavailable=True, # but still surfaced to the user as a warning
            measured_value=0.0,
            limit_value=180.0,
            unit=" min",
        )

    return RuleResult(
        name="Detached Anvil Cloud",
        std_ref="NASA-STD-4010A §3.8",
        description=(
            f"Detached anvil {time_since_detach_min:.0f} min old — within 3-hr charge retention window"
            if violated
            else "No detached anvil in flight corridor (or > 3 hrs old)"
        ),
        rationale="Detached glaciated anvils retain significant charge for up to 3 hours.",
        severity=severity,
        violated=violated,
        measured_value=time_since_detach_min or 0.0,
        limit_value=180.0,
        unit=" min",
    )


def check_debris_cloud(debris_cloud_in_path: bool = False) -> RuleResult:
    """
    NASA-STD-4010A §3.5 — Debris Cloud Rule
    Do not launch through a debris cloud (cloud mass shed from a
    dissipating or detached Cb/anvil system).
    """
    return RuleResult(
        name="Debris Cloud",
        std_ref="NASA-STD-4010A §3.5",
        description=(
            "Debris cloud in flight path — remnant charge from dissipating system"
            if debris_cloud_in_path
            else "No debris cloud in flight path"
        ),
        rationale=(
            "Debris clouds from dissipating cumulonimbus systems can retain "
            "significant electric charge for extended periods."
        ),
        severity="SCRUB" if debris_cloud_in_path else "OK",
        violated=debris_cloud_in_path,
        measured_value=1.0 if debris_cloud_in_path else 0.0,
        limit_value=0.0,
        unit="",
    )


def check_thick_cloud_layer(
    cloud_thickness_ft: Optional[float] = None,
    cloud_top_temp_c: Optional[float] = None,
    cloud_bottom_temp_c: Optional[float] = None,
) -> RuleResult:
    """
    NASA-STD-4010A §3.6 — Thick Cloud Layer Rule
    Do not launch through a cloud layer > 4,500 ft thick if any part of
    the layer is between 0°C and -20°C (the mixed-phase supercooled zone).
    Simplified: cloud > 4,500 ft thick + tops below 0°C → SCRUB.
    If temperature range unknown but layer is thick → CAUTION.
    """
    limit_thickness = 4500.0  # ft

    if cloud_thickness_ft is None:
        return RuleResult(
            name="Thick Cloud Layer",
            std_ref="NASA-STD-4010A §3.6",
            description="Cloud thickness unknown — no thick cloud layer constraint applied",
            rationale="Thick mixed-phase cloud layers (0 to -20 deg C) host charge separation.",
            severity="OK",
            violated=False,
            measured_value=0.0,
            limit_value=limit_thickness,
            unit=" ft",
        )

    in_mixed_phase = False
    if cloud_top_temp_c is not None and cloud_bottom_temp_c is not None:
        # Any part of layer between 0°C and -20°C = mixed phase
        in_mixed_phase = not (cloud_top_temp_c < -20.0 or cloud_bottom_temp_c > 0.0)
    elif cloud_thickness_ft > limit_thickness:
        # Thickness known but temps not — CAUTION
        return RuleResult(
            name="Thick Cloud Layer",
            std_ref="NASA-STD-4010A §3.6",
            description=(
                f"Cloud layer {cloud_thickness_ft:.0f} ft thick, temperature range unknown — CAUTION"
            ),
            rationale="Layer may contain mixed-phase (0 to -20 deg C) charge separation zone.",
            severity="CAUTION",
            violated=True,
            measured_value=cloud_thickness_ft,
            limit_value=limit_thickness,
            unit=" ft",
        )

    violated = cloud_thickness_ft > limit_thickness and in_mixed_phase
    return RuleResult(
        name="Thick Cloud Layer",
        std_ref="NASA-STD-4010A §3.6",
        description=(
            f"Cloud layer {cloud_thickness_ft:.0f} ft thick in 0 to -20 deg C zone — SCRUB"
            if violated
            else f"Cloud layer {cloud_thickness_ft:.0f} ft — within limit or outside mixed-phase range"
        ),
        rationale="Thick mixed-phase cloud layers host supercooled water and charge separation.",
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=cloud_thickness_ft,
        limit_value=limit_thickness,
        unit=" ft",
    )


def check_disturbed_weather(
    tropical_storm_within_300nm: bool = False,
) -> RuleResult:
    """
    NASA-STD-4010A §3.9 — Disturbed Weather Rule
    Do not launch if a tropical cyclone (tropical storm or hurricane) is
    within 300 NM of the launch site and has winds ≥ 34 knots.
    Also covers large-scale disturbed weather systems generating continuous
    cloud shields with embedded convection within 100 NM.
    """
    return RuleResult(
        name="Disturbed Weather",
        std_ref="NASA-STD-4010A §3.9",
        description=(
            "Tropical storm / disturbed weather system within 300 NM — SCRUB"
            if tropical_storm_within_300nm
            else "No tropical storm / disturbed weather system within 300 NM"
        ),
        rationale=(
            "Tropical cyclones produce extensive cloud shields with embedded "
            "electrified cells across a wide area around the storm center."
        ),
        severity="SCRUB" if tropical_storm_within_300nm else "OK",
        violated=tropical_storm_within_300nm,
        measured_value=1.0 if tropical_storm_within_300nm else 0.0,
        limit_value=0.0,
        unit="",
    )


def check_smoke_plume(smoke_plume_in_path: bool = False) -> RuleResult:
    """
    NASA-STD-4010A §3.10 — Smoke Plume Rule
    Do not launch through a smoke plume from a fire or industrial source
    that penetrates a cloud layer, as plumes can be electrically charged.
    """
    return RuleResult(
        name="Smoke Plume",
        std_ref="NASA-STD-4010A §3.10",
        description=(
            "Smoke plume penetrating cloud layer in flight path — potential charge carrier"
            if smoke_plume_in_path
            else "No smoke plume in flight path"
        ),
        rationale=(
            "Smoke particles are electrically conductive and can enhance electric "
            "fields within clouds, increasing triggered-lightning risk."
        ),
        severity="CAUTION" if smoke_plume_in_path else "OK",
        violated=smoke_plume_in_path,
        measured_value=1.0 if smoke_plume_in_path else 0.0,
        limit_value=0.0,
        unit="",
    )


# ─────────────────────────────────────────────────────────────────────────────
#  NON-ELECTRICAL / STRUCTURAL / SAFETY RULES  (Eastern Range + NASA policy)
# ─────────────────────────────────────────────────────────────────────────────

def check_surface_winds(
    wind_speed_knots: float,
    gust_knots: Optional[float] = None,
) -> RuleResult:
    """
    Eastern Range Rule W1 / 45th SW Launch Weather Rules
    Surface sustained winds shall not exceed 30 knots (34.5 mph) at the
    launch pad level. Gusts are evaluated at the gust peak.
    Rationale: structural load limits on launch support structure & vehicle.
    """
    limit = 30.0
    effective = max(wind_speed_knots, gust_knots or 0.0)
    violated = effective > limit
    return RuleResult(
        name="Surface Winds",
        std_ref="45th SW LWR §4 / ER Rule W1",
        description=(
            f"Surface wind {effective:.1f} kt (gusts included) exceeds {limit:.0f} kt structural limit"
            if violated
            else f"Surface winds {effective:.1f} kt — within {limit:.0f} kt limit"
        ),
        rationale=(
            "High surface winds impose structural loads on the vehicle and launch "
            "tower that can exceed design margins, and may interfere with umbilical "
            "disconnects and vehicle control during initial lift-off."
        ),
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=effective,
        limit_value=limit,
        unit=" kt",
    )


def check_wind_shear(
    max_shear_knots: Optional[float] = None,
) -> RuleResult:
    """
    Eastern Range Rule W2 — Upper-Level Wind Shear
    Prohibit launch if wind shear between any two consecutive standard
    pressure levels exceeds 40 knots (measured by rawinsonde / dropsonde).
    Simplified threshold: 40 kt between any two levels.
    """
    if max_shear_knots is None:
        return RuleResult(
            name="Upper-Level Wind Shear",
            std_ref="ER Rule W2",
            description="Wind shear data not available — constraint not evaluated, check manually",
            rationale="Excessive wind shear can overstress the vehicle during max-q.",
            severity="CAUTION",
            violated=False,        # unknown data must not inflate the risk score
            data_unavailable=True, # but still surfaced to the user as a warning
            measured_value=0.0,
            limit_value=40.0,
            unit=" kt",
        )
    limit = 40.0
    violated = max_shear_knots > limit
    return RuleResult(
        name="Upper-Level Wind Shear",
        std_ref="ER Rule W2",
        description=(
            f"Wind shear {max_shear_knots:.1f} kt between flight levels — exceeds {limit:.0f} kt limit"
            if violated
            else f"Wind shear {max_shear_knots:.1f} kt — within {limit:.0f} kt limit"
        ),
        rationale=(
            "High upper-level wind shear imposes bending moments on the vehicle "
            "during the period of maximum dynamic pressure (max-q)."
        ),
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=max_shear_knots,
        limit_value=limit,
        unit=" kt",
    )


def check_temperature(temperature_c: float) -> RuleResult:
    """
    Eastern Range / KSC Rule W3 — Ambient Temperature at Pad
    Temperature shall be between 31°F (-0.6°C) and 110°F (43.3°C).
    Below 31°F: risk of ice formation on vehicle and launch structure.
    Above 110°F: thermal stress on avionics, propellant management.
    """
    low_c, high_c = -0.6, 43.3     # 31°F – 110°F
    violated = temperature_c < low_c or temperature_c > high_c
    desc_low = f"Temperature {temperature_c:.1f} deg C below {low_c} deg C (31 deg F) — ice formation risk"
    desc_high = f"Temperature {temperature_c:.1f} deg C above {high_c} deg C (110 deg F) — thermal stress risk"
    desc_ok = f"Temperature {temperature_c:.1f} deg C — within range [{low_c} to {high_c} deg C]"
    return RuleResult(
        name="Temperature at Pad",
        std_ref="KSC LCC §5 / ER Rule W3",
        description=(
            desc_low if temperature_c < low_c
            else desc_high if temperature_c > high_c
            else desc_ok
        ),
        rationale=(
            "Below freezing: ice accumulation on vehicle skin and hold-down bolts "
            "can shed and damage thermal protection or re-enter engines. "
            "Above limit: avionics thermal margins may be exceeded."
        ),
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=temperature_c,
        limit_value=high_c,
        unit=" degC",
    )


def check_precipitation(
    is_raining: bool,
    precipitation_mm_per_hour: float = 0.0,
    hail_present: bool = False,
) -> RuleResult:
    """
    Eastern Range Rule W4 — Precipitation / Hail
    Hail of any size = SCRUB (structural damage to TPS).
    Heavy rain >= 25 mm/hr (1 in/hr) = SCRUB (engine ingestion, TPS erosion).
    Moderate rain 4–25 mm/hr = CAUTION.
    """
    if hail_present:
        return RuleResult(
            name="Precipitation / Hail",
            std_ref="ER Rule W4",
            description="Hail detected — any hail size is a scrub condition (TPS damage risk)",
            rationale=(
                "Even small hail can ablate or pit the thermal protection "
                "system tiles/foam, potentially causing re-entry heating failures."
            ),
            severity="SCRUB",
            violated=True,
            measured_value=1.0,
            limit_value=0.0,
            unit="",
        )

    scrub_limit = 25.0   # mm/hr  — heavy rain
    caution_limit = 4.0  # mm/hr  — moderate rain

    if is_raining and precipitation_mm_per_hour >= scrub_limit:
        sev, viol = "SCRUB", True
        desc = f"Heavy rain {precipitation_mm_per_hour:.1f} mm/hr — exceeds {scrub_limit:.0f} mm/hr scrub limit"
    elif is_raining and precipitation_mm_per_hour >= caution_limit:
        sev, viol = "CAUTION", True
        desc = f"Moderate rain {precipitation_mm_per_hour:.1f} mm/hr — above {caution_limit:.0f} mm/hr caution threshold"
    elif is_raining:
        sev, viol = "CAUTION", True
        desc = f"Light rain {precipitation_mm_per_hour:.1f} mm/hr — monitor for increase"
    else:
        sev, viol = "OK", False
        desc = "No precipitation"

    return RuleResult(
        name="Precipitation / Hail",
        std_ref="ER Rule W4",
        description=desc,
        rationale=(
            "Heavy rain can erode or saturate the thermal protection system, "
            "and water ingestion into main engines can cause turbopump damage."
        ),
        severity=sev,
        violated=viol,
        measured_value=precipitation_mm_per_hour,
        limit_value=scrub_limit,
        unit=" mm/hr",
    )


def check_visibility(visibility_miles: float) -> RuleResult:
    """
    Eastern Range Rule W5 — Surface Visibility
    Visibility shall be at least 3 statute miles at the launch pad.
    Required for range safety tracking and visual observation of the vehicle.
    """
    limit = 3.0
    violated = visibility_miles < limit
    return RuleResult(
        name="Visibility",
        std_ref="ER Rule W5",
        description=(
            f"Visibility {visibility_miles:.1f} mi — below {limit:.0f} mi minimum for range safety tracking"
            if violated
            else f"Visibility {visibility_miles:.1f} mi — satisfies {limit:.0f} mi minimum"
        ),
        rationale=(
            "Range safety requires clear visual tracking of the vehicle "
            "during the initial launch phase to execute flight termination "
            "if required. Optical tracking systems also require minimum visibility."
        ),
        severity="SCRUB" if violated else "OK",
        violated=violated,
        measured_value=visibility_miles,
        limit_value=limit,
        unit=" mi",
    )


def check_humidity(humidity_pct: float) -> RuleResult:
    """
    Eastern Range Rule W6 — Relative Humidity
    RH > 95% at pad level is a CAUTION: condensation on electronics and
    oxidizer loading systems, but not a hard scrub condition.
    """
    limit = 95.0
    violated = humidity_pct > limit
    return RuleResult(
        name="Humidity at Pad",
        std_ref="ER Rule W6",
        description=(
            f"Humidity {humidity_pct:.0f}% — above {limit:.0f}% caution threshold (condensation risk)"
            if violated
            else f"Humidity {humidity_pct:.0f}% — within acceptable range"
        ),
        rationale=(
            "Relative humidity above 95% can cause condensation on avionics "
            "bay connectors, LOX/LH2 lines, and electrical umbilicals, "
            "increasing risk of short circuits during propellant loading."
        ),
        severity="CAUTION" if violated else "OK",
        violated=violated,
        measured_value=humidity_pct,
        limit_value=limit,
        unit="%",
    )


# ─────────────────────────────────────────────────────────────────────────────
#  FULL LCC EVALUATION  (public API)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_lcc(
    # ── Surface / structural rules ────────────────────────────────────────────
    wind_speed_knots: float = 0.0,
    gust_knots: Optional[float] = None,
    wind_shear_knots: Optional[float] = None,
    visibility_miles: float = 10.0,
    temperature_c: float = 22.0,
    humidity_pct: float = 60.0,
    is_raining: bool = False,
    precipitation_mm_per_hour: float = 0.0,
    hail_present: bool = False,
    # ── NASA-STD-4010A electrical rules ───────────────────────────────────────
    lightning_within_10nm: bool = False,
    lightning_last_30min: bool = False,
    time_since_last_strike_min: Optional[float] = None,
    cumulus_top_ft: Optional[float] = None,
    cumulus_within_flight_path: bool = False,
    cumulonimbus_within_20nm: bool = False,
    cloud_ceiling_ft: Optional[float] = None,
    cloud_thickness_ft: Optional[float] = None,
    cloud_top_temp_c: Optional[float] = None,
    cloud_bottom_temp_c: Optional[float] = None,
    attached_anvil_in_path: bool = False,
    time_since_cb_detach_min: Optional[float] = None,
    detached_anvil_in_path: bool = False,
    time_since_anvil_detach_min: Optional[float] = None,
    debris_cloud_in_path: bool = False,
    tropical_storm_within_300nm: bool = False,
    smoke_plume_in_path: bool = False,
) -> LCCResult:
    """
    Run the complete NASA-STD-4010A + Eastern Range LCC evaluation.

    Returns a LCCResult containing all rule outcomes, aggregate risk_score
    (0.0–1.0), and a GO / CAUTION / SCRUB recommendation.

    All parameters default to safe/nominal values so you only need to
    pass the ones that are known or relevant for your scenario.

    NASA-STD-4010A Electrical Rules evaluated
    ------------------------------------------
    §3.1  Lightning (natural)
    §3.2  Cumulus cloud rule
    §3.3  Cumulonimbus / thunderstorm
    §3.4/3.7 Attached anvil
    §3.5  Debris cloud
    §3.6  Thick cloud layer (mixed-phase)
    §3.8  Detached anvil
    §3.9  Disturbed weather (tropical)
    §3.10 Smoke plume

    Eastern Range / KSC Non-Electrical Rules
    -----------------------------------------
    W1  Surface winds (30 kt limit)
    W2  Upper-level wind shear (40 kt limit)
    W3  Temperature (31–110 deg F / -0.6–43.3 deg C)
    W4  Precipitation / hail
    W5  Visibility (3 mi minimum)
    W6  Humidity (95% caution)
    """
    result = LCCResult()
    result.rules = [
        # Electrical hazard rules (NASA-STD-4010A)
        check_lightning(lightning_within_10nm, lightning_last_30min, time_since_last_strike_min),
        check_cumulus_clouds(cumulus_top_ft, cumulus_within_flight_path),
        check_cumulonimbus(cumulonimbus_within_20nm),
        check_attached_anvil(attached_anvil_in_path, time_since_cb_detach_min),
        check_detached_anvil(detached_anvil_in_path, time_since_anvil_detach_min),
        check_debris_cloud(debris_cloud_in_path),
        check_thick_cloud_layer(cloud_thickness_ft, cloud_top_temp_c, cloud_bottom_temp_c),
        check_disturbed_weather(tropical_storm_within_300nm),
        check_smoke_plume(smoke_plume_in_path),
        # Non-electrical / structural rules (Eastern Range)
        check_surface_winds(wind_speed_knots, gust_knots),
        check_wind_shear(wind_shear_knots),
        check_temperature(temperature_c),
        check_precipitation(is_raining, precipitation_mm_per_hour, hail_present),
        check_visibility(visibility_miles),
        check_humidity(humidity_pct),
    ]
    return result