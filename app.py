from flask import Flask, Response, jsonify, send_file, request
import os
import json
import html
import gc
import traceback
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def env_int(name, default, low=None, high=None):
    """Read small dashboard limits from environment safely.

    This keeps the live Render dashboard lightweight while still allowing you to
    increase limits later from Render environment variables without editing code.
    """
    try:
        value = int(os.environ.get(name, default))
    except Exception:
        value = int(default)
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def _data_dirs():
    """Return likely FRIS data folders on local PC and Render.

    Earlier FRIS runs saved files in output/, while some Render repos use data/.
    The app now checks both so a missing data/ folder will not break the dashboard.
    You can also set FRIS_DATA_DIR in Render if needed.
    """
    dirs = []
    env_dir = os.environ.get("FRIS_DATA_DIR")
    if env_dir:
        dirs.append(env_dir)
    dirs.extend([
        os.path.join(BASE_DIR, "data"),
        os.path.join(BASE_DIR, "output"),
        BASE_DIR,
    ])
    # keep order, remove duplicates
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
    # default write/display path if file is still missing
    return os.path.join(_data_dirs()[0], filename)


DATA_DIR = _data_dirs()[0]
CSV_FILE = _find_file("fris_latest.csv")
GEOJSON_FILE = _find_file("fris_latest.geojson")
MAP_FILE = _find_file("fris_latest_map.html")
IST = ZoneInfo("Asia/Kolkata")

# Tiny in-process CSV cache. This prevents Render from reading the same CSV
# again for /, /geojson, /health, and /api calls during one page load.
_CSV_CACHE = {"path": None, "mtime": None, "df": None, "error": None}

# Render memory safety limits
MAX_TABLE_ROWS = env_int("MAX_TABLE_ROWS", 20, low=5, high=100)
MAX_WATCH_ROWS = env_int("MAX_WATCH_ROWS", 40, low=10, high=200)
MAX_MAP_FEATURES = env_int("MAX_MAP_FEATURES", 40, low=10, high=150)

IMPORTANT_COLUMNS = [
    # Identity + geometry
    "grid_id", "lat", "lon", "lng", "latitude", "longitude", "center_lat", "center_lon", "center_lng",
    "grid_lat", "grid_lon", "grid_lng", "centroid_lat", "centroid_lon", "centroid_lng", "x", "y",

    # Area + vegetation condition
    "forest_pct", "effective_forest_area_ha", "forest_area_ha", "area_ha",
    "ndvi", "ndmi", "health_class", "moisture_class", "moisture_class_calibrated",
    "rain_adjusted_ndmi_for_moisture", "moisture_reference_source",

    # Priority + operational layer
    "final_priority", "risk_class", "priority", "final_risk_score",
    "operational_attention_label", "operational_attention_class", "operational_attention_reason",
    "field_verification_required", "patrol_action", "google_maps_link",

    # Fire layer: keep old and new FRIS names
    "fire_count", "recent_fire_count", "fire_alert_count", "firms_count", "fire_detected", "active_fire",
    "fire_status", "fire_frp_max", "firms_frp_max", "fire_intensity_class", "fire_age_hours",
    "fire_age_days", "distance_to_fire_km",

    # Disturbance / mining / terrain / soil
    "hansen_treecover2000_pct", "hansen_loss_pct", "mining_pressure_class", "elevation_m", "slope_deg", "terrain_class",
    "soil_type", "soil_moisture_retention_class", "soil_drying_speed", "soil_supported_ecological_stability",

    # Watch-list / ecology inference
    "ecological_watch_category", "watch_category", "ecological_watch_level", "watch_level",
    "ecological_watch_reason", "watch_reason", "ecological_watch_action", "watch_action",
    "ecological_inference", "ecology_inference", "ecology_recommendation", "ecology_status", "field_inference",
    "ecological_verification_reason_hindi",

    # Carbon MRV + opportunity layer
    "agb_ton_per_ha", "gedi_agbd_ton_per_ha", "gedi_biomass_confidence", "carbon_estimation_method",
    "ecosystem_carbon_total_ton", "estimated_ecosystem_carbon_ton", "biomass_carbon_total_ton",
    "carbon_change_ton", "carbon_change_co2e_ton", "carbon_change_from_365d", "carbon_change_status",
    "raw_positive_co2e_change_ton", "carbon_gain_allowed", "carbon_grid_lock_status", "carbon_grid_lock_reason",
    "carbon_opportunity_confidence_factor", "preliminary_carbon_opportunity_ton_co2e",
    "mrv_confidence", "carbon_credit_claim_status",

    # 365-day memory + trees / plantation
    "history_days_available_365d", "ecological_memory_class", "ecological_memory_score",
    "estimated_tree_count", "estimated_tree_density_class", "tree_estimation_confidence",
    "plantation_signal_class", "plantation_signal_score", "plantation_detection_confidence",
    "canopy_change_class",

    # Weather
    "weather_status", "temperature_c", "temperature", "temp_c", "rainfall_current_mm", "rainfall", "rain_mm", "rainfall_24h_mm",
    "wind_speed_kmph", "wind_kmph", "wind_speed", "wind_gust_kmph", "weather_fire_spread_class",
    "weather_provider", "weather_validation_level", "era5_rain_sum_30d_mm", "era5_temp_anomaly_c", "imd_validation_status"
]


def ist_now():
    return datetime.now(IST)


def format_ist(dt):
    return dt.strftime("%d %B %Y, %I:%M:%S %p IST")


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


def build_saved_map_overlay():
    """Small fixed explanation panel injected into the saved FRIS map.

    This does not recolour or rebuild the map. It only writes the meaning of
    the existing colours so officers do not read every yellow/orange grid as fire.
    """
    return """
    <div id="fris-dashboard-injected-legend" style="
        position: fixed;
        top: 72px;
        left: 14px;
        z-index: 999999;
        width: 310px;
        max-width: calc(100vw - 32px);
        background: rgba(4, 18, 7, 0.90);
        color: #ffffff;
        padding: 13px 14px;
        border-radius: 14px;
        border: 1px solid rgba(223, 255, 0, 0.55);
        box-shadow: 0 8px 24px rgba(0,0,0,0.45);
        font-family: Arial, sans-serif;
        font-size: 12.5px;
        line-height: 1.45;
    ">
        <div style="font-size:15px;font-weight:800;color:#dfff00;margin-bottom:6px;">
            FRIS Risk & Patrol Priority Layer
        </div>
        <div style="margin-bottom:7px;">
            This map shows <b>grid-wise risk and patrol priority</b>.
            Colour means <b>field priority</b>, not always active fire.
        </div>
        <div style="display:grid;grid-template-columns:18px 1fr;gap:5px 7px;align-items:center;">
            <span style="width:15px;height:15px;border-radius:4px;background:#ef4444;border:1px solid #fff;display:inline-block;"></span>
            <span><b>Red:</b> active FIRMS / thermal fire</span>
            <span style="width:15px;height:15px;border-radius:4px;background:#f97316;border:1px solid #fff;display:inline-block;"></span>
            <span><b>Orange:</b> fire-check / field verification</span>
            <span style="width:15px;height:15px;border-radius:4px;background:#facc15;border:1px solid #fff;display:inline-block;"></span>
            <span><b>Yellow:</b> high operational attention</span>
            <span style="width:15px;height:15px;border-radius:4px;background:#a855f7;border:1px solid #fff;display:inline-block;"></span>
            <span><b>Purple:</b> ecological watch / repeated stress</span>
            <span style="width:15px;height:15px;border-radius:4px;background:#3b82f6;border:1px solid #fff;display:inline-block;"></span>
            <span><b>Blue:</b> moisture/anomaly attention</span>
            <span style="width:15px;height:15px;border-radius:4px;background:#22c55e;border:1px solid #fff;display:inline-block;"></span>
            <span><b>Green:</b> stable / routine</span>
        </div>
        <div style="
            margin-top:9px;
            padding:7px 8px;
            border-radius:10px;
            background:rgba(223,255,0,0.12);
            color:#f4ffb8;
            font-weight:700;
        ">
            Popup shows only Grid, Risk and Action. Full details remain in tables and CSV.
        </div>
    </div>
    """


