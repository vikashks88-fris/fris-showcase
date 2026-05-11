# ============================================================
# FRIS SHOWCASE APP - GODDA FOREST DIVISION
# File: app.py
# Purpose: Render / Local Flask dashboard for sks11.py / FRIS outputs
# Author: FRIS Godda Forest Division Showcase
# ============================================================

from flask import Flask, render_template_string, send_file, jsonify
from pathlib import Path
from datetime import datetime
import os
import math
import pandas as pd

# ============================================================
# BASIC CONFIG
# ============================================================

app = Flask(__name__)

APP_NAME = "FRIS Showcase"
DIVISION_NAME = "Godda Forest Division"
SUBTITLE = "Forest Resilience Intelligence System"
BASELINE_LOCK_DATE = "27 April 2026"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"

CSV_CANDIDATES = [
    DATA_DIR / "fris_latest.csv",
    DATA_DIR / "fris_priority_latest.csv",
    BASE_DIR / "fris_latest.csv",
    BASE_DIR / "fris_priority_latest.csv",
]

MAP_CANDIDATES = [
    STATIC_DIR / "fris_latest_map.html",
    STATIC_DIR / "fris_master_map_latest.html",
    DATA_DIR / "fris_latest_map.html",
    DATA_DIR / "fris_master_map_latest.html",
    BASE_DIR / "fris_latest_map.html",
    BASE_DIR / "fris_master_map_latest.html",
]

# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def first_existing(paths):
    for path in paths:
        if path.exists() and path.is_file():
            return path
    return None


def clean_float(value, default=0.0, decimals=2):
    try:
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        if abs(value) < 0.0001:
            value = 0.0
        return round(value, decimals)
    except Exception:
        return default


def clean_int(value, default=0):
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except Exception:
        return default


def clean_text(value, default="UNKNOWN"):
    try:
        if pd.isna(value):
            return default
        value = str(value).strip()
        return value if value else default
    except Exception:
        return default


