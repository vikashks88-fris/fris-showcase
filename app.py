# FRIS DASHBOARD V37 - corrected popup risk + visible All Grid Info panel
# Render/local ready. Put this app.py with fris_latest.csv, fris_latest.geojson and
# fris_latest_map.html in project root, data/, output/, or set FRIS_DATA_DIR.

from flask import Flask, Response, jsonify, send_file, request
import os
import math
import html
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


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

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

# Broad but controlled list. Full CSV is still available from Download CSV.
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


# -----------------------------------------------------------------------------
# Basic helpers
# -----------------------------------------------------------------------------

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
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def safe_text(value, default="N/A"):
    try:
        if value is None or pd.isna(value):
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


# -----------------------------------------------------------------------------
# CSV loading
# -----------------------------------------------------------------------------

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


def estimate_area_ha(df):
    value = sum_first_available_numeric(df, ["effective_forest_area_ha", "forest_area_ha", "area_ha"])
    if value is not None and value > 0:
        return value
    return float(len(df) * 100) if df is not None else None


# -----------------------------------------------------------------------------
# Fire logic
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# Ecology/watch/action logic
# -----------------------------------------------------------------------------

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
    return {"status": status, "inference": watch["reason"], "recommendation": watch["action"]}


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
    score += safe_float(row.get("final_risk_score", row.get("risk_score")), 0) or 0
    ndmi = safe_float(row.get("ndmi"))
    ndvi = safe_float(row.get("ndvi"))
    if ndmi is not None and ndmi < -0.10:
        score += 40
    if ndvi is not None and ndvi < 0.35:
        score += 30
    return float(score)


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


