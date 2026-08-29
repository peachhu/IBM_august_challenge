"""
app.py - Mission Readiness Advisor - Streamlit Dashboard
=========================================================
Run with (Windows - full path):
  streamlit.exe run app.py
  (use the streamlit.exe in Python314/Scripts folder)

Or if Python314/Scripts is in PATH:
  streamlit run app.py
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

# ── Fix sys.path so all internal modules resolve correctly ─────────────────
# This must happen BEFORE any internal imports, regardless of cwd.
_HERE = Path(__file__).resolve().parent          # .../mission_readiness_advisor
_PARENT = _HERE.parent                           # .../IBM_august_challenge
for _p in [str(_HERE), str(_PARENT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
# Also set cwd to the app folder so relative dataset paths work
os.chdir(str(_HERE))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta, date

from config import LAUNCH_SITES, NASA_API_KEY, OWM_API_KEY
from core.risk_engine import evaluate_mission_readiness, MissionRiskReport, DimensionScore, _level, _recommendation
from core.lcc_rules import evaluate_lcc
from core.space_weather_risk import evaluate_space_weather
from api_clients.weather_client import WeatherSnapshot, get_weather_for_site
from llm_advisor import generate_advisory


# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Mission Readiness Advisor",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .metric-card {
      background: #f7f8fa; border: 1px solid #e5e7eb;
      border-radius: 8px; padding: 16px; text-align: center;
  }
  .big-score { font-size: 3rem; font-weight: 800; line-height: 1; }
  .score-go    { color: #16a34a; }
  .score-caution { color: #d97706; }
  .score-nogo  { color: #dc2626; }
  .factor-pill {
      display: inline-block; background: #fee2e2; color: #991b1b;
      border-radius: 999px; padding: 2px 12px; font-size: 0.8rem;
      margin: 2px 4px;
  }
  .factor-pill-warn {
      background: #fef9c3; color: #854d0e;
  }
  .factor-pill-ok {
      background: #dcfce7; color: #166534;
  }
  div[data-testid="stMarkdownContainer"] h2 { margin-top: 1rem; }
</style>
""", unsafe_allow_html=True)


# ─── Helpers ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def cached_evaluate(
    mission_date: str,
    site_key: str,
    wind_knots: float,
    vis_miles: float,
    temp_c: float,
    humidity: float,
    precip: float,
    hail: bool,
    lightning: bool,
    cumulonimbus: bool,
    attached_anvil: bool,
    detached_anvil: bool,
    debris_cloud: bool,
    tropical_storm: bool,
    cumulus_top: float,
    cloud_thickness: float,
    use_live: bool,
) -> MissionRiskReport:
    """Cache evaluation results for 5 minutes to avoid repeated API calls."""
    site_cfg = LAUNCH_SITES[site_key]

    wx = WeatherSnapshot(
        temperature_c=temp_c,
        humidity_pct=humidity,
        wind_speed_ms=wind_knots / 1.94384,
        visibility_m=vis_miles * 1609.34,
        weather_main="Thunderstorm" if (lightning or cumulonimbus) else ("Rain" if precip > 0 else "Clear"),
        rain_1h_mm=precip,
        cloud_cover_pct=0.0,
        source="manual",
    )

    # Full NASA-STD-4010A LCC evaluation
    lcc = evaluate_lcc(
        wind_speed_knots=wind_knots,
        visibility_miles=vis_miles,
        temperature_c=temp_c,
        humidity_pct=humidity,
        is_raining=precip > 0,
        precipitation_mm_per_hour=precip,
        hail_present=hail,
        lightning_within_10nm=lightning,
        lightning_last_30min=lightning,
        cumulonimbus_within_20nm=cumulonimbus,
        attached_anvil_in_path=attached_anvil,
        detached_anvil_in_path=detached_anvil,
        debris_cloud_in_path=debris_cloud,
        tropical_storm_within_300nm=tropical_storm,
        cumulus_top_ft=float(cumulus_top) if cumulus_top > 0 else None,
        cloud_thickness_ft=float(cloud_thickness) if cloud_thickness > 0 else None,
    )

    sw = evaluate_space_weather(mission_date)

    report = evaluate_mission_readiness(
        mission_date=mission_date,
        site_key=site_key,
        site_config=site_cfg,
        weather_snapshot=wx,
        space_weather_result=sw,
        use_live_donki=use_live,
        nasa_api_key=NASA_API_KEY,
    )
    # Attach manual LCC (overrides the one computed from wx)
    report.lcc_result = lcc
    # Recalculate weather dimension with manual LCC
    report.dimensions[0] = DimensionScore(
        name="Weather",
        score=lcc.risk_score,
        weight=0.45,
        weighted=lcc.risk_score * 0.45,
        level=_level(lcc.risk_score),
        summary=lcc.summary,
        factors=[r.description for r in lcc.rules if r.violated],
    )
    # Recompute overall
    total = sum(d.weighted for d in report.dimensions)
    report.overall_score = round(min(total, 1.0), 3)
    report.recommendation = _recommendation(report.overall_score, lcc)
    return report