def normalize_columns(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    rename_map = {
        "lat": "lat_center",
        "latitude": "lat_center",
        "lon": "lon_center",
        "lng": "lon_center",
        "longitude": "lon_center",
        "priority": "final_priority",
        "risk": "final_priority",
        "risk_class": "final_priority",
        "risk_score": "final_risk_score",
        "moisture_class": "moisture_class_calibrated",
        "map_link": "google_maps_link",
        "maps_link": "google_maps_link",
        "google_link": "google_maps_link",
    }

    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df.rename(columns={old: new}, inplace=True)

    defaults = {
        "grid_id": "N/A",
        "final_priority": "LOW",
        "final_risk_score": 0.0,
        "forest_pct": 0.0,
        "hansen_treecover2000": 0.0,
        "hansen_loss": 0.0,
        "fire_frp_max": 0.0,
        "fire_intensity_class": "NO_FIRE",
        "health_class": "UNKNOWN",
        "moisture_class_calibrated": "UNKNOWN",
        "mining_pressure_class": "NONE",
        "agb_ton_per_ha": 0.0,
        "biomass_carbon_total_ton": 0.0,
        "ecosystem_carbon_total_ton": 0.0,
        "carbon_change_co2e_ton": 0.0,
        "potential_carbon_credits": 0.0,
        "mrv_confidence": "NOT_AVAILABLE",
        "carbon_credit_claim_status": "NO_CREDIT_CLAIM_CURRENTLY",
        "patrol_action": "Routine monitoring",
        "field_inference_why_to_go": "Routine patrol",
        "google_maps_link": "",
        "system_run_timestamp_local": "",
        "run_timestamp_local": "",
    }

    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    numeric_cols = [
        "final_risk_score",
        "forest_pct",
        "hansen_treecover2000",
        "hansen_loss",
        "fire_frp_max",
        "agb_ton_per_ha",
        "biomass_carbon_total_ton",
        "ecosystem_carbon_total_ton",
        "carbon_change_co2e_ton",
        "potential_carbon_credits",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        df[col] = df[col].apply(lambda x: 0.0 if abs(float(x)) < 0.0001 else float(x))

    text_cols = [
        "final_priority",
        "fire_intensity_class",
        "health_class",
        "moisture_class_calibrated",
        "mining_pressure_class",
        "mrv_confidence",
        "carbon_credit_claim_status",
        "patrol_action",
        "field_inference_why_to_go",
    ]

    for col in text_cols:
        df[col] = df[col].fillna("UNKNOWN").astype(str).str.strip()

    return df


def load_fris_csv():
    csv_path = first_existing(CSV_CANDIDATES)
    if not csv_path:
        return None, None, "No FRIS CSV found. Put fris_latest.csv inside data/ folder."

    try:
        df = pd.read_csv(csv_path)
        df = normalize_columns(df)
        return df, csv_path, None
    except Exception as e:
        return None, csv_path, f"CSV read error: {e}"


def get_last_updated(df):
    if df is None or df.empty:
        return datetime.now().strftime("%d %b %Y, %I:%M %p")

    for col in ["system_run_timestamp_local", "run_timestamp_local", "analysis_end_date"]:
        if col in df.columns:
            values = df[col].dropna().astype(str).str.strip()
            values = values[values != ""]
            if not values.empty:
                return values.iloc[-1]

    return datetime.now().strftime("%d %b %Y, %I:%M %p")


def count_contains(df, col, terms):
    if df is None or df.empty or col not in df.columns:
        return 0
    s = df[col].fillna("").astype(str).str.upper()
    mask = pd.Series(False, index=df.index)
    for term in terms:
        mask = mask | s.str.contains(term.upper(), na=False)
    return int(mask.sum())


def build_summary(df):
    if df is None or df.empty:
        return {
            "total_grids": 0,
            "forest_area_ha": 0,
            "high_critical": 0,
            "medium": 0,
            "low": 0,
            "active_fire_points": 0,
            "avg_forest_pct": 0,
            "avg_risk": 0,
            "avg_agb": 0,
            "ecosystem_carbon": 0,
            "ecosystem_co2e": 0,
            "carbon_change": 0,
            "potential_credits": 0,
            "health_status": "NO DATA",
            "moisture_status": "NO DATA",
            "last_updated": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        }

    total_grids = len(df)
    forest_area_ha = total_grids * 100  # 1 km x 1 km = 100 ha per grid

    high_critical = count_contains(df, "final_priority", ["HIGH", "CRITICAL"])
    medium = count_contains(df, "final_priority", ["MEDIUM", "MODERATE"])
    low = count_contains(df, "final_priority", ["LOW"])

    active_fire_points = count_contains(df, "fire_intensity_class", ["FIRE", "LOW_FIRE", "MEDIUM_FIRE", "HIGH_FIRE"])
    no_fire_rows = count_contains(df, "fire_intensity_class", ["NO_FIRE"])
    if active_fire_points == no_fire_rows:
        active_fire_points = 0

    avg_risk = clean_float(df["final_risk_score"].mean(), decimals=2)
    avg_forest_pct = clean_float(df["forest_pct"].mean(), decimals=2)
    avg_agb = clean_float(df["agb_ton_per_ha"].mean(), decimals=2)

    ecosystem_carbon = clean_float(df["ecosystem_carbon_total_ton"].sum(), decimals=2)
    ecosystem_co2e = clean_float(ecosystem_carbon * 3.667, decimals=2)
    carbon_change = clean_float(df["carbon_change_co2e_ton"].sum(), decimals=2)
    potential_credits = clean_float(df["potential_carbon_credits"].sum(), decimals=2)

    stressed = count_contains(df, "health_class", ["STRESSED", "CRITICAL"])
    dry = count_contains(df, "moisture_class_calibrated", ["DRY", "VERY_DRY", "DRY_CRITICAL"])

    if stressed > total_grids * 0.35:
        health_status = "STRESSED"
    elif stressed > total_grids * 0.15:
        health_status = "WATCH"
    else:
        health_status = "STABLE"

    if dry > total_grids * 0.35:
        moisture_status = "MOISTURE DEFICIT HIGH"
    elif dry > total_grids * 0.15:
        moisture_status = "MODERATE DRYNESS"
    else:
        moisture_status = "NORMAL"

    return {
        "total_grids": total_grids,
        "forest_area_ha": forest_area_ha,
        "high_critical": high_critical,
        "medium": medium,
        "low": low,
        "active_fire_points": active_fire_points,
        "avg_forest_pct": avg_forest_pct,
        "avg_risk": avg_risk,
        "avg_agb": avg_agb,
        "ecosystem_carbon": ecosystem_carbon,
        "ecosystem_co2e": ecosystem_co2e,
        "carbon_change": carbon_change,
        "potential_credits": potential_credits,
        "health_status": health_status,
        "moisture_status": moisture_status,
        "last_updated": get_last_updated(df),
    }


def build_priority_rows(df, limit=30):
    if df is None or df.empty:
        return []

    temp = df.copy()

    priority_order = {
        "CRITICAL": 1,
        "HIGH": 2,
        "MEDIUM": 3,
        "MODERATE": 3,
        "LOW": 4,
    }

    temp["priority_rank"] = temp["final_priority"].str.upper().map(priority_order).fillna(5)
    temp = temp.sort_values(["priority_rank", "final_risk_score"], ascending=[True, False]).head(limit)

    rows = []
    for _, r in temp.iterrows():
        inference = clean_text(r.get("field_inference_why_to_go"), "Routine patrol")
        if inference.upper() in ["UNKNOWN", "NONE", "NAN", ""]:
            inference = clean_text(r.get("patrol_action"), "Routine patrol")

        rows.append({
            "grid_id": clean_text(r.get("grid_id")),
            "priority": clean_text(r.get("final_priority")),
            "risk_score": clean_float(r.get("final_risk_score"), decimals=2),
            "forest_pct": clean_float(r.get("forest_pct"), decimals=2),
            "health": clean_text(r.get("health_class")),
            "moisture": clean_text(r.get("moisture_class_calibrated")),
            "fire": clean_text(r.get("fire_intensity_class")),
            "mining": clean_text(r.get("mining_pressure_class")),
            "carbon_change": clean_float(r.get("carbon_change_co2e_ton"), decimals=2),
            "credits": clean_float(r.get("potential_carbon_credits"), decimals=2),
            "mrv": clean_text(r.get("mrv_confidence")),
            "claim": clean_text(r.get("carbon_credit_claim_status")),
            "action": clean_text(r.get("patrol_action"), "Routine monitoring"),
            "why": inference,
            "link": clean_text(r.get("google_maps_link"), ""),
        })

    return rows


def build_chart_data(summary):
    return {
        "priority": [summary["high_critical"], summary["medium"], summary["low"]],
        "carbon": [
            max(summary["carbon_change"], 0),
            summary["potential_credits"],
        ],
        "risk": [summary["avg_risk"], max(0, 100 - summary["avg_risk"])],
    }

# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def dashboard():
    df, csv_path, csv_error = load_fris_csv()
    map_path = first_existing(MAP_CANDIDATES)

    summary = build_summary(df)
    rows = build_priority_rows(df, limit=30)
    chart_data = build_chart_data(summary)

    return render_template_string(
        HTML_TEMPLATE,
        app_name=APP_NAME,
        division_name=DIVISION_NAME,
        subtitle=SUBTITLE,
        baseline_lock_date=BASELINE_LOCK_DATE,
        summary=summary,
        rows=rows,
        chart_data=chart_data,
        csv_found=csv_path is not None,
        csv_name=csv_path.name if csv_path else "Not found",
        csv_error=csv_error,
        map_found=map_path is not None,
        map_url="/map" if map_path else None,
        year=datetime.now().year,
    )


@app.route("/map")
def map_page():
    map_path = first_existing(MAP_CANDIDATES)
    if not map_path:
        return "FRIS map not found. Upload fris_latest_map.html inside static/ folder.", 404
    return send_file(map_path)


@app.route("/download-csv")
def download_csv():
    csv_path = first_existing(CSV_CANDIDATES)
    if not csv_path:
        return "FRIS CSV not found.", 404
    return send_file(csv_path, as_attachment=True)


@app.route("/api/summary")
def api_summary():
    df, csv_path, csv_error = load_fris_csv()
    return jsonify({
        "app": APP_NAME,
        "division": DIVISION_NAME,
        "baseline_lock_date": BASELINE_LOCK_DATE,
        "csv_found": csv_path is not None,
        "csv_error": csv_error,
        "summary": build_summary(df),
    })

# ============================================================
# HTML TEMPLATE
# ============================================================

HTML_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{ app_name }} - {{ division_name }}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg: #04170f;
            --bg2: #08291b;
            --panel: rgba(9, 43, 27, 0.92);
            --panel2: rgba(18, 72, 39, 0.78);
            --border: rgba(154, 255, 145, 0.18);
            --text: #f2fff4;
            --muted: #afc8b2;
            --green: #86e34e;
            --green2: #38b957;
            --yellow: #ffd348;
            --orange: #ff8c2a;
            --red: #ff4b38;
            --blue: #80c8ff;
            --shadow: 0 22px 70px rgba(0, 0, 0, 0.38);
        }

        * { box-sizing: border-box; }
        html { scroll-behavior: smooth; }
        body {
            margin: 0;
            font-family: Inter, Segoe UI, Arial, sans-serif;
            color: var(--text);
            background:
                radial-gradient(circle at 20% 0%, rgba(67, 180, 83, 0.32), transparent 28%),
                radial-gradient(circle at 100% 20%, rgba(28, 91, 64, 0.5), transparent 30%),
                linear-gradient(135deg, #03110b, #082218 45%, #03130e);
        }
        a { color: inherit; }

        .app-shell {
            display: grid;
            grid-template-columns: 270px minmax(0, 1fr);
            min-height: 100vh;
        }

        .sidebar {
            position: sticky;
            top: 0;
            height: 100vh;
            padding: 26px 20px;
            background: linear-gradient(180deg, rgba(4, 38, 22, 0.98), rgba(2, 15, 11, 0.98));
            border-right: 1px solid var(--border);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 30px;
        }
        .brand-logo {
            width: 64px;
            height: 64px;
            border-radius: 22px;
            background: linear-gradient(135deg, #b9ff73, #1d7f42);
            display: grid;
            place-items: center;
            font-size: 34px;
            box-shadow: var(--shadow);
        }
        .brand h1 { margin: 0; font-size: 25px; letter-spacing: -0.5px; }
        .brand p { margin: 4px 0 0; color: var(--muted); font-size: 12px; }

        .nav a {
            display: flex;
            gap: 12px;
            align-items: center;
            padding: 14px 14px;
            margin: 7px 0;
            text-decoration: none;
            color: var(--muted);
            border-radius: 16px;
            font-weight: 750;
            border: 1px solid transparent;
        }
        .nav a.active,
        .nav a:hover {
            color: white;
            background: rgba(115, 218, 74, 0.18);
            border-color: rgba(115, 218, 74, 0.22);
        }

        .sidebar-card {
            position: absolute;
            left: 20px;
            right: 20px;
            bottom: 22px;
            padding: 16px;
            border: 1px solid var(--border);
            border-radius: 20px;
            background: rgba(10, 54, 31, 0.7);
        }
        .dot {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--green);
            margin-right: 8px;
        }
        .sidebar-card p { margin: 8px 0 0; color: var(--muted); font-size: 12px; line-height: 1.5; }

        .main {
            padding: 28px;
            max-width: 1680px;
            width: 100%;
            margin: 0 auto;
        }

        .hero {
            display: flex;
            justify-content: space-between;
            gap: 20px;
            align-items: flex-start;
            margin-bottom: 20px;
        }
        .hero h2 {
            font-size: 38px;
            margin: 0;
            letter-spacing: -1px;
            line-height: 1.04;
        }
        .hero h2 span { color: var(--green); }
        .hero p { color: var(--muted); margin: 10px 0 0; font-size: 15px; }
        .hero-actions { display: flex; gap: 12px; flex-wrap: wrap; justify-content: flex-end; }
        .btn {
            text-decoration: none;
            padding: 12px 16px;
            border-radius: 15px;
            border: 1px solid var(--border);
            background: linear-gradient(135deg, rgba(79, 165, 64, 0.9), rgba(19, 95, 47, 0.86));
            color: white;
            font-weight: 850;
            box-shadow: var(--shadow);
        }
        .btn.secondary { background: rgba(12, 44, 33, 0.82); }

        .warning {
            padding: 14px 16px;
            margin-bottom: 16px;
            border-radius: 18px;
            background: rgba(255, 211, 72, 0.12);
            border: 1px solid rgba(255, 211, 72, 0.3);
            color: #ffe6a0;
        }

        .cards {
            display: grid;
            grid-template-columns: repeat(5, minmax(150px, 1fr));
            gap: 14px;
            margin-bottom: 16px;
        }
        .card, .panel {
            background: linear-gradient(180deg, var(--panel), rgba(4, 22, 16, 0.94));
            border: 1px solid var(--border);
            border-radius: 22px;
            box-shadow: var(--shadow);
        }
        .card { padding: 18px; min-height: 130px; }
        .card .icon { font-size: 28px; margin-bottom: 10px; }
        .card .label { color: var(--muted); font-size: 13px; font-weight: 800; }
        .card .value { font-size: 33px; font-weight: 950; margin-top: 7px; letter-spacing: -0.8px; }
        .card .hint { color: var(--muted); font-size: 12px; margin-top: 7px; }
        .green { color: var(--green); }
        .yellow { color: var(--yellow); }
        .red { color: var(--red); }
        .blue { color: var(--blue); }
        .orange { color: var(--orange); }

        .grid-main {
            display: grid;
            grid-template-columns: minmax(0, 1.65fr) minmax(340px, 0.8fr);
            gap: 16px;
            margin-bottom: 16px;
        }
        .panel { padding: 18px; }
        .panel h3 { margin: 0 0 14px; font-size: 19px; }
        .panel-sub { color: var(--muted); font-size: 13px; margin-top: -8px; margin-bottom: 14px; }

        .map-frame {
            width: 100%;
            height: 575px;
            border: 0;
            border-radius: 18px;
            background: rgba(0,0,0,0.25);
        }
        .map-missing {
            height: 575px;
            border: 1px dashed rgba(255,255,255,0.25);
            border-radius: 18px;
            display: grid;
            place-items: center;
            text-align: center;
            color: var(--muted);
            padding: 30px;
        }

        .status-list { display: grid; gap: 12px; }
        .status-item {
            padding: 14px;
            border-radius: 17px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.045);
        }
        .status-item strong { display: block; margin-bottom: 6px; }
        .status-item span { color: var(--muted); font-size: 13px; line-height: 1.4; }

        .charts {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 16px;
            margin-bottom: 16px;
        }
        canvas { max-height: 280px; }

        .table-wrap { overflow-x: auto; }
        table {
            width: 100%;
            border-collapse: collapse;
            min-width: 1220px;
        }
        th, td {
            padding: 12px 10px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            text-align: left;
            font-size: 13px;
            vertical-align: top;
        }
        th {
            color: var(--muted);
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.05em;
        }
        .why-cell { min-width: 260px; color: #e8ffe8; line-height: 1.4; }
        .action-cell { min-width: 220px; color: var(--muted); line-height: 1.4; }
        .badge {
            display: inline-block;
            padding: 6px 10px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 900;
            border: 1px solid rgba(255,255,255,0.13);
            white-space: nowrap;
        }
        .badge.critical, .badge.high { background: rgba(255,75,56,0.18); color: #ffb5ad; }
        .badge.medium, .badge.moderate { background: rgba(255,211,72,0.16); color: #ffe18a; }
        .badge.low { background: rgba(134,227,78,0.15); color: #b8ff93; }
        .badge.default { background: rgba(255,255,255,0.08); color: var(--muted); }

        .footer {
            text-align: center;
            color: var(--muted);
            font-size: 12px;
            padding: 20px 0 6px;
        }

        @media (max-width: 1180px) {
            .app-shell { grid-template-columns: 1fr; }
            .sidebar { position: relative; height: auto; }
            .sidebar-card { position: static; margin-top: 18px; }
            .cards { grid-template-columns: repeat(2, 1fr); }
            .grid-main, .charts { grid-template-columns: 1fr; }
            .hero { flex-direction: column; }
            .hero-actions { justify-content: flex-start; }
        }
        @media (max-width: 640px) {
            .main { padding: 16px; }
            .cards { grid-template-columns: 1fr; }
            .hero h2 { font-size: 29px; }
            .map-frame, .map-missing { height: 430px; }
        }
    </style>
</head>
<body>
<div class="app-shell">
    <aside class="sidebar">
        <div class="brand">
            <div class="brand-logo">🌳</div>
            <div>
                <h1>FRIS</h1>
                <p>{{ division_name }}</p>
            </div>
        </div>

        <nav class="nav">
            <a href="#" class="active">🏠 Dashboard</a>
            <a href="#map-section">🗺️ Risk Map</a>
            <a href="#priority-table">🛡️ Patrol & Action</a>
            <a href="#carbon">🌍 Carbon MRV</a>
            <a href="#charts">📈 Trends</a>
            <a href="/api/summary" target="_blank">🔌 API</a>
        </nav>

        <div class="sidebar-card">
            <strong><span class="dot"></span>System Status</strong>
            <p>
                CSV: {{ csv_name }}<br>
                Map: {% if map_found %}Available{% else %}Not found{% endif %}<br>
                Baseline: {{ baseline_lock_date }}
            </p>
        </div>
    </aside>

    <main class="main">
        <section class="hero">
            <div>
                <h2><span>FRIS</span> – {{ division_name }}</h2>
                <p>{{ subtitle }} · Smart monitoring, patrol intelligence, carbon MRV support · Last updated: {{ summary.last_updated }}</p>
            </div>
            <div class="hero-actions">
                {% if csv_found %}<a class="btn" href="/download-csv">⬇ Download CSV</a>{% endif %}
                <a class="btn secondary" href="/api/summary" target="_blank">View Summary API</a>
            </div>
        </section>

        {% if csv_error %}
        <div class="warning">
            {{ csv_error }}<br>
            Expected: <b>fris_showcase/data/fris_latest.csv</b>
        </div>
        {% endif %}

        <section class="cards">
            <div class="card">
                <div class="icon">🧩</div>
                <div class="label">Total Grids</div>
                <div class="value green">{{ summary.total_grids }}</div>
                <div class="hint">1 km × 1 km grid cells</div>
            </div>
            <div class="card">
                <div class="icon">🌲</div>
                <div class="label">Forest Area</div>
                <div class="value green">{{ summary.forest_area_ha }}</div>
                <div class="hint">ha forest-dominant estimate</div>
            </div>
            <div class="card">
                <div class="icon">🛡️</div>
                <div class="label">High & Critical</div>
                <div class="value yellow">{{ summary.high_critical }}</div>
                <div class="hint">priority patrol grids</div>
            </div>
            <div class="card">
                <div class="icon">🔥</div>
                <div class="label">Active Fire</div>
                <div class="value red">{{ summary.active_fire_points }}</div>
                <div class="hint">fire signal rows</div>
            </div>
            <div class="card" id="carbon">
                <div class="icon">🍃</div>
                <div class="label">Potential Credits</div>
                <div class="value green">{{ summary.potential_credits }}</div>
                <div class="hint">tCO₂e indicative only</div>
            </div>
        </section>

        <section class="grid-main" id="map-section">
            <div class="panel">
                <h3>Operational Risk Map</h3>
                <div class="panel-sub">Grid risk, patrol priority, fire, moisture and forest health layers.</div>
                {% if map_found %}
                    <iframe class="map-frame" src="{{ map_url }}"></iframe>
                {% else %}
                    <div class="map-missing">
                        <div>
                            <h3>Map not found</h3>
                            <p>Put your generated map here:<br><b>fris_showcase/static/fris_latest_map.html</b></p>
                        </div>
                    </div>
                {% endif %}
            </div>

            <div class="panel">
                <h3>Division Status</h3>
                <div class="status-list">
                    <div class="status-item">
                        <strong class="green">🌲 Forest Cover Avg: {{ summary.avg_forest_pct }}%</strong>
                        <span>Strict forest-dominant grid monitoring layer.</span>
                    </div>
                    <div class="status-item">
                        <strong class="yellow">📊 Avg Risk Score: {{ summary.avg_risk }}</strong>
                        <span>Used to sort operational patrol priority.</span>
                    </div>
                    <div class="status-item">
                        <strong class="orange">🍂 Health: {{ summary.health_status }}</strong>
                        <span>{{ summary.moisture_status }}</span>
                    </div>
                    <div class="status-item">
                        <strong class="blue">🌍 Ecosystem CO₂e: {{ summary.ecosystem_co2e }}</strong>
                        <span>MRV support estimate only, not verified credit issuance.</span>
                    </div>
                    <div class="status-item">
                        <strong class="green">📌 Baseline Locked: {{ baseline_lock_date }}</strong>
                        <span>Used for carbon change comparison and monitoring continuity.</span>
                    </div>
                </div>
            </div>
        </section>

        <section class="charts" id="charts">
            <div class="panel">
                <h3>Priority Distribution</h3>
                <canvas id="priorityChart"></canvas>
            </div>
            <div class="panel">
                <h3>Carbon MRV Layer</h3>
                <canvas id="carbonChart"></canvas>
            </div>
            <div class="panel">
                <h3>Average Risk Gauge</h3>
                <canvas id="riskChart"></canvas>
            </div>
        </section>

        <section class="panel" id="priority-table">
            <h3>Top Priority Grids — Why To Go There</h3>
            <div class="panel-sub">This table separates operational patrol reasons from carbon-credit status.</div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Grid</th>
                            <th>Priority</th>
                            <th>Risk</th>
                            <th>Health</th>
                            <th>Moisture</th>
                            <th>Forest %</th>
                            <th>Fire</th>
                            <th>Why go there?</th>
                            <th>Action</th>
                            <th>Carbon Change</th>
                            <th>Credits</th>
                            <th>Map</th>
                        </tr>
                    </thead>
                    <tbody>
                    {% for r in rows %}
                        <tr>
                            <td><strong>{{ r.grid_id }}</strong></td>
                            <td><span class="badge {{ r.priority|lower if r.priority|lower in ['critical','high','medium','moderate','low'] else 'default' }}">{{ r.priority }}</span></td>
                            <td>{{ r.risk_score }}</td>
                            <td>{{ r.health }}</td>
                            <td>{{ r.moisture }}</td>
                            <td>{{ r.forest_pct }}</td>
                            <td>{{ r.fire }}</td>
                            <td class="why-cell">{{ r.why }}</td>
                            <td class="action-cell">{{ r.action }}</td>
                            <td>{{ r.carbon_change }}</td>
                            <td>{{ r.credits }}</td>
                            <td>{% if r.link %}<a href="{{ r.link }}" target="_blank">Open</a>{% else %}-{% endif %}</td>
                        </tr>
                    {% endfor %}
                    {% if not rows %}
                        <tr><td colspan="12">No FRIS records available.</td></tr>
                    {% endif %}
                    </tbody>
                </table>
            </div>
        </section>

        <div class="footer">
            © {{ year }} FRIS Showcase · {{ division_name }} · Field verification required before official action · Carbon layer is MRV support only.
        </div>
    </main>
</div>

<script>
const chartData = {{ chart_data | tojson }};

const chartTextColor = '#f2fff4';
const gridColor = 'rgba(255,255,255,0.07)';

new Chart(document.getElementById('priorityChart'), {
    type: 'doughnut',
    data: {
        labels: ['High/Critical', 'Medium', 'Low'],
        datasets: [{
            data: chartData.priority,
            backgroundColor: ['#ff4b38', '#ffd348', '#86e34e'],
            borderColor: '#062016',
            borderWidth: 3
        }]
    },
    options: {
        plugins: { legend: { labels: { color: chartTextColor } } }
    }
});

new Chart(document.getElementById('carbonChart'), {
    type: 'bar',
    data: {
        labels: ['Positive CO₂e Change', 'Potential Credits'],
        datasets: [{
            label: 'tCO₂e',
            data: chartData.carbon,
            backgroundColor: ['#80c8ff', '#86e34e'],
            borderRadius: 12
        }]
    },
    options: {
        scales: {
            x: { ticks: { color: chartTextColor }, grid: { color: gridColor } },
            y: { ticks: { color: chartTextColor }, grid: { color: gridColor } }
        },
        plugins: { legend: { labels: { color: chartTextColor } } }
    }
});

new Chart(document.getElementById('riskChart'), {
    type: 'doughnut',
    data: {
        labels: ['Risk', 'Remaining'],
        datasets: [{
            data: chartData.risk,
            backgroundColor: ['#ff8c2a', 'rgba(255,255,255,0.12)'],
            borderColor: '#062016',
            borderWidth: 3
        }]
    },
    options: {
        circumference: 180,
        rotation: 270,
        plugins: { legend: { labels: { color: chartTextColor } } }
    }
});
</script>
</body>
</html>
'''

# ============================================================
# RUN APP
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
