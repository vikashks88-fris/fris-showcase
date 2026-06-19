# FRIS DASHBOARD V36 - visible All Grid Info panel + compact map popup
# Render/local ready. Put app.py with fris_latest.csv, fris_latest.geojson and fris_latest_map.html
# in the project root, data/, output/, or set FRIS_DATA_DIR.

from flask import Flask, Response, jsonify, send_file, request
import os
import json
import math
import html
import gc
import traceback
import pandas as pd
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def env_int(name, default, low=None, high=None):
    try:
        value = int(os.environ.get(name, default))
    except Exception:
        value = int(default)
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


MAX_TABLE_ROWS = env_int("MAX_TABLE_ROWS", 20, low=5, high=100)
MAX_WATCH_ROWS = env_int("MAX_WATCH_ROWS", 40, low=10, high=200)
MAX_GRID_INFO_ROWS = env_int("MAX_GRID_INFO_ROWS", 50, low=20, high=200)


def _data_dirs():
    dirs = []
    env_dir = os.environ.get("FRIS_DATA_DIR")
    if env_dir:
        dirs.append(env_dir)
    dirs.extend([
        os.path.join(BASE_DIR, "data"),
        os.path.join(BASE_DIR, "output"),
        BASE_DIR,
        r"C:\cfris\output",
    ])
    clean = []
    for d in dirs:
        if d and d not in clean:
            clean.append(d)
    return clean


def _find_file(filename):
    for folder in _data_dirs():
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            return path
    return os.path.join(_data_dirs()[0], filename)


DATA_DIR = _data_dirs()[0]
CSV_FILE = _find_file("fris_latest.csv")
GEOJSON_FILE = _find_file("fris_latest.geojson")
MAP_FILE = _find_file("fris_latest_map.html")

_CSV_CACHE = {"path": None, "mtime": None, "df": None, "error": None}

# Keep this list broad so the dashboard gets useful fields without loading very heavy
# audit columns. Full raw CSV still remains available through Download CSV.
IMPORTANT_COLUMNS = [
    # identity / location
    "grid_id", "lat", "lon", "lng", "latitude", "longitude", "center_lat", "center_lon", "center_lng",
    "grid_lat", "grid_lon", "grid_lng", "centroid_lat", "centroid_lon", "centroid_lng", "x", "y",
    "google_maps_link", "navigation_link",

    # area / vegetation / moisture
    "forest_pct", "effective_forest_area_ha", "forest_area_ha", "area_ha",
    "ndvi", "ndmi", "health_class", "health_score", "moisture_class", "moisture_class_calibrated",
    "rain_adjusted_ndmi_for_moisture", "moisture_reference_source", "ndvi_30d_trend", "ndmi_30d_trend",
    "ndvi_change_from_365d", "ndmi_change_from_365d",

    # priority / operation
    "final_priority", "risk_class", "priority", "final_risk_score", "risk_score", "patrol_priority",
    "operational_attention_label", "operational_attention_class", "operational_attention_reason",
    "field_verification_required", "patrol_action", "recommended_action", "officer_action", "why_go",

    # fire
    "fire_count", "recent_fire_count", "fire_alert_count", "firms_count", "fire_detected", "active_fire",
    "fire_status", "fire_frp_max", "firms_frp_max", "fire_intensity_class", "fire_age_hours",
    "fire_age_days", "distance_to_fire_km", "latest_fire_date", "latest_fire_time", "fire_sources",

    # disturbance / terrain / soil
    "hansen_treecover2000_pct", "hansen_loss_pct", "hansen_loss_year", "forest_pct_change_from_365d",
    "mining_pressure_class", "elevation_m", "slope_deg", "terrain_class",
    "soil_type", "soil_moisture_retention_class", "soil_drying_speed", "soil_supported_ecological_stability",
    "nbss_ph_risk", "nbss_boron_risk", "nbss_texture_risk", "ph_class", "b_class", "texture_class",

    # watch-list / ecology inference
    "ecological_watch_category", "watch_category", "ecological_watch_level", "watch_level",
    "ecological_watch_reason", "watch_reason", "ecological_watch_action", "watch_action",
    "ecological_inference", "ecology_inference", "ecology_recommendation", "ecology_status", "field_inference",
    "ecological_verification_reason_hindi",

    # carbon / MRV
    "agb_ton_per_ha", "gedi_agbd_ton_per_ha", "gedi_biomass_confidence", "carbon_estimation_method",
    "ecosystem_carbon_total_ton", "estimated_ecosystem_carbon_ton", "ecosystem_carbon_co2e_total",
    "biomass_carbon_total_ton", "carbon_change_ton", "carbon_change_co2e_ton", "carbon_change_from_365d",
    "carbon_change_status", "raw_positive_co2e_change_ton", "carbon_gain_allowed", "carbon_grid_lock_status",
    "carbon_grid_lock_reason", "carbon_opportunity_confidence_factor", "preliminary_carbon_opportunity_ton_co2e",
    "mrv_confidence", "carbon_credit_claim_status",

    # memory / trees / plantation
    "history_days_available_365d", "ecological_memory_class", "ecological_memory_score",
    "estimated_tree_count", "estimated_tree_density_class", "tree_estimation_confidence",
    "plantation_signal_class", "plantation_signal_score", "plantation_detection_confidence", "canopy_change_class",

    # weather
    "weather_status", "temperature_c", "temperature", "temp_c", "rainfall_current_mm", "rainfall", "rain_mm",
    "rainfall_24h_mm", "wind_speed_kmph", "wind_kmph", "wind_speed", "wind_gust_kmph",
    "weather_fire_spread_class", "weather_provider", "weather_validation_level", "era5_rain_sum_30d_mm",
    "era5_temp_mean_30d_c", "era5_temp_anomaly_c", "imd_validation_status",
]


# ----------------------------- basic helpers -----------------------------

def ist_now():
    return datetime.now(IST)


def format_ist(dt):
    try:
        return dt.strftime("%d %B %Y, %I:%M:%S %p IST")
    except Exception:
        return str(dt)


def get_file_update_time(path):
    if not os.path.exists(path):
        return "File not found"
    return format_ist(datetime.fromtimestamp(os.path.getmtime(path), IST))