def gauge_chart(score: float, rec: str) -> go.Figure:
    colour = {"GO": "#16a34a", "CAUTION": "#d97706", "NO-GO": "#dc2626"}.get(rec, "#6b7280")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(score * 100, 1),
        number={"suffix": "%", "font": {"size": 40}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": colour, "thickness": 0.3},
            "steps": [
                {"range": [0, 35], "color": "#dcfce7"},
                {"range": [35, 65], "color": "#fef9c3"},
                {"range": [65, 100], "color": "#fee2e2"},
            ],
            "threshold": {
                "line": {"color": colour, "width": 4},
                "thickness": 0.75,
                "value": round(score * 100, 1),
            },
        },
        title={"text": "Delay Risk", "font": {"size": 16}},
    ))
    fig.update_layout(height=280, margin=dict(t=40, b=10, l=30, r=30))
    return fig


def breakdown_bar(dims) -> go.Figure:
    names = [d.name for d in dims]
    scores = [round(d.score * 100, 1) for d in dims]
    weights = [round(d.weight * 100) for d in dims]
    colours = []
    for d in dims:
        if d.level == "LOW":         colours.append("#16a34a")
        elif d.level == "MODERATE":  colours.append("#d97706")
        elif d.level == "HIGH":      colours.append("#ef4444")
        else:                        colours.append("#7f1d1d")

    fig = go.Figure(go.Bar(
        x=names,
        y=scores,
        marker_color=colours,
        text=[f"{s:.0f}%<br>(weight {w}%)" for s, w in zip(scores, weights)],
        textposition="outside",
    ))
    fig.update_layout(
        yaxis=dict(range=[0, 110], title="Risk Score (%)"),
        height=300,
        margin=dict(t=20, b=20, l=10, r=10),
        plot_bgcolor="white",
    )
    return fig


def space_weather_timeline() -> go.Figure:
    """Mini Kp timeline from daily_geomagnetic_data.csv."""
    try:
        from config import DATASETS
        df = pd.read_csv(DATASETS["daily_geomagnetic"], low_memory=False)
        df["_dt"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        df = df.sort_values("_dt").tail(90)
        df["Kp"] = pd.to_numeric(df["Estimated K"], errors="coerce")
        fig = px.line(df, x="_dt", y="Kp", title="Kp Index — Last 90 Data Points",
                      color_discrete_sequence=["#3b82f6"])
        fig.add_hrect(y0=5, y1=9, fillcolor="#fee2e2", opacity=0.3, line_width=0,
                      annotation_text="G1+", annotation_position="top left")
        fig.update_layout(height=250, margin=dict(t=40, b=20, l=10, r=10))
        return fig
    except Exception:
        return go.Figure()


# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://www.nasa.gov/wp-content/themes/nasa/assets/images/nasa-logo.svg",
             width=80)
    st.title("⚙️ Mission Parameters")
    st.divider()

    site_key = st.selectbox("🚀 Launch Site", list(LAUNCH_SITES.keys()))
    mission_date = st.date_input(
        "📅 Target Launch Date",
        value=date.today() + timedelta(days=1),
        min_value=date(2020, 1, 1),
        max_value=date(2030, 12, 31),
    )

    st.divider()
    st.subheader("🌦️ Surface Weather  (ER Rules)")
    wind_knots = st.slider("Wind Speed (knots)  [W1 limit: 30 kt]", 0.0, 80.0, 8.0, 0.5)
    vis_miles  = st.slider("Visibility (miles)  [W5 limit: 3 mi]", 0.0, 15.0, 10.0, 0.5)
    temp_c     = st.slider("Temperature (°C)  [W3: -0.6 to 43.3°C]", -20.0, 50.0, 24.0, 0.5)
    humidity   = st.slider("Humidity (%)  [W6 caution: >95%]", 0, 100, 65)
    precip     = st.slider("Precipitation (mm/hr)  [W4 scrub: >=25]", 0.0, 50.0, 0.0, 0.5)
    hail       = st.checkbox("Hail present (any size = SCRUB)  [W4]")
    lightning  = st.checkbox("Lightning within 10 NM  [STD-4010A §3.1]")

    st.divider()
    st.subheader("NASA-STD-4010A Cloud Rules")
    st.caption("Electrostatic / triggered-lightning criteria")
    cumulonimbus   = st.checkbox("Cumulonimbus within 20 NM  [§3.3]")
    attached_anvil = st.checkbox("Attached anvil in flight path  [§3.4/3.7]")
    detached_anvil = st.checkbox("Detached anvil in flight path  [§3.8]")
    debris_cloud   = st.checkbox("Debris cloud in flight path  [§3.5]")
    tropical_storm = st.checkbox("Tropical storm within 300 NM  [§3.9]")
    cumulus_top    = st.number_input(
        "Cumulus cloud top (ft MSL, 0=none)  [§3.2 limit: 25,000 ft]",
        0, 60000, 0, 1000
    )
    cloud_thickness = st.number_input(
        "Cloud layer thickness (ft, 0=unknown)  [§3.6 limit: 4,500 ft]",
        0, 30000, 0, 500
    )

    st.divider()
    st.subheader("⚙️ Options")
    use_live_donki = st.checkbox("Use live NASA DONKI API", value=bool(NASA_API_KEY and NASA_API_KEY != "DEMO_KEY"))
    use_llm = st.checkbox("Generate LLM Advisory (watsonx)", value=False)

    st.divider()
    run_btn = st.button("🚀 Evaluate Mission Readiness", type="primary", use_container_width=True)


