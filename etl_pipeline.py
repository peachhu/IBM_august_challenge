"""
=============================================================================
NASA-STD-4010 Aligned Space-Weather ETL Pipeline (Fixed Version)
=============================================================================
"""

import os
import re
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# 0. PATHS (Fixed for Notebooks / Interactive Shells / Standalone Scripts)
# ---------------------------------------------------------------------------
try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    BASE_DIR = os.getcwd()

DATA_DIR = os.path.join(BASE_DIR, "Datasets")
OUTPUT_FILE = os.path.join(BASE_DIR, "ml_ready_dataset.csv")
SCHEMA_REPORT_FILE = os.path.join(BASE_DIR, "schema_mapping_matrix.csv")

# ---------------------------------------------------------------------------
# 1. HELPER FUNCTIONS (Fixed Data Type conversions)
# ---------------------------------------------------------------------------

def load_csv(filename, **kwargs):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        # Fallback if datasets are in the current root directory
        path = os.path.join(BASE_DIR, filename)
    return pd.read_csv(path, **kwargs)

def parse_timedelta_col(series):
    """Convert timedelta string or numeric seconds safely to total seconds."""
    def _convert(val):
        if pd.isna(val):
            return np.nan
        try:
            if str(val).replace('.', '', 1).isdigit():
                return float(val)
            td = pd.to_timedelta(val)
            return td.total_seconds()
        except Exception:
            return np.nan
    return series.apply(_convert)

def clean_star_values(series):
    """Replace '*' or invalid missing sentinels with NaN and cast to float safely."""
    return pd.to_numeric(series.astype(str).str.replace("*", "", regex=False), errors="coerce")

def xray_class_to_float(series):
    class_map = {"A": 1e-8, "B": 1e-7, "C": 1e-6, "M": 1e-5, "X": 1e-4}
    def _parse(v):
        if pd.isna(v) or str(v).strip() in ["*", "", "nan"]:
            return np.nan
        v = str(v).strip().upper()
        for k, mult in class_map.items():
            if v.startswith(k):
                try:
                    return mult * float(v[1:])
                except ValueError:
                    return mult
        return np.nan
    return series.apply(_parse)

# ---------------------------------------------------------------------------
# 2. INGESTION FUNCTIONS (With Safety Guards)
# ---------------------------------------------------------------------------

def ingest_solar_wind():
    print("  [1/7] Loading solar_wind.csv ...")
    df = load_csv("solar_wind.csv")
    df.columns = [c.strip() for c in df.columns]
    df["timedelta_s"] = parse_timedelta_col(df["timedelta"])
    
    df.rename(columns={
        "bx_gse": "bx_gse_nt", "by_gse": "by_gse_nt", "bz_gse": "bz_gse_nt",
        "theta_gse": "theta_gse_deg", "phi_gse": "phi_gse_deg",
        "bx_gsm": "bx_gsm_nt", "by_gsm": "by_gsm_nt", "bz_gsm": "bz_gsm_nt",
        "theta_gsm": "theta_gsm_deg", "phi_gsm": "phi_gsm_deg",
        "bt": "bt_total_nt", "density": "solar_wind_density_cm3",
        "speed": "velocity_m_s", "temperature": "solar_wind_temp_k",
        "source": "instrument_source",
    }, inplace=True)
    
    df.drop(columns=["timedelta"], inplace=True, errors="ignore")
    
    # Safe Numeric Conversion before filter
    df["velocity_m_s"] = pd.to_numeric(df["velocity_m_s"], errors="coerce")
    df = df[~(df["velocity_m_s"] < 0)]
    
    sensor_cols = ["bx_gse_nt","by_gse_nt","bz_gse_nt","bx_gsm_nt","by_gsm_nt",
                   "bz_gsm_nt","bt_total_nt","solar_wind_density_cm3",
                   "velocity_m_s","solar_wind_temp_k"]
    
    for col in sensor_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            
    df[sensor_cols] = df[sensor_cols].interpolate(method="linear", limit_direction="both")
    df["instrument_source"] = df["instrument_source"].fillna("UNKNOWN")
    print(f"     -> {df.shape[0]:,} rows, {df.shape[1]} cols")
    return df