def inject_overlay_into_saved_map(map_html):
    """Return saved map HTML with FRIS explanation written inside the map view."""
    if not map_html:
        return map_html

    # Avoid adding the panel twice if the route is refreshed or a map already contains it.
    if "fris-dashboard-injected-legend" in map_html:
        return map_html

    overlay_html = build_saved_map_overlay()

    # Keep the overlay above Leaflet layers.
    extra_css = """
    <style id="fris-dashboard-injected-css">
        .leaflet-control-layers,
        .leaflet-control-zoom,
        .leaflet-control-scale {
            z-index: 99999 !important;
        }
        .leaflet-popup-content-wrapper {
            border-radius: 12px !important;
            box-shadow: 0 10px 28px rgba(0,0,0,0.35) !important;
        }
        .leaflet-popup-content {
            max-width: 210px !important;
            min-width: 150px !important;
            margin: 10px 12px !important;
            font-family: Arial, sans-serif !important;
            font-size: 12px !important;
            line-height: 1.35 !important;
        }
        .fris-mini-popup {
            min-width: 150px;
            max-width: 210px;
            color: #102000;
        }
        .fris-mini-grid {
            font-size: 13px;
            font-weight: 800;
            margin-bottom: 6px;
            color: #173f18;
        }
        .fris-mini-row {
            margin: 3px 0;
            white-space: normal;
        }
        .fris-mini-risk {
            display: inline-block;
            padding: 2px 7px;
            border-radius: 999px;
            font-weight: 800;
            background: #eef5dc;
            color: #173f18;
        }
        .fris-mini-risk.high,
        .fris-mini-risk.critical {
            background: #fee2e2;
            color: #991b1b;
        }
        .fris-mini-risk.medium {
            background: #fef3c7;
            color: #92400e;
        }
        .fris-mini-risk.low {
            background: #dcfce7;
            color: #166534;
        }
        @media (max-width: 700px) {
            #fris-dashboard-injected-legend {
                top: 62px !important;
                left: 10px !important;
                width: 285px !important;
                font-size: 11.5px !important;
            }
            .leaflet-popup-content {
                max-width: 185px !important;
            }
        }
    </style>
    """

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

        function hasNegativeFireText(text) {
            return /\bNO[_\s-]*(FIRE|ACTIVE|THERMAL)\b|NO ACTIVE|NO FIRE|NOT DETECTED/i.test(text);
        }

        function extractRisk(text) {
            var labelled = firstMatch(text, [
                /(?:Risk|Priority|final_priority|risk_class|Final Priority|Final Risk)\s*[:=\-]\s*(CRITICAL|HIGH|MEDIUM|MODERATE|LOW|NORMAL|ROUTINE)/i,
                /\b(CRITICAL|HIGH|MEDIUM|MODERATE|LOW)\s+(?:RISK|PRIORITY)\b/i,
                /\b(RISK|PRIORITY)\s+(CRITICAL|HIGH|MEDIUM|MODERATE|LOW)\b/i
            ]).toUpperCase();

            if (labelled) {
                if (labelled.indexOf('CRITICAL') >= 0) return 'CRITICAL';
                if (labelled.indexOf('HIGH') >= 0) return 'HIGH';
                if (labelled.indexOf('MEDIUM') >= 0 || labelled.indexOf('MODERATE') >= 0) return 'MEDIUM';
                if (labelled.indexOf('LOW') >= 0 || labelled.indexOf('NORMAL') >= 0 || labelled.indexOf('ROUTINE') >= 0) return 'LOW';
            }

            if (/CRITICAL|SAME-DAY|SAME DAY|24 HOURS|FIELD VERIFICATION|HIGH_ECOLOGICAL_VERIFICATION/i.test(text)) return 'HIGH';
            if (/\bHIGH\b/i.test(text) && !/LOW_MRV_CONFIDENCE|LOW_RADAR/i.test(text)) return 'HIGH';
            if (/MEDIUM|MODERATE|WATCH|MONITOR WITHIN 3 DAYS|CHRONIC|REPEATED|DEGRADATION/i.test(text)) return 'MEDIUM';
            return 'LOW';
        }

        function extractAction(text, risk) {
            if (!hasNegativeFireText(text) && /ACTIVE|THERMAL|FIRMS|FRP|FIRE_DETECTED|RECENT_FIRE/i.test(text)) {
                return 'Fire verification';
            }
            if (/FIELD VERIFICATION|FIELD_VERIFICATION|VERIFY|PRIORITY PATROL|24 HOURS|SAME-DAY|SAME DAY|CRITICAL/i.test(text) || risk === 'HIGH' || risk === 'CRITICAL') {
                return 'Field verification';
            }
            if (/WATCH|MONITOR|MEDIUM|MODERATE|CHRONIC|REPEATED|DEGRADATION|STRESS/i.test(text) || risk === 'MEDIUM') {
                return 'Monitor';
            }
            return 'Routine patrolling';
        }

        function compactOnePopup(el) {
            try {
                if (!el || el.getAttribute('data-fris-compact-done') === '1') return;
                var text = cleanText(el.innerText || el.textContent || '');
                if (!text || text.length < 8) return;

                var grid = firstMatch(text, [/\bGD-\d{1,3}-\d{1,3}\b/i, /Grid\s*[:=\-]\s*([A-Za-z0-9_\-]+)/i]);
                if (!grid) grid = 'Selected grid';

                var risk = extractRisk(text);
                var action = extractAction(text, risk);
                var cls = risk.toLowerCase();
                if (risk === 'MODERATE') { risk = 'MEDIUM'; cls = 'medium'; }

                el.innerHTML = '' +
                    '<div class="fris-mini-popup">' +
                    '<div class="fris-mini-grid">' + htmlEscape(grid) + '</div>' +
                    '<div class="fris-mini-row"><b>Risk:</b> <span class="fris-mini-risk ' + htmlEscape(cls) + '">' + htmlEscape(risk) + '</span></div>' +
                    '<div class="fris-mini-row"><b>Action:</b> ' + htmlEscape(action) + '</div>' +
                    '</div>';
                el.setAttribute('data-fris-compact-done', '1');
            } catch (e) {
                if (window.console && console.debug) console.debug('FRIS popup compact skipped:', e);
            }
        }

        function compactAllPopups() {
            var popups = document.querySelectorAll('.leaflet-popup-content');
            for (var i = 0; i < popups.length; i++) compactOnePopup(popups[i]);
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', compactAllPopups);
        } else {
            compactAllPopups();
        }

        var observer = new MutationObserver(function () { compactAllPopups(); });
        observer.observe(document.documentElement || document.body, { childList: true, subtree: true });
    })();
    </script>
    """

    if "</head>" in map_html:
        map_html = map_html.replace("</head>", extra_css + "\n</head>", 1)
    else:
        map_html = extra_css + map_html

    if "</body>" in map_html:
        return map_html.replace("</body>", overlay_html + compact_popup_script + "\n</body>", 1)

    return map_html + overlay_html + compact_popup_script


def next_expected_run():
    now = ist_now()
    morning = now.replace(hour=9, minute=30, second=0, microsecond=0)
    evening = now.replace(hour=19, minute=30, second=0, microsecond=0)
    if now < morning:
        return format_ist(morning)
    if now < evening:
        return format_ist(evening)
    return format_ist((now + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0))


def existing_usecols(path):
    try:
        cols = pd.read_csv(path, nrows=0).columns.tolist()
        return [c for c in IMPORTANT_COLUMNS if c in cols]
    except Exception:
        return None


def read_csv_light():
    """Read FRIS CSV safely and lightly.

    Returns a shallow copy of cached data when the file has not changed.
    This reduces 502 risk on Render caused by repeated CSV loading.
    """
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

        # Normalize column names. This protects against accidental spaces in CSV headers.
        df.columns = [str(c).strip() for c in df.columns]

        _CSV_CACHE.update({"path": CSV_FILE, "mtime": mtime, "df": df, "error": None})
        return df.copy(deep=False)
    except Exception as e:
        _CSV_CACHE["error"] = str(e)
        print("CSV load error:", e)
        traceback.print_exc()
        return None


def json_safe_value(value):
    """Convert pandas/numpy values to normal JSON-safe Python values."""
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
        value = str(value).strip()
        return value if value else default
    except Exception:
        return default


def avg_col(df, col):
    if df is None or df.empty or col not in df.columns:
        return "N/A"
    value = pd.to_numeric(df[col], errors="coerce").mean()
    return "N/A" if pd.isna(value) else round(float(value), 3)


def sum_first_available_col(df, columns):
    if df is None or df.empty:
        return "N/A"
    for col in columns:
        if col in df.columns:
            value = pd.to_numeric(df[col], errors="coerce").sum()
            return "N/A" if pd.isna(value) else value
    return "N/A"


def count_contains(df, columns, keyword):
    """Count unique rows where any of the listed columns contains a keyword.

    The older version added counts column-by-column, which could double-count a
    grid if both final_priority and risk_class contained the same word.
    """
    if df is None or df.empty:
        return 0
    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.upper().str.contains(keyword.upper(), na=False)
    return int(mask.sum())


def is_truthy(value):
    text_value = safe_text(value, "").strip().upper()
    return text_value in {"TRUE", "YES", "Y", "1", "ACTIVE", "DETECTED"}


def _positive_fire_status(value):
    """Return True only for confirmed/recent/active fire text.

    Important dashboard rule:
    - "fire risk" is NOT treated as active fire.
    - "No fire" / "NO_FIRE" / "No active fire" must never become active fire.
    """
    text_value = safe_text(value, "").strip().upper().replace("-", "_").replace(" ", "_")
    if not text_value or text_value in {"N/A", "NONE", "FALSE", "0", "NO", "NO_FIRE", "NO_ACTIVE_FIRE", "NOT_DETECTED"}:
        return False
    if text_value.startswith("NO_") or "NO_FIRE" in text_value or "NO_ACTIVE" in text_value:
        return False
    active_terms = {
        "ACTIVE", "DETECTED", "FIRE_DETECTED", "ACTIVE_FIRE", "RECENT_FIRE",
        "FIRMS_DETECTED", "THERMAL_DETECTED", "THERMAL_ANOMALY", "CONFIRMED"
    }
    return text_value in active_terms


def _positive_fire_risk_text(value):
    """Return True for fire-risk/check wording without calling it active fire."""
    text_value = safe_text(value, "").strip().upper().replace("-", "_").replace(" ", "_")
    if not text_value or text_value in {"N/A", "NONE", "FALSE", "0", "NO", "NO_FIRE", "NO_ACTIVE_FIRE", "NOT_DETECTED"}:
        return False
    if text_value.startswith("NO_") or "NO_FIRE" in text_value or "NO_ACTIVE" in text_value:
        return False
    risk_terms = [
        "FIRE_RISK", "FIRE_CHECK", "FIRE_WATCH", "FIRE_ALERT", "FIRE_INTELLIGENCE",
        "FIRE_PRONE", "BURN_RISK", "THERMAL_RISK", "DRY_FIRE", "SPREAD"
    ]
    if any(term in text_value for term in risk_terms):
        return True
    # Some older FRIS priority labels may simply contain FIRE.
    return "FIRE" in text_value


def row_has_fire(row):
    """Detect ACTIVE/RECENT fire only.

    This function intentionally does NOT use final_priority containing FIRE,
    because that may mean fire-risk / fire-check / dry-stress screening and not
    an actual FIRMS fire point. This fixes the dashboard issue where many grids
    looked like they were burning.
    """
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
    """Detect fire-risk / fire-check condition separately from active fire."""
    if row_has_fire(row):
        return True

    for col in [
        "final_priority", "risk_class", "priority", "operational_attention_label",
        "operational_attention_class", "fire_status", "fire_intensity_class",
        "weather_fire_spread_class", "patrol_action"
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
        if intensity and intensity != "N/A":
            return f"Fire-risk / {intensity}"
        return "Fire-risk / check only"

    return "No active thermal signal"

def count_fire_rows(df):
    if df is None or df.empty:
        return 0
    return int(sum(1 for _, row in df.iterrows() if row_has_fire(row)))


def count_field_required(df):
    if df is None or df.empty:
        return 0
    if "field_verification_required" not in df.columns:
        return 0
    return int(df["field_verification_required"].apply(is_truthy).sum())


def sum_first_available_numeric(df, columns):
    if df is None or df.empty:
        return None
    for col in columns:
        if col in df.columns:
            value = pd.to_numeric(df[col], errors="coerce").sum()
            if not pd.isna(value):
                return float(value)
    return None


def estimate_area_ha(df):
    value = sum_first_available_numeric(df, ["effective_forest_area_ha", "forest_area_ha", "area_ha"])
    if value is not None and value > 0:
        return value
    # FRIS uses 1 km grids. If no area column exists, show operational grid area.
    return float(len(df) * 100) if df is not None else None


def value_counts_html(df, col, limit=4):
    if df is None or df.empty or col not in df.columns:
        return "N/A"
    counts = df[col].fillna("N/A").astype(str).value_counts().head(limit)
    return ", ".join(f"{html.escape(k)}: {int(v)}" for k, v in counts.items())


def format_number(value, decimals=1, suffix=""):
    try:
        return f"{float(value):,.{decimals}f}{suffix}"
    except Exception:
        return "N/A"


def format_carbon(value):
    try:
        return f"{float(value):,.0f} tons"
    except Exception:
        return "N/A"


def get_first_value(df, columns, default=None):
    if df is None or df.empty:
        return default
    for col in columns:
        if col in df.columns:
            values = df[col].dropna()
            if len(values) > 0:
                return values.iloc[0]
    return default


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
        "status": "CSV Weather" if temperature is not None else "Not available in CSV",
        "temperature": format_number(temperature, 1, "°C"),
        "rainfall": format_number(rain_now, 1, " mm"),
        "rainfall_24h": format_number(rain_24h, 1, " mm"),
        "wind": format_number(wind, 1, " km/h"),
        "gust": format_number(gust, 1, " km/h"),
        "spread": safe_text(spread)
    }


def find_lat_lon_columns(df):
    if df is None:
        return None, None
    lat_cols = ["lat", "latitude", "center_lat", "grid_lat", "centroid_lat", "y", "LAT", "Latitude"]
    lon_cols = ["lon", "lng", "longitude", "center_lon", "center_lng", "grid_lon", "grid_lng", "centroid_lon", "centroid_lng", "x", "LON", "Longitude"]
    lat_col = next((c for c in lat_cols if c in df.columns), None)
    lon_col = next((c for c in lon_cols if c in df.columns), None)
    return lat_col, lon_col


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
            "action": existing_action if existing_action and existing_action != "N/A" else "Follow FRIS patrol action and field verification guidance."
        }

    forest_pct = safe_float(row.get("forest_pct"), 0) or 0
    ndvi = safe_float(row.get("ndvi"), 0) or 0
    ndmi = safe_float(row.get("ndmi"), 0) or 0
    hansen_loss = safe_float(row.get("hansen_loss_pct"), 0) or 0
    final_risk = safe_float(row.get("final_risk_score"), 0) or 0
    priority = safe_text(row.get("final_priority", row.get("risk_class", row.get("priority", ""))), "").upper()
    mining_class = safe_text(row.get("mining_pressure_class"), "NONE").upper()
    operational_label = safe_text(row.get("operational_attention_label"), "")
    operational_class = safe_text(row.get("operational_attention_class"), "").upper()
    operational_reason = safe_text(row.get("operational_attention_reason"), "")
    memory_class = safe_text(row.get("ecological_memory_class"), "").upper()
    field_required = is_truthy(row.get("field_verification_required"))

    if row_has_fire(row):
        reason = operational_reason if operational_reason and operational_reason != "N/A" else "Active/recent fire or FIRMS thermal signal is present."
        return {"category": "Fire Verification Alert", "level": "HIGH", "reason": reason, "action": "Immediate or same-day field verification."}

    if "CRITICAL" in priority or (forest_pct >= 70 and ndvi < 0.20):
        return {"category": "Ecological Anomaly Alert", "level": "HIGH", "reason": "Forest extent is meaningful but vegetation health is critically weak.", "action": "Priority ecological field verification before any conclusion."}

    if field_required or "FIELD" in operational_class:
        level = "HIGH" if final_risk >= 70 or "HIGH" in priority else "MEDIUM"
        reason = operational_reason if operational_reason and operational_reason != "N/A" else "Multiple FRIS indicators require ground checking."
        action = safe_text(row.get("patrol_action"), "Follow FRIS patrol action and field verification guidance.")
        return {"category": operational_label if operational_label and operational_label != "N/A" else "Field Verification Watch", "level": level, "reason": reason, "action": action}

    if hansen_loss >= 15 and forest_pct >= 30:
        return {"category": "Historical Disturbance Watch", "level": "MEDIUM", "reason": "Historical forest-loss evidence is elevated for this forest grid.", "action": "Periodic ecological monitoring and disturbance verification."}

    if "REPEATED" in memory_class or "CHRONIC" in memory_class:
        return {"category": "Repeated Stress Watch", "level": "MEDIUM", "reason": "365-day FRIS memory shows repeated ecological stress pattern.", "action": "Compare with previous runs and verify persistent stress causes."}

    if forest_pct >= 30 and ndvi < 0.40:
        return {"category": "Vegetation Stress Watch", "level": "MEDIUM", "reason": "Forest grid shows stressed vegetation signal.", "action": "Monitor in next runs and verify if stress continues."}

    if mining_class in ["HIGH", "VERY_HIGH"] and forest_pct >= 30:
        return {"category": "Mining Influence Watch", "level": "MEDIUM", "reason": "Grid is near mining influence zone; this does not prove illegal activity.", "action": "Routine patrol and long-term trend monitoring."}

    if ndmi < -0.10 and forest_pct >= 30:
        return {"category": "Moisture Stress Watch", "level": "MEDIUM", "reason": "Forest grid shows weak moisture signal.", "action": "Monitor moisture trend and rainfall context."}

    return {"category": "Stable Forest Zone", "level": "LOW", "reason": "No major ecological watch-list condition detected.", "action": "Routine patrolling."}


def watch_rank(row):
    watch = classify_ecological_watch(row)
    rank = 0
    if row_has_fire(row):
        rank += 7000
    if watch["level"] == "HIGH":
        rank += 5000
    elif watch["level"] == "MEDIUM":
        rank += 2500
    rank += (safe_float(row.get("hansen_loss_pct"), 0) or 0) * 10
    rank += (safe_float(row.get("final_risk_score"), 0) or 0)
    if (safe_float(row.get("ndvi"), 1) or 1) < 0.20:
        rank += 300
    return rank


def make_ecology_inference(row):
    watch = classify_ecological_watch(row)
    engine_inference = safe_text(row.get("ecological_inference", row.get("ecology_inference", "")), "")
    engine_recommendation = safe_text(row.get("ecology_recommendation", row.get("patrol_action", "")), "")
    engine_status = safe_text(row.get("ecology_status", row.get("final_priority", "")), "")
    if engine_inference and engine_inference != "N/A":
        return {"status": engine_status or watch["category"], "category": watch["category"], "level": watch["level"], "inference": engine_inference, "recommendation": engine_recommendation or "Follow field verification guidance."}
    return {"status": watch["category"], "category": watch["category"], "level": watch["level"], "inference": watch["reason"], "recommendation": watch["action"]}


def patrol_priority_rank(row):
    """Rank grids for the dashboard map using officer patrol priority.

    Highest first:
    1. active/fire-check grids
    2. same-day / 24-hour patrol actions
    3. field-verification-required grids
    4. HIGH/CRITICAL final priority and final risk score
    5. repeated stress, Hansen loss, mining influence, NDVI/NDMI stress
    """
    priority = safe_text(row.get("final_priority", row.get("risk_class", row.get("priority", ""))), "").upper()
    action = safe_text(row.get("patrol_action"), "").upper()
    operational_class = safe_text(row.get("operational_attention_class"), "").upper()
    watch = classify_ecological_watch(row)
    mining_class = safe_text(row.get("mining_pressure_class"), "").upper()
    memory_class = safe_text(row.get("ecological_memory_class"), "").upper()

    rank = 0

    # 1) Active fire comes first; fire-risk/check stays high but separate.
    if row_has_fire(row):
        rank += 100000
    elif row_has_fire_risk(row):
        rank += 45000

    # 2) Explicit patrol instruction from FRIS engine.
    if "IMMEDIATE" in action or "SAME-DAY" in action or "SAME DAY" in action:
        rank += 50000
    elif "24 HOUR" in action or "24 HOURS" in action or "PRIORITY PATROL" in action:
        rank += 35000
    elif "MONITOR WITHIN 3 DAYS" in action:
        rank += 12000
    elif "ROUTINE" in action:
        rank += 1000

    # 3) Field verification layer.
    if is_truthy(row.get("field_verification_required")) or "FIELD" in operational_class:
        rank += 20000

    # 4) Priority and watch level.
    if "CRITICAL" in priority:
        rank += 18000
    if "HIGH" in priority:
        rank += 14000
    elif "MEDIUM" in priority or "MODERATE" in priority:
        rank += 6000

    if watch.get("level") == "HIGH":
        rank += 10000
    elif watch.get("level") == "MEDIUM":
        rank += 4000

    # 5) Supporting risk evidence.
    rank += (safe_float(row.get("final_risk_score"), 0) or 0) * 100
    rank += (safe_float(row.get("hansen_loss_pct"), 0) or 0) * 40

    if mining_class == "VERY_HIGH":
        rank += 3000
    elif mining_class == "HIGH":
        rank += 1500

    if "CHRONIC" in memory_class:
        rank += 3000
    elif "REPEATED" in memory_class or "DEGRADATION" in memory_class:
        rank += 1800

    ndvi = safe_float(row.get("ndvi"))
    ndmi = safe_float(row.get("ndmi"))
    if ndvi is not None and ndvi < 0.35:
        rank += 1500
    if ndmi is not None and ndmi < 0.10:
        rank += 1200

    return rank


def map_display_rank(row):
    """Rank grids for the dashboard map using both patrol priority and ecological watch-list evidence.

    This keeps the web map light but ensures watch-list grids are not hidden behind
    ordinary priority sorting. Fire and urgent patrol grids still remain first.
    """
    watch = classify_ecological_watch(row)
    rank = patrol_priority_rank(row)

    # Give clear map visibility to ecological watch-list grids.
    if watch.get("category") != "Stable Forest Zone":
        rank += 8000
    if watch.get("level") == "HIGH":
        rank += 12000
    elif watch.get("level") == "MEDIUM":
        rank += 6000

    # Keep repeated stress and historical disturbance visible for field planning.
    memory_class = safe_text(row.get("ecological_memory_class"), "").upper()
    if "CHRONIC" in memory_class:
        rank += 5000
    elif "REPEATED" in memory_class or "DEGRADATION" in memory_class:
        rank += 3000

    return rank


def priority_rank(row):
    # Backward-compatible name used by tables and APIs.
    return patrol_priority_rank(row)


def make_why_go(row):
    reasons = []
    if row_has_fire(row):
        reasons.append("active/recent thermal signal needs verification")
    elif row_has_fire_risk(row):
        reasons.append("fire-risk/check condition needs field review")
    priority = safe_text(row.get("final_priority", row.get("risk_class", row.get("priority", ""))), "").upper()
    if priority:
        reasons.append(f"priority is {priority}")
    operational_reason = safe_text(row.get("operational_attention_reason"), "")
    if operational_reason and operational_reason != "N/A":
        reasons.append(operational_reason)
    ndmi = safe_float(row.get("ndmi"))
    ndvi = safe_float(row.get("ndvi"))
    if ndmi is not None and ndmi < 0.10:
        reasons.append("low NDMI indicates dryness")
    if ndvi is not None and ndvi < 0.35:
        reasons.append("NDVI indicates vegetation stress")
    return "; ".join(reasons[:4]) + "." if reasons else "Routine patrolling grid."


def make_action(row):
    engine_action = safe_text(row.get("patrol_action"), "")
    if engine_action and engine_action != "N/A":
        return engine_action
    if row_has_fire(row):
        return "Immediate active-fire verification"
    priority = safe_text(row.get("final_priority", row.get("risk_class", row.get("priority", ""))), "").upper()
    if "CRITICAL" in priority:
        return "Same-day patrol required"
    if row_has_fire_risk(row):
        return "Fire-risk field check / patrol"
    if "HIGH" in priority:
        return "Patrol within 24 hours"
    ndmi = safe_float(row.get("ndmi"))
    if ndmi is not None and ndmi < 0.10:
        return "Moisture stress check"
    return "Routine patrolling"


def sorted_priority_df(df, limit):
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["_rank"] = work.apply(priority_rank, axis=1)
    return work.sort_values("_rank", ascending=False).head(limit)


def build_priority_table(df, limit=MAX_TABLE_ROWS):
    work = sorted_priority_df(df, limit)
    if work.empty:
        return "<div class='empty'>CSV not loaded.</div>"
    rows = ""
    for _, row in work.iterrows():
        maps = safe_text(row.get("google_maps_link"), "#")
        maps_link = maps if maps.startswith("http") else "#"
        carbon_status = safe_text(row.get("carbon_change_status"), "N/A")
        mrv = safe_text(row.get("mrv_confidence"), "N/A")
        rows += f"""
        <tr><td><b>{html.escape(safe_text(row.get('grid_id')))}</b></td><td>{html.escape(safe_text(row.get('final_priority', row.get('risk_class'))))}</td>
        <td>{format_number(row.get('ndvi'), 3)}</td><td>{format_number(row.get('ndmi'), 3)}</td><td>{html.escape(fire_display(row))}</td>
        <td>{format_number(row.get('final_risk_score'), 1)}</td><td>{html.escape(carbon_status)}<br><small>{html.escape(mrv)}</small></td>
        <td>{html.escape(make_why_go(row))}</td><td>{html.escape(make_action(row))}</td>
        <td><a href='{html.escape(maps_link)}' target='_blank'>Open</a></td></tr>"""
    return f"<div class='table-wrap'><table><thead><tr><th>Grid</th><th>Priority</th><th>NDVI</th><th>NDMI</th><th>Fire</th><th>Risk</th><th>Carbon/MRV</th><th>Why go?</th><th>Action</th><th>Map</th></tr></thead><tbody>{rows}</tbody></table></div>"


def build_watchlist_table(df, limit=MAX_WATCH_ROWS):
    if df is None or df.empty:
        return "<div class='empty'>CSV not loaded.</div>"
    work = df.copy()
    work["_watch_rank"] = work.apply(watch_rank, axis=1)
    work["_watch_category"] = work.apply(lambda r: classify_ecological_watch(r)["category"], axis=1)
    work = work[work["_watch_category"] != "Stable Forest Zone"].sort_values("_watch_rank", ascending=False).head(limit)
    if work.empty:
        return "<div class='empty'>No ecological watch-list grid found.</div>"
    rows = ""
    for _, row in work.iterrows():
        watch = classify_ecological_watch(row)
        maps = safe_text(row.get("google_maps_link"), "#")
        maps_link = maps if maps.startswith("http") else "#"
        level_class = "watch-high" if watch["level"] == "HIGH" else "watch-medium"
        rows += f"""
        <tr><td><b>{html.escape(safe_text(row.get('grid_id')))}</b></td><td><span class='{level_class}'>{html.escape(watch['level'])}</span></td>
        <td>{html.escape(watch['category'])}</td><td>{format_number(row.get('forest_pct'), 1, '%')}</td><td>{format_number(row.get('ndvi'), 3)}</td><td>{format_number(row.get('ndmi'), 3)}</td>
        <td>{html.escape(watch['reason'])}</td><td>{html.escape(watch['action'])}</td><td><a href='{html.escape(maps_link)}' target='_blank'>Open</a></td></tr>"""
    return f"<div class='table-wrap'><table><thead><tr><th>Grid</th><th>Level</th><th>Category</th><th>Forest %</th><th>NDVI</th><th>NDMI</th><th>Why listed?</th><th>Action</th><th>Map</th></tr></thead><tbody>{rows}</tbody></table></div>"


def build_ecology_panel(df, limit=6):
    work = sorted_priority_df(df, limit)
    if work.empty:
        return "<div class='watch-note'>No ecological inference available.</div>"
    cards = ""
    for _, row in work.iterrows():
        eco = make_ecology_inference(row)
        maps = safe_text(row.get("google_maps_link"), "#")
        maps_link = maps if maps.startswith("http") else "#"
        level_class = "watch-high" if eco["level"] == "HIGH" else "watch-medium"
        cards += f"""
        <div class='eco-card'><div class='eco-head'><b>{html.escape(safe_text(row.get('grid_id'), 'Grid'))}</b><span class='{level_class}'>{html.escape(eco['level'])}</span></div>
        <div><b>Status:</b> {html.escape(eco['status'])}</div><div><b>Inference:</b> {html.escape(eco['inference'])}</div>
        <div><b>Recommendation:</b> {html.escape(eco['recommendation'])}</div><div class='eco-metrics'>Forest {format_number(row.get('forest_pct'), 1, '%')} | NDVI {format_number(row.get('ndvi'), 3)} | NDMI {format_number(row.get('ndmi'), 3)}</div>
        <a href='{html.escape(maps_link)}' target='_blank'>Open navigation</a></div>"""
    return cards


def count_watchlist(df):
    if df is None or df.empty:
        return 0
    return int(sum(1 for _, row in df.iterrows() if classify_ecological_watch(row)["category"] != "Stable Forest Zone"))


def ecological_summary_text(df):
    if df is None or df.empty:
        return "No FRIS CSV data found."
    fire_rows = count_fire_rows(df)
    high = count_contains(df, ["final_priority", "risk_class", "priority"], "HIGH") + count_contains(df, ["final_priority", "risk_class", "priority"], "CRITICAL")
    if fire_rows or high:
        return "FRIS has detected elevated operational concern in selected grids. Focus field verification on high-risk, fire-check, and anomaly grids first."
    if count_watchlist(df):
        return "Most grids are stable, but selected grids need watch-list monitoring due to disturbance, dryness, vegetation stress, or influence-zone signals."
    return "Most grids remain stable in the current run. Routine monitoring is sufficient."


def _dashboard_row_properties(row):
    """CSV properties used in the lightweight dashboard layer."""
    props = {c: json_safe_value(row.get(c)) for c in row.index if not str(c).startswith("_")}
    watch = classify_ecological_watch(row)
    eco = make_ecology_inference(row)
    props.update({
        "ecological_watch_category": watch["category"],
        "ecological_watch_level": watch["level"],
        "ecological_watch_reason": watch["reason"],
        "ecological_watch_action": watch["action"],
        "ecology_inference": eco["inference"],
        "ecology_recommendation": eco["recommendation"],
        "ecology_status": eco["status"],
        "fire_display": fire_display(row),
        "active_fire_signal": bool(row_has_fire(row)),
        "fire_risk_signal": bool(row_has_fire_risk(row)),
        "dashboard_priority_rank": priority_rank(row),
        "patrol_priority_rank": patrol_priority_rank(row),
        "officer_action": make_action(row),
        "why_go": make_why_go(row),
    })
    return props


def _selected_dashboard_rows(df):
    """All rows for the dashboard map, sorted by patrol priority.

    User requirement:
    - show the whole clipped FRIS map in the dashboard, not only 40 grids.

    Safety:
    - geometry still comes from fris_latest.geojson, so mine-clipped shapes are preserved.
    - CSV is used for ranking/properties, not for creating fake full-square grids.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["_map_rank"] = work.apply(map_display_rank, axis=1)
    return work.sort_values("_map_rank", ascending=False)


