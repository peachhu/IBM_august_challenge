"""
config.py — Central configuration for Mission Readiness Advisor
Load API keys from .env file (or environment variables) using python-dotenv.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Locate project root (the folder that contains this file) ────────────────
BASE_DIR = Path(__file__).resolve().parent
DATASETS_DIR = BASE_DIR.parent / "Datasets"

# ── Load .env from project root ─────────────────────────────────────────────
load_dotenv(BASE_DIR / ".env")

# ── API Keys ─────────────────────────────────────────────────────────────────
NASA_API_KEY: str = os.getenv("NASA_API_KEY", "DEMO_KEY")          # api.nasa.gov
OWM_API_KEY: str = os.getenv("OWM_API_KEY", "")                    # openweathermap.org
WATSONX_API_KEY: str = os.getenv("WATSONX_API_KEY", "")            # watsonx.ai
WATSONX_PROJECT_ID: str = os.getenv("WATSONX_PROJECT_ID", "")      # watsonx project
WATSONX_URL: str = os.getenv(
    "WATSONX_URL", "https://us-south.ml.cloud.ibm.com"
)

# ── Launch Sites ─────────────────────────────────────────────────────────────
LAUNCH_SITES: dict = {
    "Kennedy Space Center (KSC), FL": {
        "lat": 28.5721, "lon": -80.6480,
        "ll2_name": "Kennedy Space Center",
        "timezone": "US/Eastern",
    },
    "Vandenberg SFB, CA": {
        "lat": 34.7420, "lon": -120.5724,
        "ll2_name": "Vandenberg Space Force Base",
        "timezone": "US/Pacific",
    },
    "Cape Canaveral SFS, FL": {
        "lat": 28.4889, "lon": -80.5778,
        "ll2_name": "Cape Canaveral",
        "timezone": "US/Eastern",
    },
    "Baikonur Cosmodrome, KZ": {
        "lat": 45.9200, "lon": 63.3420,
        "ll2_name": "Baikonur Cosmodrome",
        "timezone": "Asia/Almaty",
    },
    "Jiuquan, China": {
        "lat": 40.9583, "lon": 100.2982,
        "ll2_name": "Jiuquan Satellite Launch Center",
        "timezone": "Asia/Shanghai",
    },
}

# ── Risk Weights (must sum to 1.0) ────────────────────────────────────────────
RISK_WEIGHTS: dict = {
    "weather": 0.45,       # Surface weather vs. LCC rules — biggest factor
    "space_weather": 0.35, # Solar/geomagnetic conditions
    "historical": 0.20,    # Past scrub frequency at this site / season
}

# ── Space Weather Thresholds ─────────────────────────────────────────────────
KP_THRESHOLDS: dict = {"moderate": 4, "severe": 6, "extreme": 8}
FLARE_RISK_MAP: dict = {"X": 1.0, "M": 0.55, "C": 0.15, "B": 0.03, "A": 0.0}
CME_SPEED_RISK: dict = {"Extreme": 1.0, "Fast": 0.65, "Normal": 0.2, "Slow": 0.05}

# ── Dataset paths (used by offline/historical analysis) ──────────────────────
DATASETS: dict = {
    "solar_flares":       DATASETS_DIR / "solar_flares.csv",
    "geomagnetic_storms": DATASETS_DIR / "geomagnetic_storms.csv",
    "cme_events":         DATASETS_DIR / "cme_events_2year.csv",
    "daily_solar":        DATASETS_DIR / "daily_solar_data.csv",
    "daily_geomagnetic":  DATASETS_DIR / "daily_geomagnetic_data.csv",
    "high_speed_streams": DATASETS_DIR / "high_speed_streams.csv",
    "space_weather_unified": DATASETS_DIR / "space_weather_unified.csv",
    "city_weather":       DATASETS_DIR / "city_weather_dataset.csv",
}