def ingest_labels():
    print("  [2/7] Loading labels.csv ...")
    df = load_csv("labels.csv")
    df["timedelta_s"] = parse_timedelta_col(df["timedelta"])
    df.rename(columns={"dst": "dst_index_nt"}, inplace=True)
    df.drop(columns=["timedelta"], inplace=True, errors="ignore")
    df["dst_index_nt"] = pd.to_numeric(df["dst_index_nt"], errors="coerce")
    print(f"     -> {df.shape[0]:,} rows, {df.shape[1]} cols")
    return df

def ingest_satellite_pos():
    print("  [3/7] Loading satellite_pos.csv ...")
    df = load_csv("satellite_pos.csv")
    df["timedelta_s"] = parse_timedelta_col(df["timedelta"])
    df.rename(columns={
        "gse_x_ace": "gse_x_ace_km", "gse_y_ace": "gse_y_ace_km", "gse_z_ace": "gse_z_ace_km",
        "gse_x_dscovr": "gse_x_dscovr_km", "gse_y_dscovr": "gse_y_dscovr_km",
        "gse_z_dscovr": "gse_z_dscovr_km",
    }, inplace=True)
    df.drop(columns=["timedelta"], inplace=True, errors="ignore")
    for col in ["gse_x_ace_km", "gse_y_ace_km", "gse_z_ace_km", "gse_x_dscovr_km", "gse_y_dscovr_km", "gse_z_dscovr_km"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    print(f"     -> {df.shape[0]:,} rows, {df.shape[1]} cols")
    return df

def ingest_sunspots():
    print("  [4/7] Loading sunspots.csv ...")
    df = load_csv("sunspots.csv")
    df["timedelta_s"] = parse_timedelta_col(df["timedelta"])
    df.rename(columns={"smoothed_ssn": "smoothed_sunspot_number"}, inplace=True)
    df.drop(columns=["timedelta"], inplace=True, errors="ignore")
    df["smoothed_sunspot_number"] = pd.to_numeric(df["smoothed_sunspot_number"], errors="coerce")
    print(f"     -> {df.shape[0]:,} rows, {df.shape[1]} cols")
    return df

def ingest_daily_solar():
    print("  [5/7] Loading daily_solar_data.csv ...")
    df = load_csv("daily_solar_data.csv")
    df.columns = [c.strip() for c in df.columns]
    df.rename(columns={
        "Date": "timestamp_utc",
        "Radio Flux 10.7cm": "radio_flux_107_sfu",
        "Sunspot Number": "daily_sunspot_number",
        "Sunspot Area (10^6 Hemis.)": "sunspot_area_mhd",
        "New Regions": "new_active_regions",
        "Stanford Mean Solar Field (GOES15)": "stanford_mean_field_g",
        "Stanford Background X-Ray Flux": "xray_flux_class",
        "Flares: C": "flares_c_count",
        "Flares: M": "flares_m_count",
        "Flares: X": "flares_x_count",
    }, inplace=True)
    df.drop(columns=["Flares: S", "Flares: 1", "Flares: 2", "Flares: 3"], inplace=True, errors="ignore")
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], errors="coerce")
    df["stanford_mean_field_g"] = clean_star_values(df["stanford_mean_field_g"])
    df["xray_flux_numeric"] = xray_class_to_float(df["xray_flux_class"])
    for col in ["radio_flux_107_sfu", "daily_sunspot_number", "sunspot_area_mhd",
                "new_active_regions", "flares_c_count", "flares_m_count", "flares_x_count"]:
        if col in df.columns:
            df[col] = clean_star_values(df[col])
    print(f"     -> {df.shape[0]:,} rows, {df.shape[1]} cols")
    return df