def _read_selected_clipped_geometries(grid_ids):
    """Read only selected geometries from latest GeoJSON.

    Important:
    - The dashboard must not create fake full 1 km grid squares from CSV centroids.
    - When fris_latest.geojson exists, it should contain the mine-clipped grid geometry
      produced by sks1a.py. We reuse only the selected top-priority features.
    - If GeoJSON is unavailable/stale, the dashboard falls back to centroid points,
      not full grid polygons. This prevents showing mine areas as included.
    """
    selected = {str(g) for g in grid_ids if str(g).strip()}
    if not selected or not os.path.exists(GEOJSON_FILE):
        return {}, "GEOJSON_NOT_AVAILABLE_CENTROID_POINT_FALLBACK"

    try:
        with open(GEOJSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("GeoJSON read error:", e)
        return {}, "GEOJSON_READ_FAILED_CENTROID_POINT_FALLBACK"

    by_id = {}
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        gid = str(props.get("grid_id", "")).strip()
        geom = feat.get("geometry")
        if gid in selected and geom and geom.get("coordinates"):
            by_id[gid] = geom

    if by_id:
        return by_id, "CLIPPED_GEOJSON_GEOMETRY_SELECTED_BY_CSV_PRIORITY"
    return {}, "GRID_IDS_NOT_FOUND_IN_GEOJSON_CENTROID_POINT_FALLBACK"


def make_csv_grid_geojson(df):
    """Build the live dashboard map using the whole clipped FRIS GeoJSON.

    Best mode:
      CSV supplies grid properties/ranking, and latest GeoJSON supplies the real
      mine-clipped geometry for every grid.

    Fallback mode:
      If GeoJSON is missing, show centroid point markers only. Do not draw full 1 km
      squares from CSV, because clipped mine-area geometry cannot be reconstructed
      from centroid columns alone.
    """
    if df is None or df.empty:
        return {"type": "FeatureCollection", "features": []}

    lat_col, lon_col = find_lat_lon_columns(df)
    work = _selected_dashboard_rows(df)
    if work.empty:
        return {"type": "FeatureCollection", "features": []}

    grid_ids = [safe_text(row.get("grid_id"), "") for _, row in work.iterrows()]
    geom_by_grid, geometry_source = _read_selected_clipped_geometries(grid_ids)

    features = []
    clipped_count = 0
    point_count = 0

    for _, row in work.iterrows():
        gid = safe_text(row.get("grid_id"), "")
        props = _dashboard_row_properties(row)
        geom = geom_by_grid.get(gid)

        if geom:
            clipped_count += 1
            features.append({"type": "Feature", "properties": props, "geometry": geom})
            continue

        # Safe fallback: point marker only, not a fake full grid polygon.
        if lat_col is None or lon_col is None:
            continue
        lat = safe_float(row.get(lat_col))
        lon = safe_float(row.get(lon_col))
        if lat is None or lon is None:
            continue
        point_count += 1
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "source": "FULL dashboard map: CSV properties + clipped GeoJSON geometry where available",
        "geometry_source": geometry_source,
        "feature_count": len(features),
        "selected_clipped_geometry_features": clipped_count,
        "centroid_point_fallback_features": point_count,
        "selection_rule": "all available FRIS grids using real clipped GeoJSON geometry; no fake whole-grid polygons",
    }


