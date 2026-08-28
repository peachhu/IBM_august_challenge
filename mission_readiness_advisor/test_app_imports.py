"""
test_app_imports.py — verify all app.py imports and a sample evaluation work
Run: python test_app_imports.py
"""
import sys, os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PARENT = _HERE.parent
for _p in [str(_HERE), str(_PARENT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.chdir(str(_HERE))

print("cwd:", os.getcwd())

print("1. config...")
from config import LAUNCH_SITES, NASA_API_KEY, OWM_API_KEY
print("   sites:", list(LAUNCH_SITES.keys())[:2])

print("2. risk_engine...")
from core.risk_engine import evaluate_mission_readiness, MissionRiskReport, DimensionScore, _level, _recommendation
print("   OK")

print("3. lcc_rules...")
from core.lcc_rules import evaluate_lcc
print("   OK")

print("4. space_weather_risk...")
from core.space_weather_risk import evaluate_space_weather
print("   OK")

print("5. weather_client...")
from api_clients.weather_client import WeatherSnapshot, get_weather_for_site
print("   OK")

print("6. llm_advisor...")
from llm_advisor import generate_advisory
print("   OK")

print("")
print("Running full evaluation...")
wx = WeatherSnapshot(
    temperature_c=24, humidity_pct=65, wind_speed_ms=5,
    visibility_m=9999, weather_main="Clear", source="manual"
)
sw = evaluate_space_weather("2024-05-10")
site_key = "Kennedy Space Center (KSC), FL"
site_cfg = LAUNCH_SITES[site_key]
report = evaluate_mission_readiness(
    mission_date="2024-05-10",
    site_key=site_key,
    site_config=site_cfg,
    weather_snapshot=wx,
    space_weather_result=sw,
    use_live_donki=False,
)
print("  Recommendation:", report.recommendation)
print("  Delay risk:    ", str(report.delay_probability_pct) + "%")
advisory = generate_advisory(report, use_llm=False)
lines = advisory.split("\n")
print("  Advisory start:", lines[0])
print("")
print("ALL TESTS PASSED — app.py is ready to launch")