def get_file_age_minutes(path):
    if not os.path.exists(path):
        return "N/A"
    minutes = int((ist_now() - datetime.fromtimestamp(os.path.getmtime(path), IST)).total_seconds() // 60)
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
    return format_ist((now + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0))


def json_safe_value(value):
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return value


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
        text = str(value).strip()
        return text if text else default
    except Exception:
        return default


def e(value):
    return html.escape(safe_text(value, ""))


def format_number(value, decimals=1, suffix=""):
    try:
        if value is None or pd.isna(value):
            return "N/A"
        return f"{float(value):,.{decimals}f}{suffix}"
    except Exception:
        return "N/A"


def format_carbon(value):
    try:
        if value is None or pd.isna(value):
            return "N/A"
        return f"{float(value):,.0f} tons"
    except Exception:
        return "N/A"


def is_truthy(value):
    text_value = safe_text(value, "").strip().upper()
    return text_value in {"TRUE", "YES", "Y", "1", "ACTIVE", "DETECTED", "REQUIRED"}


# ----------------------------- CSV loading -----------------------------

def existing_usecols(path):
    try:
        header = pd.read_csv(path, nrows=0)
        original_cols = header.columns.tolist()
        wanted = set(IMPORTANT_COLUMNS)
        usecols = [c for c in original_cols if str(c).strip() in wanted]
        return usecols or None
    except Exception:
        return None


def read_csv_light():
    """Read the FRIS CSV safely with cache and useful columns only."""
    if not os.path.exists(CSV_FILE):
        _CSV_CACHE["error"] = f"CSV not found: {CSV_FILE}"
        return None
    try:
        mtime = os.path.getmtime(CSV_FILE)
        if (
            _CSV_CACHE.get("path") == CSV_FILE
            and _CSV_CACHE.get("mtime") == mtime
            and _CSV_CACHE.get("df") is not None
        ):
            return _CSV_CACHE["df"].copy(deep=False)

        usecols = existing_usecols(CSV_FILE)
        if usecols:
            df = pd.read_csv(CSV_FILE, usecols=usecols, low_memory=False)
        else:
            df = pd.read_csv(CSV_FILE, low_memory=False)

        df.columns = [str(c).strip() for c in df.columns]
        _CSV_CACHE.update({"path": CSV_FILE, "mtime": mtime, "df": df, "error": None})
        return df.copy(deep=False)
    except Exception as exc:
        _CSV_CACHE["error"] = str(exc)
        print("CSV load error:", exc)
        traceback.print_exc()
        return None


def get_first_value(df, columns, default=None):
    if df is None or df.empty:
        return default
    for col in columns:
        if col in df.columns:
            values = df[col].dropna()
            if len(values) > 0:
                return values.iloc[0]
    return default


def avg_col(df, col):
    if df is None or df.empty or col not in df.columns:
        return "N/A"
    value = pd.to_numeric(df[col], errors="coerce").mean()
    return "N/A" if pd.isna(value) else round(float(value), 3)


def sum_first_available_numeric(df, columns):
    if df is None or df.empty:
        return None
    for col in columns:
        if col in df.columns:
            value = pd.to_numeric(df[col], errors="coerce").sum()
            if not pd.isna(value):
                return float(value)
    return None


def count_contains(df, columns, keyword):
    if df is None or df.empty:
        return 0
    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.upper().str.contains(keyword.upper(), na=False, regex=False)
    return int(mask.sum())


def value_counts_html(df, col, limit=4):
    if df is None or df.empty or col not in df.columns:
        return "N/A"
    counts = df[col].fillna("N/A").astype(str).value_counts().head(limit)
    return ", ".join(f"{html.escape(str(k))}: {int(v)}" for k, v in counts.items())


def find_lat_lon_columns(df):
    if df is None:
        return None, None
    lat_cols = ["lat", "latitude", "center_lat", "grid_lat", "centroid_lat", "y", "LAT", "Latitude"]
    lon_cols = ["lon", "lng", "longitude", "center_lon", "center_lng", "grid_lon", "grid_lng", "centroid_lon", "centroid_lng", "x", "LON", "Longitude"]
    lat_col = next((c for c in lat_cols if c in df.columns), None)
    lon_col = next((c for c in lon_cols if c in df.columns), None)
    return lat_col, lon_col


def estimate_area_ha(df):
    value = sum_first_available_numeric(df, ["effective_forest_area_ha", "forest_area_ha", "area_ha"])
    if value is not None and value > 0:
        return value
    return float(len(df) * 100) if df is not None else None


# ----------------------------- fire logic -----------------------------

def _positive_fire_status(value):
    text_value = safe_text(value, "").strip().upper().replace("-", "_").replace(" ", "_")
    if not text_value or text_value in {"N/A", "NONE", "FALSE", "0", "NO", "NO_FIRE", "NO_ACTIVE_FIRE", "NOT_DETECTED"}:
        return False
    if text_value.startswith("NO_") or "NO_FIRE" in text_value or "NO_ACTIVE" in text_value:
        return False
    active_terms = {
        "ACTIVE", "DETECTED", "FIRE_DETECTED", "ACTIVE_FIRE", "RECENT_FIRE",
        "FIRMS_DETECTED", "THERMAL_DETECTED", "THERMAL_ANOMALY", "CONFIRMED",
    }
    return text_value in active_terms


def _positive_fire_risk_text(value):
    text_value = safe_text(value, "").strip().upper().replace("-", "_").replace(" ", "_")
    if not text_value or text_value in {"N/A", "NONE", "FALSE", "0", "NO", "NO_FIRE", "NO_ACTIVE_FIRE", "NOT_DETECTED"}:
        return False
    if text_value.startswith("NO_") or "NO_FIRE" in text_value or "NO_ACTIVE" in text_value:
        return False
    risk_terms = [
        "FIRE_RISK", "FIRE_CHECK", "FIRE_WATCH", "FIRE_ALERT", "FIRE_INTELLIGENCE",
        "FIRE_PRONE", "BURN_RISK", "THERMAL_RISK", "DRY_FIRE", "SPREAD",
    ]
    if any(term in text_value for term in risk_terms):
        return True
    return "FIRE" in text_value


def row_has_fire(row):
    for col in ["fire_count", "recent_fire_count", "fire_alert_count", "firms_count"]:
        if (safe_float(row.get(col), 0) or 0) > 0:
            return True
    if is_truthy(row.get("fire_detected")) or is_truthy(row.get("active_fire")):
        return True
    if _positive_fire_status(row.get("fire_status")):
        return True
    for col in ["fire_frp_max", "firms_frp_max"]:
        if (safe_float(row.get(col), 0) or 0) > 0:
            return True
    return False


def row_has_fire_risk(row):
    if row_has_fire(row):
        return True
    for col in [
        "final_priority", "risk_class", "priority", "operational_attention_label",
        "operational_attention_class", "fire_status", "fire_intensity_class",
        "weather_fire_spread_class", "patrol_action", "recommended_action",
    ]:
        if _positive_fire_risk_text(row.get(col)):
            return True
    return False


def fire_display(row):
    frp = safe_float(row.get("fire_frp_max"))
    if frp is None:
        frp = safe_float(row.get("firms_frp_max"))

    count = None
    for col in ["fire_count", "recent_fire_count", "fire_alert_count", "firms_count"]:
        count = safe_float(row.get(col))
        if count is not None and count > 0:
            break

    intensity = safe_text(row.get("fire_intensity_class"), "")
    if row_has_fire(row):
        if frp is not None and frp > 0:
            return f"Active/recent thermal signal / FRP {frp:.2f}"
        if count is not None and count > 0:
            return f"Active/recent thermal signal / {int(count)} point(s)"
        return "Active/recent thermal signal"

    if row_has_fire_risk(row):
        intensity_text = safe_text(intensity, "").strip().upper().replace("-", "_").replace(" ", "_")
        if intensity_text in {"NO_FIRE", "NO_ACTIVE_FIRE", "NOT_DETECTED", "NONE", "N/A", "FALSE", "0"} or intensity_text.startswith("NO_"):
            return "Fire-check only, no active FIRMS fire"
        if intensity and intensity != "N/A":
            return f"Fire-check only / {intensity}"
        return "Fire-check only, no active FIRMS fire"

    return "No active thermal signal"


def count_fire_rows(df):
    if df is None or df.empty:
        return 0
    return int(sum(1 for _, row in df.iterrows() if row_has_fire(row)))


def count_fire_risk_rows(df):
    if df is None or df.empty:
        return 0
    return int(sum(1 for _, row in df.iterrows() if row_has_fire_risk(row)))


def count_field_required(df):
    if df is None or df.empty or "field_verification_required" not in df.columns:
        return 0
    return int(df["field_verification_required"].apply(is_truthy).sum())


# ----------------------------- ecology/watch/action logic -----------------------------

def classify_ecological_watch(row):
    existing_category = safe_text(row.get("ecological_watch_category", row.get("watch_category", "")), "")
    existing_level = safe_text(row.get("ecological_watch_level", row.get("watch_level", "")), "")
    existing_reason = safe_text(row.get("ecological_watch_reason", row.get("watch_reason", "")), "")
    existing_action = safe_text(row.get("ecological_watch_action", row.get("watch_action", "")), "")
    if existing_category and existing_category != "N/A":
        return {
            "category": existing_category,
            "level": existing_level if existing_level and existing_level != "N/A" else "LOW",
            "reason": existing_reason if existing_reason and existing_reason != "N/A" else "Engine-generated ecological watch category.",
            "action": existing_action if existing_action and existing_action != "N/A" else "Follow FRIS patrol action and field verification guidance.",
        }

    forest_pct = safe_float(row.get("forest_pct"), 0) or 0
    ndvi = safe_float(row.get("ndvi"), 0) or 0
    ndmi = safe_float(row.get("ndmi"), 0) or 0
    hansen_loss = safe_float(row.get("hansen_loss_pct"), 0) or 0
    final_risk = safe_float(row.get("final_risk_score", row.get("risk_score")), 0) or 0
    priority = safe_text(row.get("final_priority", row.get("risk_class", row.get("priority", ""))), "").upper()
    memory_class = safe_text(row.get("ecological_memory_class"), "").upper()
    operational_reason = safe_text(row.get("operational_attention_reason"), "")
    operational_label = safe_text(row.get("operational_attention_label"), "")
    field_required = is_truthy(row.get("field_verification_required"))

    if row_has_fire(row):
        reason = operational_reason if operational_reason and operational_reason != "N/A" else "Active/recent FIRMS or thermal fire signal is present."
        return {"category": "Fire Verification Alert", "level": "HIGH", "reason": reason, "action": "Immediate or same-day field verification."}

    if "CRITICAL" in priority or (forest_pct >= 70 and ndvi < 0.20):
        return {"category": "Ecological Anomaly Alert", "level": "HIGH", "reason": "Forest extent is meaningful but vegetation health is critically weak.", "action": "Priority ecological field verification before any conclusion."}

    if field_required or final_risk >= 70 or "HIGH" in priority:
        reason = operational_reason if operational_reason and operational_reason != "N/A" else "Multiple FRIS indicators require ground checking."
        action = safe_text(row.get("patrol_action", row.get("recommended_action")), "Field verification and officer review.")
        return {"category": operational_label if operational_label and operational_label != "N/A" else "Field Verification Watch", "level": "HIGH", "reason": reason, "action": action}

    if "CHRONIC" in memory_class:
        return {"category": "Chronic Risk Grid", "level": "MEDIUM", "reason": "365-day FRIS memory shows chronic/repeated risk pattern.", "action": "Compare with earlier runs and verify persistent stress causes."}

    if "REPEATED" in memory_class or "DEGRADATION" in memory_class:
        return {"category": "Repeated Stress Watch", "level": "MEDIUM", "reason": "365-day FRIS memory shows repeated yearly stress or degradation signal.", "action": "Monitor trend and verify in field if repeated."}

    if hansen_loss >= 15 and forest_pct >= 30:
        return {"category": "Historical Disturbance Watch", "level": "MEDIUM", "reason": "Historical forest-loss evidence is elevated for this forest grid.", "action": "Periodic ecological monitoring and disturbance verification."}

    if forest_pct >= 30 and ndvi < 0.40:
        return {"category": "Vegetation Stress Watch", "level": "MEDIUM", "reason": "Forest grid shows stressed vegetation signal.", "action": "Monitor in next run and verify if stress continues."}

    if ndmi < -0.10 and forest_pct >= 30:
        return {"category": "Moisture Stress Watch", "level": "MEDIUM", "reason": "Forest grid shows weak moisture/dryness signal.", "action": "Monitor moisture trend and rainfall context."}

    if row_has_fire_risk(row):
        return {"category": "Fire-Check Watch", "level": "MEDIUM", "reason": "Fire-risk/check wording exists but active FIRMS fire is not confirmed.", "action": "Check if patrol route passes nearby; verify only when field context supports."}

    return {"category": "Stable Forest Zone", "level": "LOW", "reason": "No major ecological watch-list condition detected.", "action": "Routine monitoring."}


def make_ecology_inference(row):
    watch = classify_ecological_watch(row)
    if watch["level"].upper() == "HIGH":
        status = "HIGH_ECOLOGICAL_VERIFICATION"
    elif watch["level"].upper() == "MEDIUM":
        status = "ECOLOGICAL_WATCH"
    else:
        status = "ROUTINE_MONITORING"
    return {
        "status": status,
        "inference": watch["reason"],
        "recommendation": watch["action"],
    }


def make_action(row):
    explicit = safe_text(row.get("officer_action", row.get("patrol_action", row.get("recommended_action", ""))), "")
    if explicit and explicit != "N/A":
        return explicit
    if row_has_fire(row):
        return "Immediate fire verification"
    watch = classify_ecological_watch(row)
    priority = safe_text(row.get("final_priority", row.get("risk_class", row.get("priority", ""))), "").upper()
    if watch["level"] == "HIGH" or "HIGH" in priority or "CRITICAL" in priority:
        return "Field verification"
    if watch["level"] == "MEDIUM":
        return "Monitor and verify if repeated"
    return "Routine monitoring"


def make_why_go(row):
    existing = safe_text(row.get("why_go"), "")
    if existing and existing != "N/A":
        return existing

    reasons = []
    if row_has_fire(row):
        reasons.append("active/recent thermal fire signal")
    elif row_has_fire_risk(row):
        reasons.append("fire-check risk, no active fire confirmed")

    priority = safe_text(row.get("final_priority", row.get("risk_class", row.get("priority", ""))), "").upper()
    if "HIGH" in priority or "CRITICAL" in priority:
        reasons.append("high operational priority")
    if is_truthy(row.get("field_verification_required")):
        reasons.append("field verification required")

    ndvi = safe_float(row.get("ndvi"))
    ndmi = safe_float(row.get("ndmi"))
    if ndvi is not None and ndvi < 0.35:
        reasons.append("weak vegetation signal")
    if ndmi is not None and ndmi < -0.10:
        reasons.append("dry moisture signal")

    memory = safe_text(row.get("ecological_memory_class"), "").upper()
    if "CHRONIC" in memory:
        reasons.append("chronic risk memory")
    elif "REPEATED" in memory or "DEGRADATION" in memory:
        reasons.append("repeated stress memory")

    hansen = safe_float(row.get("hansen_loss_pct"), 0) or 0
    if hansen >= 15:
        reasons.append("historical loss signal")

    carbon_status = safe_text(row.get("carbon_change_status"), "").upper()
    if "LOSS" in carbon_status:
        reasons.append("carbon loss support")

    if not reasons:
        return "Routine grid; no strong immediate concern detected."
    return "Why visit this grid? " + " | ".join(reasons[:4])


def watch_rank(row):
    watch = classify_ecological_watch(row)
    level = safe_text(watch.get("level"), "LOW").upper()
    score = 0
    if level == "HIGH":
        score += 500
    elif level == "MEDIUM":
        score += 250
    if "CHRONIC" in safe_text(row.get("ecological_memory_class"), "").upper():
        score += 80
    if "REPEATED" in safe_text(row.get("ecological_memory_class"), "").upper():
        score += 50
    score += safe_float(row.get("final_risk_score", row.get("risk_score")), 0) or 0
    return score


def priority_rank(row):
    score = 0
    if row_has_fire(row):
        score += 1000
    elif row_has_fire_risk(row):
        score += 450
    priority = safe_text(row.get("final_priority", row.get("risk_class", row.get("priority", ""))), "").upper()
    if "CRITICAL" in priority:
        score += 800
    elif "HIGH" in priority:
        score += 600
    elif "MEDIUM" in priority or "MODERATE" in priority:
        score += 250
    if is_truthy(row.get("field_verification_required")):
        score += 350
    score += watch_rank(row)
    score += (safe_float(row.get("final_risk_score", row.get("risk_score")), 0) or 0)
    ndmi = safe_float(row.get("ndmi"))
    ndvi = safe_float(row.get("ndvi"))
    if ndmi is not None and ndmi < -0.10:
        score += 40
    if ndvi is not None and ndvi < 0.35:
        score += 30
    return float(score)


def map_display_rank(row):
    return priority_rank(row)


def sorted_priority_df(df, limit=MAX_TABLE_ROWS):
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["_rank"] = work.apply(priority_rank, axis=1)
    return work.sort_values("_rank", ascending=False).head(limit)


def count_watchlist(df):
    if df is None or df.empty:
        return 0
    count = 0
    for _, row in df.iterrows():
        watch = classify_ecological_watch(row)
        category = safe_text(watch.get("category"), "").upper()
        level = safe_text(watch.get("level"), "").upper()
        if level in {"HIGH", "MEDIUM"} and "STABLE" not in category and "ROUTINE" not in category:
            count += 1
    return count


# ----------------------------- links and tables -----------------------------

def grid_detail_href(row):
    gid = safe_text(row.get("grid_id"), "")
    if not gid or gid == "N/A":
        return "#"
    return "/grid/" + quote(str(gid), safe="")


def google_maps_href(row):
    for col in ["google_maps_link", "navigation_link"]:
        maps = safe_text(row.get(col), "")
        if maps.startswith("http"):
            return maps
    lat = safe_float(row.get("lat", row.get("latitude", row.get("center_lat", row.get("centroid_lat")))))
    lon = safe_float(row.get("lon", row.get("lng", row.get("longitude", row.get("center_lon", row.get("centroid_lon"))))))
    if lat is not None and lon is not None:
        return f"https://www.google.com/maps?q={lat},{lon}"
    return "#"


def _grid_info_search_filter(work, q):
    q = safe_text(q, "").strip()
    if not q:
        return work
    q_upper = q.upper()
    search_cols = [
        "grid_id", "final_priority", "risk_class", "priority", "operational_attention_label",
        "operational_attention_class", "health_class", "moisture_class_calibrated", "moisture_class",
        "ecological_memory_class", "carbon_change_status", "mrv_confidence", "soil_type",
        "weather_fire_spread_class", "fire_intensity_class", "field_inference", "ecology_inference",
    ]
    mask = pd.Series(False, index=work.index)
    for col in search_cols:
        if col in work.columns:
            mask = mask | work[col].astype(str).str.upper().str.contains(q_upper, na=False, regex=False)
    try:
        derived = work.apply(
            lambda r: (classify_ecological_watch(r)["category"] + " " + classify_ecological_watch(r)["level"] + " " + fire_display(r)).upper(),
            axis=1,
        )
        mask = mask | derived.str.contains(q_upper, na=False, regex=False)
    except Exception:
        pass
    return work[mask].copy()


def build_all_grid_information_table(df, page=1, per_page=MAX_GRID_INFO_ROWS, q=""):
    """Paginated grid-wise information table. This is the visible information layer."""
    if df is None or df.empty:
        return "<div class='empty'>CSV not loaded.</div>", 0, 1, 1, 0, 0

    try:
        page = max(1, int(page or 1))
    except Exception:
        page = 1
    try:
        per_page = max(20, min(int(per_page or MAX_GRID_INFO_ROWS), 200))
    except Exception:
        per_page = MAX_GRID_INFO_ROWS

    work = df.copy()
    work["_grid_info_rank"] = work.apply(map_display_rank, axis=1)
    work = _grid_info_search_filter(work, q)
    work = work.sort_values("_grid_info_rank", ascending=False)

    total = len(work)
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    page = min(page, total_pages)
    start = (page - 1) * per_page
    end = min(start + per_page, total)
    page_df = work.iloc[start:end]

    if page_df.empty:
        return "<div class='empty'>No grid matched this search.</div>", total, page, total_pages, start, end

    rows = []
    for _, row in page_df.iterrows():
        watch = classify_ecological_watch(row)
        detail_link = grid_detail_href(row)
        map_link = google_maps_href(row)
        memory = safe_text(row.get("ecological_memory_class"), "N/A")
        moisture = safe_text(row.get("moisture_class_calibrated", row.get("moisture_class")), "N/A")
        health = safe_text(row.get("health_class"), "N/A")
        carbon_status = safe_text(row.get("carbon_change_status"), "N/A")
        action = make_action(row)
        map_cell = f"<a href='{html.escape(map_link)}' target='_blank'>Map</a>" if map_link != "#" else "N/A"
        level_class = "watch-high" if safe_text(watch.get("level"), "").upper() == "HIGH" else "watch-medium" if safe_text(watch.get("level"), "").upper() == "MEDIUM" else "watch-low"
        rows.append(f"""
        <tr>
            <td><b>{e(row.get('grid_id'))}</b></td>
            <td>{e(row.get('final_priority', row.get('risk_class', row.get('priority'))))}<br><small>Score {format_number(row.get('final_risk_score', row.get('risk_score')), 1)}</small></td>
            <td><span class='{level_class}'>{html.escape(safe_text(watch.get('level')))}</span><br><small>{html.escape(safe_text(watch.get('category')))}</small></td>
            <td>{format_number(row.get('forest_pct'), 1, '%')}</td>
            <td>{format_number(row.get('ndvi'), 3)}<br><small>{html.escape(health)}</small></td>
            <td>{format_number(row.get('ndmi'), 3)}<br><small>{html.escape(moisture)}</small></td>
            <td>{html.escape(memory)}</td>
            <td>{html.escape(fire_display(row))}</td>
            <td>{html.escape(carbon_status)}</td>
            <td>{html.escape(action)}</td>
            <td><a href='{detail_link}' target='_blank'>Grid Details</a><br>{map_cell}</td>
        </tr>
        """)

    table = f"""
    <div class='table-wrap'><table>
        <thead><tr>
            <th>Grid</th><th>Risk</th><th>Watch / Anomaly</th><th>Forest %</th>
            <th>NDVI / Health</th><th>NDMI / Moisture</th><th>365-Day Memory</th>
            <th>Fire</th><th>Carbon</th><th>Action</th><th>Information</th>
        </tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table></div>
    """
    return table, total, page, total_pages, start + 1 if total else 0, end


def build_priority_table(df, limit=MAX_TABLE_ROWS):
    work = sorted_priority_df(df, limit)
    if work.empty:
        return "<div class='empty'>CSV not loaded.</div>"
    rows = []
    for _, row in work.iterrows():
        grid_link = grid_detail_href(row)
        carbon_status = safe_text(row.get("carbon_change_status"), "N/A")
        mrv = safe_text(row.get("mrv_confidence"), "N/A")
        rows.append(f"""
        <tr><td><b>{e(row.get('grid_id'))}</b></td><td>{e(row.get('final_priority', row.get('risk_class', row.get('priority'))))}</td>
        <td>{format_number(row.get('ndvi'), 3)}</td><td>{format_number(row.get('ndmi'), 3)}</td><td>{html.escape(fire_display(row))}</td>
        <td>{format_number(row.get('final_risk_score', row.get('risk_score')), 1)}</td><td>{html.escape(carbon_status)}<br><small>{html.escape(mrv)}</small></td>
        <td>{html.escape(make_why_go(row))}</td><td>{html.escape(make_action(row))}</td>
        <td><a href='{grid_link}' target='_blank'>Grid Details</a></td></tr>
        """)
    return f"<div class='table-wrap'><table><thead><tr><th>Grid</th><th>Priority</th><th>NDVI</th><th>NDMI</th><th>Fire</th><th>Risk</th><th>Carbon/MRV</th><th>Why go?</th><th>Action</th><th>Information</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def build_watchlist_table(df, limit=MAX_WATCH_ROWS):
    if df is None or df.empty:
        return "<div class='empty'>CSV not loaded.</div>"
    work = df.copy()
    work["_watch_rank"] = work.apply(watch_rank, axis=1)
    work["_watch_category"] = work.apply(lambda r: classify_ecological_watch(r)["category"], axis=1)
    work["_watch_level"] = work.apply(lambda r: classify_ecological_watch(r)["level"], axis=1)
    routine_mask = (
        work["_watch_category"].astype(str).str.upper().str.contains("STABLE|ROUTINE", na=False)
        | work["_watch_level"].astype(str).str.upper().str.contains("ROUTINE|LOW", na=False)
    )
    work = work[~routine_mask].sort_values("_watch_rank", ascending=False).head(limit)
    if work.empty:
        return "<div class='empty'>No ecological watch-list grid found.</div>"
    rows = []
    for _, row in work.iterrows():
        watch = classify_ecological_watch(row)
        grid_link = grid_detail_href(row)
        level_class = "watch-high" if watch["level"] == "HIGH" else "watch-medium"
        rows.append(f"""
        <tr><td><b>{e(row.get('grid_id'))}</b></td><td><span class='{level_class}'>{html.escape(watch['level'])}</span></td>
        <td>{html.escape(watch['category'])}</td><td>{format_number(row.get('forest_pct'), 1, '%')}</td><td>{format_number(row.get('ndvi'), 3)}</td><td>{format_number(row.get('ndmi'), 3)}</td>
        <td>{html.escape(watch['reason'])}</td><td>{html.escape(watch['action'])}</td><td><a href='{grid_link}' target='_blank'>Grid Details</a></td></tr>
        """)
    return f"<div class='table-wrap'><table><thead><tr><th>Grid</th><th>Level</th><th>Category</th><th>Forest %</th><th>NDVI</th><th>NDMI</th><th>Why listed?</th><th>Action</th><th>Information</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


# ----------------------------- saved map injection -----------------------------

def build_saved_map_overlay():
    return """
    <div id="fris-dashboard-injected-legend" style="
        position: fixed; top: 72px; left: 14px; z-index: 999999; width: 310px;
        max-width: calc(100vw - 32px); background: rgba(4,18,7,.90); color:#fff;
        padding: 13px 14px; border-radius:14px; border:1px solid rgba(223,255,0,.55);
        box-shadow:0 8px 24px rgba(0,0,0,.45); font-family:Arial,sans-serif;
        font-size:12.5px; line-height:1.45;">
        <div style="font-size:15px;font-weight:800;color:#dfff00;margin-bottom:6px;">FRIS Risk & Patrol Priority Layer</div>
        <div style="margin-bottom:7px;">Colour means <b>field priority</b>, not always active fire.</div>
        <div style="display:grid;grid-template-columns:18px 1fr;gap:5px 7px;align-items:center;">
            <span style="width:15px;height:15px;border-radius:4px;background:#ef4444;border:1px solid #fff;display:inline-block;"></span><span><b>Red:</b> active FIRMS / thermal fire</span>
            <span style="width:15px;height:15px;border-radius:4px;background:#f97316;border:1px solid #fff;display:inline-block;"></span><span><b>Orange:</b> fire-check / field verification</span>
            <span style="width:15px;height:15px;border-radius:4px;background:#facc15;border:1px solid #fff;display:inline-block;"></span><span><b>Yellow:</b> high operational attention</span>
            <span style="width:15px;height:15px;border-radius:4px;background:#a855f7;border:1px solid #fff;display:inline-block;"></span><span><b>Purple:</b> ecological watch / repeated stress</span>
            <span style="width:15px;height:15px;border-radius:4px;background:#3b82f6;border:1px solid #fff;display:inline-block;"></span><span><b>Blue:</b> moisture/anomaly attention</span>
            <span style="width:15px;height:15px;border-radius:4px;background:#22c55e;border:1px solid #fff;display:inline-block;"></span><span><b>Green:</b> stable / routine</span>
        </div>
        <div style="margin-top:9px;padding:7px 8px;border-radius:10px;background:rgba(223,255,0,.12);color:#f4ffb8;font-weight:700;">
            Popup shows only Grid, Risk and Action. Full details are in dashboard tables and CSV.
        </div>
    </div>
    """


def inject_overlay_into_saved_map(map_html):
    if not map_html or "fris-dashboard-injected-legend" in map_html:
        return map_html

    extra_css = """
    <style id="fris-dashboard-injected-css">
        .leaflet-control-layers,.leaflet-control-zoom,.leaflet-control-scale{z-index:99999!important;}
        .leaflet-popup-content-wrapper{border-radius:12px!important;box-shadow:0 10px 28px rgba(0,0,0,.35)!important;}
        .leaflet-popup-content{max-width:210px!important;min-width:150px!important;margin:10px 12px!important;font-family:Arial,sans-serif!important;font-size:12px!important;line-height:1.35!important;}
        .fris-mini-popup{min-width:150px;max-width:210px;color:#102000}.fris-mini-grid{font-size:13px;font-weight:800;margin-bottom:6px;color:#173f18}.fris-mini-row{margin:3px 0;white-space:normal}.fris-mini-risk{display:inline-block;padding:2px 7px;border-radius:999px;font-weight:800;background:#eef5dc;color:#173f18}.fris-mini-risk.high,.fris-mini-risk.critical{background:#fee2e2;color:#991b1b}.fris-mini-risk.medium{background:#fef3c7;color:#92400e}.fris-mini-risk.low{background:#dcfce7;color:#166534}
        @media(max-width:700px){#fris-dashboard-injected-legend{top:62px!important;left:10px!important;width:285px!important;font-size:11.5px!important}.leaflet-popup-content{max-width:185px!important;}}
    </style>
    """

    compact_popup_script = r"""
    <script id="fris-dashboard-popup-compactor">
    (function(){
        function esc(v){return String(v||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');}
        function clean(v){return String(v||'').replace(/\s+/g,' ').trim();}
        function first(text, patterns){for(var i=0;i<patterns.length;i++){var m=text.match(patterns[i]);if(m&&m[1])return clean(m[1]);if(m&&m[0])return clean(m[0]);}return '';}
        function negFire(text){return /\bNO[_\s-]*(FIRE|ACTIVE|THERMAL)\b|NO ACTIVE|NO FIRE|NOT DETECTED/i.test(text);}
        function risk(text){
            var r=first(text,[/(?:Risk|Priority|final_priority|risk_class|Final Priority|Final Risk)\s*[:=\-]\s*(CRITICAL|HIGH|MEDIUM|MODERATE|LOW|NORMAL|ROUTINE)/i,/\b(CRITICAL|HIGH|MEDIUM|MODERATE|LOW)\s+(?:RISK|PRIORITY)\b/i]).toUpperCase();
            if(r){if(r.indexOf('CRITICAL')>=0)return 'CRITICAL';if(r.indexOf('HIGH')>=0)return 'HIGH';if(r.indexOf('MEDIUM')>=0||r.indexOf('MODERATE')>=0)return 'MEDIUM';return 'LOW';}
            if(/CRITICAL|SAME-DAY|SAME DAY|24 HOURS|FIELD VERIFICATION|HIGH_ECOLOGICAL_VERIFICATION/i.test(text))return 'HIGH';
            if(/\bHIGH\b/i.test(text)&&!/LOW_MRV_CONFIDENCE|LOW_RADAR/i.test(text))return 'HIGH';
            if(/MEDIUM|MODERATE|WATCH|MONITOR WITHIN 3 DAYS|CHRONIC|REPEATED|DEGRADATION/i.test(text))return 'MEDIUM';
            return 'LOW';
        }
        function action(text,r){if(!negFire(text)&&/ACTIVE|THERMAL|FIRMS|FRP|FIRE_DETECTED|RECENT_FIRE/i.test(text))return 'Fire verification'; if(/FIELD VERIFICATION|FIELD_VERIFICATION|VERIFY|PRIORITY PATROL|24 HOURS|SAME-DAY|SAME DAY|CRITICAL/i.test(text)||r==='HIGH'||r==='CRITICAL')return 'Field verification'; if(/WATCH|MONITOR|MEDIUM|MODERATE|CHRONIC|REPEATED|DEGRADATION|STRESS/i.test(text)||r==='MEDIUM')return 'Monitor'; return 'Routine patrolling';}
        function compact(el){try{if(!el||el.getAttribute('data-fris-compact-done')==='1')return;var text=clean(el.innerText||el.textContent||'');if(!text||text.length<8)return;var grid=first(text,[/\bGD[-_]\d{1,3}[-_]\d{1,3}\b/i,/Grid\s*[:=\-]\s*([A-Za-z0-9_\-]+)/i]);if(!grid)grid='Selected grid';var r=risk(text);var a=action(text,r);var cls=r.toLowerCase();if(r==='MODERATE'){r='MEDIUM';cls='medium';}el.innerHTML='<div class="fris-mini-popup"><div class="fris-mini-grid">'+esc(grid)+'</div><div class="fris-mini-row"><b>Risk:</b> <span class="fris-mini-risk '+esc(cls)+'">'+esc(r)+'</span></div><div class="fris-mini-row"><b>Action:</b> '+esc(a)+'</div></div>';el.setAttribute('data-fris-compact-done','1');}catch(e){}}
        function all(){var p=document.querySelectorAll('.leaflet-popup-content');for(var i=0;i<p.length;i++)compact(p[i]);}
        if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',all);}else{all();}
        var obs=new MutationObserver(function(){all();});obs.observe(document.documentElement||document.body,{childList:true,subtree:true});
    })();
    </script>
    """

    map_html = map_html.replace("</head>", extra_css + "\n</head>", 1) if "</head>" in map_html else extra_css + map_html
    overlay_html = build_saved_map_overlay()
    if "</body>" in map_html:
        return map_html.replace("</body>", overlay_html + compact_popup_script + "\n</body>", 1)
    return map_html + overlay_html + compact_popup_script


# ----------------------------- style -----------------------------

BASE_STYLE = """
<style>
*{box-sizing:border-box;font-family:Arial,sans-serif}body{margin:0;background:#061307;color:white}.layout{display:flex;min-height:100vh}.sidebar{width:270px;padding:25px;background:linear-gradient(180deg,#173f18,#071507);border-right:1px solid rgba(255,255,255,.15)}.logo h1{color:#dfff00;font-size:38px;margin:0}.logo p{color:#c6ff6b;font-size:13px;margin:4px 0 30px}.nav{padding:15px;margin-bottom:13px;border-radius:15px;background:rgba(255,255,255,.12);font-weight:bold}.nav.active{background:#dfff00;color:#102000}.nav a{color:inherit;text-decoration:none;display:block}.side-card,.map-card,.card,.table-card,.box{background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.18);border-radius:24px;padding:18px}.side-card{margin-top:25px;font-size:14px;line-height:1.7}.ok{color:#dfff00;font-weight:bold}.bad{color:#ff6b6b;font-weight:bold}.main{flex:1;padding:25px}.topbar{display:grid;grid-template-columns:repeat(3,1fr) auto;gap:15px;align-items:center;padding:18px;border-radius:22px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.18);margin-bottom:22px}.time-box{font-size:14px;line-height:1.4}.time-box b{display:block}.time-box span,.value,td a,.box a{color:#dfff00;font-weight:bold}.btn{display:inline-block;background:#dfff00;color:#102000!important;padding:12px 16px;border-radius:14px;text-decoration:none;font-weight:bold;margin:4px;border:0;cursor:pointer}.btn.disabled{background:rgba(255,255,255,.18);color:#8a968a!important}.content{display:grid;grid-template-columns:1fr 340px;gap:22px}.map-frame{width:100%;height:620px;border:0;border-radius:18px;background:#1b5525;overflow:hidden}.right{display:flex;flex-direction:column;gap:15px}.row{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.12);font-size:14px}.table-card{margin-top:22px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th{background:rgba(223,255,0,.18);color:#dfff00;text-align:left;padding:10px;white-space:nowrap}td{padding:10px;border-bottom:1px solid rgba(255,255,255,.12);vertical-align:top}.watch-high{color:#ff6b6b;font-weight:bold}.watch-medium{color:#ffd400;font-weight:bold}.watch-low{color:#8dff8d;font-weight:bold}.watch-note{background:rgba(223,255,0,.10);border-left:5px solid #dfff00;padding:14px;border-radius:14px;margin-bottom:14px;line-height:1.5;color:#eaffc4}.empty{padding:18px;color:#eaffc4}.footer{margin-top:18px;font-size:13px;color:#c5d6c5}input,select{padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.25);background:#102000;color:white;margin:4px;min-width:180px}.detail-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.detail-grid .card{min-height:120px}small{color:#d4e6d4}@media(max-width:1000px){.layout{flex-direction:column}.sidebar{width:100%}.topbar,.content,.detail-grid{grid-template-columns:1fr}.map-frame{height:520px}}
</style>
"""


def get_weather(df):
    temperature = get_first_value(df, ["temperature_c", "temperature", "temp_c"])
    rain_now = get_first_value(df, ["rainfall_current_mm", "rainfall", "rain_mm"])
    rain_24h = get_first_value(df, ["rainfall_24h_mm"])
    wind = get_first_value(df, ["wind_speed_kmph", "wind_kmph", "wind_speed"])
    gust = get_first_value(df, ["wind_gust_kmph"])
    spread = get_first_value(df, ["weather_fire_spread_class"], "N/A")
    provider = get_first_value(df, ["weather_status", "weather_provider"], "CSV Weather")
    if rain_now is None and rain_24h is not None:
        rain_now = rain_24h
    return {
        "source": safe_text(provider) if temperature is not None else "CSV / Offline",
        "temperature": format_number(temperature, 1, "°C"),
        "rainfall": format_number(rain_now, 1, " mm"),
        "rainfall_24h": format_number(rain_24h, 1, " mm"),
        "wind": format_number(wind, 1, " km/h"),
        "gust": format_number(gust, 1, " km/h"),
        "spread": safe_text(spread),
    }


def dashboard_error_page(message):
    dirs = "".join(f"<li><code>{html.escape(d)}</code></li>" for d in _data_dirs())
    return f"""<!DOCTYPE html><html><head><title>FRIS Dashboard</title><meta name='viewport' content='width=device-width,initial-scale=1'>{BASE_STYLE}</head><body style='padding:30px'><div class='box'><h1 style='color:#dfff00'>FRIS Dashboard</h1><h2>CSV not loaded</h2><p>{html.escape(message)}</p><p>The app searched:</p><ul>{dirs}</ul><p>Keep <b>fris_latest.csv</b>, <b>fris_latest.geojson</b> and <b>fris_latest_map.html</b> in the same folder as app.py, data/, output/, or set FRIS_DATA_DIR.</p></div></body></html>"""


# ----------------------------- routes -----------------------------

@app.route("/")
def dashboard():
    df = read_csv_light()
    if df is None or df.empty:
        return Response(dashboard_error_page(_CSV_CACHE.get("error") or "fris_latest.csv missing or empty."), mimetype="text/html")

    total_grids = len(df)
    high_risk = count_contains(df, ["final_priority", "risk_class", "priority"], "HIGH")
    critical_risk = count_contains(df, ["final_priority", "risk_class", "priority"], "CRITICAL")
    active_fire = count_fire_rows(df)
    fire_check = count_fire_risk_rows(df)
    field_required_count = count_field_required(df)
    watchlist_count = count_watchlist(df)

    avg_ndvi = avg_col(df, "ndvi")
    avg_ndmi = avg_col(df, "ndmi")
    soil_counts = value_counts_html(df, "soil_moisture_retention_class", 3)
    memory_counts = value_counts_html(df, "ecological_memory_class", 4)
    mrv_counts = value_counts_html(df, "mrv_confidence", 3)
    weather = get_weather(df)

    total_carbon = sum_first_available_numeric(df, ["ecosystem_carbon_co2e_total", "ecosystem_carbon_total_ton", "estimated_ecosystem_carbon_ton"])
    carbon_change = sum_first_available_numeric(df, ["carbon_change_co2e_ton", "carbon_change_ton", "carbon_change_from_365d"])
    carbon_opp = sum_first_available_numeric(df, ["preliminary_carbon_opportunity_ton_co2e"])
    tree_count = sum_first_available_numeric(df, ["estimated_tree_count"])
    high_carbon_loss = count_contains(df, ["carbon_change_status"], "LOSS")
    high_carbon_gain = count_contains(df, ["carbon_change_status"], "GAIN")
    forest_area_text = format_number(estimate_area_ha(df), 1, " ha")

    summary_text = "FRIS has detected elevated operational concern in selected grids. Focus first on high-risk, fire-check, anomaly and chronic/repeated stress grids."
    priority_table = build_priority_table(df, MAX_TABLE_ROWS)
    grid_info_preview, grid_total, grid_page, grid_pages, grid_start, grid_end = build_all_grid_information_table(df, 1, MAX_GRID_INFO_ROWS, "")
    watchlist_table = build_watchlist_table(df, MAX_WATCH_ROWS)

    csv_found = os.path.exists(CSV_FILE)
    geojson_found = os.path.exists(GEOJSON_FILE)
    map_found = os.path.exists(MAP_FILE)

    page = f"""<!DOCTYPE html><html><head><title>FRIS Jharkhand Dashboard</title><meta name='viewport' content='width=device-width,initial-scale=1'>{BASE_STYLE}</head><body><div class='layout'>
    <div class='sidebar'>
        <div class='logo'><h1>FRIS</h1><p>Forest Resilience Information System</p></div>
        <div class='nav active'>🏠 Dashboard</div>
        <div class='nav'><a href='#map-section'>🗺️ Operational Map</a></div>
        <div class='nav'><a href='#grid-info-section'>📋 All Grid Info</a></div>
        <div class='nav'><a href='#priority-section'>🧭 Priority Grids</a></div>
        <div class='nav'><a href='#watchlist-section'>🟣 Operational Watch</a></div>
        <div class='nav'>🔥 Fire Intelligence</div>
        <div class='nav'>💧 Moisture Stress</div>
        <div class='nav'>🌿 Carbon MRV</div>
        <div class='side-card'><b>Jharkhand FRIS Screening</b><br><br>
            CSV: <span class='{'ok' if csv_found else 'bad'}'>{'Found' if csv_found else 'Missing'}</span><br>
            GeoJSON: <span class='{'ok' if geojson_found else 'bad'}'>{'Found' if geojson_found else 'Missing'}</span><br>
            Saved Map: <span class='{'ok' if map_found else 'bad'}'>{'Found' if map_found else 'Missing'}</span><br><br>
            <b>Analysed Area:</b><br>{forest_area_text}<br><br><b>Memory Mode:</b><br>Light + Informative
        </div>
    </div>
    <div class='main'>
        <div class='topbar'>
            <div class='time-box'><b>Current Time</b><span>{format_ist(ist_now())}</span></div>
            <div class='time-box'><b>Last Data Update</b><span>{get_file_update_time(CSV_FILE)}</span><br><small>{get_file_age_minutes(CSV_FILE)}</small></div>
            <div class='time-box'><b>Next Expected Run</b><span>{next_expected_run()}</span></div>
            <div>
                <a class='btn' href='/'>Refresh</a><a class='btn' href='/download/csv'>Download CSV</a>
                <a class='btn' href='/view/full-map' target='_blank'>Open Full Map</a><a class='btn' href='/download/map'>Download Map</a>
                <a class='btn' href='/download/geojson'>Full GeoJSON</a><a class='btn' href='/grids'>All Grid Info</a>
                <a class='btn' href='/api/summary'>API</a><a class='btn' href='/debug'>Debug</a>
            </div>
        </div>
        <div class='content' id='map-section'>
            <div class='map-card'><h2>FRIS Forest Risk & Patrol Map</h2>
                <div class='watch-note'>Layer: <b>FRIS Risk & Patrol Priority Layer</b>. Click any grid for a small popup showing only <b>Grid, Risk and Action</b>. Full information for every grid is shown in the <b>All Grid Info</b> panel below.</div>
                <iframe class='map-frame' src='/view/full-map' loading='lazy' title='FRIS saved operational map'></iframe>
            </div>
            <div class='right'>
                <div class='card'><h3>📊 Operational Summary</h3><div class='row'><span>Total Grids</span><span class='value'>{total_grids}</span></div><div class='row'><span>High Risk</span><span class='value'>{high_risk}</span></div><div class='row'><span>Critical Risk</span><span class='value'>{critical_risk}</span></div><div class='row'><span>Fire Risk / Check</span><span class='value'>{fire_check}</span></div><div class='row'><span>Active Fire Signals</span><span class='value'>{active_fire}</span></div><div class='row'><span>Field Verification</span><span class='value'>{field_required_count}</span></div><div class='row'><span>Watch-List</span><span class='value'>{watchlist_count}</span></div></div>
                <div class='card'><h3>💧 Forest Condition</h3><div class='row'><span>Average NDVI</span><span class='value'>{avg_ndvi}</span></div><div class='row'><span>Average NDMI</span><span class='value'>{avg_ndmi}</span></div><div class='row'><span>Soil Retention</span><span class='value'>{soil_counts}</span></div></div>
                <div class='card'><h3>🟣 Operational Watch Summary</h3><div class='watch-note'>{html.escape(summary_text)}</div><div class='row'><span>365-Day Memory</span><span class='value'>{memory_counts}</span></div></div>
                <div class='card'><h3>🌦️ Weather</h3><div class='row'><span>Source</span><span class='value'>{html.escape(weather['source'])}</span></div><div class='row'><span>Temperature</span><span class='value'>{weather['temperature']}</span></div><div class='row'><span>Rainfall 24h</span><span class='value'>{weather['rainfall_24h']}</span></div><div class='row'><span>Wind</span><span class='value'>{weather['wind']}</span></div><div class='row'><span>Fire Spread</span><span class='value'>{html.escape(weather['spread'])}</span></div></div>
                <div class='card'><h3>🌿 Carbon MRV</h3><div class='row'><span>Total Carbon</span><span class='value'>{format_carbon(total_carbon)}</span></div><div class='row'><span>Carbon Change</span><span class='value'>{format_carbon(carbon_change)}</span></div><div class='row'><span>Preliminary Opportunity</span><span class='value'>{format_carbon(carbon_opp)}</span></div><div class='row'><span>High Loss / Gain</span><span class='value'>{high_carbon_loss} / {high_carbon_gain}</span></div><div class='row'><span>MRV Confidence</span><span class='value'>{mrv_counts}</span></div><div class='row'><span>Claim Status</span><span class='value'>Not Certified</span></div></div>
                <div class='card'><h3>🌲 Tree Position Estimate</h3><div class='row'><span>Estimated Count</span><span class='value'>{format_number(tree_count, 0)}</span></div><small>Estimate only; not exact tree census.</small></div>
            </div>
        </div>
        <div class='table-card' id='grid-info-section'><h2>📋 All Grid Info — Every Grid</h2><div class='watch-note'>This is the separate information layer for the whole FRIS grid dataset. Showing {grid_start}-{grid_end} of {grid_total} grids here. Use the button for search and pagination.</div>{grid_info_preview}<a class='btn' href='/grids'>Open Searchable All Grid Info</a><a class='btn' href='/download/csv'>Download Full CSV</a></div>
        <div class='table-card' id='priority-section'><h2>🧭 Priority Grid Intelligence</h2>{priority_table}</div>
        <div class='table-card' id='watchlist-section'><h2>🟣 Ecological Anomaly & Chronic Risk Watch-List</h2><div class='watch-note'>Separate verification layer for ecological anomaly, chronic/repeated stress, fire-check, moisture stress, vegetation stress, and historical disturbance signals.</div>{watchlist_table}</div>
        <div class='footer'>Dashboard popup is intentionally small. The full grid-wise information is in the All Grid Info table, Grid Details pages and full CSV download.</div>
    </div>
</div></body></html>"""
    del df
    gc.collect()
    return Response(page, mimetype="text/html")


@app.route("/view/full-map")
def view_full_map():
    if not os.path.exists(MAP_FILE):
        return Response("FRIS map file not found. Put fris_latest_map.html inside data/, output/, or project root.", status=404, mimetype="text/plain")
    try:
        with open(MAP_FILE, "r", encoding="utf-8", errors="ignore") as f:
            map_html = f.read()
        map_html = inject_overlay_into_saved_map(map_html)
        return Response(map_html, mimetype="text/html", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})
    except Exception as exc:
        return Response(f"Could not read FRIS map: {exc}", status=500, mimetype="text/plain")


