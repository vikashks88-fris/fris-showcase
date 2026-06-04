from flask import Flask, Response, jsonify, send_file
import os
import json
import html
import requests
import glob
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CSV_FILE = os.path.join(DATA_DIR, "fris_latest.csv")
GEOJSON_FILE = os.path.join(DATA_DIR, "fris_latest.geojson")
MAP_FILE = os.path.join(DATA_DIR, "fris_latest_map.html")
# Genuine Carbon Engine output created by carbon_genuine.py
# Priority order:
# 1) fris_carbon_genuine.csv       -> new genuine FRIS carbon score
# 2) fris_carbon_opportunity_v2.csv -> older carbon opportunity engine
# 3) fris_carbon_opportunity.csv    -> old fallback
CARBON_GENUINE_FILE = os.path.join(DATA_DIR, "fris_carbon_genuine.csv")
CARBON_FILE = os.path.join(DATA_DIR, "fris_carbon_opportunity_v2.csv")
CARBON_FILE_OLD = os.path.join(DATA_DIR, "fris_carbon_opportunity.csv")

# Separate Plantation Engine output created by plantation_engine.py
# Priority order:
# 1) app data folder -> useful for Render/dashboard deployment
# 2) C:\cfris\output -> useful while running locally on Windows
PLANTATION_ENGINE_FILE = os.path.join(DATA_DIR, "fris_plantation_engine.csv")
PLANTATION_ENGINE_FILE_OUTPUT = os.path.join(r"C:\cfris\output", "fris_plantation_engine.csv")

def find_latest_map_file():
    """Return the newest FRIS Folium map file.
    Priority: app data folder, C:\\cfris\\output, then app root.
    This prevents the dashboard from showing an older rebuilt GeoJSON map.
    """
    patterns = [
        os.path.join(DATA_DIR, "fris_latest_map*.html"),
        os.path.join(r"C:\cfris\output", "fris_latest_map*.html"),
        os.path.join(BASE_DIR, "fris_latest_map*.html"),
    ]
    candidates = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))

    candidates = [f for f in candidates if os.path.isfile(f)]
    if not candidates:
        return MAP_FILE

    return max(candidates, key=os.path.getmtime)


IST = ZoneInfo("Asia/Kolkata")


# =============================
# TIME
# =============================

def ist_now():
    return datetime.now(IST)


def format_ist(dt):
    return dt.strftime("%d %B %Y, %I:%M:%S %p IST")


def get_file_update_time(file_path):
    if not os.path.exists(file_path):
        return "File not found"

    ts = os.path.getmtime(file_path)
    return format_ist(datetime.fromtimestamp(ts, IST))