# ─── Main Content ─────────────────────────────────────────────────────────────

st.title("🚀 Mission Readiness Advisor")
st.caption("AI-powered launch risk assessment · IBM August Challenge")

if not run_btn:
    # Landing state
    st.info(
        "👈 Configure mission parameters in the sidebar, then click **Evaluate Mission Readiness** "
        "to get your risk assessment."
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### 🌦️ Weather\nSurface conditions checked against NASA/SpaceX "
                    "**Launch Commit Criteria** (wind, visibility, lightning, etc.)")
    with col2:
        st.markdown("### ☀️ Space Weather\nGeomagnetic storms, solar flares, CME events "
                    "from **NOAA DONKI** + historical datasets (2023–2025)")
    with col3:
        st.markdown("### 📚 History\nHistorical scrub rate from **Launch Library 2 API** "
                    "— seasonal patterns at this launch site")

    st.divider()
    st.subheader("📊 Space Weather Background")
    timeline_fig = space_weather_timeline()
    if timeline_fig.data:
        st.plotly_chart(timeline_fig, use_container_width=True)
    st.stop()

# ── Run evaluation ───────────────────────────────────────────────────────────
with st.spinner("🔍 Evaluating mission readiness…"):
    try:
        report = cached_evaluate(
            mission_date=mission_date.isoformat(),
            site_key=site_key,
            wind_knots=wind_knots,
            vis_miles=vis_miles,
            temp_c=temp_c,
            humidity=float(humidity),
            precip=precip,
            hail=hail,
            lightning=lightning,
            cumulonimbus=cumulonimbus,
            attached_anvil=attached_anvil,
            detached_anvil=detached_anvil,
            debris_cloud=debris_cloud,
            tropical_storm=tropical_storm,
            cumulus_top=float(cumulus_top),
            cloud_thickness=float(cloud_thickness),
            use_live=use_live_donki,
        )
    except Exception as exc:
        st.error(f"Evaluation failed: {exc}")
        st.stop()

# ── Header ───────────────────────────────────────────────────────────────────
rec_colour = {"GO": "success", "CAUTION": "warning", "NO-GO": "error"}.get(report.recommendation, "info")
getattr(st, rec_colour)(f"**{report.recommendation_emoji} {report.recommendation}** — "
                         f"Estimated Delay Risk: **{report.delay_probability_pct}%** "
                         f"| Confidence: {report.confidence} "
                         f"| Site: {site_key} | Date: {mission_date}")

st.divider()

# ── Key Metrics Row ───────────────────────────────────────────────────────────
col_g, col_b, col_sw, col_h = st.columns(4)

with col_g:
    score_cls = {"GO": "score-go", "CAUTION": "score-caution", "NO-GO": "score-nogo"}.get(report.recommendation, "")
    st.markdown(f"""
    <div class="metric-card">
      <div class="big-score {score_cls}">{report.delay_probability_pct}%</div>
      <div>Overall Delay Risk</div>
      <div style="font-size:1.5rem">{report.recommendation_emoji} {report.recommendation}</div>
    </div>""", unsafe_allow_html=True)

wx_dim  = report.dimension_by_name("Weather")
sw_dim  = report.dimension_by_name("Space Weather")
hist_dim = report.dimension_by_name("Historical")

with col_b:
    icon = "🔴" if (wx_dim and wx_dim.level in ("HIGH", "EXTREME")) else ("🟡" if wx_dim and wx_dim.level == "MODERATE" else "🟢")
    st.metric("🌦️ Weather Risk", f"{int((wx_dim.score if wx_dim else 0)*100)}%",
              delta=wx_dim.level if wx_dim else "N/A")
with col_sw:
    sw_icon = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🔴", "EXTREME": "☢️"}.get(sw_dim.level if sw_dim else "LOW", "❓")
    st.metric("☀️ Space Weather Risk", f"{int((sw_dim.score if sw_dim else 0)*100)}%",
              delta=sw_dim.level if sw_dim else "N/A")