@app.route("/map")
def map_alias():
    return view_full_map()


@app.route("/download/csv")
def download_csv():
    if not os.path.exists(CSV_FILE):
        return Response("FRIS CSV file not found.", status=404, mimetype="text/plain")
    return send_file(CSV_FILE, mimetype="text/csv", as_attachment=True, download_name="fris_latest.csv", max_age=0)


@app.route("/download/geojson")
def download_geojson():
    if not os.path.exists(GEOJSON_FILE):
        return Response("FRIS GeoJSON file not found.", status=404, mimetype="text/plain")
    return send_file(GEOJSON_FILE, mimetype="application/geo+json", as_attachment=True, download_name="fris_latest.geojson", max_age=0)


@app.route("/download/map")
def download_map():
    if not os.path.exists(MAP_FILE):
        return Response("FRIS map file not found.", status=404, mimetype="text/plain")
    return send_file(MAP_FILE, mimetype="text/html", as_attachment=True, download_name="fris_latest_map.html", max_age=0)


@app.route("/grids")
def all_grid_information():
    df = read_csv_light()
    q = safe_text(request.args.get("q", ""), "")
    try:
        page_num = int(request.args.get("page", "1"))
    except Exception:
        page_num = 1
    try:
        per_page = int(request.args.get("per_page", str(MAX_GRID_INFO_ROWS)))
    except Exception:
        per_page = MAX_GRID_INFO_ROWS

    table, total, page_num, total_pages, start, end = build_all_grid_information_table(df, page_num, per_page, q)

    def page_link(label, target_page, disabled=False):
        if disabled:
            return f"<span class='btn disabled'>{html.escape(label)}</span>"
        return f"<a class='btn' href='/grids?page={int(target_page)}&per_page={int(max(20, min(per_page, 200)))}&q={quote(q, safe='')}'>{html.escape(label)}</a>"

    prev_link = page_link("← Previous", max(1, page_num - 1), page_num <= 1)
    next_link = page_link("Next →", min(total_pages, page_num + 1), page_num >= total_pages)
    q_value = html.escape(q)

    page = f"""<!DOCTYPE html><html><head><title>FRIS All Grid Information</title><meta name='viewport' content='width=device-width,initial-scale=1'>{BASE_STYLE}</head><body style='padding:24px'>
    <div class='box'><h1>📋 FRIS All Grid Information</h1><div class='watch-note'>This page shows grid-wise information for the whole FRIS dataset. Map popup remains small; this table carries the detailed information layer.</div>
    <form method='get' action='/grids'><input type='text' name='q' value='{q_value}' placeholder='Search grid, HIGH, CHRONIC, FIRE, DRY...'><select name='per_page'><option value='50' {'selected' if per_page==50 else ''}>50 rows</option><option value='100' {'selected' if per_page==100 else ''}>100 rows</option><option value='200' {'selected' if per_page==200 else ''}>200 rows</option></select><button class='btn' type='submit'>Search</button><a class='btn' href='/grids'>Clear</a><a class='btn' href='/'>Dashboard</a><a class='btn' href='/download/csv'>Download Full CSV</a></form>
    <p>Showing <b>{start}-{end}</b> of <b>{total}</b> matching grids. Page <b>{page_num}</b> of <b>{total_pages}</b>.</p>{prev_link}{next_link}</div>
    <div class='box'>{table}</div>
    <div class='box'>{prev_link}{next_link}<p><small>Full raw audit columns remain available in the CSV download.</small></p></div>
    </body></html>"""
    del df
    gc.collect()
    return Response(page, mimetype="text/html")