def get_file_age_minutes(file_path):
    if not os.path.exists(file_path):
        return "N/A"

    modified = datetime.fromtimestamp(os.path.getmtime(file_path), IST)
    diff = ist_now() - modified
    minutes = int(diff.total_seconds() // 60)

    if minutes < 1:
        return "Updated just now"
    if minutes == 1:
        return "Updated 1 minute ago"

    return f"Updated {minutes} minutes ago"


def next_expected_run():
    now = ist_now()

    morning = now.replace(hour=9, minute=30, second=0, microsecond=0)
    evening = now.replace(hour=19, minute=30, second=0, microsecond=0)

    if now < morning:
        return format_ist(morning)

    if now < evening:
        return format_ist(evening)

    tomorrow = now + timedelta(days=1)
    return format_ist(tomorrow.replace(hour=9, minute=30, second=0, microsecond=0))


# =============================
# DATA HELPERS
# =============================

def read_csv():
    if not os.path.exists(CSV_FILE):
        return None

    try:
        df = pd.read_csv(CSV_FILE)
        df = df.loc[:, ~df.columns.duplicated()].copy()
        return df
    except Exception:
        return None


def read_carbon_csv():
    """Read separate FRIS Carbon output.

    Preferred:
    - fris_carbon_genuine.csv from carbon_genuine.py

    Fallback:
    - fris_carbon_opportunity_v2.csv
    - fris_carbon_opportunity.csv
    """
    path = carbon_file_path_used()

    if not os.path.exists(path):
        return None

    try:
        df = pd.read_csv(path)
        df = df.loc[:, ~df.columns.duplicated()].copy()
        return df
    except Exception:
        return None


def carbon_file_path_used():
    if os.path.exists(CARBON_GENUINE_FILE):
        return CARBON_GENUINE_FILE
    if os.path.exists(CARBON_FILE):
        return CARBON_FILE
    if os.path.exists(CARBON_FILE_OLD):
        return CARBON_FILE_OLD
    return CARBON_GENUINE_FILE


def plantation_file_path_used():
    if os.path.exists(PLANTATION_ENGINE_FILE):
        return PLANTATION_ENGINE_FILE
    if os.path.exists(PLANTATION_ENGINE_FILE_OUTPUT):
        return PLANTATION_ENGINE_FILE_OUTPUT
    return PLANTATION_ENGINE_FILE


def read_plantation_csv():
    """Read separate FRIS Plantation Engine output.

    This keeps the 30% restoration/plantation layer separate from the
    85% dense-forest ecological inference layer in fris_latest.csv.
    """
    path = plantation_file_path_used()

    if not os.path.exists(path):
        return None

    try:
        df = pd.read_csv(path)
        df = df.loc[:, ~df.columns.duplicated()].copy()
        return df
    except Exception:
        return None


def safe_float(value, default=None):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def safe_text(value, default="N/A"):
    try:
        if pd.isna(value):
            return default

        value = str(value).strip()
        return value if value else default

    except Exception:
        return default


def avg_col(df, col):
    if df is None or df.empty or col not in df.columns:
        return "N/A"

    value = pd.to_numeric(df[col], errors="coerce").mean()

    if pd.isna(value):
        return "N/A"

    return round(float(value), 3)


def sum_col(df, col):
    if df is None or df.empty or col not in df.columns:
        return "N/A"

    value = pd.to_numeric(df[col], errors="coerce").sum()

    if pd.isna(value):
        return "N/A"

    return value


def sum_first_available_col(df, columns):
    """Sum the first column that exists. Useful when engine column names evolve."""
    if df is None or df.empty:
        return "N/A"

    for col in columns:
        if col in df.columns:
            return sum_col(df, col)

    return "N/A"


def count_contains(df, columns, keyword):
    if df is None or df.empty:
        return 0

    total = 0

    for col in columns:
        if col in df.columns:
            total += df[col].astype(str).str.upper().str.contains(
                keyword.upper(),
                na=False
            ).sum()

    return int(total)


def format_number(value, decimals=1, suffix=""):
    try:
        value = float(value)
        return f"{value:,.{decimals}f}{suffix}"
    except Exception:
        return "N/A"


def format_carbon(value):
    try:
        value = float(value)
        return f"{value:,.0f} tons"
    except Exception:
        return "N/A"


def format_co2e(value):
    try:
        value = float(value)
        return f"{value:,.0f} tCO₂e"
    except Exception:
        return "N/A"


def carbon_status_counts(df):
    """Return clean carbon gain/loss/stable grid counts using current CSV columns.
    This uses the engine's carbon_change_status and does not treat tiny numerical noise as gain/loss.
    """
    if df is None or df.empty or "carbon_change_status" not in df.columns:
        return {"gain": 0, "loss": 0, "stable": 0, "unknown": 0}

    s = df["carbon_change_status"].astype(str).str.upper().fillna("")
    gain = int(s.str.contains("GAIN", na=False).sum())
    loss = int(s.str.contains("LOSS", na=False).sum())
    stable = int(s.str.contains("STABLE", na=False).sum())
    unknown = int(len(df) - gain - loss - stable)
    return {"gain": gain, "loss": loss, "stable": stable, "unknown": max(unknown, 0)}


def tree_confidence_counts(df):
    if df is None or df.empty or "tree_estimation_confidence" not in df.columns:
        return {"high": 0, "medium": 0, "low": 0}
    s = df["tree_estimation_confidence"].astype(str).str.upper().fillna("")
    return {
        "high": int(s.str.contains("HIGH", na=False).sum()),
        "medium": int(s.str.contains("MEDIUM", na=False).sum()),
        "low": int(s.str.contains("LOW", na=False).sum()),
    }


def sentinel1_support_counts(df):
    if df is None or df.empty or "sentinel1_structure_confidence" not in df.columns:
        return {"high": 0, "medium": 0, "low": 0, "none": 0}
    s = df["sentinel1_structure_confidence"].astype(str).str.upper().fillna("")
    return {
        "high": int(s.str.contains("HIGH_RADAR", na=False).sum()),
        "medium": int(s.str.contains("MEDIUM_RADAR", na=False).sum()),
        "low": int(s.str.contains("LOW_RADAR", na=False).sum()),
        "none": int(s.str.contains("NO_SENTINEL1|NO_RADAR", regex=True, na=False).sum()),
    }


def first_sum_text(df, columns, formatter=format_number, decimals=1, suffix=""):
    value = sum_first_available_col(df, columns)
    if formatter == format_number:
        return format_number(value, decimals, suffix)
    return formatter(value)


def get_first_value(df, columns, default=None):
    if df is None or df.empty:
        return default

    for col in columns:
        if col in df.columns:
            values = df[col].dropna()
            if len(values) > 0:
                return values.iloc[0]

    return default


# =============================
# PLANTATION / TREE ESTIMATION HELPERS
# =============================

def first_existing_col(df, columns):
    if df is None or df.empty:
        return None
    for col in columns:
        if col in df.columns:
            return col
    return None


def count_values_contains(df, columns, keywords):
    if df is None or df.empty:
        return 0

    if isinstance(keywords, str):
        keywords = [keywords]

    total_mask = None
    for col in columns:
        if col in df.columns:
            series = df[col].astype(str).str.upper()
            col_mask = False
            for keyword in keywords:
                col_mask = col_mask | series.str.contains(str(keyword).upper(), na=False)
            total_mask = col_mask if total_mask is None else (total_mask | col_mask)

    if total_mask is None:
        return 0
    return int(total_mask.sum())


def sum_tree_count(df):
    col = first_existing_col(df, ["estimated_tree_count", "approx_tree_count", "tree_count_estimate"])
    if df is None or df.empty or col is None:
        return "N/A"
    value = pd.to_numeric(df[col], errors="coerce").fillna(0).sum()
    return value


def plantation_counts(df):
    if df is None or df.empty:
        return {
            "possible_plantation": 0,
            "vegetation_recovery": 0,
            "canopy_recovery": 0,
            "canopy_decline": 0,
        }

    return {
        "possible_plantation": count_values_contains(df, ["plantation_signal_class"], ["POSSIBLE_NEW_PLANTATION", "REGENERATION"]),
        "vegetation_recovery": count_values_contains(df, ["plantation_signal_class"], ["VEGETATION_RECOVERY", "GREENING_SIGNAL"]),
        "canopy_recovery": count_values_contains(df, ["canopy_change_class"], ["STRONG_GREENING", "MODERATE_GREENING", "RECOVERY"]),
        "canopy_decline": count_values_contains(df, ["canopy_change_class", "plantation_signal_class"], ["DECLINE", "DECLINING"]),
    }


def plantation_rank(row):
    score = safe_float(row.get("plantation_signal_score"), 0) or 0
    tree_count = safe_float(row.get("estimated_tree_count"), 0) or 0
    signal = safe_text(row.get("plantation_signal_class"), "").upper()
    confidence = safe_text(row.get("plantation_detection_confidence"), "").upper()
    canopy = safe_text(row.get("canopy_change_class"), "").upper()

    rank = score

    if "POSSIBLE_NEW_PLANTATION" in signal or "REGENERATION" in signal:
        rank += 5000
    elif "VEGETATION_RECOVERY" in signal or "GREENING" in signal:
        rank += 2500
    elif "DECLINE" in signal:
        rank += 1800

    if "HIGH" in confidence:
        rank += 1000
    elif "MODERATE" in confidence:
        rank += 500

    if "STRONG_GREENING" in canopy:
        rank += 900
    elif "MODERATE_GREENING" in canopy:
        rank += 400
    elif "DECLINE" in canopy:
        rank += 700

    rank += min(tree_count / 1000, 500)
    return rank


def plantation_summary_text(df):
    if df is None or df.empty:
        return "No FRIS CSV data found for plantation and regeneration intelligence."

    counts = plantation_counts(df)
    if counts["possible_plantation"] > 0:
        return "FRIS has detected possible plantation or natural regeneration signals in selected grids. Treat this as satellite-assisted evidence and verify with field photos, plantation records, or high-resolution imagery."
    if counts["vegetation_recovery"] > 0 or counts["canopy_recovery"] > 0:
        return "FRIS has detected vegetation recovery or canopy greening signals in selected grids. Continue monitoring to confirm whether the signal is persistent or seasonal."
    if counts["canopy_decline"] > 0:
        return "FRIS has detected canopy decline signals in selected grids. Review ecological stress, moisture, fire, and field conditions."
    return "No clear plantation or regeneration signal is detected in the current FRIS run. Continue timestamped monitoring."


def build_plantation_table(df, limit=15):
    if df is None or df.empty:
        return "<div class='empty'>CSV not loaded.</div>"

    required_any = [
        "estimated_tree_count", "estimated_tree_density_class", "plantation_signal_class",
        "plantation_detection_confidence", "plantation_reason", "canopy_change_class"
    ]
    if not any(col in df.columns for col in required_any):
        return "<div class='empty'>Plantation/tree-estimation columns not found. Run the updated sks12 engine first.</div>"

    work = df.copy()
    work["_plantation_rank"] = work.apply(plantation_rank, axis=1)
    work = work.sort_values("_plantation_rank", ascending=False).head(limit)

    rows = ""
    for _, row in work.iterrows():
        grid_id = safe_text(row.get("grid_id"))
        tree_count = safe_float(row.get("estimated_tree_count"), None)
        tree_text = "N/A" if tree_count is None else f"{tree_count:,.0f}"
        density = safe_text(row.get("estimated_tree_density_class"), "N/A")
        signal = safe_text(row.get("plantation_signal_class"), "N/A")
        confidence = safe_text(row.get("plantation_detection_confidence"), "N/A")
        tree_confidence = safe_text(row.get("tree_estimation_confidence"), "N/A")
        score = safe_float(row.get("plantation_signal_score"), None)
        score_text = "N/A" if score is None else f"{score:.1f}"
        canopy = safe_text(row.get("canopy_change_class"), "N/A")
        reason = safe_text(row.get("plantation_reason", row.get("plantation_signal_note", "N/A")), "N/A")
        disclaimer = safe_text(row.get("tree_count_disclaimer"), "Satellite-assisted estimate only. Not exact tree counting.")
        maps = safe_text(row.get("google_maps_link"), "#")
        maps_link = maps if maps.startswith("http") else "#"

        rows += f"""
        <tr>
            <td><b>{html.escape(grid_id)}</b></td>
            <td>{tree_text}</td>
            <td>{html.escape(density)}</td>
            <td>{html.escape(signal)}</td>
            <td>{html.escape(confidence)}</td>
            <td>{html.escape(tree_confidence)}</td>
            <td>{score_text}</td>
            <td>{html.escape(canopy)}</td>
            <td>{html.escape(reason)}</td>
            <td>{html.escape(disclaimer)}</td>
            <td><a href=\"{html.escape(maps_link)}\" target=\"_blank\">Open</a></td>
        </tr>
        """

    return f"""
    <div class=\"table-wrap\">
        <table>
            <thead>
                <tr>
                    <th>Grid</th>
                    <th>Estimated Trees</th>
                    <th>Density Class</th>
                    <th>Plantation Signal</th>
                    <th>Plantation Confidence</th>
                    <th>Tree Confidence</th>
                    <th>Signal Score</th>
                    <th>Canopy Change</th>
                    <th>Reason</th>
                    <th>Disclaimer</th>
                    <th>Map</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """

# =============================
# SEPARATE PLANTATION ENGINE HELPERS
# =============================

def plantation_engine_counts(plant_df):
    defaults = {
        "high": 0,
        "restoration": 0,
        "assisted": 0,
        "protect": 0,
        "low": 0,
        "fire_check": 0,
        "not_priority": 0,
        "total": 0,
    }

    if plant_df is None or plant_df.empty or "plantation_suitability" not in plant_df.columns:
        return defaults

    s = plant_df["plantation_suitability"].astype(str).str.upper().fillna("")
    defaults["total"] = int(len(plant_df))
    defaults["high"] = int(s.str.contains("HIGH_PLANTATION_PRIORITY", na=False).sum())
    defaults["restoration"] = int(s.str.contains("RESTORATION_PLANTATION_GRID", na=False).sum())
    defaults["assisted"] = int(s.str.contains("ASSISTED_REGENERATION_GRID", na=False).sum())
    defaults["protect"] = int(s.str.contains("PROTECT_EXISTING_FOREST", na=False).sum())
    defaults["low"] = int(s.str.contains("LOW_PLANTATION_PRIORITY", na=False).sum())
    defaults["fire_check"] = int(s.str.contains("FIRE_RECOVERY_CHECK", na=False).sum())
    defaults["not_priority"] = int(s.str.contains("NOT_PLANTATION_PRIORITY", na=False).sum())
    return defaults


def plantation_engine_summary_text(plant_df):
    if plant_df is None or plant_df.empty:
        return "Separate Plantation Engine output not found. Run plantation_engine.py and place fris_plantation_engine.csv in the data folder or C:\\cfris\\output."

    counts = plantation_engine_counts(plant_df)
    return (
        "Separate Plantation Engine is active. It uses the 30% forest-mask FRIS output to classify grids for "
        "high-priority plantation, restoration plantation, assisted natural regeneration, low priority, fire recovery check, "
        "and existing forest protection. Dense-forest ecological inference remains separate and still uses the 85% forest logic. "
        f"File: {os.path.basename(plantation_file_path_used())}. Total plantation grids analysed: {counts['total']}."
    )


def plantation_engine_rank(row):
    score = safe_float(row.get("plantation_score"), 0) or 0
    label = safe_text(row.get("plantation_suitability"), "").upper()

    if "HIGH_PLANTATION_PRIORITY" in label:
        return 10000 + score
    if "RESTORATION_PLANTATION_GRID" in label:
        return 8000 + score
    if "ASSISTED_REGENERATION_GRID" in label:
        return 6000 + score
    if "FIRE_RECOVERY_CHECK" in label:
        return 5000 + score
    if "LOW_PLANTATION_PRIORITY" in label:
        return 3000 + score
    if "PROTECT_EXISTING_FOREST" in label:
        return 1000 + score
    return score


def build_plantation_engine_table(plant_df, limit=15):
    if plant_df is None or plant_df.empty:
        return "<div class='empty'>Plantation Engine CSV not loaded. Run plantation_engine.py first.</div>"

    if "plantation_suitability" not in plant_df.columns:
        return "<div class='empty'>plantation_suitability column not found. Use the new plantation_engine.py output.</div>"

    work = plant_df.copy()
    work = work.loc[:, ~work.columns.duplicated()].copy()
    work["_plantation_engine_rank"] = work.apply(plantation_engine_rank, axis=1)
    work = work.sort_values("_plantation_engine_rank", ascending=False).head(limit)

    rows = ""
    for _, row in work.iterrows():
        grid_id = safe_text(row.get("grid_id"), "N/A")
        label = safe_text(row.get("plantation_suitability"), "N/A")
        score = safe_float(row.get("plantation_score"), None)
        score_text = "N/A" if score is None else f"{score:.0f}"
        reason = safe_text(row.get("plantation_reason"), "N/A")
        forest_pct = safe_float(row.get("forest_pct"), None)
        forest_text = "N/A" if forest_pct is None else f"{forest_pct:.1f}%"
        health = safe_text(row.get("health_class"), "N/A")
        moisture = safe_text(row.get("moisture_class_calibrated"), "N/A")
        memory = safe_text(row.get("ecological_memory_class"), "N/A")
        hansen = safe_float(row.get("hansen_loss_pct"), None)
        hansen_text = "N/A" if hansen is None else f"{hansen:.2f}%"
        soil = safe_text(row.get("soil_moisture_retention_class"), "N/A")
        mining = safe_text(row.get("mining_pressure_class"), "N/A")
        maps = safe_text(row.get("google_maps_link"), "#")
        maps_link = maps if maps.startswith("http") else "#"

        rows += f"""
        <tr>
            <td><b>{html.escape(grid_id)}</b></td>
            <td>{html.escape(label)}</td>
            <td>{score_text}</td>
            <td>{forest_text}</td>
            <td>{html.escape(health)}</td>
            <td>{html.escape(moisture)}</td>
            <td>{html.escape(memory)}</td>
            <td>{hansen_text}</td>
            <td>{html.escape(soil)}</td>
            <td>{html.escape(mining)}</td>
            <td>{html.escape(reason)}</td>
            <td><a href=\"{html.escape(maps_link)}\" target=\"_blank\">Open</a></td>
        </tr>
        """

    return f"""
    <div class=\"table-wrap\">
        <table>
            <thead>
                <tr>
                    <th>Grid</th>
                    <th>Plantation Class</th>
                    <th>Score</th>
                    <th>Forest %</th>
                    <th>Health</th>
                    <th>Moisture</th>
                    <th>Ecological Memory</th>
                    <th>Hansen Loss</th>
                    <th>Soil Retention</th>
                    <th>Mining Pressure</th>
                    <th>Why selected?</th>
                    <th>Map</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


# =============================
# WEATHER
# =============================

def get_csv_weather(df):
    temperature = get_first_value(df, ["temperature_c", "temperature", "temp_c"], None)
    rainfall_now = get_first_value(df, ["rainfall_current_mm", "rainfall", "rain_mm"], None)
    rainfall_24h = get_first_value(df, ["rainfall_24h_mm"], None)

    # Engine usually writes rainfall_24h_mm. Use it as current rainfall display if no separate rainfall_current column exists.
    if rainfall_now is None and rainfall_24h is not None:
        rainfall_now = rainfall_24h
    wind = get_first_value(df, ["wind_speed_kmph", "wind_kmph", "wind_speed"], None)
    gust = get_first_value(df, ["wind_gust_kmph"], None)
    spread = get_first_value(df, ["weather_fire_spread_class"], "N/A")
    provider = get_first_value(df, ["weather_provider"], "CSV Weather")

    if temperature is not None and rainfall_now is not None and wind is not None:
        return {
            "source": safe_text(provider),
            "status": "CSV Weather",
            "temperature": format_number(temperature, 1, "°C"),
            "rainfall": format_number(rainfall_now, 1, " mm"),
            "rainfall_24h": format_number(rainfall_24h, 1, " mm") if rainfall_24h is not None else "N/A",
            "wind": format_number(wind, 1, " km/h"),
            "gust": format_number(gust, 1, " km/h") if gust is not None else "N/A",
            "spread": safe_text(spread)
        }

    return None


def get_live_weather_api():
    lat = 24.83
    lon = 87.22

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}"
        f"&longitude={lon}"
        "&current=temperature_2m,precipitation,rain,wind_speed_10m,wind_gusts_10m"
        "&timezone=Asia%2FKolkata"
        "&temperature_unit=celsius"
        "&wind_speed_unit=kmh"
        "&precipitation_unit=mm"
    )

    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        current = data.get("current", {})

        return {
            "source": "Open-Meteo Live API",
            "status": "Live API",
            "temperature": format_number(current.get("temperature_2m"), 1, "°C"),
            "rainfall": format_number(current.get("rain", current.get("precipitation")), 1, " mm"),
            "rainfall_24h": "N/A",
            "wind": format_number(current.get("wind_speed_10m"), 1, " km/h"),
            "gust": format_number(current.get("wind_gusts_10m"), 1, " km/h"),
            "spread": "Live weather only"
        }

    except Exception:
        return {
            "source": "Weather unavailable",
            "status": "API Error",
            "temperature": "N/A",
            "rainfall": "N/A",
            "rainfall_24h": "N/A",
            "wind": "N/A",
            "gust": "N/A",
            "spread": "N/A"
        }


def get_weather(df):
    csv_weather = get_csv_weather(df)

    if csv_weather:
        return csv_weather

    return get_live_weather_api()


# =============================
# GRID / GEOJSON HELPERS
# =============================

def find_lat_lon_columns(df):
    lat_cols = [
        "lat", "latitude", "center_lat", "grid_lat", "centroid_lat",
        "y", "LAT", "Latitude"
    ]

    lon_cols = [
        "lon", "lng", "longitude", "center_lon", "center_lng",
        "grid_lon", "grid_lng", "centroid_lon", "centroid_lng",
        "x", "LON", "Longitude"
    ]

    lat_col = None
    lon_col = None

    for col in lat_cols:
        if col in df.columns:
            lat_col = col
            break

    for col in lon_cols:
        if col in df.columns:
            lon_col = col
            break

    return lat_col, lon_col


def make_csv_grid_geojson(df):
    if df is None or df.empty:
        return {
            "type": "FeatureCollection",
            "features": []
        }

    lat_col, lon_col = find_lat_lon_columns(df)

    if lat_col is None or lon_col is None:
        return {
            "type": "FeatureCollection",
            "features": [],
            "error": "No latitude/longitude columns found in CSV"
        }

    features = []

    for _, row in df.iterrows():
        lat = safe_float(row.get(lat_col))
        lon = safe_float(row.get(lon_col))

        if lat is None or lon is None:
            continue

        d = 0.0045

        props = {}

        for col in df.columns:
            value = row.get(col)

            try:
                if pd.isna(value):
                    value = None
            except Exception:
                pass

            if isinstance(value, (int, float, str)) or value is None:
                props[col] = value
            else:
                props[col] = str(value)

        # Add ecological watch-list properties to map popup even if CSV does not contain them
        watch = classify_ecological_watch(row)
        props["ecological_watch_category"] = watch["category"]
        props["ecological_watch_level"] = watch["level"]
        props["ecological_watch_reason"] = watch["reason"]
        props["ecological_watch_action"] = watch["action"]

        # Add human-readable ecology inference extracted from app11c.py logic
        eco = make_ecology_inference(row)
        props["ecology_inference"] = eco["inference"]
        props["ecology_recommendation"] = eco["recommendation"]
        props["ecology_status"] = eco["status"]

        # Preserve plantation / tree-count intelligence for map popup if present in CSV
        for plant_col in [
            "estimated_tree_count", "estimated_tree_density_class", "tree_estimation_confidence",
            "plantation_signal_score", "plantation_signal_class", "plantation_detection_confidence",
            "plantation_reason", "plantation_signal_note", "canopy_change_class", "tree_count_disclaimer"
        ]:
            if plant_col in row.index and plant_col not in props:
                props[plant_col] = row.get(plant_col)

        feature = {
            "type": "Feature",
            "properties": props,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [lon - d, lat - d],
                    [lon + d, lat - d],
                    [lon + d, lat + d],
                    [lon - d, lat + d],
                    [lon - d, lat - d]
                ]]
            }
        }

        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
        "source": "CSV fallback grid builder",
        "lat_column_used": lat_col,
        "lon_column_used": lon_col
    }


# =============================
# ECOLOGICAL WATCH-LIST
# =============================

def classify_ecological_watch(row):
    # Prefer engine-generated watch columns when present.
    # IMPORTANT FIX:
    # The engine may write values like "Routine ecological monitoring" or
    # "LOW_ECOLOGICAL_WATCH" for normal grids. The old dashboard treated every
    # non-empty category as watch-list, so all 399 grids were counted.
    # This normalization keeps only real HIGH/MEDIUM verification/anomaly grids
    # in the Ecological Watch-List summary.
    existing_category = safe_text(row.get("ecological_watch_category", row.get("watch_category", "")), "")
    existing_level = safe_text(row.get("ecological_watch_level", row.get("watch_level", "")), "")
    existing_reason = safe_text(row.get("ecological_watch_reason", row.get("watch_reason", "")), "")
    existing_action = safe_text(row.get("ecological_watch_action", row.get("watch_action", "")), "")

    if existing_category and existing_category != "N/A":
        cat_upper = existing_category.upper()
        level_upper = existing_level.upper()

        # Treat routine/low monitoring rows as stable, not as watch-list rows.
        is_routine_category = (
            "ROUTINE" in cat_upper
            or "STABLE" in cat_upper
            or "NORMAL" in cat_upper
            or "NO WATCH" in cat_upper
        )
        is_low_or_routine_level = (
            "ROUTINE" in level_upper
            or "LOW" in level_upper
            or level_upper in ["", "N/A"]
        )
        is_real_watch_category = (
            "ANOMALY" in cat_upper
            or "VERIFICATION" in cat_upper
            or "STRESS" in cat_upper
            or "DISTURBANCE" in cat_upper
            or "FIRE" in cat_upper
            or "MINING" in cat_upper
            or "MOISTURE" in cat_upper
        )
        is_real_watch_level = (
            "HIGH" in level_upper
            or "MEDIUM" in level_upper
            or "MODERATE" in level_upper
            or "VERIFICATION" in level_upper
        )

        if is_routine_category and is_low_or_routine_level and not is_real_watch_category:
            return {
                "category": "Stable Forest Zone",
                "level": "LOW",
                "reason": "Routine ecological monitoring grid. No separate watch-list condition detected.",
                "action": "Routine monitoring."
            }

        if not is_real_watch_category and not is_real_watch_level:
            return {
                "category": "Stable Forest Zone",
                "level": "LOW",
                "reason": "No major ecological watch-list condition detected.",
                "action": "Routine monitoring."
            }

        readable_level = "HIGH" if "HIGH" in level_upper else "MEDIUM" if ("MEDIUM" in level_upper or "MODERATE" in level_upper) else "LOW"
        return {
            "category": existing_category,
            "level": readable_level,
            "reason": existing_reason if existing_reason and existing_reason != "N/A" else "Engine-generated ecological watch category.",
            "action": existing_action if existing_action and existing_action != "N/A" else "Follow FRIS patrol action and field verification guidance."
        }

    forest_pct = safe_float(row.get("forest_pct"), 0) or 0
    ndvi = safe_float(row.get("ndvi"), 0) or 0
    ndmi = safe_float(row.get("ndmi"), 0) or 0
    hansen_loss = safe_float(row.get("hansen_loss_pct"), 0) or 0
    fire_count = safe_float(row.get("fire_count"), 0) or 0

    priority = safe_text(row.get("final_priority"), "").upper()
    mining_class = safe_text(row.get("mining_pressure_class"), "NONE").upper()

    if fire_count > 0 or "FIRE" in priority or "CRITICAL" in priority:
        return {
            "category": "Fire Verification Alert",
            "level": "HIGH",
            "reason": "Active/recent fire or critical-priority signal is present.",
            "action": "Immediate or same-day field verification."
        }

    if forest_pct >= 85 and ndvi < 0.20:
        return {
            "category": "Ecological Anomaly Alert",
            "level": "HIGH",
            "reason": "Forest extent is high but NDVI is abnormally low.",
            "action": "Priority ecological field verification before any conclusion."
        }

    if hansen_loss >= 15 and forest_pct >= 85 and ndvi >= 0.40:
        return {
            "category": "Historical Disturbance Watch",
            "level": "MEDIUM",
            "reason": "Current forest appears stable, but historical forest-loss evidence is elevated.",
            "action": "Periodic ecological monitoring and disturbance verification."
        }

    if forest_pct >= 85 and ndvi < 0.40:
        return {
            "category": "Vegetation Stress Watch",
            "level": "MEDIUM",
            "reason": "Forest-dominant grid shows stressed vegetation signal.",
            "action": "Monitor in next runs and verify if stress continues."
        }

    if mining_class in ["HIGH", "VERY_HIGH"] and forest_pct >= 85:
        return {
            "category": "Mining Influence Watch",
            "level": "MEDIUM",
            "reason": "Grid is near mining influence zone; this does not prove illegal activity.",
            "action": "Routine patrol and long-term trend monitoring."
        }

    if ndmi < -0.10 and forest_pct >= 85:
        return {
            "category": "Moisture Stress Watch",
            "level": "MEDIUM",
            "reason": "Forest-dominant grid shows weak moisture signal.",
            "action": "Monitor moisture trend and rainfall context."
        }

    return {
        "category": "Stable Forest Zone",
        "level": "LOW",
        "reason": "No major ecological watch-list condition detected.",
        "action": "Routine monitoring."
    }


def watch_rank(row):
    watch = classify_ecological_watch(row)
    level = watch["level"]
    category = watch["category"]
    hansen_loss = safe_float(row.get("hansen_loss_pct"), 0) or 0
    ndvi = safe_float(row.get("ndvi"), 0) or 0
    risk = safe_float(row.get("final_risk_score"), 0) or 0

    rank = 0

    if level == "HIGH":
        rank += 5000
    elif level == "MEDIUM":
        rank += 2500

    if category == "Ecological Anomaly Alert":
        rank += 1200
    elif category == "Fire Verification Alert":
        rank += 1100
    elif category == "Historical Disturbance Watch":
        rank += 900
    elif category == "Vegetation Stress Watch":
        rank += 700
    elif category == "Mining Influence Watch":
        rank += 500

    rank += hansen_loss * 10
    rank += risk

    if ndvi < 0.20:
        rank += 300

    return rank


def build_watchlist_table(df, limit=15):
    if df is None or df.empty:
        return "<div class='empty'>CSV not loaded.</div>"

    work = df.copy()
    work["_watch_rank"] = work.apply(watch_rank, axis=1)
    work["_watch_category"] = work.apply(lambda r: classify_ecological_watch(r)["category"], axis=1)

    work = work[work["_watch_category"] != "Stable Forest Zone"]
    work = work.sort_values("_watch_rank", ascending=False).head(limit)

    if work.empty:
        return "<div class='empty'>No ecological watch-list grid found in current CSV.</div>"

    rows = ""

    for _, row in work.iterrows():
        watch = classify_ecological_watch(row)

        grid_id = safe_text(row.get("grid_id"))
        forest_pct = safe_float(row.get("forest_pct"))
        ndvi = safe_float(row.get("ndvi"))
        ndmi = safe_float(row.get("ndmi"))
        hansen_loss = safe_float(row.get("hansen_loss_pct"), 0) or 0
        mining = safe_text(row.get("mining_pressure_class"), "N/A")
        maps = safe_text(row.get("google_maps_link"), "#")

        forest_text = "N/A" if forest_pct is None else f"{forest_pct:.1f}%"
        ndvi_text = "N/A" if ndvi is None else f"{ndvi:.3f}"
        ndmi_text = "N/A" if ndmi is None else f"{ndmi:.3f}"
        maps_link = maps if maps.startswith("http") else "#"

        level_class = "watch-high" if watch["level"] == "HIGH" else "watch-medium"

        rows += f"""
        <tr>
            <td><b>{html.escape(grid_id)}</b></td>
            <td><span class="{level_class}">{html.escape(watch['level'])}</span></td>
            <td>{html.escape(watch['category'])}</td>
            <td>{forest_text}</td>
            <td>{ndvi_text}</td>
            <td>{ndmi_text}</td>
            <td>{hansen_loss:.2f}%</td>
            <td>{html.escape(mining)}</td>
            <td>{html.escape(watch['reason'])}</td>
            <td>{html.escape(watch['action'])}</td>
            <td><a href="{html.escape(maps_link)}" target="_blank">Open</a></td>
        </tr>
        """

    return f"""
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Grid</th>
                    <th>Level</th>
                    <th>Watch Category</th>
                    <th>Forest %</th>
                    <th>NDVI</th>
                    <th>NDMI</th>
                    <th>Hansen Loss</th>
                    <th>Mining</th>
                    <th>Why Listed?</th>
                    <th>Action</th>
                    <th>Map</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


def count_watchlist(df):
    if df is None or df.empty:
        return 0

    count = 0
    for _, row in df.iterrows():
        if classify_ecological_watch(row)["category"] != "Stable Forest Zone":
            count += 1

    return count


def make_ecology_inference(row):
    """Human-readable ecological inference. Prefer engine columns; fallback only if older CSV lacks them."""
    watch = classify_ecological_watch(row)

    engine_inference = safe_text(row.get("ecological_inference", row.get("ecology_inference", "")), "")
    engine_recommendation = safe_text(row.get("ecology_recommendation", row.get("patrol_action", "")), "")
    engine_status = safe_text(row.get("ecology_status", row.get("final_priority", "")), "")

    if engine_inference and engine_inference != "N/A":
        return {
            "status": engine_status if engine_status and engine_status != "N/A" else watch["category"],
            "category": watch["category"],
            "level": watch["level"],
            "inference": engine_inference,
            "recommendation": engine_recommendation if engine_recommendation and engine_recommendation != "N/A" else "Follow FRIS patrol action and field verification guidance.",
            "health": safe_text(row.get("health_class"), "N/A"),
            "moisture": safe_text(row.get("moisture_class_calibrated", row.get("moisture_class", "N/A"))),
            "forest_pct": safe_float(row.get("forest_pct"), 0) or 0,
            "ndvi": safe_float(row.get("ndvi"), 0) or 0,
            "ndmi": safe_float(row.get("ndmi"), 0) or 0,
            "hansen_loss": safe_float(row.get("hansen_loss_pct"), 0) or 0,
            "fire_count": safe_float(row.get("fire_count"), 0) or 0,
            "risk": safe_float(row.get("final_risk_score"), 0) or 0,
            "priority": safe_text(row.get("final_priority"), "LOW").upper(),
        }

    forest_pct = safe_float(row.get("forest_pct"), 0) or 0
    ndvi = safe_float(row.get("ndvi"), 0) or 0
    ndmi = safe_float(row.get("ndmi"), 0) or 0
    hansen_loss = safe_float(row.get("hansen_loss_pct"), 0) or 0
    fire_count = safe_float(row.get("fire_count"), 0) or 0
    risk = safe_float(row.get("final_risk_score"), 0) or 0

    priority = safe_text(row.get("final_priority"), "LOW").upper()
    health = safe_text(row.get("health_class"), "N/A")
    moisture = safe_text(row.get("moisture_class_calibrated", row.get("moisture_class", "N/A")))
    memory_inference = safe_text(row.get("ecological_memory_inference"), "")
    field_inference = safe_text(row.get("field_inference"), "")

    if watch["category"] == "Fire Verification Alert":
        status = "Urgent field verification"
        inference = "Fire or critical-priority signal is present. Treat this as an operational verification grid, not a final legal conclusion."
        recommendation = "Immediate or same-day patrol; check smoke, burn marks, human activity, and nearby vulnerable forest patches."
    elif watch["category"] == "Ecological Anomaly Alert":
        status = "High ecological anomaly"
        inference = "Forest percentage is high but NDVI is abnormally low. This can happen from real vegetation stress, cloud/shadow, dry season condition, grazing, or local disturbance."
        recommendation = "Verify on ground and compare next satellite run before making any enforcement conclusion."
    elif watch["category"] == "Historical Disturbance Watch":
        status = "Historical disturbance verification"
        inference = "Current vegetation appears stable, but historical loss evidence is elevated. This grid should be kept as a separate ecological memory/watch-list item."
        recommendation = "Keep under periodic monitoring; compare old imagery, recent NDVI/NDMI trend, and field photos."
    elif watch["category"] == "Vegetation Stress Watch":
        status = "Vegetation stress monitoring"
        inference = "Forest-dominant grid is showing weak vegetation health. It may be seasonal or moisture-related, but repeated signals can indicate degradation."
        recommendation = "Monitor next runs; field check if stress repeats or NDMI also falls."
    elif watch["category"] == "Mining Influence Watch":
        status = "Influence-zone monitoring"
        inference = "Grid is near a mining influence zone. This does not prove illegal mining, but it is useful for ecological trend monitoring."
        recommendation = "Use long-term trend evidence only; avoid accusation language."
    elif watch["category"] == "Moisture Stress Watch":
        status = "Dryness watch"
        inference = "Forest-dominant grid shows low moisture signal. Fire-spread or leaf-dryness risk can rise if wind and temperature also support it."
        recommendation = "Monitor moisture trend, rainfall, and wind before patrol escalation."
    else:
        status = "Stable / routine monitoring"
        inference = "No strong ecological anomaly is detected in this run. Routine monitoring is sufficient."
        recommendation = "Routine patrol; keep history record for future comparison."

    # Prefer existing engine text if CSV already contains a stronger field inference.
    if field_inference and field_inference != "N/A":
        inference = f"{inference} Existing FRIS field note: {field_inference}"

    if memory_inference and memory_inference != "N/A":
        inference = f"{inference} Memory note: {memory_inference}"

    return {
        "status": status,
        "category": watch["category"],
        "level": watch["level"],
        "inference": inference,
        "recommendation": recommendation,
        "health": health,
        "moisture": moisture,
        "forest_pct": forest_pct,
        "ndvi": ndvi,
        "ndmi": ndmi,
        "hansen_loss": hansen_loss,
        "fire_count": fire_count,
        "risk": risk,
        "priority": priority,
    }


def build_ecology_inference_panel(df, limit=6):
    if df is None or df.empty:
        return "<div class='empty'>CSV not loaded.</div>"

    work = df.copy()
    work["_watch_rank"] = work.apply(watch_rank, axis=1)
    work["_watch_category"] = work.apply(lambda r: classify_ecological_watch(r)["category"], axis=1)
    work = work[work["_watch_category"] != "Stable Forest Zone"]
    work = work.sort_values("_watch_rank", ascending=False).head(limit)

    if work.empty:
        return """
        <div class='watch-note'>
            <b>Ecology Inference:</b> Most grids are stable in the current run. Continue routine monitoring and keep the history layer active.
        </div>
        """

    cards = ""
    for _, row in work.iterrows():
        eco = make_ecology_inference(row)
        grid_id = safe_text(row.get("grid_id"), "Grid")
        maps = safe_text(row.get("google_maps_link"), "#")
        maps_link = maps if maps.startswith("http") else "#"

        level_class = "watch-high" if eco["level"] == "HIGH" else "watch-medium"

        cards += f"""
        <div class="eco-card">
            <div class="eco-head">
                <b>{html.escape(grid_id)}</b>
                <span class="{level_class}">{html.escape(eco['level'])}</span>
            </div>
            <div><b>Status:</b> {html.escape(eco['status'])}</div>
            <div><b>Category:</b> {html.escape(eco['category'])}</div>
            <div><b>Inference:</b> {html.escape(eco['inference'])}</div>
            <div><b>Recommendation:</b> {html.escape(eco['recommendation'])}</div>
            <div class="eco-metrics">
                Forest {eco['forest_pct']:.1f}% | NDVI {eco['ndvi']:.3f} | NDMI {eco['ndmi']:.3f} | Hansen loss {eco['hansen_loss']:.2f}%
            </div>
            <a href="{html.escape(maps_link)}" target="_blank">Open navigation</a>
        </div>
        """

    return cards


def ecological_summary_text(df):
    if df is None or df.empty:
        return "No FRIS CSV data found."

    watch_count = count_watchlist(df)
    fire_count = 0
    if "fire_count" in df.columns:
        fire_count = int(pd.to_numeric(df["fire_count"], errors="coerce").fillna(0).gt(0).sum())

    high_priority = 0
    if "final_priority" in df.columns:
        p = df["final_priority"].astype(str).str.upper()
        high_priority = int(p.isin(["HIGH", "CRITICAL", "FIRE_CHECK"]).sum())

    if fire_count > 0 or high_priority > 0:
        return "FRIS has detected elevated operational concern in selected grids. Priority patrol and ecological verification should focus on high-risk, fire-check, and anomaly grids before any legal or enforcement conclusion."

    if watch_count > 0:
        return "Most grids are operationally stable, but selected grids need ecological watch-list monitoring due to historical disturbance, weak vegetation/moisture signal, or influence-zone indicators."

    return "Most Godda, Jharkhand forest grids remain stable in the current run. No major active fire emergency or ecological anomaly is detected."


# =============================
# INTELLIGENCE TABLE
# =============================

def make_why_go(row):
    reasons = []

    grid_id = safe_text(row.get("grid_id"), "Grid")
    fire_detected = safe_text(row.get("fire_detected"), "").upper()
    fire_count = safe_float(row.get("fire_count"), 0) or 0
    priority = safe_text(row.get("final_priority"), "").upper()
    ndvi = safe_float(row.get("ndvi"))
    ndmi = safe_float(row.get("ndmi"))
    carbon_change = safe_float(row.get("carbon_change_ton"), 0) or 0

    if fire_detected in ["TRUE", "YES", "ACTIVE", "1"] or fire_count > 0:
        reasons.append("active fire or thermal signal needs verification")

    if "CRITICAL" in priority:
        reasons.append("grid is marked CRITICAL priority")
    elif "HIGH" in priority:
        reasons.append("grid is marked HIGH priority")

    if ndmi is not None:
        if ndmi < 0.05:
            reasons.append("low NDMI shows dry vegetation condition")
        elif ndmi < 0.15:
            reasons.append("NDMI indicates early drying stage")

    if ndvi is not None:
        if ndvi < 0.20:
            reasons.append("low NDVI indicates severe vegetation stress")
        elif ndvi < 0.35:
            reasons.append("NDVI indicates moderate vegetation stress")

    if carbon_change < 0:
        reasons.append("negative carbon change may indicate biomass decline")

    if not reasons:
        return f"{grid_id}: routine patrol only; no strong stress signal found."

    return f"{grid_id}: " + "; ".join(reasons[:4]) + "."


def make_action(row):
    fire_detected = safe_text(row.get("fire_detected"), "").upper()
    fire_count = safe_float(row.get("fire_count"), 0) or 0
    priority = safe_text(row.get("final_priority"), "").upper()
    ndmi = safe_float(row.get("ndmi"))
    ndvi = safe_float(row.get("ndvi"))

    if fire_detected in ["TRUE", "YES", "ACTIVE", "1"] or fire_count > 0:
        return "Immediate field verification"

    if "CRITICAL" in priority:
        return "Same-day patrol required"

    if "HIGH" in priority:
        return "Patrol within 24 hours"

    if ndmi is not None and ndvi is not None and ndmi < 0.10 and ndvi < 0.35:
        return "Moisture and vegetation stress check"

    if ndmi is not None and ndmi < 0.10:
        return "Monitor drying forest sector"

    return "Routine patrol"


def priority_rank(row):
    priority = safe_text(row.get("final_priority"), "").upper()
    fire_count = safe_float(row.get("fire_count"), 0) or 0
    fire_detected = safe_text(row.get("fire_detected"), "").upper()
    score = safe_float(row.get("final_risk_score"), 0) or 0

    rank = 0

    if "CRITICAL" in priority:
        rank += 5000
    elif "HIGH" in priority:
        rank += 3000
    elif "MEDIUM" in priority or "MODERATE" in priority:
        rank += 1000

    if fire_detected in ["TRUE", "YES", "ACTIVE", "1"] or fire_count > 0:
        rank += 2000

    rank += score

    return rank


def build_priority_table(df, limit=15):
    if df is None or df.empty:
        return "<div class='empty'>CSV not loaded.</div>"

    work = df.copy()
    work["_rank"] = work.apply(priority_rank, axis=1)
    work = work.sort_values("_rank", ascending=False).head(limit)

    rows = ""

    for _, row in work.iterrows():
        grid_id = safe_text(row.get("grid_id"))
        priority = safe_text(row.get("final_priority"))
        ndvi = safe_float(row.get("ndvi"))
        ndmi = safe_float(row.get("ndmi"))
        fire_count = safe_float(row.get("fire_count"), 0) or 0
        risk_score = safe_float(row.get("final_risk_score"), 0)
        maps = safe_text(row.get("google_maps_link"), "#")

        ndvi_text = "N/A" if ndvi is None else f"{ndvi:.3f}"
        ndmi_text = "N/A" if ndmi is None else f"{ndmi:.3f}"
        risk_text = "N/A" if risk_score is None else f"{risk_score:.1f}"
        maps_link = maps if maps.startswith("http") else "#"

        rows += f"""
        <tr>
            <td><b>{html.escape(grid_id)}</b></td>
            <td>{html.escape(priority)}</td>
            <td>{ndvi_text}</td>
            <td>{ndmi_text}</td>
            <td>{int(fire_count)}</td>
            <td>{risk_text}</td>
            <td>{html.escape(make_why_go(row))}</td>
            <td>{html.escape(make_action(row))}</td>
            <td><a href="{html.escape(maps_link)}" target="_blank">Open</a></td>
        </tr>
        """

    return f"""
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Grid</th>
                    <th>Priority</th>
                    <th>NDVI</th>
                    <th>NDMI</th>
                    <th>Fire</th>
                    <th>Risk</th>
                    <th>Why go there?</th>
                    <th>Action</th>
                    <th>Map</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """



# =============================
# CARBON OPPORTUNITY ENGINE HELPERS
# =============================

def carbon_class_column(carbon_df):
    return first_existing_col(carbon_df, [
        "genuine_carbon_class",
        "carbon_opportunity_class",
        "carbon_zone",
        "carbon_class",
    ])


def carbon_score_column(carbon_df):
    return first_existing_col(carbon_df, [
        "genuine_carbon_score",
        "carbon_opportunity_score",
        "carbon_score",
    ])


def carbon_rank_column(carbon_df):
    return first_existing_col(carbon_df, [
        "genuine_carbon_rank",
        "carbon_priority_rank",
        "carbon_rank",
    ])


def carbon_reason_column(carbon_df):
    return first_existing_col(carbon_df, [
        "genuine_carbon_reason",
        "carbon_reason",
        "carbon_scoring_reason",
        "reason",
    ])


def carbon_opportunity_counts(carbon_df):
    """Count classes from the genuine FRIS Carbon Engine or older fallback files."""
    defaults = {
        # New genuine classes
        "strong_long_term": 0,
        "moderate_opportunity": 0,
        "field_verification": 0,
        "risk_emerging": 0,
        "low_opportunity": 0,

        # Old dashboard-compatible keys
        "high_opportunity": 0,
        "stable_reserve": 0,
        "watch_zone": 0,
        "restoration_potential": 0,
        "risk_zone": 0,
        "verification_zone": 0,
        "loss_alert": 0,
        "verification_required": 0,
        "total_carbon_grids": 0,
    }

    if carbon_df is None or carbon_df.empty:
        return defaults

    defaults["total_carbon_grids"] = int(len(carbon_df))

    class_col = carbon_class_column(carbon_df)

    if class_col:
        s = carbon_df[class_col].astype(str).str.upper().fillna("")

        # Genuine classes from carbon_genuine.py
        defaults["strong_long_term"] = int(s.str.contains("STRONG_LONG_TERM_CARBON_OPPORTUNITY", na=False).sum())
        defaults["moderate_opportunity"] = int(s.str.contains("MODERATE_CARBON_OPPORTUNITY", na=False).sum())
        defaults["field_verification"] = int(s.str.contains("FIELD_VERIFICATION_REQUIRED", na=False).sum())
        defaults["risk_emerging"] = int(s.str.contains("CARBON_RISK_EMERGING", na=False).sum())
        defaults["low_opportunity"] = int(s.str.contains("LOW_CARBON_OPPORTUNITY", na=False).sum())

        # Older class names
        defaults["high_opportunity"] = int(s.str.contains("HIGH_CARBON_OPPORTUNITY", na=False).sum())
        defaults["stable_reserve"] = int(s.str.contains("CARBON_STABLE_RESERVE", na=False).sum())
        defaults["watch_zone"] = int(s.str.contains("CARBON_WATCH_ZONE", na=False).sum())
        defaults["restoration_potential"] = int(s.str.contains("RESTORATION_CARBON_POTENTIAL", na=False).sum())
        defaults["risk_zone"] = int(s.str.contains("CARBON_RISK_ZONE", na=False).sum())
        defaults["verification_zone"] = int(s.str.contains("CARBON_VERIFICATION_ZONE", na=False).sum())
        defaults["loss_alert"] = int(s.str.contains("CARBON_LOSS_ALERT", na=False).sum())

        # Map genuine classes into old cards so the dashboard still works
        if defaults["strong_long_term"] or defaults["moderate_opportunity"]:
            defaults["high_opportunity"] += defaults["moderate_opportunity"]
            defaults["stable_reserve"] += defaults["strong_long_term"]
            defaults["verification_zone"] += defaults["field_verification"]
            defaults["risk_zone"] += defaults["risk_emerging"]
            defaults["loss_alert"] += defaults["low_opportunity"]

    verify_col = first_existing_col(carbon_df, [
        "field_verification_required",
        "carbon_field_verification_required",
        "verification_required",
    ])

    if verify_col:
        v = carbon_df[verify_col].astype(str).str.upper().fillna("")
        defaults["verification_required"] = int(v.str.contains("YES|TRUE|REQUIRED", regex=True, na=False).sum())
    else:
        defaults["verification_required"] = (
            defaults["field_verification"]
            + defaults["risk_emerging"]
            + defaults["low_opportunity"]
            + defaults["risk_zone"]
            + defaults["verification_zone"]
            + defaults["loss_alert"]
        )

    return defaults


def carbon_summary_text(carbon_df):
    if carbon_df is None or carbon_df.empty:
        return (
            "Genuine Carbon Engine output not found. Run carbon_genuine.py and place "
            "fris_carbon_genuine.csv inside the data folder."
        )

    counts = carbon_opportunity_counts(carbon_df)
    file_name = os.path.basename(carbon_file_path_used())

    if "genuine_carbon_score" in carbon_df.columns:
        return (
            "Genuine FRIS Carbon Opportunity Engine is active. The score gives highest weight to forest persistence, "
            "Godda history trend, FRIS ecological condition, disturbance absence, fire absence, and moisture resilience. "
            "It avoids over-weighting one-day NDVI/NDMI and is planning-level MRV support only. "
            f"File: {file_name}. Total carbon grids analysed: {counts['total_carbon_grids']}."
        )

    return (
        "FRIS Carbon Opportunity Engine is active using an older carbon output file. It separates stable carbon reserve, "
        "recovery opportunity, watch, risk, verification, and loss-alert grids for planning-level MRV support. "
        f"File: {file_name}. Total carbon grids analysed: {counts['total_carbon_grids']}."
    )


def carbon_rank_value(row):
    # If genuine rank exists, rank 1 should sort highest
    rank = safe_float(row.get("genuine_carbon_rank"), None)
    if rank is not None:
        return -rank

    rank = safe_float(row.get("carbon_priority_rank"), None)
    if rank is not None:
        return -rank

    score = safe_float(row.get("genuine_carbon_score", row.get("carbon_opportunity_score", row.get("carbon_score", 0))), 0) or 0
    cls = safe_text(row.get("genuine_carbon_class", row.get("carbon_opportunity_class", row.get("carbon_zone", ""))), "").upper()

    bonus = 0

    # Genuine classes
    if "STRONG_LONG_TERM_CARBON_OPPORTUNITY" in cls:
        bonus = 10000
    elif "MODERATE_CARBON_OPPORTUNITY" in cls:
        bonus = 8500
    elif "FIELD_VERIFICATION_REQUIRED" in cls:
        bonus = 6000
    elif "CARBON_RISK_EMERGING" in cls:
        bonus = 3000
    elif "LOW_CARBON_OPPORTUNITY" in cls:
        bonus = 1000

    # Older classes
    elif "HIGH_CARBON_OPPORTUNITY" in cls:
        bonus = 10000
    elif "CARBON_RECOVERY_OPPORTUNITY" in cls:
        bonus = 8000
    elif "RESTORATION_CARBON_POTENTIAL" in cls:
        bonus = 7000
    elif "CARBON_STABLE_RESERVE" in cls:
        bonus = 6000
    elif "CARBON_WATCH_ZONE" in cls:
        bonus = 3000
    elif "CARBON_RISK_ZONE" in cls:
        bonus = 1000

    return bonus + score


def make_genuine_carbon_recommendation(carbon_class):
    cls = str(carbon_class).upper()

    if "STRONG_LONG_TERM" in cls:
        return "Protect as long-term carbon-stable forest. Continue routine monitoring and keep evidence history."
    if "MODERATE_CARBON_OPPORTUNITY" in cls:
        return "Good candidate for restoration/protection planning. Verify field condition before any claim."
    if "FIELD_VERIFICATION_REQUIRED" in cls:
        return "Do field verification first. Do not use as carbon opportunity claim without ground evidence."
    if "CARBON_RISK_EMERGING" in cls:
        return "Investigate stress drivers, fire history, disturbance, and local pressure before carbon planning."
    if "LOW_CARBON_OPPORTUNITY" in cls:
        return "Low current carbon opportunity. Treat as risk/restoration watch zone, not carbon claim area."

    return "Use as planning-level MRV support only. Field verification is required before any formal claim."


def build_carbon_table(carbon_df, limit=15):
    if carbon_df is None or carbon_df.empty:
        return "<div class='empty'>Carbon CSV not loaded. Run carbon_genuine.py first.</div>"

    score_col = carbon_score_column(carbon_df)
    class_col = carbon_class_column(carbon_df)

    if score_col is None or class_col is None:
        return "<div class='empty'>Carbon score/class columns not found. Run the updated carbon_genuine.py engine first.</div>"

    rank_col = carbon_rank_column(carbon_df)
    reason_col = carbon_reason_column(carbon_df)

    work = carbon_df.copy()
    work["_carbon_rank_sort"] = work.apply(carbon_rank_value, axis=1)
    work = work.sort_values("_carbon_rank_sort", ascending=False).head(limit)

    rows = ""
    for _, row in work.iterrows():
        grid_id = safe_text(row.get("grid_id", row.get("grid", "N/A")))

        score = safe_float(row.get(score_col), None)
        score_text = "N/A" if score is None else f"{score:.1f}"

        carbon_class = safe_text(row.get(class_col), "N/A")

        rank = safe_float(row.get(rank_col), None) if rank_col else None
        rank_text = "N/A" if rank is None else f"{rank:.0f}"

        recommendation = safe_text(
            row.get("carbon_recommendation", make_genuine_carbon_recommendation(carbon_class)),
            make_genuine_carbon_recommendation(carbon_class)
        )

        reason = safe_text(row.get(reason_col), "N/A") if reason_col else "N/A"

        forest_component = safe_float(row.get("forest_persistence_component"), None)
        history_component = safe_float(row.get("history_trend_component"), None)
        fris_component = safe_float(row.get("fris_condition_component"), None)
        disturbance_component = safe_float(row.get("disturbance_control_component"), None)
        fire_component = safe_float(row.get("fire_control_component"), None)
        moisture_component = safe_float(row.get("moisture_resilience_component"), None)

        def comp_text(v):
            return "N/A" if v is None else f"{v:.0f}"

        verification = safe_text(row.get("field_verification_required"), "")
        if not verification or verification == "N/A":
            verification = "YES" if any(x in carbon_class.upper() for x in ["VERIFICATION", "RISK", "LOW"]) else "AS NEEDED"

        maps = safe_text(row.get("google_maps_link"), "#")
        maps_link = maps if maps.startswith("http") else "#"

        rows += f"""
        <tr>
            <td><b>{html.escape(grid_id)}</b></td>
            <td>{score_text}</td>
            <td>{html.escape(carbon_class)}</td>
            <td>{rank_text}</td>
            <td>{comp_text(forest_component)}</td>
            <td>{comp_text(history_component)}</td>
            <td>{comp_text(fris_component)}</td>
            <td>{comp_text(disturbance_component)}</td>
            <td>{comp_text(fire_component)}</td>
            <td>{comp_text(moisture_component)}</td>
            <td>{html.escape(recommendation)}</td>
            <td>{html.escape(reason)}</td>
            <td>{html.escape(verification)}</td>
            <td><a href=\"{html.escape(maps_link)}\" target=\"_blank\">Open</a></td>
        </tr>
        """

    return f"""
    <div class=\"table-wrap\">
        <table>
            <thead>
                <tr>
                    <th>Grid</th>
                    <th>Genuine Score</th>
                    <th>Carbon Class</th>
                    <th>Rank</th>
                    <th>Forest</th>
                    <th>History</th>
                    <th>FRIS</th>
                    <th>Disturbance</th>
                    <th>Fire</th>
                    <th>Moisture</th>
                    <th>Recommendation</th>
                    <th>Reason</th>
                    <th>Verification</th>
                    <th>Map</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """

# =============================
# DASHBOARD
# =============================

@app.route("/")
def dashboard():
    df = read_csv()
    carbon_df = read_carbon_csv()
    plantation_df = read_plantation_csv()

    current_time = format_ist(ist_now())
    last_csv_update = get_file_update_time(CSV_FILE)
    csv_age = get_file_age_minutes(CSV_FILE)
    next_run = next_expected_run()

    csv_found = os.path.exists(CSV_FILE)
    geojson_found = os.path.exists(GEOJSON_FILE)
    carbon_found = carbon_df is not None and not carbon_df.empty
    carbon_data_update = get_file_update_time(carbon_file_path_used())
    latest_map_file = find_latest_map_file()
    old_map_found = os.path.exists(latest_map_file)

    total_grids = len(df) if df is not None else 0

    high_risk = count_contains(df, ["final_priority", "risk_class", "priority"], "HIGH")
    critical_risk = count_contains(df, ["final_priority", "risk_class", "priority"], "CRITICAL")
    # Correct active fire count: count rows with fire_count > 0 once, avoiding TRUE/YES/ACTIVE double counting.
    if df is not None and not df.empty and "fire_count" in df.columns:
        active_fire = int(pd.to_numeric(df["fire_count"], errors="coerce").fillna(0).gt(0).sum())
    else:
        active_fire = (
            count_contains(df, ["fire_detected", "active_fire", "fire_status"], "TRUE")
            + count_contains(df, ["fire_detected", "active_fire", "fire_status"], "YES")
            + count_contains(df, ["fire_detected", "active_fire", "fire_status"], "ACTIVE")
        )

    watchlist_count = count_watchlist(df)

    avg_ndvi = avg_col(df, "ndvi")
    avg_ndmi = avg_col(df, "ndmi")

    # Carbon dashboard: show existing carbon pool and movement separately.
    # ecosystem_carbon_total_ton = carbon pool in tons C.
    # ecosystem_carbon_co2e_total = same pool converted to CO2e.
    total_carbon_text = format_carbon(sum_first_available_col(df, [
        "ecosystem_carbon_total_ton",
        "estimated_ecosystem_carbon_ton"
    ]))

    total_carbon_co2e_text = format_co2e(sum_first_available_col(df, [
        "ecosystem_carbon_co2e_total",
        "estimated_ecosystem_carbon_co2e_total"
    ]))

    carbon_change_text = format_co2e(sum_first_available_col(df, [
        "carbon_change_co2e_ton",
        "carbon_change_from_365d"
    ]))

    preliminary_carbon_opportunity_text = format_co2e(sum_first_available_col(df, [
        "preliminary_carbon_opportunity_ton_co2e",
        "department_carbon_opportunity_gain_tco2e"
    ]))

    carbon_counts = carbon_status_counts(df)
    carbon_gain_grid_count = carbon_counts["gain"]
    carbon_loss_grid_count = carbon_counts["loss"]
    carbon_stable_grid_count = carbon_counts["stable"]

    carbon_opp_counts = carbon_opportunity_counts(carbon_df)
    high_carbon_opportunity_count = carbon_opp_counts["high_opportunity"]
    carbon_stable_reserve_count = carbon_opp_counts["stable_reserve"]
    carbon_watch_zone_count = carbon_opp_counts["watch_zone"]
    restoration_carbon_potential_count = carbon_opp_counts["restoration_potential"]
    carbon_risk_zone_count = carbon_opp_counts["risk_zone"]
    carbon_verification_zone_count = carbon_opp_counts["verification_zone"]
    carbon_loss_alert_count = carbon_opp_counts["loss_alert"]
    carbon_field_verification_required_count = carbon_opp_counts["verification_required"]
    carbon_total_grids_count = carbon_opp_counts["total_carbon_grids"]

    # Use true forest fraction area. Fallback to area_ha only for old CSVs.
    forest_area_value = sum_first_available_col(df, [
        "effective_forest_area_ha",
        "forest_area_ha",
        "area_ha"
    ])
    forest_area_text = format_number(forest_area_value, 1, " ha")

    weather = get_weather(df)
    priority_table = build_priority_table(df, limit=15)
    watchlist_table = build_watchlist_table(df, limit=15)
    ecology_inference_panel = build_ecology_inference_panel(df, limit=6)
    ecology_summary = ecological_summary_text(df)

    plant_counts = plantation_engine_counts(plantation_df)
    high_plantation_count = plant_counts["high"]
    restoration_plantation_count = plant_counts["restoration"]
    assisted_regeneration_count = plant_counts["assisted"]
    protect_existing_forest_count = plant_counts["protect"]
    low_plantation_count = plant_counts["low"]
    fire_recovery_check_count = plant_counts["fire_check"]
    total_tree_estimate_text = format_number(sum_tree_count(df), 0, " trees")
    tree_conf_counts = tree_confidence_counts(df)
    tree_high_conf_count = tree_conf_counts["high"]
    tree_medium_conf_count = tree_conf_counts["medium"]
    tree_low_conf_count = tree_conf_counts["low"]
    s1_counts = sentinel1_support_counts(df)
    sentinel1_high_count = s1_counts["high"]
    sentinel1_medium_count = s1_counts["medium"]
    plantation_table = build_plantation_engine_table(plantation_df, limit=15)
    plantation_summary = plantation_engine_summary_text(plantation_df)
    carbon_table = build_carbon_table(carbon_df, limit=15)
    carbon_opportunity_summary = carbon_summary_text(carbon_df)

    html_page = f"""
<!DOCTYPE html>
<html>
<head>
    <title>FRIS Godda, Jharkhand Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

    <style>
        * {{
            box-sizing: border-box;
            font-family: Arial, sans-serif;
        }}

        body {{
            margin: 0;
            background: #061307;
            color: white;
        }}

        .layout {{
            display: flex;
            min-height: 100vh;
        }}

        .sidebar {{
            width: 270px;
            padding: 25px;
            background: linear-gradient(180deg, #173f18, #071507);
            border-right: 1px solid rgba(255,255,255,0.15);
        }}

        .logo h1 {{
            color: #dfff00;
            font-size: 38px;
            margin: 0;
        }}

        .logo p {{
            color: #c6ff6b;
            font-size: 13px;
            margin: 4px 0 30px;
        }}

        .nav {{
            padding: 15px;
            margin-bottom: 13px;
            border-radius: 15px;
            background: rgba(255,255,255,0.12);
            font-weight: bold;
        }}

        .nav.active {{
            background: #dfff00;
            color: #102000;
        }}

        .nav a {{
            color: inherit;
            text-decoration: none;
            display: block;
        }}

        .side-card {{
            margin-top: 25px;
            padding: 18px;
            border-radius: 18px;
            background: rgba(255,255,255,0.12);
            border: 1px solid rgba(255,255,255,0.18);
            font-size: 14px;
            line-height: 1.7;
        }}

        .ok {{
            color: #dfff00;
            font-weight: bold;
        }}

        .bad {{
            color: #ff6b6b;
            font-weight: bold;
        }}

        .main {{
            flex: 1;
            padding: 25px;
        }}

        .topbar {{
            display: grid;
            grid-template-columns: repeat(3, 1fr) auto;
            gap: 15px;
            align-items: center;
            padding: 18px;
            border-radius: 22px;
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.18);
            margin-bottom: 22px;
        }}

        .time-box {{
            font-size: 14px;
            line-height: 1.4;
        }}

        .time-box b {{
            display: block;
            color: white;
        }}

        .time-box span {{
            color: #dfff00;
            font-weight: bold;
        }}

        .btn {{
            display: inline-block;
            background: #dfff00;
            color: #102000;
            padding: 12px 16px;
            border-radius: 14px;
            text-decoration: none;
            font-weight: bold;
            margin: 4px;
        }}

        .content {{
            display: grid;
            grid-template-columns: 1fr 340px;
            gap: 22px;
        }}

        .map-card,
        .card,
        .table-card {{
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.18);
            border-radius: 24px;
            padding: 18px;
        }}

        #fris-map {{
            width: 100%;
            height: 650px;
            border-radius: 18px;
            background: #1b5525;
            overflow: hidden;
        }}

        .right {{
            display: flex;
            flex-direction: column;
            gap: 15px;
        }}

        .card h3,
        .map-card h2,
        .table-card h2 {{
            margin-top: 0;
        }}

        .row {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 9px 0;
            border-bottom: 1px solid rgba(255,255,255,0.12);
            font-size: 14px;
        }}

        .value {{
            color: #dfff00;
            font-weight: bold;
            text-align: right;
        }}

        .table-card {{
            margin-top: 22px;
        }}

        .table-wrap {{
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}

        th {{
            background: rgba(223,255,0,0.18);
            color: #dfff00;
            text-align: left;
            padding: 10px;
            white-space: nowrap;
        }}

        td {{
            padding: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.12);
            vertical-align: top;
        }}

        td a {{
            color: #dfff00;
            font-weight: bold;
        }}

        .watch-high {{
            color: #ff6b6b;
            font-weight: bold;
        }}

        .watch-medium {{
            color: #ffd400;
            font-weight: bold;
        }}

        .watch-note {{
            background: rgba(223,255,0,0.10);
            border-left: 5px solid #dfff00;
            padding: 14px;
            border-radius: 14px;
            margin-bottom: 14px;
            line-height: 1.5;
            color: #eaffc4;
        }}

        .eco-card {{
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(223,255,0,0.20);
            border-left: 5px solid #a855f7;
            border-radius: 16px;
            padding: 14px;
            margin-bottom: 12px;
            line-height: 1.55;
            font-size: 14px;
        }}

        .eco-head {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 8px;
            color: #dfff00;
        }}

        .eco-metrics {{
            margin-top: 8px;
            color: #c6ff6b;
            font-size: 13px;
        }}

        .eco-card a {{
            color: #dfff00;
            font-weight: bold;
        }}

        .footer {{
            margin-top: 18px;
            font-size: 13px;
            color: #c5d6c5;
        }}

        @media(max-width: 1000px) {{
            .layout {{
                flex-direction: column;
            }}

            .sidebar {{
                width: 100%;
            }}

            .topbar {{
                grid-template-columns: 1fr;
            }}

            .content {{
                grid-template-columns: 1fr;
            }}

            #fris-map {{
                height: 520px;
            }}
        }}
    </style>
</head>

<body>
<div class="layout">

    <div class="sidebar">
        <div class="logo">
            <h1>FRIS</h1>
            <p>Forest Resilience Information System</p>
        </div>

        <div class="nav active">🏠 Dashboard</div>
        <div class="nav"><a href="#map-section">🗺️ Operational Map</a></div>
        <div class="nav"><a href="#priority-section">🧭 Priority Grids</a></div>
        <div class="nav"><a href="#ecology-inference-section">🌳 Ecology Inference</a></div>
        <div class="nav"><a href="#plantation-section">🌱 Plantation Intelligence</a></div>
        <div class="nav"><a href="#watchlist-section">🟣 Ecological Watch-List</a></div>
        <div class="nav">🔥 Fire Intelligence</div>
        <div class="nav">💧 Moisture Stress</div>
        <div class="nav">🌦️ Weather</div>
        <div class="nav"><a href="#carbon-opportunity-section">🌿 Carbon Opportunity</a></div>
        <div class="nav"><a href="/carbon" target="_blank">🌿 Carbon MRV</a></div>

        <div class="side-card">
            <b>Godda, Jharkhand FRIS Screening</b><br><br>

            CSV:
            <span class="{'ok' if csv_found else 'bad'}">{'Found' if csv_found else 'Missing'}</span><br>

            GeoJSON:
            <span class="{'ok' if geojson_found else 'bad'}">{'Found' if geojson_found else 'Missing'}</span><br>

            Carbon CSV:
            <span class="{'ok' if carbon_found else 'bad'}">{'Found' if carbon_found else 'Missing'}</span><br>

            Old Folium Map:
            <span class="{'ok' if old_map_found else 'bad'}">{'Found' if old_map_found else 'Not Required'}</span><br><br>

            <b>Analysed Area:</b><br>
            {forest_area_text}
        </div>
    </div>

    <div class="main">

        <div class="topbar">
            <div class="time-box">
                <b>Current Dashboard Time</b>
                <span>{current_time}</span>
            </div>

            <div class="time-box">
                <b>Last FRIS Data Update</b>
                <span>{last_csv_update}</span><br>
                <small>{csv_age}</small>
            </div>

            <div class="time-box">
                <b>Next Expected Run</b>
                <span>{next_run}</span>
            </div>

            <div>
                <a class="btn" href="/">Refresh</a>
                <a class="btn" href="/download/csv">Download CSV</a>
                <a class="btn" href="/download/map">Download Map</a>
                <a class="btn" href="/download/geojson">Download GeoJSON</a>
                <a class="btn" href="/watchlist" target="_blank">Watch-List</a>
                <a class="btn" href="/plantation" target="_blank">Plantation</a>
                <a class="btn" href="/carbon" target="_blank">Carbon</a>
                <a class="btn" href="/download/carbon">Download Carbon CSV</a>
                <a class="btn" href="/debug" target="_blank">Debug</a>
            </div>
        </div>

        <div class="content" id="map-section">

            <div class="map-card">
                <h2>FRIS Operational Map</h2>
                <iframe id="fris-map" src="/latest-map?ts={int(ist_now().timestamp())}" frameborder="0"></iframe>
            </div>

            <div class="right">

                <div class="card">
                    <h3>📊 Operational Summary</h3>
                    <div class="row"><span>Total Grids</span><span class="value">{total_grids}</span></div>
                    <div class="row"><span>High Risk</span><span class="value">{high_risk}</span></div>
                    <div class="row"><span>Critical Risk</span><span class="value">{critical_risk}</span></div>
                    <div class="row"><span>Active Fire</span><span class="value">{active_fire}</span></div>
                    <div class="row"><span>Ecological Watch-List</span><span class="value">{watchlist_count}</span></div>
                </div>

                <div class="card">
                    <h3>💧 Forest Condition</h3>
                    <div class="row"><span>Average NDVI</span><span class="value">{avg_ndvi}</span></div>
                    <div class="row"><span>Average NDMI</span><span class="value">{avg_ndmi}</span></div>
                </div>

                <div class="card">
                    <h3>🌱 Plantation / Restoration</h3>
                    <div class="row"><span>High Plantation Priority</span><span class="value">{high_plantation_count}</span></div>
                    <div class="row"><span>Restoration Plantation</span><span class="value">{restoration_plantation_count}</span></div>
                    <div class="row"><span>Assisted Regeneration</span><span class="value">{assisted_regeneration_count}</span></div>
                    <div class="row"><span>Protect Existing Forest</span><span class="value">{protect_existing_forest_count}</span></div>
                    <div class="row"><span>Low Plantation Priority</span><span class="value">{low_plantation_count}</span></div>
                    <div class="row"><span>Fire Recovery Check</span><span class="value">{fire_recovery_check_count}</span></div>
                    <div class="row"><span>Estimated Tree Count</span><span class="value">{total_tree_estimate_text}</span></div>
                    <div class="row"><span>High Tree Confidence</span><span class="value">{tree_high_conf_count}</span></div>
                    <div class="row"><span>Medium Tree Confidence</span><span class="value">{tree_medium_conf_count}</span></div>
                    <div class="row"><span>Low Tree Confidence</span><span class="value">{tree_low_conf_count}</span></div>
                </div>

                <div class="card">
                    <h3>🌳 Ecology Inference</h3>
                    <div class="watch-note">{html.escape(ecology_summary)}</div>
                </div>

                <div class="card">
                    <h3>🌦️ Weather</h3>
                    <div class="row"><span>Source</span><span class="value">{html.escape(weather['source'])}</span></div>
                    <div class="row"><span>Status</span><span class="value">{html.escape(weather['status'])}</span></div>
                    <div class="row"><span>Temperature</span><span class="value">{weather['temperature']}</span></div>
                    <div class="row"><span>Rainfall Now</span><span class="value">{weather['rainfall']}</span></div>
                    <div class="row"><span>Rainfall 24h</span><span class="value">{weather['rainfall_24h']}</span></div>
                    <div class="row"><span>Wind</span><span class="value">{weather['wind']}</span></div>
                    <div class="row"><span>Gust</span><span class="value">{weather['gust']}</span></div>
                    <div class="row"><span>Fire Spread</span><span class="value">{html.escape(weather['spread'])}</span></div>
                </div>

                <div class="card">
                    <h3>🌿 Carbon Pool & Movement</h3>
                    <div class="row"><span>Existing Carbon Pool</span><span class="value">{total_carbon_text}</span></div>
                    <div class="row"><span>Existing CO₂e Pool</span><span class="value">{total_carbon_co2e_text}</span></div>
                    <div class="row"><span>Net Change vs Locked Baseline</span><span class="value">{carbon_change_text}</span></div>
                    <div class="row"><span>Stable Grids</span><span class="value">{carbon_stable_grid_count}</span></div>
                    <div class="row"><span>Gain Grids</span><span class="value">{carbon_gain_grid_count}</span></div>
                    <div class="row"><span>Loss Grids</span><span class="value">{carbon_loss_grid_count}</span></div>
                    <div class="row"><span>Preliminary Opportunity</span><span class="value">{preliminary_carbon_opportunity_text}</span></div>
                    <div class="row"><span>Sentinel-1 High/Medium Support</span><span class="value">{sentinel1_high_count}/{sentinel1_medium_count}</span></div>
                    <div class="row"><span>Claim Status</span><span class="value">Planning Only</span></div>
                </div>

                <div class="card">
                    <h3>🌿 Carbon Opportunity Engine</h3>
                    <div class="row"><span>Carbon CSV</span><span class="value">{'Found' if carbon_found else 'Missing'}</span></div>
                    <div class="row"><span>Carbon Grids Analysed</span><span class="value">{carbon_total_grids_count}</span></div>
                    <div class="row"><span>High Carbon Opportunity</span><span class="value">{high_carbon_opportunity_count}</span></div>
                    <div class="row"><span>Carbon Stable Reserve</span><span class="value">{carbon_stable_reserve_count}</span></div>
                    <div class="row"><span>Carbon Watch Zone</span><span class="value">{carbon_watch_zone_count}</span></div>
                    <div class="row"><span>Restoration Carbon Potential</span><span class="value">{restoration_carbon_potential_count}</span></div>
                    <div class="row"><span>Carbon Risk Zone</span><span class="value">{carbon_risk_zone_count}</span></div>
                    <div class="row"><span>Carbon Verification Zone</span><span class="value">{carbon_verification_zone_count}</span></div>
                    <div class="row"><span>Carbon Loss Alert</span><span class="value">{carbon_loss_alert_count}</span></div>
                    <div class="row"><span>Field Verification Required</span><span class="value">{carbon_field_verification_required_count}</span></div>
                    <div class="row"><span>Carbon Data Update</span><span class="value">{carbon_data_update}</span></div>
                    <div class="row"><span>Claim Status</span><span class="value">Planning-level MRV Support</span></div>
                </div>

            </div>
        </div>

        <div class="table-card" id="ecology-inference-section">
            <h2>🌳 Ecology Inference — Engine Output</h2>
            <div class="watch-note">
                This panel converts FRIS values into human-readable ecological interpretation: why the grid is listed, what it may mean, and what field team should verify.
            </div>
            {ecology_inference_panel}
        </div>

        <div class="table-card" id="plantation-section">
            <h2>🌱 Plantation & Regeneration Intelligence</h2>
            <div class="watch-note">
                {html.escape(plantation_summary)} This is separate from the 85% dense-forest ecological inference/watch-list logic, which is kept active in the Ecology Inference and Watch-List sections.
            </div>
            {plantation_table}
        </div>

        <div class="table-card" id="carbon-opportunity-section">
            <h2>🌿 Carbon Opportunity Engine — Top Grids</h2>
            <div class="watch-note">
                {html.escape(carbon_opportunity_summary)}
            </div>
            {carbon_table}
        </div>

        <div class="table-card" id="priority-section">
            <h2>🧭 Priority Grid Intelligence — Why Go There?</h2>
            {priority_table}
        </div>

        <div class="table-card" id="watchlist-section">
            <h2>🟣 Ecological Watch-List — Separate Verification Layer</h2>

            <div class="watch-note">
                This section is informative only. It highlights grids needing ecological verification due to
                historical disturbance evidence, abnormal NDVI, vegetation stress, moisture stress, fire signal,
                or mining-influence indicators. It does not prove illegal activity or confirmed deforestation.
            </div>

            {watchlist_table}
        </div>

        <div class="footer">
            Map is loaded directly from the latest FRIS Folium HTML output, so the dashboard uses the same latest interpretation popup and color logic as the generated map file.
        </div>

    </div>
</div>

<!-- Latest FRIS Folium map is shown above by iframe. Old GeoJSON redraw script removed to avoid stale/old map interpretation. -->


</body>
</html>
"""

    return Response(html_page, mimetype="text/html")


# =============================
# ROUTES
# =============================

def fallback_leaflet_map_html():
    """Fallback map with CartoDB + Esri Satellite if fris_latest_map.html is missing.

    The preferred map is still the Folium HTML generated by the FRIS engine.
    This fallback guarantees the dashboard still shows a map with both basemaps.
    """
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>FRIS Fallback Map</title>
    <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" />
    <script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script>
    <style>
        html, body, #map { height: 100%; width: 100%; margin: 0; padding: 0; }
        .leaflet-popup-content { font-family: Arial, sans-serif; font-size: 12px; line-height: 1.45; }
        .popup-title { font-weight: bold; color: #14532d; font-size: 14px; margin-bottom: 6px; }
    </style>
</head>
<body>
<div id=\"map\"></div>
<script>
    const map = L.map('map').setView([24.83, 87.22], 10);

    const carto = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 20,
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
    }).addTo(map);

    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        attribution: 'Tiles &copy; Esri'
    });

    function colorFor(props) {
        const priority = String(props.final_priority || '').toUpperCase();
        const plant = String(props.plantation_suitability || '').toUpperCase();
        const carbon = String(props.genuine_carbon_class || props.carbon_officer_label || '').toUpperCase();

        if (priority.includes('FIRE') || priority.includes('CRITICAL') || carbon.includes('LOSS')) return '#dc2626';
        if (plant.includes('HIGH_PLANTATION')) return '#16a34a';
        if (plant.includes('RESTORATION')) return '#22c55e';
        if (plant.includes('ASSISTED')) return '#84cc16';
        if (priority.includes('HIGH')) return '#f97316';
        if (priority.includes('MEDIUM') || priority.includes('MODERATE')) return '#facc15';
        if (carbon.includes('RECOVERY')) return '#06b6d4';
        return '#65a30d';
    }

    function popupHtml(props) {
        const mapLink = props.google_maps_link || '#';
        return `
            <div class=\"popup-title\">${props.grid_id || 'FRIS Grid'}</div>
            <b>Priority:</b> ${props.final_priority || 'N/A'}<br>
            <b>Risk:</b> ${props.final_risk_score || 'N/A'}<br>
            <b>Forest:</b> ${props.forest_pct || 'N/A'}%<br>
            <b>Health:</b> ${props.health_class || 'N/A'}<br>
            <b>Moisture:</b> ${props.moisture_class_calibrated || 'N/A'}<br>
            <b>Memory:</b> ${props.ecological_memory_class || 'N/A'}<br>
            <b>Plantation:</b> ${props.plantation_suitability || 'N/A'}<br>
            <b>Carbon:</b> ${props.genuine_carbon_class || props.carbon_officer_label || 'N/A'}<br>
            <b>Action:</b> ${props.patrol_action || 'Routine monitoring'}<br>
            <a href=\"${mapLink}\" target=\"_blank\">Open in Google Maps</a>
        `;
    }

    fetch('/geojson')
        .then(r => r.json())
        .then(data => {
            const layer = L.geoJSON(data, {
                style: feature => ({
                    color: colorFor(feature.properties || {}),
                    weight: 1.2,
                    fillOpacity: 0.45
                }),
                onEachFeature: (feature, layer) => {
                    layer.bindPopup(popupHtml(feature.properties || {}));
                }
            }).addTo(map);

            try {
                const bounds = layer.getBounds();
                if (bounds.isValid()) map.fitBounds(bounds, { padding: [20, 20] });
            } catch (e) {}
        })
        .catch(() => {
            document.body.innerHTML = '<div style=\"padding:20px;font-family:Arial\">Map data not available.</div>';
        });

    L.control.layers({
        'CartoDB Positron': carto,
        'Esri Satellite': satellite
    }).addTo(map);