def ingest_city_weather():
    print("  [6/7] Loading city_weather_dataset.csv ...")
    df = load_csv("city_weather_dataset.csv")
    df.columns = [c.strip() for c in df.columns]
    df.rename(columns={
        "city": "launch_pad_location",
        "temperature": "surface_temp_c",
        "humidity": "surface_humidity_pct",
        "pressure": "surface_pressure_hpa",
        "weather": "precipitation_type",
        "wind_speed": "surface_wind_speed_knots",
        "clouds": "cloud_cover_pct",
        "latitude": "launch_lat_deg",
        "longitude": "launch_lon_deg",
    }, inplace=True)
    df.drop(columns=["country"], inplace=True, errors="ignore")
    
    # Safe Numeric Casting before calculation
    for col in ["surface_temp_c", "surface_humidity_pct", "surface_pressure_hpa", "surface_wind_speed_knots", "cloud_cover_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            
    df["surface_wind_speed_knots"] = df["surface_wind_speed_knots"] * 1.94384
    df = df[~(df["surface_temp_c"] < -273.15)]
    print(f"     -> {df.shape[0]:,} rows, {df.shape[1]} cols")
    return df

# ---------------------------------------------------------------------------
# 3. PIPELINE ORCHESTRATION
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("  NASA-STD-4010 Space-Weather ETL Pipeline (Execution)")
    print("=" * 70)

    # Ingest Sources
    solar_wind  = ingest_solar_wind()
    labels      = ingest_labels()
    satellite   = ingest_satellite_pos()
    sunspots    = ingest_sunspots()
    daily_solar = ingest_daily_solar()
    city_wx     = ingest_city_weather()

    # Time-Series Merge Core
    print("\n[MERGE] Building time-series core...")
    for d in [solar_wind, labels, satellite, sunspots]:
        d["timedelta_s"] = d["timedelta_s"].round(0)

    core = solar_wind.merge(labels, on=["period", "timedelta_s"], how="left")
    core = core.merge(satellite, on=["period", "timedelta_s"], how="left")
    
    sunspots_daily = sunspots.groupby("period")["smoothed_sunspot_number"].mean().reset_index()
    core = core.merge(sunspots_daily, on="period", how="left")

    # Flag Anomalies Safely
    print("[ANOMALY] Flagging physical anomalies...")
    core["is_anomaly_flagged"] = 0
    core["anomaly_reason"] = ""

    if "velocity_m_s" in core.columns:
        mask = core["velocity_m_s"] > 1200
        core.loc[mask, "is_anomaly_flagged"] = 1
        core.loc[mask, "anomaly_reason"] += "Solar wind speed >1200 km/s; "

    if "dst_index_nt" in core.columns:
        mask = core["dst_index_nt"] < -100
        core.loc[mask, "is_anomaly_flagged"] = 1
        core.loc[mask, "anomaly_reason"] += "Dst < -100 nT; "

    # Enrich with Solar & Weather Summaries
    print("[ENRICH] Aggregating solar and weather features...")
    daily_solar["year_key"] = daily_solar["timestamp_utc"].dt.year
    solar_period = daily_solar.groupby("year_key").agg(
        radio_flux_107_sfu_mean=("radio_flux_107_sfu", "mean"),
        flares_x_count_sum=("flares_x_count", "sum")
    ).reset_index()

    period_year_map = {"train_a": 2016, "train_b": 2017, "train_c": 2018, "test_a": 2019, "test_b": 2020}
    core["year_key"] = core["period"].map(period_year_map).fillna(2016).astype(int)
    
    # Safe Merge on Exact Int Type
    solar_period["year_key"] = solar_period["year_key"].fillna(2016).astype(int)
    core = core.merge(solar_period, on="year_key", how="left")

    # Clean & Fill
    num_cols = core.select_dtypes(include=[np.number]).columns
    core[num_cols] = core[num_cols].ffill().fillna(0)

    # Save Output
    core.to_csv(OUTPUT_FILE, index=False)
    print(f"\n[OUTPUT] ML-ready dataset successfully saved to -> {OUTPUT_FILE}")
    print(f"  Shape: {core.shape[0]:,} rows x {core.shape[1]} columns")

if __name__ == "__main__":
    main()