@app.route("/", methods=["GET", "HEAD"])
def dashboard():
    # Render and uptime monitors often call HEAD /.
    # Return immediately so health checks do not rebuild the full dashboard.
    if request.method == "HEAD":
        return "", 200

    df = read_csv_light()
    csv_found = os.path.exists(CSV_FILE)
    geojson_found = os.path.exists(GEOJSON_FILE)
    map_found = os.path.exists(MAP_FILE)
    total_grids = len(df) if df is not None else 0
    high_risk = count_contains(df, ["final_priority", "risk_class", "priority"], "HIGH")
    critical_risk = count_contains(df, ["final_priority", "risk_class", "priority"], "CRITICAL")
    fire_check = count_contains(df, ["final_priority", "risk_class", "priority"], "FIRE")
    active_fire = count_fire_rows(df)
    field_required_count = count_field_required(df)
    watchlist_count = count_watchlist(df)
    avg_ndvi = avg_col(df, "ndvi")
    avg_ndmi = avg_col(df, "ndmi")
    forest_area_text = format_number(estimate_area_ha(df), 1, " ha")
    total_carbon_text = format_carbon(sum_first_available_numeric(df, ["ecosystem_carbon_total_ton", "estimated_ecosystem_carbon_ton"]))
    carbon_change_text = format_number(sum_first_available_numeric(df, ["carbon_change_co2e_ton", "carbon_change_from_365d", "carbon_change_ton"]), 1, " tons CO₂e")
    carbon_opp_text = format_number(sum_first_available_numeric(df, ["preliminary_carbon_opportunity_ton_co2e"]), 1, " tons CO₂e")
    high_carbon_loss = count_contains(df, ["carbon_change_status"], "HIGH_CARBON_LOSS")
    high_carbon_gain = count_contains(df, ["carbon_change_status"], "HIGH_CARBON_GAIN")
    tree_estimate_text = format_number(sum_first_available_numeric(df, ["estimated_tree_count"]), 0, "")
    mrv_counts = value_counts_html(df, "mrv_confidence")
    memory_counts = value_counts_html(df, "ecological_memory_class")
    soil_counts = value_counts_html(df, "soil_moisture_retention_class")
    weather = get_weather(df)
    priority_table = build_priority_table(df)
    watchlist_table = build_watchlist_table(df, 20)
    summary = ecological_summary_text(df)

    page = f"""
<!DOCTYPE html><html><head><title>FRIS Jharkhand Dashboard</title><meta name='viewport' content='width=device-width, initial-scale=1.0'>
<style>
*{{box-sizing:border-box;font-family:Arial,sans-serif}}body{{margin:0;background:#061307;color:white}}.layout{{display:flex;min-height:100vh}}.sidebar{{width:270px;padding:25px;background:linear-gradient(180deg,#173f18,#071507);border-right:1px solid rgba(255,255,255,.15)}}.logo h1{{color:#dfff00;font-size:38px;margin:0}}.logo p{{color:#c6ff6b;font-size:13px;margin:4px 0 30px}}.nav{{padding:15px;margin-bottom:13px;border-radius:15px;background:rgba(255,255,255,.12);font-weight:bold}}.nav.active{{background:#dfff00;color:#102000}}.nav a{{color:inherit;text-decoration:none;display:block}}.side-card,.map-card,.card,.table-card{{background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.18);border-radius:24px;padding:18px}}.side-card{{margin-top:25px;font-size:14px;line-height:1.7}}.ok{{color:#dfff00;font-weight:bold}}.bad{{color:#ff6b6b;font-weight:bold}}.main{{flex:1;padding:25px}}.topbar{{display:grid;grid-template-columns:repeat(3,1fr) auto;gap:15px;align-items:center;padding:18px;border-radius:22px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.18);margin-bottom:22px}}.time-box{{font-size:14px;line-height:1.4}}.time-box b{{display:block}}.time-box span,.value,td a,.eco-card a{{color:#dfff00;font-weight:bold}}.btn{{display:inline-block;background:#dfff00;color:#102000;padding:12px 16px;border-radius:14px;text-decoration:none;font-weight:bold;margin:4px}}.content{{display:grid;grid-template-columns:1fr 340px;gap:22px}}.map-frame{{width:100%;height:620px;border:0;border-radius:18px;background:#1b5525;overflow:hidden}}.right{{display:flex;flex-direction:column;gap:15px}}.row{{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.12);font-size:14px}}.table-card{{margin-top:22px}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:13px}}th{{background:rgba(223,255,0,.18);color:#dfff00;text-align:left;padding:10px;white-space:nowrap}}td{{padding:10px;border-bottom:1px solid rgba(255,255,255,.12);vertical-align:top}}.watch-high{{color:#ff6b6b;font-weight:bold}}.watch-medium{{color:#ffd400;font-weight:bold}}.watch-note{{background:rgba(223,255,0,.10);border-left:5px solid #dfff00;padding:14px;border-radius:14px;margin-bottom:14px;line-height:1.5;color:#eaffc4}}.eco-card{{background:rgba(255,255,255,.08);border:1px solid rgba(223,255,0,.20);border-left:5px solid #a855f7;border-radius:16px;padding:14px;margin-bottom:12px;line-height:1.55;font-size:14px}}.eco-head{{display:flex;justify-content:space-between;gap:12px;margin-bottom:8px;color:#dfff00}}.eco-metrics{{margin-top:8px;color:#c6ff6b;font-size:13px}}.footer{{margin-top:18px;font-size:13px;color:#c5d6c5}}.map-legend{{background:rgba(6,19,7,.94);color:white;padding:12px 14px;border-radius:14px;border:1px solid rgba(255,255,255,.30);box-shadow:0 4px 18px rgba(0,0,0,.35);line-height:1.45;font-size:13px;min-width:190px}}.map-legend b{{color:#dfff00;font-size:14px}}.legend-row{{display:flex;align-items:center;gap:8px;margin:6px 0}}.legend-swatch{{width:16px;height:16px;border-radius:4px;border:1px solid rgba(255,255,255,.65);display:inline-block;flex:0 0 16px}}@media(max-width:1000px){{.layout{{flex-direction:column}}.sidebar{{width:100%}}.topbar,.content{{grid-template-columns:1fr}}.map-frame{{height:520px}}}}
</style></head><body><div class='layout'><div class='sidebar'><div class='logo'><h1>FRIS</h1><p>Forest Resilience Information System</p></div>
<div class='nav active'>🏠 Dashboard</div><div class='nav'><a href='#map-section'>🗺️ Operational Map</a></div><div class='nav'><a href='#priority-section'>🧭 Priority Grids</a></div><div class='nav'><a href='#watchlist-section'>🟣 Operational Watch</a></div><div class='nav'>🔥 Fire Intelligence</div><div class='nav'>💧 Moisture Stress</div><div class='nav'>🌿 Carbon MRV</div>
<div class='side-card'><b>Jharkhand FRIS Screening</b><br><br>CSV: <span class='{'ok' if csv_found else 'bad'}'>{'Found' if csv_found else 'Missing'}</span><br>GeoJSON: <span class='{'ok' if geojson_found else 'bad'}'>{'Found' if geojson_found else 'Missing'}</span><br>Saved Map: <span class='{'ok' if map_found else 'bad'}'>{'Found' if map_found else 'Missing'}</span><br><br><b>Analysed Area:</b><br>{forest_area_text}<br><br><b>Memory Mode:</b><br>Light + Informative</div></div>
<div class='main'><div class='topbar'><div class='time-box'><b>Current Time</b><span>{format_ist(ist_now())}</span></div><div class='time-box'><b>Last Data Update</b><span>{get_file_update_time(CSV_FILE)}</span><br><small>{get_file_age_minutes(CSV_FILE)}</small></div><div class='time-box'><b>Next Expected Run</b><span>{next_expected_run()}</span></div><div><a class='btn' href='/'>Refresh</a><a class='btn' href='/download/csv'>Download CSV</a><a class='btn' href='/view/full-map' target='_blank'>Open Full Map</a><a class='btn' href='/download/map'>Download Map</a><a class='btn' href='/download/geojson'>Full GeoJSON</a><a class='btn' href='/watchlist'>Watch-List</a><a class='btn' href='/api/summary'>API</a><a class='btn' href='/debug'>Debug</a></div></div>
<div class='content' id='map-section'><div class='map-card'><h2>FRIS Forest Risk & Patrol Map</h2><div class='watch-note'>Layer: <b>FRIS Risk & Patrol Priority Layer</b>. Click any grid for a small popup showing only Grid, Risk and Action. Full scientific details remain in the priority table, ecological watch-list and CSV download.</div><iframe class='map-frame' src='/view/full-map' loading='lazy' title='FRIS saved operational map'></iframe></div><div class='right'><div class='card'><h3>📊 Operational Summary</h3><div class='row'><span>Total Grids</span><span class='value'>{total_grids}</span></div><div class='row'><span>High Risk</span><span class='value'>{high_risk}</span></div><div class='row'><span>Critical Risk</span><span class='value'>{critical_risk}</span></div><div class='row'><span>Fire Risk / Check</span><span class='value'>{fire_check}</span></div><div class='row'><span>Active Fire Signals</span><span class='value'>{active_fire}</span></div><div class='row'><span>Field Verification</span><span class='value'>{field_required_count}</span></div><div class='row'><span>Watch-List</span><span class='value'>{watchlist_count}</span></div></div><div class='card'><h3>💧 Forest Condition</h3><div class='row'><span>Average NDVI</span><span class='value'>{avg_ndvi}</span></div><div class='row'><span>Average NDMI</span><span class='value'>{avg_ndmi}</span></div><div class='row'><span>Soil Retention</span><span class='value'>{soil_counts}</span></div></div><div class='card'><h3>🟣 Operational Watch Summary</h3><div class='watch-note'>{html.escape(summary)}</div><div class='row'><span>365-Day Memory</span><span class='value'>{memory_counts}</span></div></div><div class='card'><h3>🌦️ Weather</h3><div class='row'><span>Source</span><span class='value'>{html.escape(weather['source'])}</span></div><div class='row'><span>Temperature</span><span class='value'>{weather['temperature']}</span></div><div class='row'><span>Rainfall 24h</span><span class='value'>{weather['rainfall_24h']}</span></div><div class='row'><span>Wind</span><span class='value'>{weather['wind']}</span></div><div class='row'><span>Fire Spread</span><span class='value'>{html.escape(weather['spread'])}</span></div></div><div class='card'><h3>🌿 Carbon MRV</h3><div class='row'><span>Total Carbon</span><span class='value'>{total_carbon_text}</span></div><div class='row'><span>Carbon Change</span><span class='value'>{carbon_change_text}</span></div><div class='row'><span>Preliminary Opportunity</span><span class='value'>{carbon_opp_text}</span></div><div class='row'><span>High Loss / Gain</span><span class='value'>{high_carbon_loss} / {high_carbon_gain}</span></div><div class='row'><span>MRV Confidence</span><span class='value'>{mrv_counts}</span></div><div class='row'><span>Claim Status</span><span class='value'>Not Certified</span></div></div><div class='card'><h3>🌲 Tree Position Estimate</h3><div class='row'><span>Estimated Count</span><span class='value'>{tree_estimate_text}</span></div><small>Dashboard wording remains “estimate”; this is not exact tree enumeration.</small></div></div></div>
<div class='table-card' id='priority-section'><h2>🧭 Priority Grid Intelligence</h2>{priority_table}</div>
<div class='table-card' id='watchlist-section'><h2>🟣 Ecological Anomaly & Chronic Risk Watch-List</h2><div class='watch-note'>Separate verification layer for ecological anomaly, chronic/repeated stress, fire-check, moisture stress, vegetation stress, historical disturbance, or influence-zone signals.</div>{watchlist_table}</div><div class='footer'>This app reads selected CSV columns for summaries/tables and displays the exact saved FRIS HTML map from the download file inside the dashboard.</div></div></div>
</body></html>"""
    del df
    gc.collect()
    return Response(page, mimetype="text/html")