@app.route("/grid/<path:grid_id>")
def grid_detail(grid_id):
    df = read_csv_light()
    if df is None or df.empty or "grid_id" not in df.columns:
        return Response("Grid data not available.", status=404, mimetype="text/plain")
    gid = unquote(grid_id)
    work = df[df["grid_id"].astype(str) == str(gid)]
    if work.empty:
        return Response(f"Grid not found: {html.escape(gid)}", status=404, mimetype="text/plain")
    row = work.iloc[0]
    watch = classify_ecological_watch(row)
    eco = make_ecology_inference(row)
    map_link = google_maps_href(row)

    cards = f"""
    <div class='detail-grid'>
        <div class='card'><h3>Grid</h3><h2>{e(row.get('grid_id'))}</h2><p>Forest: {format_number(row.get('forest_pct'),1,'%')}</p><p>Risk: {e(row.get('final_priority', row.get('risk_class', row.get('priority'))))}</p></div>
        <div class='card'><h3>Vegetation / Moisture</h3><p>NDVI: <b>{format_number(row.get('ndvi'),3)}</b></p><p>NDMI: <b>{format_number(row.get('ndmi'),3)}</b></p><p>{e(row.get('health_class'))} / {e(row.get('moisture_class_calibrated', row.get('moisture_class')))}</p></div>
        <div class='card'><h3>Watch Layer</h3><p><b>{html.escape(watch['level'])}</b> — {html.escape(watch['category'])}</p><p>{html.escape(watch['reason'])}</p></div>
        <div class='card'><h3>Fire</h3><p>{html.escape(fire_display(row))}</p></div>
        <div class='card'><h3>Carbon / MRV</h3><p>{e(row.get('carbon_change_status'))}</p><p>{e(row.get('mrv_confidence'))}</p></div>
        <div class='card'><h3>Action</h3><p>{html.escape(make_action(row))}</p><p><a class='btn' href='{html.escape(map_link)}' target='_blank'>Open Google Map</a></p></div>
    </div>
    """

    all_rows = []
    for col in row.index:
        if str(col).startswith("_"):
            continue
        all_rows.append(f"<tr><th>{html.escape(str(col))}</th><td>{html.escape(safe_text(row.get(col), ''))}</td></tr>")

    page = f"""<!DOCTYPE html><html><head><title>FRIS Grid {html.escape(gid)}</title><meta name='viewport' content='width=device-width,initial-scale=1'>{BASE_STYLE}</head><body style='padding:24px'>
    <div class='box'><a class='btn' href='/'>Dashboard</a><a class='btn' href='/grids'>All Grid Info</a><a class='btn' href='/download/csv'>Download CSV</a><h1>FRIS Grid Details: {html.escape(gid)}</h1><div class='watch-note'><b>Ecology status:</b> {html.escape(eco['status'])}. {html.escape(eco['inference'])}</div>{cards}</div>
    <div class='box'><h2>All available dashboard fields for this grid</h2><div class='table-wrap'><table><tbody>{''.join(all_rows)}</tbody></table></div></div>
    </body></html>"""
    del df
    gc.collect()
    return Response(page, mimetype="text/html")