</script>
</body>
</html>
"""


@app.route("/latest-map")
def latest_map():
    latest_map_file = find_latest_map_file()

    # Preferred: show the original FRIS Folium HTML map generated by the engine.
    if os.path.exists(latest_map_file):
        response = send_file(latest_map_file, mimetype="text/html")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # Safe fallback: build a live Leaflet map from /geojson with CartoDB + Esri Satellite.
    return Response(fallback_leaflet_map_html(), mimetype="text/html")

@app.route("/geojson")
def geojson():
    # First try original GeoJSON
    if os.path.exists(GEOJSON_FILE):
        try:
            with open(GEOJSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            features = data.get("features", [])

            # Add ecological watch-list properties to existing GeoJSON features
            if len(features) > 0:
                for feature in features:
                    props = feature.get("properties", {})
                    watch = classify_ecological_watch(props)
                    props["ecological_watch_category"] = watch["category"]
                    props["ecological_watch_level"] = watch["level"]
                    props["ecological_watch_reason"] = watch["reason"]
                    props["ecological_watch_action"] = watch["action"]

                    eco = make_ecology_inference(props)
                    props["ecology_inference"] = eco["inference"]
                    props["ecology_recommendation"] = eco["recommendation"]
                    props["ecology_status"] = eco["status"]

                    feature["properties"] = props

                response = jsonify(data)
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                return response

        except Exception:
            pass

    # Fallback: build grid boxes from CSV lat/lon
    df = read_csv()
    data = make_csv_grid_geojson(df)

    response = jsonify(data)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/watchlist")
def watchlist():
    df = read_csv()
    watchlist_table = build_watchlist_table(df, limit=100)

    page = f"""