@app.route("/geojson")
def geojson():
    # Full dashboard behavior: send all available clipped FRIS geometries.
    # Do not rebuild fake full-square grids from CSV centroids.
    df = read_csv_light()
    data = make_csv_grid_geojson(df)
    del df
    gc.collect()
    response = jsonify(data)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/watchlist")
def watchlist():
    df = read_csv_light()
    table = build_watchlist_table(df, limit=100)
    del df
    gc.collect()
    return Response(f"""<!DOCTYPE html><html><head><title>FRIS Watch-List</title><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{margin:0;background:#061307;color:white;padding:24px;font-family:Arial}}.box{{background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.18);border-radius:24px;padding:20px}}h1{{color:#dfff00}}.btn{{display:inline-block;background:#dfff00;color:#102000;padding:12px 16px;border-radius:14px;text-decoration:none;font-weight:bold;margin-bottom:18px}}.note{{background:rgba(223,255,0,.10);border-left:5px solid #dfff00;padding:14px;border-radius:14px;margin-bottom:18px;color:#eaffc4}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:13px}}th{{background:rgba(223,255,0,.18);color:#dfff00;text-align:left;padding:10px;white-space:nowrap}}td{{padding:10px;border-bottom:1px solid rgba(255,255,255,.12);vertical-align:top}}td a{{color:#dfff00;font-weight:bold}}.watch-high{{color:#ff6b6b;font-weight:bold}}.watch-medium{{color:#ffd400;font-weight:bold}}</style></head><body><a class='btn' href='/'>← Back</a><div class='box'><h1>🟣 FRIS Ecological Watch-List</h1><div class='note'>Informative verification layer only. It does not prove illegal activity, confirmed deforestation, compensation liability, or carbon-credit eligibility.</div>{table}</div></body></html>""", mimetype="text/html")