with col_h:
    st.metric("📚 Historical Scrub Rate",
              f"{int((hist_dim.score if hist_dim else 0)*100)}%",
              delta=hist_dim.level if hist_dim else "N/A")

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
c1, c2 = st.columns([1, 1.4])

with c1:
    st.plotly_chart(gauge_chart(report.overall_score, report.recommendation),
                    use_container_width=True)

with c2:
    st.plotly_chart(breakdown_bar(report.dimensions), use_container_width=True)

st.divider()

# ── LCC Rule Table ────────────────────────────────────────────────────────────
st.subheader("Launch Commit Criteria — NASA-STD-4010A + Eastern Range")
st.caption("Source: https://standards.nasa.gov/standard/NASA/NASA-STD-4010")
if report.lcc_result:
    rows = []
    for r in report.lcc_result.rules:
        if r.violated:
            status = "SCRUB" if r.severity == "SCRUB" else "CAUTION"
        else:
            status = "OK"
        rows.append({
            "Status": status,
            "Rule": r.name,
            "Std Ref": r.std_ref,
            "Measured": f"{r.measured_value:.1f}{r.unit}",
            "Limit": f"{r.limit_value:.1f}{r.unit}" if r.limit_value else "—",
            "Description": r.description,
            "Rationale": r.rationale,
        })
    lcc_df = pd.DataFrame(rows)
    # Color-code by status
    def _style_status(val):
        if val == "SCRUB":   return "background-color: #fee2e2; color: #991b1b; font-weight: bold"
        if val == "CAUTION": return "background-color: #fef9c3; color: #854d0e; font-weight: bold"
        return "background-color: #dcfce7; color: #166534"
    styled = lcc_df.style.applymap(_style_status, subset=["Status"])
    st.dataframe(styled, hide_index=True, use_container_width=True)

    # Summary counts
    n_scrub   = sum(1 for r in report.lcc_result.rules if r.severity == "SCRUB"   and r.violated)
    n_caution = sum(1 for r in report.lcc_result.rules if r.severity == "CAUTION" and r.violated)
    n_ok      = sum(1 for r in report.lcc_result.rules if not r.violated)
    st.caption(
        f"15 rules evaluated — "
        f"SCRUB: {n_scrub}  |  CAUTION: {n_caution}  |  OK: {n_ok}"
    )

# ── Space Weather Summary ─────────────────────────────────────────────────────
st.subheader("☀️ Space Weather Summary")
if report.space_weather:
    sw = report.space_weather
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Geomagnetic", sw.geomag_level, f"Kp={sw.kp_max:.1f}")
    c2.metric("Max Flare", sw.flare_class_max if sw.flare_class_max != "None" else "None")
    c3.metric("CME Events", sw.cme_count,
              "🛰️ Geoeffective" if sw.cme_geoeffective else "Not geoeffective")
    c4.metric("HSS Stream", "Active ⚠️" if sw.hss_active else "None")
    c5.metric("Space Wx Level", sw.risk_level)

    if sw.risk_factors:
        st.markdown("**Risk factors detected:**")
        for factor in sw.risk_factors:
            st.markdown(f"- {factor}")

    st.divider()
    st.plotly_chart(space_weather_timeline(), use_container_width=True)

# ── Key Risk Factors ──────────────────────────────────────────────────────────
if report.key_factors:
    st.subheader("⚠️ Key Risk Factors")
    for kf in report.key_factors:
        pill_class = "factor-pill" if report.recommendation == "NO-GO" else "factor-pill-warn"
        st.markdown(f'<span class="{pill_class}">{kf}</span>', unsafe_allow_html=True)
    st.markdown("")

# ── Historical Context ────────────────────────────────────────────────────────
if report.historical and report.historical.get("total_count", 0) > 0:
    st.subheader("📚 Historical Launch Context")
    hist = report.historical
    hc1, hc2, hc3 = st.columns(3)
    hc1.metric("Total Launches Analysed", hist.get("total_count", 0))
    hc2.metric("Historical Scrub Rate", f"{hist.get('scrub_rate', 0):.0%}")
    hc3.metric("Seasonal Modifier", f"{hist.get('seasonal_modifier', 0):+.0%}")
    if hist.get("notes"):
        st.caption(hist["notes"])

# ── LLM Advisory ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("🤖 AI Advisory Briefing")
with st.spinner("Generating advisory…"):
    advisory = generate_advisory(report, use_llm=use_llm)
st.markdown(advisory)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    f"Mission Readiness Advisor · IBM August Challenge · "
    f"Generated {report.generated_at} UTC · "
    f"Data: NASA DONKI, OpenWeatherMap, Launch Library 2, Historical Datasets"
)
