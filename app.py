import os
from pathlib import Path
from datetime import datetime

import pandas as pd
from flask import Flask, render_template_string, send_from_directory, abort


# ============================================================
# FRIS GODDA DASHBOARD APP
# Forest Resilience Information System
# Reads latest FRIS outputs from C:\cfris\output
# ============================================================

APP_TITLE = "FRIS GODDA"
APP_SUBTITLE = "Forest Resilience Information System"

BASE_DIR = Path(r"C:\cfris")
OUTPUT_DIR = BASE_DIR / "output"

LATEST_CSV = OUTPUT_DIR / "fris_latest.csv"
LATEST_MAP = OUTPUT_DIR / "fris_latest_map.html"

app = Flask(__name__)


def safe_float(value, default=0.0):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def safe_text(value, default="--"):
    try:
        if value is None or pd.isna(value):
            return default
        text = str(value).strip()
        return text if text else default
    except Exception:
        return default


def load_fris_data():
    if not LATEST_CSV.exists():
        return pd.DataFrame(), {
            "csv_found": False,
            "message": f"No FRIS CSV found at {LATEST_CSV}"
        }

    df = pd.read_csv(LATEST_CSV)

    # Ensure expected columns exist safely
    defaults = {
        "final_priority": "LOW",
        "final_risk_score": 0,
        "forest_pct": 0,
        "health_class": "UNKNOWN",
        "moisture_class_calibrated": "UNKNOWN",
        "fire_intensity_class": "NO_FIRE",
        "fire_count": 0,
        "fire_frp_max": 0,
        "temperature_c": 0,
        "rainfall_24h_mm": 0,
        "wind_speed_kmph": 0,
        "wind_gust_kmph": 0,
        "weather_fire_spread_class": "UNKNOWN",
        "weather_validation_level": "UNKNOWN",
        "era5_rain_sum_30d_mm": 0,
        "era5_temp_mean_30d_c": 0,
        "era5_temp_anomaly_c": 0,
        "imd_validation_status": "NO_IMD_FILE",
        "soil_type": "LOCAL_SOIL_DATA_PENDING",
        "soil_moisture_retention_class": "UNKNOWN",
        "soil_drying_speed": "UNKNOWN",
        "soil_supported_ecological_stability": "UNKNOWN",
        "ecosystem_carbon_co2e_total": 0,
        "preliminary_carbon_opportunity_ton_co2e": 0,
        "mrv_confidence": "EARLY_STAGE",
        "carbon_credit_claim_status": "EARLY_STAGE_ECOLOGICAL_MONITORING",
        "ecological_memory_class": "EARLY_TIMESTAMPED_MEMORY",
        "ecological_memory_score": 0,
        "history_days_available_365d": 0,
        "patrol_action": "Routine monitoring",
        "google_maps_link": "#",
        "grid_id": "--",
        "agb_ton_per_ha": 0,
        "mining_pressure_class": "NONE",
    }

    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    numeric_cols = [
        "final_risk_score", "forest_pct", "fire_count", "fire_frp_max",
        "temperature_c", "rainfall_24h_mm", "wind_speed_kmph", "wind_gust_kmph",
        "era5_rain_sum_30d_mm", "era5_temp_mean_30d_c", "era5_temp_anomaly_c",
        "ecosystem_carbon_co2e_total", "preliminary_carbon_opportunity_ton_co2e",
        "ecological_memory_score", "history_days_available_365d", "agb_ton_per_ha",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Sort priority
    priority_order = {
        "FIRE_CHECK": 0,
        "CRITICAL": 1,
        "HIGH": 2,
        "MEDIUM": 3,
        "LOW": 4,
    }
    df["_priority_sort"] = df["final_priority"].map(priority_order).fillna(9)
    df = df.sort_values(["_priority_sort", "final_risk_score"], ascending=[True, False])

    meta = {
        "csv_found": True,
        "csv_path": str(LATEST_CSV),
        "map_found": LATEST_MAP.exists(),
        "map_path": str(LATEST_MAP),
        "last_updated": datetime.fromtimestamp(LATEST_CSV.stat().st_mtime).strftime("%d %b %Y %I:%M %p"),
        "total_rows": len(df),
    }
    return df, meta


def build_summary(df, meta):
    if df.empty:
        return {}

    top = df.iloc[0]

    fire_points = int(df["fire_count"].sum()) if "fire_count" in df.columns else 0
    max_frp = df["fire_frp_max"].max() if "fire_frp_max" in df.columns else 0

    area_ha = len(df) * 100

    summary = {
        "app_title": APP_TITLE,
        "app_subtitle": APP_SUBTITLE,
        "last_updated": meta.get("last_updated", "--"),
        "total_grids": len(df),
        "area_ha": area_ha,

        "temperature": safe_float(top.get("temperature_c")),
        "rainfall": safe_float(top.get("rainfall_24h_mm")),
        "wind": safe_float(top.get("wind_speed_kmph")),
        "gust": safe_float(top.get("wind_gust_kmph")),
        "weather_fire": safe_text(top.get("weather_fire_spread_class")),
        "weather_validation": safe_text(top.get("weather_validation_level")),

        "era5_rain_30d": safe_float(top.get("era5_rain_sum_30d_mm")),
        "era5_temp_mean": safe_float(top.get("era5_temp_mean_30d_c")),
        "era5_temp_anomaly": safe_float(top.get("era5_temp_anomaly_c")),
        "imd_status": safe_text(top.get("imd_validation_status")),

        "fire_points": fire_points,
        "max_frp": safe_float(max_frp),
        "top_fire_intensity": safe_text(top.get("fire_intensity_class")),
        "top_action": safe_text(top.get("patrol_action")),

        "ecosystem_co2e": safe_float(df["ecosystem_carbon_co2e_total"].sum()),
        "carbon_opportunity": safe_float(df["preliminary_carbon_opportunity_ton_co2e"].sum()),
        "mrv_confidence": safe_text(top.get("mrv_confidence")),
        "carbon_status": safe_text(top.get("carbon_credit_claim_status")),

        "memory_class": safe_text(top.get("ecological_memory_class")),
        "memory_score": safe_float(top.get("ecological_memory_score")),
        "history_days": int(safe_float(top.get("history_days_available_365d"))),

        "soil_type": safe_text(top.get("soil_type")),
        "soil_retention": safe_text(top.get("soil_moisture_retention_class")),
        "soil_drying": safe_text(top.get("soil_drying_speed")),
        "soil_stability": safe_text(top.get("soil_supported_ecological_stability")),

        "top_grid": safe_text(top.get("grid_id")),
        "top_priority": safe_text(top.get("final_priority")),
        "top_risk": safe_float(top.get("final_risk_score")),
    }

    return summary


def priority_badge(priority):
    p = str(priority).upper()
    if p == "FIRE_CHECK":
        return "badge-fire"
    if p in ["CRITICAL", "HIGH"]:
        return "badge-high"
    if p == "MEDIUM":
        return "badge-med"
    return "badge-low"


@app.route("/")
def dashboard():
    df, meta = load_fris_data()

    if df.empty:
        return render_template_string(ERROR_TEMPLATE, title=APP_TITLE, subtitle=APP_SUBTITLE, meta=meta)

    summary = build_summary(df, meta)

    top20 = df.head(20).copy()
    rows = []
    for i, (_, r) in enumerate(top20.iterrows(), start=1):
        rows.append({
            "rank": i,
            "grid_id": safe_text(r.get("grid_id")),
            "priority": safe_text(r.get("final_priority")),
            "priority_class": priority_badge(r.get("final_priority")),
            "risk": round(safe_float(r.get("final_risk_score")), 2),
            "forest_pct": round(safe_float(r.get("forest_pct")), 2),
            "moisture": safe_text(r.get("moisture_class_calibrated")),
            "health": safe_text(r.get("health_class")),
            "fire": safe_text(r.get("fire_intensity_class")),
            "weather_fire": safe_text(r.get("weather_fire_spread_class")),
            "soil": safe_text(r.get("soil_moisture_retention_class")),
            "agb": round(safe_float(r.get("agb_ton_per_ha")), 2),
            "frp": round(safe_float(r.get("fire_frp_max")), 2),
            "action": safe_text(r.get("patrol_action")),
            "maps": safe_text(r.get("google_maps_link"), "#"),
        })

    return render_template_string(
        DASHBOARD_TEMPLATE,
        title=APP_TITLE,
        subtitle=APP_SUBTITLE,
        summary=summary,
        rows=rows,
        meta=meta,
        map_available=LATEST_MAP.exists(),
    )


@app.route("/map")
def map_view():
    if not LATEST_MAP.exists():
        abort(404)
    return send_from_directory(str(OUTPUT_DIR), "fris_latest_map.html")


ERROR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ title }}</title>
    <style>
        body { background:#06140f; color:#fff; font-family:Arial; padding:40px; }
        .box { max-width:900px; margin:auto; background:#0e211b; border:1px solid #264d38; border-radius:18px; padding:30px; }
        h1 { color:#9cff57; }
        code { color:#ffd166; }
    </style>
</head>
<body>
<div class="box">
    <h1>{{ title }}</h1>
    <h2>{{ subtitle }}</h2>
    <p>{{ meta.message }}</p>
    <p>Run your FRIS engine first so it creates:</p>
    <code>C:\\cfris\\output\\fris_latest.csv</code>
</div>
</body>
</html>
"""


DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{{ title }} - {{ subtitle }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <style>
        :root {
            --bg: #03120d;
            --panel: rgba(12, 34, 28, 0.92);
            --panel2: rgba(9, 24, 21, 0.94);
            --border: rgba(132, 255, 119, 0.15);
            --green: #86ef45;
            --green2: #38d646;
            --yellow: #ffd166;
            --orange: #ff8a00;
            --red: #ff3b30;
            --blue: #6ab7ff;
            --text: #f4fff8;
            --muted: #b7c9be;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: Arial, Helvetica, sans-serif;
            background:
                radial-gradient(circle at 20% 10%, rgba(50, 120, 68, 0.25), transparent 25%),
                radial-gradient(circle at 80% 20%, rgba(23, 95, 71, 0.25), transparent 30%),
                var(--bg);
            color: var(--text);
        }

        .layout {
            display: grid;
            grid-template-columns: 230px 1fr;
            min-height: 100vh;
        }

        .sidebar {
            background: linear-gradient(180deg, #082015, #03100c);
            border-right: 1px solid var(--border);
            padding: 20px 14px;
        }

        .brand {
            display: flex;
            gap: 12px;
            align-items: center;
            margin-bottom: 28px;
        }

        .logo {
            width: 50px;
            height: 50px;
            border-radius: 16px;
            background: linear-gradient(135deg, #42d742, #f59e0b);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            box-shadow: 0 0 22px rgba(88, 255, 93, 0.25);
        }

        .brand h1 {
            margin: 0;
            font-size: 26px;
            letter-spacing: 1px;
        }

        .brand p {
            margin: 2px 0 0;
            color: var(--green);
            font-size: 12px;
        }

        .nav a {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 13px 14px;
            border-radius: 12px;
            color: var(--text);
            text-decoration: none;
            margin-bottom: 8px;
            font-size: 15px;
        }

        .nav a.active, .nav a:hover {
            background: rgba(106, 239, 69, 0.18);
            color: white;
        }

        .side-info {
            margin-top: 28px;
            padding: 16px;
            border: 1px solid var(--border);
            border-radius: 16px;
            background: rgba(255,255,255,0.03);
            color: var(--muted);
            font-size: 13px;
            line-height: 1.5;
        }

        .main {
            padding: 18px;
        }

        .topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(6, 28, 19, 0.72);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 14px 18px;
            margin-bottom: 16px;
        }

        .live {
            color: var(--green);
            border: 1px solid rgba(134,239,69,0.4);
            padding: 8px 14px;
            border-radius: 12px;
            font-weight: bold;
        }

        .top-metrics {
            display: flex;
            gap: 20px;
            align-items: center;
            font-size: 17px;
        }

        .top-metrics b { color: white; font-size: 24px; }

        .grid {
            display: grid;
            grid-template-columns: 1.45fr 1fr;
            gap: 16px;
        }

        .map-card, .panel {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 18px;
            overflow: hidden;
            box-shadow: 0 16px 40px rgba(0,0,0,0.25);
        }

        .map-card {
            min-height: 590px;
            position: relative;
        }

        .map-title {
            position: absolute;
            z-index: 10;
            top: 16px;
            left: 16px;
            background: rgba(0,0,0,0.72);
            padding: 14px 16px;
            border-radius: 14px;
            font-weight: bold;
        }

        iframe {
            width: 100%;
            height: 590px;
            border: none;
            filter: saturate(1.1) contrast(1.05);
        }

        .fake-map {
            height: 590px;
            display:flex;
            align-items:center;
            justify-content:center;
            background: linear-gradient(135deg, #123d24, #071510);
            color: var(--yellow);
            text-align:center;
            padding:30px;
        }

        .panel {
            padding: 16px;
        }

        .panel h3 {
            margin: 0 0 14px;
            font-size: 17px;
            letter-spacing: 0.5px;
        }

        .cards {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
        }

        .stat-row {
            display: flex;
            justify-content: space-between;
            border-top: 1px solid rgba(255,255,255,0.08);
            padding: 11px 0;
            color: var(--muted);
            gap: 20px;
        }

        .stat-row span:last-child {
            color: white;
            text-align: right;
            font-weight: 600;
        }

        .green { color: var(--green) !important; }
        .yellow { color: var(--yellow) !important; }
        .orange { color: var(--orange) !important; }
        .red { color: var(--red) !important; }
        .blue { color: var(--blue) !important; }

        .wide {
            margin-top: 16px;
        }

        .summary-strip {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 14px;
            margin-top: 16px;
        }

        .big-number {
            font-size: 25px;
            color: var(--green);
            font-weight: bold;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            overflow: hidden;
            font-size: 13px;
        }

        th, td {
            padding: 10px 9px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            text-align: left;
            white-space: nowrap;
        }

        th {
            color: var(--muted);
            font-weight: normal;
            background: rgba(255,255,255,0.035);
        }

        tr:hover {
            background: rgba(134, 239, 69, 0.06);
        }

        .badge {
            padding: 5px 8px;
            border-radius: 999px;
            font-weight: bold;
            font-size: 11px;
        }

        .badge-fire { background: rgba(255, 59, 48, 0.25); color: #ff7b72; }
        .badge-high { background: rgba(255, 138, 0, 0.25); color: #ffb86b; }
        .badge-med { background: rgba(255, 209, 102, 0.18); color: var(--yellow); }
        .badge-low { background: rgba(134, 239, 69, 0.16); color: var(--green); }

        .footer {
            margin-top: 14px;
            color: var(--muted);
            font-size: 12px;
            display: flex;
            justify-content: space-between;
            border-top: 1px solid var(--border);
            padding-top: 12px;
        }

        @media (max-width: 1100px) {
            .layout { grid-template-columns: 1fr; }
            .sidebar { display:none; }
            .grid, .cards, .summary-strip { grid-template-columns: 1fr; }
            .topbar, .top-metrics { flex-direction: column; align-items: flex-start; }
        }
    </style>
</head>

<body>
<div class="layout">

    <aside class="sidebar">
        <div class="brand">
            <div class="logo">🔥</div>
            <div>
                <h1>FRIS</h1>
                <p>Forest Resilience Information System</p>
            </div>
        </div>

        <nav class="nav">
            <a class="active" href="/">🏠 Dashboard</a>
            <a href="/map" target="_blank">🗺️ Live Risk Map</a>
            <a href="#">🔥 Fire Intelligence</a>
            <a href="#">💧 Moisture & Soil</a>
            <a href="#">🌦️ Weather & Climate</a>
            <a href="#">🌿 Carbon MRV</a>
            <a href="#">🕒 Ecological Memory</a>
            <a href="#">⛏️ Mining Pressure</a>
            <a href="#">📄 Reports</a>
            <a href="#">⚙️ Settings</a>
        </nav>

        <div class="side-info">
            <b>Area</b><br>
            Godda District, Jharkhand<br><br>
            <b>Forest-Dominant Area</b><br>
            {{ "{:,.0f}".format(summary.area_ha) }} ha<br><br>
            <b>System</b><br>
            Forest Resilience Information System
        </div>
    </aside>

    <main class="main">
        <div class="topbar">
            <div>
                <span class="live">● LIVE</span>
                <span style="margin-left:16px;">{{ summary.last_updated }}</span>
            </div>

            <div class="top-metrics">
                <span>🌡️ <b>{{ "%.1f"|format(summary.temperature) }}°C</b></span>
                <span>🌧️ <b>{{ "%.1f"|format(summary.rainfall) }}</b> mm</span>
                <span>💨 <b>{{ "%.1f"|format(summary.wind) }}</b> km/h</span>
            </div>
        </div>

        <div class="grid">
            <section class="map-card">
                <div class="map-title">
                    LIVE RISK MAP<br>
                    <span style="font-weight:normal;color:#ddd;">1 km Forest Grid</span>
                </div>

                {% if map_available %}
                    <iframe src="/map"></iframe>
                {% else %}
                    <div class="fake-map">
                        <div>
                            <h2>Map file not found</h2>
                            <p>Expected: C:\\cfris\\output\\fris_latest_map.html</p>
                        </div>
                    </div>
                {% endif %}
            </section>

            <section>
                <div class="cards">
                    <div class="panel">
                        <h3>🌦️ Weather Context</h3>
                        <div class="stat-row"><span>Status</span><span class="green">LIVE_OPEN_METEO</span></div>
                        <div class="stat-row"><span>Temperature</span><span>{{ "%.1f"|format(summary.temperature) }} °C</span></div>
                        <div class="stat-row"><span>Rain 24h</span><span>{{ "%.1f"|format(summary.rainfall) }} mm</span></div>
                        <div class="stat-row"><span>Wind / Gust</span><span>{{ "%.1f"|format(summary.wind) }} / {{ "%.1f"|format(summary.gust) }} km/h</span></div>
                        <div class="stat-row"><span>Fire Spread</span><span class="green">{{ summary.weather_fire }}</span></div>
                    </div>

                    <div class="panel">
                        <h3>🔥 Live Fire Summary</h3>
                        <div class="stat-row"><span>Active Fire Points</span><span>{{ summary.fire_points }}</span></div>
                        <div class="stat-row"><span>Max FRP</span><span>{{ "%.2f"|format(summary.max_frp) }}</span></div>
                        <div class="stat-row"><span>Top Fire Intensity</span><span class="orange">{{ summary.top_fire_intensity }}</span></div>
                        <div class="stat-row"><span>Top Action</span><span class="yellow">{{ summary.top_priority }}</span></div>
                    </div>

                    <div class="panel">
                        <h3>☁️ ERA5 30-Day Memory</h3>
                        <div class="stat-row"><span>Validation</span><span class="green">{{ summary.weather_validation }}</span></div>
                        <div class="stat-row"><span>Rain 30d</span><span>{{ "%.1f"|format(summary.era5_rain_30d) }} mm</span></div>
                        <div class="stat-row"><span>Mean Temp 30d</span><span>{{ "%.2f"|format(summary.era5_temp_mean) }} °C</span></div>
                        <div class="stat-row"><span>Temp Anomaly</span><span>{{ "%.2f"|format(summary.era5_temp_anomaly) }} °C</span></div>
                    </div>

                    <div class="panel">
                        <h3>🏛️ IMD Validation</h3>
                        <div class="stat-row"><span>Status</span><span class="red">{{ summary.imd_status }}</span></div>
                        <div class="stat-row"><span>Mode</span><span>IMD Ready</span></div>
                        <div class="stat-row"><span>File</span><span>Pending</span></div>
                        <div class="stat-row"><span>Use</span><span>Official validation</span></div>
                    </div>
                </div>
            </section>
        </div>

        <div class="summary-strip">
            <div class="panel">
                <h3>🌿 Carbon MRV</h3>
                <div class="big-number">{{ "{:,.0f}".format(summary.ecosystem_co2e) }}</div>
                <div class="muted">tons CO₂e estimated stock</div>
            </div>

            <div class="panel">
                <h3>📈 Preliminary Opportunity</h3>
                <div class="big-number">{{ "{:,.1f}".format(summary.carbon_opportunity) }}</div>
                <div class="muted">MRV support only</div>
            </div>

            <div class="panel">
                <h3>🕒 Ecological Memory</h3>
                <div class="big-number">{{ summary.memory_class }}</div>
                <div class="muted">History days: {{ summary.history_days }} / 365</div>
            </div>

            <div class="panel">
                <h3>🌱 Soil Context</h3>
                {% if summary.soil_type == "LOCAL_SOIL_DATA_PENDING" %}
                    <div class="big-number">NBSS&LUP Pending</div>
                    <div class="muted">Neutral soil mode active</div>
                {% else %}
                    <div class="big-number">{{ summary.soil_retention }}</div>
                    <div class="muted">{{ summary.soil_type }}</div>
                {% endif %}
            </div>
        </div>

        <div class="panel wide">
            <h3>🌱 Soil & Moisture Intelligence</h3>
            {% if summary.soil_type == "LOCAL_SOIL_DATA_PENDING" %}
                <div class="stat-row"><span>Soil Coverage Status</span><span class="yellow">Official NBSS&LUP soil layer pending</span></div>
                <div class="stat-row"><span>Current Mode</span><span>Neutral ecological soil interpretation</span></div>
                <div class="stat-row"><span>Moisture Retention Assumption</span><span>{{ summary.soil_retention }}</span></div>
                <div class="stat-row"><span>Drying Speed Assumption</span><span>{{ summary.soil_drying }}</span></div>
                <div class="stat-row"><span>Ecological Stability Assumption</span><span>{{ summary.soil_stability }}</span></div>
                <p style="color:#d9f99d; line-height:1.55; margin:14px 0 0;">
                    Official grid-wise soil data has not been integrated yet. FRIS is therefore using a neutral soil assumption
                    so it does not invent soil type. Once the NBSS&LUP soil layer is added, this section will show real
                    soil type, moisture retention, drying speed, and ecological stability for each forest grid.
                </p>
            {% else %}
                <div class="stat-row"><span>Soil Type</span><span class="blue">{{ summary.soil_type }}</span></div>
                <div class="stat-row"><span>Moisture Retention</span><span>{{ summary.soil_retention }}</span></div>
                <div class="stat-row"><span>Drying Speed</span><span>{{ summary.soil_drying }}</span></div>
                <div class="stat-row"><span>Ecological Stability</span><span>{{ summary.soil_stability }}</span></div>
                <p style="color:#d9f99d; line-height:1.55; margin:14px 0 0;">
                    Soil context is active. FRIS uses this to interpret whether a grid naturally dries fast,
                    retains moisture longer, or needs closer ecological monitoring.
                </p>
            {% endif %}
        </div>

        <div class="panel wide">
            <h3>Top 20 FRIS Priority Grids</h3>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Grid</th>
                        <th>Priority</th>
                        <th>Risk</th>
                        <th>Forest %</th>
                        <th>Moisture</th>
                        <th>Health</th>
                        <th>Fire</th>
                        <th>Weather</th>                        <th>AGB</th>
                        <th>FRP</th>
                        <th>Action</th>
                        <th>Map</th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in rows %}
                    <tr>
                        <td>{{ r.rank }}</td>
                        <td><b>{{ r.grid_id }}</b></td>
                        <td><span class="badge {{ r.priority_class }}">{{ r.priority }}</span></td>
                        <td class="orange"><b>{{ r.risk }}</b></td>
                        <td>{{ r.forest_pct }}</td>
                        <td class="green">{{ r.moisture }}</td>
                        <td>{{ r.health }}</td>
                        <td class="yellow">{{ r.fire }}</td>
                        <td class="green">{{ r.weather_fire }}</td>                        <td>{{ r.agb }}</td>
                        <td>{{ r.frp }}</td>
                        <td>{{ r.action }}</td>
                        <td><a class="green" href="{{ r.maps }}" target="_blank">Open</a></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="footer">
            <span>FRIS GODDA | Forest Resilience Information System</span>
            <span>Sources: Google Earth Engine, NASA FIRMS, Open-Meteo, ERA5, IMD-ready, NBSS&LUP-ready</span>
        </div>
    </main>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