<!DOCTYPE html>
<html>
<head>
    <title>FRIS Ecological Watch-List</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{
            box-sizing: border-box;
            font-family: Arial, sans-serif;
        }}

        body {{
            margin: 0;
            background: #061307;
            color: white;
            padding: 24px;
        }}

        .box {{
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.18);
            border-radius: 24px;
            padding: 20px;
        }}

        h1 {{
            color: #dfff00;
        }}

        .note {{
            background: rgba(223,255,0,0.10);
            border-left: 5px solid #dfff00;
            padding: 14px;
            border-radius: 14px;
            margin-bottom: 18px;
            line-height: 1.5;
            color: #eaffc4;
        }}

        .btn {{
            display: inline-block;
            background: #dfff00;
            color: #102000;
            padding: 12px 16px;
            border-radius: 14px;
            text-decoration: none;
            font-weight: bold;
            margin-bottom: 18px;
        }}

        .table-wrap {{
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}

        th {{
            background: rgba(223,255,0,0.18);
            color: #dfff00;
            text-align: left;
            padding: 10px;
            white-space: nowrap;
        }}

        td {{
            padding: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.12);
            vertical-align: top;
        }}

        td a {{
            color: #dfff00;
            font-weight: bold;
        }}

        .watch-high {{
            color: #ff6b6b;
            font-weight: bold;
        }}

        .watch-medium {{
            color: #ffd400;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <a class="btn" href="/">← Back to Dashboard</a>

    <div class="box">
        <h1>🟣 FRIS Ecological Watch-List</h1>

        <div class="note">
            This is a separate informative layer. It identifies grids for ecological verification based on
            historical disturbance evidence, abnormal vegetation signal, moisture stress, fire signal,
            or mining influence. It does not prove illegal activity, confirmed deforestation, compensation liability,
            or carbon-credit eligibility.
        </div>

        {watchlist_table}
    </div>
</body>
</html>
"""

    return Response(page, mimetype="text/html")



@app.route("/plantation")
def plantation():
    df = read_csv()
    plantation_df = read_plantation_csv()
    plantation_table = build_plantation_engine_table(plantation_df, limit=100)
    summary = plantation_engine_summary_text(plantation_df)
    counts = plantation_engine_counts(plantation_df)
    total_tree_estimate_text = format_number(sum_tree_count(df), 0, " trees")

    page = f"""
<!DOCTYPE html>
<html>
<head>
    <title>FRIS Plantation & Regeneration Intelligence</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; font-family: Arial, sans-serif; }}
        body {{ margin: 0; background: #061307; color: white; padding: 24px; }}
        .box {{ background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.18); border-radius: 24px; padding: 20px; }}
        h1 {{ color: #dfff00; }}
        .note {{ background: rgba(223,255,0,0.10); border-left: 5px solid #dfff00; padding: 14px; border-radius: 14px; margin-bottom: 18px; line-height: 1.5; color: #eaffc4; }}
        .btn {{ display: inline-block; background: #dfff00; color: #102000; padding: 12px 16px; border-radius: 14px; text-decoration: none; font-weight: bold; margin-bottom: 18px; }}
        .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }}
        .card {{ background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.18); border-radius: 18px; padding: 14px; }}
        .card b {{ color: #dfff00; font-size: 22px; display: block; margin-top: 8px; }}
        .table-wrap {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ background: rgba(223,255,0,0.18); color: #dfff00; text-align: left; padding: 10px; white-space: nowrap; }}
        td {{ padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.12); vertical-align: top; }}
        td a {{ color: #dfff00; font-weight: bold; }}
        @media(max-width: 1000px) {{ .cards {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <a class="btn" href="/">← Back to Dashboard</a>
    <div class="box">
        <h1>🌱 FRIS Plantation & Regeneration Intelligence</h1>
        <div class="note">
            {html.escape(summary)} This page uses FRIS satellite-assisted indicators only. Estimated tree count is approximate, not exact tree counting. Plantation confirmation requires field verification, plantation records, GPS photos, or higher-resolution imagery.
        </div>
        <div class="cards">
            <div class="card">High Plantation Priority<b>{counts['high']}</b></div>
            <div class="card">Restoration Plantation<b>{counts['restoration']}</b></div>
            <div class="card">Assisted Regeneration<b>{counts['assisted']}</b></div>
            <div class="card">Protect Existing Forest<b>{counts['protect']}</b></div>
        </div>
        {plantation_table}
    </div>
</body>
</html>
"""
    return Response(page, mimetype="text/html")



@app.route("/carbon")
def carbon_summary():
    df = read_csv()
    carbon_df = read_carbon_csv()
    counts = carbon_status_counts(df)
    opp = carbon_opportunity_counts(carbon_df)
    carbon_table = build_carbon_table(carbon_df, limit=100)
    summary = carbon_summary_text(carbon_df)
    carbon_found = carbon_df is not None and not carbon_df.empty
    carbon_update = get_file_update_time(carbon_file_path_used())

    page = f"""
<!DOCTYPE html>
<html>
<head>
    <title>FRIS Carbon Opportunity Engine</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; font-family: Arial, sans-serif; }}
        body {{ margin: 0; background: #061307; color: white; padding: 24px; }}
        .box {{ background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.18); border-radius: 24px; padding: 20px; }}
        h1 {{ color: #dfff00; }}
        .note {{ background: rgba(223,255,0,0.10); border-left: 5px solid #dfff00; padding: 14px; border-radius: 14px; margin-bottom: 18px; line-height: 1.5; color: #eaffc4; }}
        .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }}
        .card {{ background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.18); border-radius: 18px; padding: 14px; }}
        .card b {{ color: #dfff00; font-size: 22px; display: block; margin-top: 8px; }}
        .btn {{ display: inline-block; background: #dfff00; color: #102000; padding: 12px 16px; border-radius: 14px; text-decoration: none; font-weight: bold; margin: 4px 4px 18px 0; }}
        .table-wrap {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ background: rgba(223,255,0,0.18); color: #dfff00; text-align: left; padding: 10px; white-space: nowrap; }}
        td {{ padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.12); vertical-align: top; }}
        td a {{ color: #dfff00; font-weight: bold; }}
        @media(max-width: 1000px) {{ .cards {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <a class="btn" href="/">← Back to Dashboard</a>
    <a class="btn" href="/download/carbon">Download Carbon CSV</a>
    <div class="box">
        <h1>🌿 FRIS Carbon Opportunity Engine</h1>
        <div class="note">
            {html.escape(summary)}<br><br>
            <b>Carbon CSV:</b> {'Found' if carbon_found else 'Missing'} | <b>Last update:</b> {carbon_update}<br>
            This is planning-level MRV support only. It is not certified carbon-credit issuance.
        </div>
        <div class="cards">
            <div class="card">High Carbon Opportunity<b>{opp['high_opportunity']}</b></div>
            <div class="card">Carbon Stable Reserve<b>{opp['stable_reserve']}</b></div>
            <div class="card">Carbon Watch Zone<b>{opp['watch_zone']}</b></div>
            <div class="card">Restoration Carbon Potential<b>{opp['restoration_potential']}</b></div>
            <div class="card">Carbon Risk Zone<b>{opp['risk_zone']}</b></div>
            <div class="card">Carbon Verification Zone<b>{opp['verification_zone']}</b></div>
            <div class="card">Carbon Loss Alert<b>{opp['loss_alert']}</b></div>
            <div class="card">Field Verification Required<b>{opp['verification_required']}</b></div>
            <div class="card">Existing Carbon Pool<b>{format_carbon(sum_first_available_col(df, ["ecosystem_carbon_total_ton", "estimated_ecosystem_carbon_ton"]))}</b></div>
            <div class="card">Existing CO₂e Pool<b>{format_co2e(sum_first_available_col(df, ["ecosystem_carbon_co2e_total", "estimated_ecosystem_carbon_co2e_total"]))}</b></div>
            <div class="card">Stable / Gain / Loss Grids<b>{counts['stable']} / {counts['gain']} / {counts['loss']}</b></div>
            <div class="card">Claim Status<b>Planning Only</b></div>
        </div>
        <h2>Top Carbon Opportunity / Priority Grids</h2>
        {carbon_table}
    </div>
</body>
</html>
"""
    return Response(page, mimetype="text/html")


@app.route("/download/carbon")
def download_carbon():
    path = carbon_file_path_used()
    if not os.path.exists(path):
        return Response(
            "Carbon CSV not found. Run carbon_genuine.py and place fris_carbon_genuine.csv inside the data folder.",
            status=404,
            mimetype="text/plain"
        )

    return send_file(
        path,
        mimetype="text/csv",
        as_attachment=True,
        download_name=os.path.basename(path),
        max_age=0
    )


@app.route("/download/csv")
def download_csv():
    if not os.path.exists(CSV_FILE):
        return Response("FRIS CSV file not found inside data/fris_latest.csv", status=404, mimetype="text/plain")

    return send_file(
        CSV_FILE,
        mimetype="text/csv",
        as_attachment=True,
        download_name="fris_latest.csv",
        max_age=0
    )


@app.route("/download/geojson")
def download_geojson():
    if os.path.exists(GEOJSON_FILE):
        return send_file(
            GEOJSON_FILE,
            mimetype="application/geo+json",
            as_attachment=True,
            download_name="fris_latest.geojson",
            max_age=0
        )

    df = read_csv()
    data = make_csv_grid_geojson(df)

    response = Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        mimetype="application/geo+json"
    )
    response.headers["Content-Disposition"] = "attachment; filename=fris_latest_generated.geojson"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/download/map")
def download_map():
    latest_map_file = find_latest_map_file()
    if not os.path.exists(latest_map_file):
        return Response(
            "FRIS map file not found. Put fris_latest_map.html inside data folder or C:\\cfris\\output.",
            status=404,
            mimetype="text/plain"
        )

    return send_file(
        latest_map_file,
        mimetype="text/html",
        as_attachment=True,
        download_name="fris_latest_map.html",
        max_age=0
    )

@app.route("/health")
def health():
    df = read_csv()
    lat_col, lon_col = (None, None)

    if df is not None:
        lat_col, lon_col = find_lat_lon_columns(df)

    return jsonify({
        "status": "running",
        "server_time_ist": format_ist(ist_now()),
        "csv_found": os.path.exists(CSV_FILE),
        "geojson_found": os.path.exists(GEOJSON_FILE),
        "carbon_csv_found": read_carbon_csv() is not None,
        "carbon_file_used": carbon_file_path_used(),
        "plantation_csv_found": read_plantation_csv() is not None,
        "plantation_file_used": plantation_file_path_used(),
        "carbon_opportunity_counts": carbon_opportunity_counts(read_carbon_csv()),
        "old_folium_map_found": os.path.exists(MAP_FILE),
        "csv_last_update": get_file_update_time(CSV_FILE),
        "csv_age": get_file_age_minutes(CSV_FILE),
        "next_expected_run": next_expected_run(),
        "total_grids": len(df) if df is not None else 0,
        "ecological_watchlist_count": count_watchlist(df),
        "plantation_counts": plantation_counts(df),
        "tree_confidence_counts": tree_confidence_counts(df),
        "sentinel1_support_counts": sentinel1_support_counts(df),
        "carbon_status_counts": carbon_status_counts(df),
        "estimated_tree_count_total": sum_tree_count(df),
        "plantation_summary": plantation_summary_text(df),
        "ecology_summary": ecological_summary_text(df),
        "csv_lat_column_found": lat_col,
        "csv_lon_column_found": lon_col
    })


@app.route("/debug")
def debug():
    df = read_csv()
    weather = get_weather(df)
    lat_col, lon_col = (None, None)

    columns = []

    if df is not None:
        columns = list(df.columns)
        lat_col, lon_col = find_lat_lon_columns(df)

    return jsonify({
        "server_time_ist": format_ist(ist_now()),
        "csv_found": os.path.exists(CSV_FILE),
        "geojson_found": os.path.exists(GEOJSON_FILE),
        "carbon_csv_found": read_carbon_csv() is not None,
        "carbon_file_used": carbon_file_path_used(),
        "carbon_opportunity_counts": carbon_opportunity_counts(read_carbon_csv()),
        "old_folium_map_found": os.path.exists(MAP_FILE),
        "csv_last_update": get_file_update_time(CSV_FILE),
        "csv_age": get_file_age_minutes(CSV_FILE),
        "next_expected_run": next_expected_run(),
        "total_grids": len(df) if df is not None else 0,
        "ecological_watchlist_count": count_watchlist(df),
        "plantation_counts": plantation_engine_counts(read_plantation_csv()),
        "estimated_tree_count_total": sum_tree_count(df),
        "plantation_summary": plantation_engine_summary_text(read_plantation_csv()),
        "ecology_summary": ecological_summary_text(df),
        "csv_columns": columns,
        "csv_lat_column_found": lat_col,
        "csv_lon_column_found": lon_col,
        "weather": weather,
        "base_dir": BASE_DIR,
        "data_dir": DATA_DIR,
        "csv_file": CSV_FILE,
        "geojson_file": GEOJSON_FILE
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)