@app.route("/download/csv")
def download_csv():
    if not os.path.exists(CSV_FILE):
        return Response("FRIS CSV file not found inside data/fris_latest.csv", status=404, mimetype="text/plain")
    return send_file(CSV_FILE, mimetype="text/csv", as_attachment=True, download_name="fris_latest.csv", max_age=0)


@app.route("/download/geojson")
def download_geojson():
    if not os.path.exists(GEOJSON_FILE):
        return Response("FRIS GeoJSON file not found inside data/fris_latest.geojson", status=404, mimetype="text/plain")
    return send_file(GEOJSON_FILE, mimetype="application/geo+json", as_attachment=True, download_name="fris_latest.geojson", max_age=0)


@app.route("/view/full-map")
def view_full_map():
    """Show the saved FRIS HTML map file inside dashboard with written explanation.

    Important:
    - The map geometry and colour layer still come directly from fris_latest_map.html.
    - This route only injects a small legend/explanation panel into the HTML view.
    - No dashboard-side recolouring, filtering, or fake grid rebuilding is applied.
    """
    if not os.path.exists(MAP_FILE):
        return Response("FRIS map file not found. Put fris_latest_map.html inside data/, output/, or the project root.", status=404, mimetype="text/plain")

    try:
        with open(MAP_FILE, "r", encoding="utf-8") as f:
            map_html = f.read()
    except UnicodeDecodeError:
        with open(MAP_FILE, "r", encoding="latin-1", errors="ignore") as f:
            map_html = f.read()

    map_html = inject_overlay_into_saved_map(map_html)
    response = Response(map_html, mimetype="text/html")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/download/map")