@app.route("/watchlist")
def watchlist_page():
    df = read_csv_light()
    table = build_watchlist_table(df, MAX_WATCH_ROWS)
    page = f"""<!DOCTYPE html><html><head><title>FRIS Watch-List</title><meta name='viewport' content='width=device-width,initial-scale=1'>{BASE_STYLE}</head><body style='padding:24px'><div class='box'><a class='btn' href='/'>Dashboard</a><a class='btn' href='/grids'>All Grid Info</a><h1>🟣 FRIS Ecological Watch-List</h1><div class='watch-note'>Ecological anomaly, chronic/repeated stress, fire-check, moisture stress, vegetation stress, and disturbance watch grids.</div>{table}</div></body></html>"""
    del df
    gc.collect()
    return Response(page, mimetype="text/html")


def make_summary_payload(df):
    lat_col, lon_col = find_lat_lon_columns(df)
    return {
        "status": "running",
        "server_time_ist": format_ist(ist_now()),
        "csv_found": os.path.exists(CSV_FILE),
        "geojson_found": os.path.exists(GEOJSON_FILE),
        "map_found": os.path.exists(MAP_FILE),
        "csv_path": CSV_FILE,
        "geojson_path": GEOJSON_FILE,
        "map_path": MAP_FILE,
        "csv_last_update": get_file_update_time(CSV_FILE),
        "csv_age": get_file_age_minutes(CSV_FILE),
        "next_expected_run": next_expected_run(),
        "total_grids": len(df) if df is not None else 0,
        "estimated_operational_area_ha": estimate_area_ha(df),
        "high_risk_grids": count_contains(df, ["final_priority", "risk_class", "priority"], "HIGH"),
        "critical_risk_grids": count_contains(df, ["final_priority", "risk_class", "priority"], "CRITICAL"),
        "active_fire_signal_grids": count_fire_rows(df),
        "fire_risk_or_check_grids": count_fire_risk_rows(df),
        "field_verification_required_grids": count_field_required(df),
        "ecological_watchlist_count": count_watchlist(df),
        "csv_lat_column_found": lat_col,
        "csv_lon_column_found": lon_col,
    }