# -----------------------------------------------------------------------------
# Links and tables
# -----------------------------------------------------------------------------

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
    work["_grid_info_rank"] = work.apply(priority_rank, axis=1)
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
        level = safe_text(watch.get("level"), "LOW").upper()
        level_class = "watch-high" if level == "HIGH" else "watch-medium" if level == "MEDIUM" else "watch-low"
        rows.append(f"""
        <tr>
            <td><b>{e(row.get('grid_id'))}</b></td>
            <td>{e(row.get('final_priority', row.get('risk_class', row.get('priority'))))}<br><small>Score {format_number(row.get('final_risk_score', row.get('risk_score')), 1)}</small></td>
            <td><span class='{level_class}'>{html.escape(level)}</span><br><small>{html.escape(safe_text(watch.get('category')))}</small></td>
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
    return f"""<div class='table-wrap'><table><thead><tr><th>Grid</th><th>Priority</th><th>NDVI</th><th>NDMI</th><th>Fire</th><th>Risk</th><th>Carbon/MRV</th><th>Why go?</th><th>Action</th><th>Information</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"""


def build_watch_table(df, limit=MAX_WATCH_ROWS):
    if df is None or df.empty:
        return "<div class='empty'>CSV not loaded.</div>"
    work = df.copy()
    work["_watch_rank"] = work.apply(watch_rank, axis=1)
    work = work.sort_values("_watch_rank", ascending=False).head(limit)
    rows = []
    for _, row in work.iterrows():
        watch = classify_ecological_watch(row)
        if safe_text(watch.get("level"), "LOW").upper() == "LOW":
            continue
        grid_link = grid_detail_href(row)
        rows.append(f"""
        <tr><td><b>{e(row.get('grid_id'))}</b></td><td>{html.escape(watch['level'])}</td><td>{html.escape(watch['category'])}</td>
        <td>{html.escape(watch['reason'])}</td><td>{html.escape(watch['action'])}</td><td><a href='{grid_link}' target='_blank'>Details</a></td></tr>
        """)
    if not rows:
        return "<div class='empty'>No active watch-list rows detected.</div>"
    return f"""<div class='table-wrap'><table><thead><tr><th>Grid</th><th>Level</th><th>Category</th><th>Reason</th><th>Action</th><th>Information</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"""


# -----------------------------------------------------------------------------
# Saved map overlay + corrected popup compactor
# -----------------------------------------------------------------------------

def build_saved_map_overlay():
    return r"""
    <div id="fris-dashboard-injected-legend">
        <div class="fris-legend-title">FRIS Risk & Patrol Priority Layer</div>
        <div class="fris-legend-sub">Grid color means field priority, not always active fire.</div>
        <div><span class="swatch fire"></span> Active FIRMS / thermal fire</div>
        <div><span class="swatch high"></span> Same-day field verification</div>
        <div><span class="swatch medium"></span> High operational attention</div>
        <div><span class="swatch watch"></span> Ecological watch / repeated stress</div>
        <div><span class="swatch moisture"></span> Moisture/anomaly attention</div>
        <div><span class="swatch low"></span> Stable / routine</div>
        <div class="fris-legend-note">Popup shows only Grid, Risk and Action. Full details are in dashboard tables.</div>
    </div>
    """


def inject_overlay_into_saved_map(map_html):
    extra_css = r"""
    <style id="fris-dashboard-injected-css">
        .leaflet-control-layers, .leaflet-control-zoom, .leaflet-control-scale { z-index: 99999 !important; }
        #fris-dashboard-injected-legend {
            position: absolute !important;
            top: 92px !important;
            left: 18px !important;
            z-index: 99998 !important;
            width: 320px !important;
            padding: 14px 16px !important;
            border-radius: 14px !important;
            background: rgba(3, 15, 7, 0.86) !important;
            border: 1px solid rgba(223, 255, 0, 0.35) !important;
            color: #ffffff !important;
            font-family: Arial, sans-serif !important;
            font-size: 12.5px !important;
            line-height: 1.45 !important;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.35) !important;
        }
        .fris-legend-title { color: #dfff00; font-weight: 900; font-size: 15px; margin-bottom: 4px; }
        .fris-legend-sub { color: #d6e9c0; font-size: 11.5px; margin-bottom: 8px; }
        .fris-legend-note { margin-top: 10px; padding: 8px; border-radius: 10px; background: rgba(223,255,0,0.12); color: #d6e9c0; font-size: 11.5px; }
        .swatch { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 7px; vertical-align: -1px; border: 1px solid rgba(255,255,255,0.45); }
        .swatch.fire { background: #ef4444; }
        .swatch.high { background: #f97316; }
        .swatch.medium { background: #facc15; }
        .swatch.watch { background: #a855f7; }
        .swatch.moisture { background: #3b82f6; }
        .swatch.low { background: #22c55e; }
        .leaflet-popup-content-wrapper { border-radius: 12px !important; box-shadow: 0 10px 28px rgba(0,0,0,0.35) !important; }
        .leaflet-popup-content {
            max-width: 210px !important;
            min-width: 150px !important;
            margin: 10px 12px !important;
            font-family: Arial, sans-serif !important;
            font-size: 12px !important;
            line-height: 1.35 !important;
        }
        .fris-mini-popup { min-width: 150px; max-width: 210px; color: #102000; }
        .fris-mini-grid { font-size: 13px; font-weight: 800; margin-bottom: 6px; color: #173f18; }
        .fris-mini-row { margin: 3px 0; white-space: normal; }
        .fris-mini-risk { display: inline-block; padding: 2px 7px; border-radius: 999px; font-weight: 800; background: #eef5dc; color: #173f18; }
        .fris-mini-risk.critical { background: #fee2e2; color: #7f1d1d; }
        .fris-mini-risk.high { background: #ffedd5; color: #9a3412; }
        .fris-mini-risk.medium { background: #fef3c7; color: #92400e; }
        .fris-mini-risk.low { background: #dcfce7; color: #166534; }
        .fris-mini-detail-link {
            display: inline-block; margin-top: 7px; padding: 6px 8px; border-radius: 9px;
            background: #173f18; color: #dfff00 !important; text-decoration: none; font-weight: 800; font-size: 11.5px;
        }
        .fris-mini-detail-link:hover { background: #102000; color: #ffffff !important; }
        @media (max-width: 700px) {
            #fris-dashboard-injected-legend { top: 62px !important; left: 10px !important; width: 285px !important; font-size: 11.5px !important; }
            .leaflet-popup-content { max-width: 185px !important; }
        }
    </style>
    """

    # This script is the important correction. It does NOT trust the first LOW label.
    # It first checks stronger operational evidence: fire, field verification,
    # chronic/repeated stress, disturbance, anomaly and numeric risk score.
    compact_popup_script = r"""
    <script id="fris-dashboard-popup-compactor">
    (function () {
        function htmlEscape(value) {
            return String(value || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        function cleanText(value) {
            return String(value || '').replace(/\s+/g, ' ').trim();
        }

        function firstMatch(text, patterns) {
            for (var i = 0; i < patterns.length; i++) {
                var match = text.match(patterns[i]);
                if (match && match[1]) return cleanText(match[1]);
                if (match && match[0]) return cleanText(match[0]);
            }
            return '';
        }

        function extractNumberAfter(text, labels) {
            for (var i = 0; i < labels.length; i++) {
                var re = new RegExp(labels[i] + "\\s*[:=\\-]?\\s*([0-9]+(?:\\.[0-9]+)?)", "i");
                var m = text.match(re);
                if (m && m[1]) {
                    var n = parseFloat(m[1]);
                    if (!isNaN(n)) return n;
                }
            }
            return null;
        }

        function hasNegativeFireText(text) {
            return /\bNO[_\s-]*(FIRE|ACTIVE|THERMAL)\b|NO ACTIVE|NO FIRE|NOT DETECTED|ACTIVE\s*FIRE\s*[:=\-]?\s*(0|FALSE|NO)\b|FIRE\s*COUNT\s*[:=\-]?\s*0\b|FRP\s*[:=\-]?\s*0\b/i.test(text);
        }

        function hasActiveFireEvidence(text) {
            var fireCount = extractNumberAfter(text, ['Fire Count', 'fire_count', 'recent_fire_count', 'firms_count', 'FIRMS Count']);
            if (fireCount !== null && fireCount > 0) return true;

            var frp = extractNumberAfter(text, ['FRP', 'fire_frp_max', 'firms_frp_max', 'Fire FRP', 'Max FRP']);
            if (frp !== null && frp > 0) return true;

            if (/ACTIVE\s*FIRE\s*[:=\-]?\s*(1|TRUE|YES|ACTIVE|DETECTED)\b/i.test(text)) return true;
            if (/FIRE[_\s-]*DETECTED|RECENT[_\s-]*FIRE|THERMAL[_\s-]*ANOMALY/i.test(text) && !hasNegativeFireText(text)) return true;

            return false;
        }

        function extractLabelledRisk(text) {
            var labelled = firstMatch(text, [
                /(?:Risk|Priority|final_priority|risk_class|Final Priority|Final Risk|Operational Priority)\s*[:=\-]\s*(CRITICAL|VERY HIGH|VERY_HIGH|HIGH|MEDIUM|MODERATE|LOW|NORMAL|ROUTINE)/i,
                /\b(CRITICAL|VERY HIGH|VERY_HIGH|HIGH|MEDIUM|MODERATE|LOW)\s+(?:RISK|PRIORITY)\b/i,
                /\b(RISK|PRIORITY)\s+(CRITICAL|VERY HIGH|VERY_HIGH|HIGH|MEDIUM|MODERATE|LOW)\b/i
            ]).toUpperCase();

            if (!labelled) return '';
            if (labelled.indexOf('CRITICAL') >= 0 || labelled.indexOf('VERY') >= 0) return 'CRITICAL';
            if (labelled.indexOf('HIGH') >= 0) return 'HIGH';
            if (labelled.indexOf('MEDIUM') >= 0 || labelled.indexOf('MODERATE') >= 0) return 'MEDIUM';
            if (labelled.indexOf('LOW') >= 0 || labelled.indexOf('NORMAL') >= 0 || labelled.indexOf('ROUTINE') >= 0) return 'LOW';
            return '';
        }

        function extractRisk(text) {
            var upper = String(text || '').toUpperCase();
            var labelledRisk = extractLabelledRisk(text);

            // Trust explicit stronger labels, but do not blindly trust LOW.
            if (labelledRisk === 'CRITICAL' || labelledRisk === 'HIGH' || labelledRisk === 'MEDIUM') return labelledRisk;

            var score = extractNumberAfter(text, [
                'Final Risk', 'final_risk_score', 'Risk Score', 'risk_score', 'Operational Score', 'final risk'
            ]);
            if (score !== null) {
                // Some old maps store 0-1 score; dashboard stores 0-100 score.
                if (score > 0 && score <= 1) score = score * 100;
                if (score >= 75) return 'CRITICAL';
                if (score >= 55) return 'HIGH';
                if (score >= 35) return 'MEDIUM';
            }

            if (hasActiveFireEvidence(text)) return 'CRITICAL';

            if (/CRITICAL|SAME-DAY|SAME DAY|24 HOURS|HIGH_ECOLOGICAL_VERIFICATION|IMMEDIATE FIELD/i.test(text)) return 'HIGH';

            if (/FIELD VERIFICATION|FIELD_VERIFICATION|VERIFY REQUIRED|PRIORITY PATROL|FIELD CHECK/i.test(text)) return 'HIGH';

            if (/CHRONIC|REPEATED|DEGRADATION|WATCH|HISTORICAL DISTURBANCE|VEGETATION STRESS|MOISTURE STRESS|ANOMALY|DRYNESS|STRESS|DRY_STRESS/i.test(text)) return 'MEDIUM';

            if (/\bHIGH\b/i.test(text) && !/LOW_MRV_CONFIDENCE|LOW_RADAR|LOW CONFIDENCE|LOW_MATURE|LOW_3D/i.test(text)) return 'HIGH';

            if (/\bMEDIUM\b|\bMODERATE\b/i.test(text)) return 'MEDIUM';

            return 'LOW';
        }

        function extractAction(text, risk) {
            if (hasActiveFireEvidence(text)) return 'Immediate fire verification';
            if (risk === 'CRITICAL') return 'Immediate field verification';
            if (risk === 'HIGH') return 'Field verification';
            if (risk === 'MEDIUM') return 'Monitor / field check if repeated';
            return 'Routine monitoring';
        }

        function riskClass(risk) {
            if (risk === 'CRITICAL') return 'critical';
            if (risk === 'HIGH') return 'high';
            if (risk === 'MEDIUM' || risk === 'MODERATE') return 'medium';
            return 'low';
        }

        function compactOnePopup(el) {
            try {
                if (!el || el.getAttribute('data-fris-compact-done') === '1') return;
                var text = cleanText(el.innerText || el.textContent || '');
                if (!text || text.length < 8) return;

                var grid = firstMatch(text, [/\b[A-Z]{1,4}[-_]\d{1,4}[-_]\d{1,4}\b/i, /Grid\s*(?:ID)?\s*[:=\-]\s*([A-Za-z0-9_\-]+)/i]);
                if (!grid) grid = 'Selected grid';
                grid = grid.replace(/_/g, '-');

                var risk = extractRisk(text);
                if (risk === 'MODERATE') risk = 'MEDIUM';
                var action = extractAction(text, risk);
                var cls = riskClass(risk);

                var detailLink = /^GD-/i.test(grid)
                    ? '<a class="fris-mini-detail-link" href="/grid/' + encodeURIComponent(grid) + '" target="_blank" rel="noopener">Open grid details</a>'
                    : '';

                el.innerHTML = '' +
                    '<div class="fris-mini-popup">' +
                    '<div class="fris-mini-grid">' + htmlEscape(grid) + '</div>' +
                    '<div class="fris-mini-row"><b>Risk:</b> <span class="fris-mini-risk ' + htmlEscape(cls) + '">' + htmlEscape(risk) + '</span></div>' +
                    '<div class="fris-mini-row"><b>Action:</b> ' + htmlEscape(action) + '</div>' +
                    detailLink +
                    '</div>';
                el.setAttribute('data-fris-compact-done', '1');
            } catch (err) {
                if (window.console && console.debug) console.debug('FRIS popup compact skipped:', err);
            }
        }

        function compactOneTooltip(el) {
            try {
                if (!el || el.getAttribute('data-fris-tooltip-fixed') === '1') return;
                var text = cleanText(el.innerText || el.textContent || '');
                if (!text || text.length < 8) return;
                var grid = firstMatch(text, [/\b[A-Z]{1,4}[-_]\d{1,4}[-_]\d{1,4}\b/i, /Grid\s*(?:ID)?\s*[:=\-]\s*([A-Za-z0-9_\-]+)/i]);
                if (!grid) return;
                grid = grid.replace(/_/g, '-');
                var risk = extractRisk(text);
                if (risk === 'MODERATE') risk = 'MEDIUM';
                var label = '';
                if (/HISTORICAL DISTURBANCE/i.test(text)) label = 'Historical Disturbance';
                else if (/CHRONIC/i.test(text)) label = 'Chronic Grid';
                else if (/REPEATED|DEGRADATION/i.test(text)) label = 'Repeated Stress';
                else if (/MOISTURE|DRY/i.test(text)) label = 'Moisture Watch';
                else if (/VEGETATION|STRESS/i.test(text)) label = 'Vegetation Stress';
                else if (hasActiveFireEvidence(text)) label = 'Active Fire';
                else label = 'FRIS Attention';
                el.innerHTML = htmlEscape(grid + ' | ' + label + ' | Risk: ' + risk);
                el.setAttribute('data-fris-tooltip-fixed', '1');
            } catch (err) {}
        }

        function compactAll() {
            var popups = document.querySelectorAll('.leaflet-popup-content');
            for (var i = 0; i < popups.length; i++) compactOnePopup(popups[i]);
            var tips = document.querySelectorAll('.leaflet-tooltip');
            for (var j = 0; j < tips.length; j++) compactOneTooltip(tips[j]);
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', compactAll);
        } else {
            compactAll();
        }

        var observer = new MutationObserver(function () { compactAll(); });
        observer.observe(document.documentElement || document.body, { childList: true, subtree: true });
    })();
    </script>
    """

    if "</head>" in map_html:
        map_html = map_html.replace("</head>", extra_css + "\n</head>", 1)
    else:
        map_html = extra_css + map_html

    overlay_html = build_saved_map_overlay()
    if "</body>" in map_html:
        return map_html.replace("</body>", overlay_html + compact_popup_script + "\n</body>", 1)
    return map_html + overlay_html + compact_popup_script


# -----------------------------------------------------------------------------
# HTML styling
# -----------------------------------------------------------------------------

BASE_STYLE = r"""
<style>
*{box-sizing:border-box;font-family:Arial,sans-serif}body{margin:0;background:#061307;color:white}.layout{display:flex;min-height:100vh}.sidebar{width:270px;padding:25px;background:linear-gradient(180deg,#173f18,#071507);border-right:1px solid rgba(255,255,255,.15)}.logo h1{color:#dfff00;font-size:38px;margin:0}.logo p{color:#c6ff6b;font-size:13px;margin:4px 0 30px}.nav{padding:15px;margin-bottom:13px;border-radius:15px;background:rgba(255,255,255,.12);font-weight:bold}.nav.active{background:#dfff00;color:#102000}.nav a{color:inherit;text-decoration:none;display:block}.side-card,.map-card,.card,.table-card,.box{background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.18);border-radius:24px;padding:18px}.side-card{margin-top:25px;font-size:14px;line-height:1.7}.ok{color:#dfff00;font-weight:bold}.bad{color:#ff6b6b;font-weight:bold}.main{flex:1;padding:25px}.topbar{display:grid;grid-template-columns:repeat(3,1fr) auto;gap:15px;align-items:center;padding:18px;border-radius:22px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.18);margin-bottom:22px}.time-box{font-size:14px;line-height:1.4}.time-box b{display:block}.time-box span,.value,td a,.box a{color:#dfff00;font-weight:bold}.btn{display:inline-block;background:#dfff00;color:#102000!important;padding:12px 16px;border-radius:14px;text-decoration:none;font-weight:bold;margin:4px;border:0;cursor:pointer}.btn.disabled{background:rgba(255,255,255,.18);color:#8a968a!important}.content{display:grid;grid-template-columns:1fr 340px;gap:22px}.map-frame{width:100%;height:620px;border:0;border-radius:18px;background:#1b5525;overflow:hidden}.right{display:flex;flex-direction:column;gap:15px}.row{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.12);font-size:14px}.table-card{margin-top:22px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th{background:rgba(223,255,0,.18);color:#dfff00;text-align:left;padding:10px;white-space:nowrap}td{padding:10px;border-bottom:1px solid rgba(255,255,255,.12);vertical-align:top}small{color:#b9c9b9}.empty{padding:18px;border-radius:15px;background:rgba(255,255,255,.08);color:#cbd5c0}.watch-high,.watch-medium,.watch-low{display:inline-block;padding:3px 8px;border-radius:999px;font-weight:900}.watch-high{background:#fee2e2;color:#991b1b}.watch-medium{background:#fef3c7;color:#92400e}.watch-low{background:#dcfce7;color:#166534}.searchbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:8px 0 14px}.searchbar input{flex:1;min-width:240px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.18);color:white;border-radius:12px;padding:12px}.searchbar select{background:#102000;color:#fff;border:1px solid rgba(255,255,255,.25);border-radius:12px;padding:12px}.pager{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center;margin-top:12px}.pill{display:inline-block;background:rgba(223,255,0,.14);color:#dfff00;border:1px solid rgba(223,255,0,.25);padding:6px 10px;border-radius:999px;font-weight:bold;font-size:12px}.grid-page{max-width:1100px;margin:0 auto;padding:25px}.grid-title{display:flex;justify-content:space-between;gap:12px;align-items:start;flex-wrap:wrap}.grid-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:18px 0}.kv{display:grid;grid-template-columns:230px 1fr;gap:8px;border-bottom:1px solid rgba(255,255,255,.12);padding:8px 0}.kv b{color:#dfff00}@media(max-width:1000px){.layout{display:block}.sidebar{width:100%}.content{grid-template-columns:1fr}.topbar{grid-template-columns:1fr}.grid-cards{grid-template-columns:1fr}.kv{grid-template-columns:1fr}.map-frame{height:520px}}
</style>
"""


def page_shell(title, body, active="dashboard"):
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>{html.escape(title)}</title>{BASE_STYLE}</head><body><div class='layout'><aside class='sidebar'><div class='logo'><h1>FRIS</h1><p>Forest Resilience Information System</p></div><div class='nav {'active' if active=='dashboard' else ''}'><a href='/'>Dashboard</a></div><div class='nav'><a href='/map' target='_blank'>Full Map</a></div><div class='nav'><a href='/download/csv'>Download CSV</a></div><div class='nav'><a href='/download/map'>Download Map</a></div><div class='side-card'><b>District-level forest intelligence</b><br>Satellite, fire, moisture, ecological-memory and patrol-priority support.<br><br><span class='ok'>Popup corrected:</span><br>LOW is no longer forced when watch/anomaly/fire evidence exists.</div></aside><main class='main'>{body}</main></div></body></html>"""


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.route("/")
@app.route("/dashboard")
def dashboard():
    df = read_csv_light()
    q = request.args.get("q", "").strip()
    try:
        page = int(request.args.get("page", 1))
    except Exception:
        page = 1
    try:
        per_page = int(request.args.get("per_page", MAX_GRID_INFO_ROWS))
    except Exception:
        per_page = MAX_GRID_INFO_ROWS

    csv_exists = os.path.exists(CSV_FILE)
    map_exists = os.path.exists(MAP_FILE)
    grid_count = 0 if df is None else len(df)
    area_ha = estimate_area_ha(df) if df is not None else None
    active_fire = count_fire_rows(df)
    fire_risk = count_fire_risk_rows(df)
    field_required = count_field_required(df)
    watch_count = count_watchlist(df)
    avg_ndvi = avg_col(df, "ndvi")
    avg_ndmi = avg_col(df, "ndmi")
    carbon = sum_first_available_numeric(df, ["ecosystem_carbon_co2e_total", "estimated_ecosystem_carbon_ton", "ecosystem_carbon_total_ton"])

    all_grid_table, total, page, total_pages, start, end = build_all_grid_information_table(df, page=page, per_page=per_page, q=q)
    priority_table = build_priority_table(df, MAX_TABLE_ROWS)
    watch_table = build_watch_table(df, MAX_WATCH_ROWS)

    map_src = "/map"
    download_map_btn = "<a class='btn' href='/download/map'>Download Map</a>" if map_exists else "<span class='btn disabled'>Map file missing</span>"
    download_csv_btn = "<a class='btn' href='/download/csv'>Download CSV</a>" if csv_exists else "<span class='btn disabled'>CSV missing</span>"

    body = f"""
    <div class='topbar'>
        <div class='time-box'><b>FRIS Dashboard</b><span>{format_ist(ist_now())}</span></div>
        <div class='time-box'><b>CSV Update</b><span>{html.escape(get_file_age_minutes(CSV_FILE))}</span></div>
        <div class='time-box'><b>Next expected run</b><span>{html.escape(next_expected_run())}</span></div>
        <div>{download_csv_btn}{download_map_btn}</div>
    </div>

    <div class='content'>
        <div class='map-card'>
            <h2>Operational Map</h2>
            <iframe class='map-frame' src='{map_src}'></iframe>
            <small>Popup now recalculates compact risk from stronger evidence first: fire, field-verification, chronic/repeated stress, historical disturbance, moisture/vegetation anomaly, and numeric score.</small>
        </div>
        <div class='right'>
            <div class='card'><h3>🔥 Fire & Patrol</h3><div class='row'><span>Active FIRMS / thermal rows</span><b>{active_fire}</b></div><div class='row'><span>Fire-check / fire-risk rows</span><b>{fire_risk}</b></div><div class='row'><span>Field verification required</span><b>{field_required}</b></div><div class='row'><span>Watch-list / anomaly grids</span><b>{watch_count}</b></div></div>
            <div class='card'><h3>💧 Forest Condition</h3><div class='row'><span>Total grids</span><b>{grid_count}</b></div><div class='row'><span>Estimated area</span><b>{format_number(area_ha, 1, ' ha')}</b></div><div class='row'><span>Average NDVI</span><b>{avg_ndvi}</b></div><div class='row'><span>Average NDMI</span><b>{avg_ndmi}</b></div><div class='row'><span>Soil retention</span><b>{value_counts_html(df, 'soil_moisture_retention_class', 3)}</b></div></div>
            <div class='card'><h3>🟣 Operational Intelligence</h3><p><span class='pill'>All Grid Info visible below</span></p><p>Use search for a grid ID, chronic, repeated, moisture, fire, high, medium, low, or carbon loss.</p><div class='row'><span>Carbon support total</span><b>{format_carbon(carbon)}</b></div></div>
        </div>
    </div>

    <div class='table-card'>
        <h2>Top {MAX_TABLE_ROWS} Patrol Priority Grids</h2>
        {priority_table}
    </div>

    <div class='table-card'>
        <h2>Ecological Watch-List / Anomaly Layer</h2>
        {watch_table}
    </div>

    <div class='table-card'>
        <h2>All Grid Information Layer</h2>
        <form class='searchbar' method='get' action='/'>
            <input name='q' value='{html.escape(q)}' placeholder='Search grid / fire / chronic / repeated / moisture / high / medium / low'>
            <select name='per_page'>
                <option value='20' {'selected' if per_page==20 else ''}>20 rows</option>
                <option value='50' {'selected' if per_page==50 else ''}>50 rows</option>
                <option value='100' {'selected' if per_page==100 else ''}>100 rows</option>
                <option value='200' {'selected' if per_page==200 else ''}>200 rows</option>
            </select>
            <button class='btn' type='submit'>Search</button>
            <a class='btn' href='/'>Reset</a>
        </form>
        <p><span class='pill'>Showing {start}-{end} of {total}</span> <span class='pill'>Page {page} / {total_pages}</span></p>
        {all_grid_table}
        <div class='pager'>
            <div>{'<a class="btn" href="/?q=' + quote(q) + '&per_page=' + str(per_page) + '&page=' + str(page-1) + '">Previous</a>' if page > 1 else '<span class="btn disabled">Previous</span>'}</div>
            <div>{'<a class="btn" href="/?q=' + quote(q) + '&per_page=' + str(per_page) + '&page=' + str(page+1) + '">Next</a>' if page < total_pages else '<span class="btn disabled">Next</span>'}</div>
        </div>
    </div>
    """
    return page_shell("FRIS Dashboard", body)


@app.route("/map")
def map_view():
    if os.path.exists(MAP_FILE):
        try:
            with open(MAP_FILE, "r", encoding="utf-8", errors="ignore") as f:
                map_html = f.read()
            return Response(inject_overlay_into_saved_map(map_html), mimetype="text/html")
        except Exception as exc:
            return Response(f"<h2>Map read error</h2><pre>{html.escape(str(exc))}</pre>", mimetype="text/html", status=500)
    return Response("""
    <html><body style='background:#061307;color:white;font-family:Arial;padding:30px'>
    <h2>FRIS map file not found</h2>
    <p>Put <b>fris_latest_map.html</b> in project root, data/, output/, or set FRIS_DATA_DIR.</p>
    </body></html>
    """, mimetype="text/html", status=404)


@app.route("/grid/<path:grid_id>")
def grid_detail(grid_id):
    df = read_csv_light()
    if df is None or df.empty or "grid_id" not in df.columns:
        return page_shell("Grid Details", "<div class='empty'>CSV not loaded or grid_id column missing.</div>")
    requested = unquote(grid_id).strip()
    mask = df["grid_id"].astype(str).str.upper().str.replace("_", "-", regex=False) == requested.upper().replace("_", "-")
    if not mask.any():
        return page_shell("Grid not found", f"<div class='empty'>Grid not found: {html.escape(requested)}</div>")
    row = df[mask].iloc[0]
    watch = classify_ecological_watch(row)
    inference = make_ecology_inference(row)
    maps = google_maps_href(row)

    cards = f"""
    <div class='grid-cards'>
        <div class='card'><h3>Risk</h3><p><span class='pill'>{html.escape(watch['level'])}</span></p><p>{html.escape(watch['category'])}</p></div>
        <div class='card'><h3>Action</h3><p>{html.escape(make_action(row))}</p><p><a href='{html.escape(maps)}' target='_blank'>Open in Google Maps</a></p></div>
        <div class='card'><h3>Why go?</h3><p>{html.escape(make_why_go(row))}</p></div>
    </div>
    """

    key_fields = [
        ("Grid ID", row.get("grid_id")), ("Watch level", watch.get("level")), ("Watch category", watch.get("category")),
        ("Reason", watch.get("reason")), ("Recommendation", watch.get("action")), ("Ecology status", inference.get("status")),
        ("Forest %", format_number(row.get("forest_pct"), 2, "%")), ("NDVI", format_number(row.get("ndvi"), 4)),
        ("NDMI", format_number(row.get("ndmi"), 4)), ("Health class", row.get("health_class")),
        ("Moisture class", row.get("moisture_class_calibrated", row.get("moisture_class"))),
        ("365-day memory", row.get("ecological_memory_class")), ("Fire", fire_display(row)),
        ("FRP max", row.get("fire_frp_max", row.get("firms_frp_max"))), ("Final priority", row.get("final_priority", row.get("risk_class", row.get("priority")))),
        ("Final risk score", row.get("final_risk_score", row.get("risk_score"))), ("Carbon change status", row.get("carbon_change_status")),
        ("MRV confidence", row.get("mrv_confidence")), ("Estimated trees", row.get("estimated_tree_count")),
        ("Soil type", row.get("soil_type")), ("Soil moisture retention", row.get("soil_moisture_retention_class")),
        ("Elevation", row.get("elevation_m")), ("Slope", row.get("slope_deg")),
    ]
    rows = "".join(f"<div class='kv'><b>{html.escape(str(k))}</b><span>{html.escape(safe_text(v))}</span></div>" for k, v in key_fields)
    all_cols = "".join(f"<div class='kv'><b>{html.escape(str(c))}</b><span>{html.escape(safe_text(row.get(c)))}</span></div>" for c in df.columns if not str(c).startswith("_"))
    body = f"""
    <div class='grid-page'>
        <div class='grid-title'><div><h1>Grid Details: {html.escape(safe_text(row.get('grid_id')))}</h1><p>{html.escape(watch['reason'])}</p></div><div><a class='btn' href='/'>Dashboard</a><a class='btn' href='/map' target='_blank'>Map</a></div></div>
        {cards}
        <div class='table-card'><h2>Important Grid Information</h2>{rows}</div>
        <div class='table-card'><h2>All CSV Columns for this Grid</h2>{all_cols}</div>
    </div>
    """
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>FRIS Grid {html.escape(requested)}</title>{BASE_STYLE}</head><body>{body}</body></html>"


@app.route("/api/summary")
def api_summary():
    df = read_csv_light()
    payload = {
        "csv_file": CSV_FILE,
        "map_file": MAP_FILE,
        "csv_exists": os.path.exists(CSV_FILE),
        "map_exists": os.path.exists(MAP_FILE),
        "csv_error": _CSV_CACHE.get("error"),
        "grid_count": 0 if df is None else len(df),
        "active_fire_rows": count_fire_rows(df),
        "fire_risk_rows": count_fire_risk_rows(df),
        "field_verification_required": count_field_required(df),
        "watchlist_rows": count_watchlist(df),
        "avg_ndvi": avg_col(df, "ndvi"),
        "avg_ndmi": avg_col(df, "ndmi"),
        "updated": get_file_update_time(CSV_FILE),
    }
    return jsonify(payload)


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "time": format_ist(ist_now()), "csv_exists": os.path.exists(CSV_FILE), "map_exists": os.path.exists(MAP_FILE)})


@app.route("/download/csv")
def download_csv():
    if os.path.exists(CSV_FILE):
        return send_file(CSV_FILE, as_attachment=True, download_name="fris_latest.csv")
    return Response("CSV not found", status=404)


@app.route("/download/geojson")
def download_geojson():
    if os.path.exists(GEOJSON_FILE):
        return send_file(GEOJSON_FILE, as_attachment=True, download_name="fris_latest.geojson")
    return Response("GeoJSON not found", status=404)


@app.route("/download/map")
def download_map():
    if os.path.exists(MAP_FILE):
        return send_file(MAP_FILE, as_attachment=True, download_name="fris_latest_map.html")
    return Response("Map not found", status=404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