def download_map():
    """Download the same FRIS map, with the written legend included."""
    if not os.path.exists(MAP_FILE):
        return Response("FRIS map file not found inside data/fris_latest_map.html", status=404, mimetype="text/plain")

    try:
        with open(MAP_FILE, "r", encoding="utf-8") as f:
            map_html = f.read()
    except UnicodeDecodeError:
        with open(MAP_FILE, "r", encoding="latin-1", errors="ignore") as f:
            map_html = f.read()

    map_html = inject_overlay_into_saved_map(map_html)
    response = Response(map_html, mimetype="text/html")
    response.headers["Content-Disposition"] = "attachment; filename=fris_latest_map_with_legend.html"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


def make_summary_payload(df):
    lat_col, lon_col = find_lat_lon_columns(df)
    return {
        "status": "running",
        "server_time_ist": format_ist(ist_now()),
        "csv_found": os.path.exists(CSV_FILE),
        "geojson_found": os.path.exists(GEOJSON_FILE),
        "map_found": os.path.exists(MAP_FILE),
        "csv_last_update": get_file_update_time(CSV_FILE),
        "csv_age": get_file_age_minutes(CSV_FILE),
        "next_expected_run": next_expected_run(),
        "total_grids": len(df) if df is not None else 0,
        "estimated_operational_area_ha": estimate_area_ha(df),
        "high_risk_grids": count_contains(df, ["final_priority", "risk_class", "priority"], "HIGH"),
        "critical_risk_grids": count_contains(df, ["final_priority", "risk_class", "priority"], "CRITICAL"),
        "active_fire_signal_grids": count_fire_rows(df),
        "fire_risk_or_check_grids": int(sum(1 for _, row in df.iterrows() if row_has_fire_risk(row))) if df is not None and not df.empty else 0,
        "field_verification_required_grids": count_field_required(df),
        "ecological_watchlist_count": count_watchlist(df),
        "high_carbon_loss_grids": count_contains(df, ["carbon_change_status"], "HIGH_CARBON_LOSS"),
        "high_carbon_gain_grids": count_contains(df, ["carbon_change_status"], "HIGH_CARBON_GAIN"),
        "preliminary_carbon_opportunity_ton_co2e": sum_first_available_numeric(df, ["preliminary_carbon_opportunity_ton_co2e"]),
        "csv_lat_column_found": lat_col,
        "csv_lon_column_found": lon_col,
    }