@app.route("/health")
def health():
    df = read_csv_light()
    result = make_summary_payload(df)
    if df is None:
        result["csv_error"] = _CSV_CACHE.get("error")
    del df
    gc.collect()
    return jsonify(result)


@app.route("/api/summary")
def api_summary():
    df = read_csv_light()
    result = make_summary_payload(df)
    del df
    gc.collect()
    return jsonify(result)


@app.route("/api/top-priority")
def api_top_priority():
    df = read_csv_light()
    work = sorted_priority_df(df, 50)
    rows = []
    for _, row in work.iterrows():
        rows.append({
            "grid_id": safe_text(row.get("grid_id")),
            "priority": safe_text(row.get("final_priority", row.get("risk_class", row.get("priority")))),
            "risk_score": safe_float(row.get("final_risk_score", row.get("risk_score"))),
            "ndvi": safe_float(row.get("ndvi")),
            "ndmi": safe_float(row.get("ndmi")),
            "fire": fire_display(row),
            "watch": classify_ecological_watch(row),
            "why_go": make_why_go(row),
            "action": make_action(row),
            "grid_detail_url": grid_detail_href(row),
            "google_maps_url": google_maps_href(row),
        })
    del df
    gc.collect()
    return jsonify(rows)


@app.route("/api/all-grids")
def api_all_grids():
    df = read_csv_light()
    if df is None or df.empty:
        return jsonify([])
    limit = env_int("API_ALL_GRIDS_LIMIT", 200, low=20, high=1000)
    work = df.copy()
    work["_rank"] = work.apply(priority_rank, axis=1)
    work = work.sort_values("_rank", ascending=False).head(limit)
    rows = []
    for _, row in work.iterrows():
        rows.append({
            "grid_id": safe_text(row.get("grid_id")),
            "priority": safe_text(row.get("final_priority", row.get("risk_class", row.get("priority")))),
            "watch": classify_ecological_watch(row),
            "forest_pct": safe_float(row.get("forest_pct")),
            "ndvi": safe_float(row.get("ndvi")),
            "ndmi": safe_float(row.get("ndmi")),
            "fire": fire_display(row),
            "action": make_action(row),
            "grid_detail_url": grid_detail_href(row),
        })
    del df
    gc.collect()
    return jsonify(rows)


@app.route("/debug")
def debug():
    df = read_csv_light()
    payload = make_summary_payload(df)
    payload["data_dirs_checked"] = _data_dirs()
    payload["columns_loaded"] = list(df.columns) if df is not None else []
    payload["csv_cache_error"] = _CSV_CACHE.get("error")
    del df
    gc.collect()
    return Response(json.dumps(payload, indent=2, default=str), mimetype="application/json")


@app.errorhandler(Exception)
def handle_any_error(exc):
    traceback.print_exc()
    return Response(
        f"FRIS dashboard error: {html.escape(str(exc))}",
        status=500,
        mimetype="text/plain",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