@app.route("/health", methods=["GET", "HEAD"])
def health():
    # Lightweight health check for Render/uptime pings.
    # Do not read the CSV here; /api/summary and /debug are for detailed checks.
    if request.method == "HEAD":
        return "", 200
    return jsonify({
        "status": "ok",
        "service": "FRIS",
        "server_time_ist": format_ist(ist_now()),
        "csv_found": os.path.exists(CSV_FILE),
        "geojson_found": os.path.exists(GEOJSON_FILE),
        "map_found": os.path.exists(MAP_FILE),
        "csv_last_update": get_file_update_time(CSV_FILE),
        "csv_age": get_file_age_minutes(CSV_FILE),
    })


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
            "priority": safe_text(row.get("final_priority", row.get("risk_class"))),
            "risk_score": safe_float(row.get("final_risk_score")),
            "fire": fire_display(row),
            "active_fire_signal": bool(row_has_fire(row)),
            "fire_risk_signal": bool(row_has_fire_risk(row)),
            "ndvi": safe_float(row.get("ndvi")),
            "ndmi": safe_float(row.get("ndmi")),
            "watch_category": classify_ecological_watch(row)["category"],
            "watch_level": classify_ecological_watch(row)["level"],
            "action": make_action(row),
            "google_maps_link": safe_text(row.get("google_maps_link"), ""),
        })
    del df
    gc.collect()
    return jsonify({"count": len(rows), "rows": rows})


@app.route("/debug")
def debug():
    df = read_csv_light()
    lat_col, lon_col = find_lat_lon_columns(df)
    result = {"server_time_ist": format_ist(ist_now()), "csv_found": os.path.exists(CSV_FILE), "geojson_found": os.path.exists(GEOJSON_FILE), "saved_map_found": os.path.exists(MAP_FILE), "csv_last_update": get_file_update_time(CSV_FILE), "csv_age": get_file_age_minutes(CSV_FILE), "total_grids": len(df) if df is not None else 0, "columns_loaded": list(df.columns) if df is not None else [], "csv_lat_column_found": lat_col, "csv_lon_column_found": lon_col, "memory_mode": "saved_html_map_direct_iframe", "map_feature_limit": "NOT_USED_ON_DASHBOARD_DIRECT_SAVED_MAP", "map_selection_rule": "dashboard map is loaded directly from saved fris_latest_map.html via /view/full-map; /geojson is kept only as API fallback", "active_fire_detect_logic": "ACTIVE fire only: fire_count/recent_fire_count/fire_alert_count/firms_count > 0 OR fire_detected/active_fire truthy OR fire_status confirmed active OR FRP > 0. final_priority containing FIRE is treated as fire-risk, not active fire.", "base_dir": BASE_DIR, "data_dir": DATA_DIR}
    del df
    gc.collect()
    return jsonify(result)



@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Return a readable error page instead of a blank Render failure page."""
    traceback.print_exc()
    message = html.escape(str(error))
    return Response(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>FRIS dashboard error</title>
        <meta name='viewport' content='width=device-width, initial-scale=1.0'>
        <style>
            body {{ margin:0; background:#061307; color:white; font-family:Arial; padding:24px; }}
            .box {{ max-width:900px; margin:auto; background:rgba(255,255,255,.10); border:1px solid rgba(255,255,255,.18); border-radius:22px; padding:24px; }}
            h1 {{ color:#ff6b6b; }}
            code {{ color:#dfff00; }}
            a {{ color:#dfff00; font-weight:bold; }}
        </style>
    </head>
    <body>
        <div class='box'>
            <h1>FRIS dashboard error</h1>
            <p>The server is running, but this request failed.</p>
            <p><b>Error:</b> <code>{message}</code></p>
            <p>Open <a href='/debug'>/debug</a> and Render Logs to see the exact file/path issue.</p>
        </div>
    </body>
    </html>
    """, status=500, mimetype="text/html")


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "service": "FRIS", "csv_found": os.path.exists(CSV_FILE)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
