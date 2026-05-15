from flask import Flask, Response, jsonify
import os
import json
import html
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CSV_FILE = os.path.join(DATA_DIR, "fris_latest.csv")
GEOJSON_FILE = os.path.join(DATA_DIR, "fris_latest.geojson")
MAP_FILE = os.path.join(DATA_DIR, "fris_latest_map.html")

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
        return "File not available"
    ts = os.path.getmtime(file_path)
    return format_ist(datetime.fromtimestamp(ts, IST))


def get_file_age_minutes(file_path):
    if not os.path.exists(file_path):
        return "No update available"

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
        return pd.read_csv(CSV_FILE)
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
        return 0
    value = pd.to_numeric(df[col], errors="coerce").sum()
    if pd.isna(value):
        return 0
    return float(value)


def count_contains(df, columns, keyword):
    if df is None or df.empty:
        return 0

    total = 0
    for col in columns:
        if col in df.columns:
            total += df[col].astype(str).str.upper().str.contains(
                keyword.upper(), na=False
            ).sum()
    return int(total)


def count_fire(df):
    if df is None or df.empty:
        return 0

    count = 0

    for col in ["fire_detected", "active_fire", "fire_status"]:
        if col in df.columns:
            values = df[col].astype(str).str.upper()
            count += values.isin(["TRUE", "YES", "ACTIVE", "1"]).sum()

    if "fire_count" in df.columns:
        count += (pd.to_numeric(df["fire_count"], errors="coerce").fillna(0) > 0).sum()

    return int(count)


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


# =============================
# WEATHER
# =============================

def get_csv_weather(df):
    temperature = get_first_value(df, ["temperature_c", "temperature", "temp_c"], None)
    rainfall_now = get_first_value(df, ["rainfall_current_mm", "rainfall", "rain_mm"], None)
    rainfall_24h = get_first_value(df, ["rainfall_24h_mm"], None)
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
        f"?latitude={lat}&longitude={lon}"
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
# GEOJSON HELPERS
# =============================

def find_lat_lon_columns(df):
    lat_cols = ["lat", "latitude", "center_lat", "grid_lat", "centroid_lat", "y", "LAT", "Latitude"]
    lon_cols = ["lon", "lng", "longitude", "center_lon", "center_lng", "grid_lon", "grid_lng",
                "centroid_lon", "centroid_lng", "x", "LON", "Longitude"]

    lat_col = next((col for col in lat_cols if col in df.columns), None)
    lon_col = next((col for col in lon_cols if col in df.columns), None)

    return lat_col, lon_col


def make_csv_grid_geojson(df):
    if df is None or df.empty:
        return {"type": "FeatureCollection", "features": []}

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

        features.append({
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
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "source": "CSV fallback grid builder",
        "lat_column_used": lat_col,
        "lon_column_used": lon_col
    }


# =============================
# INTELLIGENCE LOGIC
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
        reasons.append("active fire or thermal signal needs field verification")

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
        return "Check moisture and vegetation stress"

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
                    <th>Recommended Action</th>
                    <th>Map</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


def forest_status(avg_ndvi, avg_ndmi, critical, high, fire):
    if fire > 0:
        return "Active fire verification required", "Field team should verify detected thermal/fire signals immediately."
    if critical > 0:
        return "Critical forest attention required", "Some grids show critical operational priority and need same-day checking."
    if high > 0:
        return "High priority monitoring required", "High-risk grids should be checked within 24 hours."
    if isinstance(avg_ndmi, float) and avg_ndmi < 0.10:
        return "Moisture stress increasing", "Dryness signal is visible. Continue monitoring vulnerable grids."
    if isinstance(avg_ndvi, float) and avg_ndvi < 0.35:
        return "Vegetation stress visible", "Some vegetation weakness is visible in satellite condition."
    return "Forest condition currently stable", "No major emergency signal is visible from the latest FRIS dataset."


# =============================
# DASHBOARD ROUTE
# =============================

@app.route("/")
def dashboard():
    df = read_csv()

    current_time = format_ist(ist_now())
    last_csv_update = get_file_update_time(CSV_FILE)
    csv_age = get_file_age_minutes(CSV_FILE)
    next_run = next_expected_run()

    csv_found = os.path.exists(CSV_FILE)
    geojson_found = os.path.exists(GEOJSON_FILE)
    old_map_found = os.path.exists(MAP_FILE)

    total_grids = len(df) if df is not None else 0

    high_risk = count_contains(df, ["final_priority", "risk_class", "priority"], "HIGH")
    critical_risk = count_contains(df, ["final_priority", "risk_class", "priority"], "CRITICAL")
    moderate_risk = count_contains(df, ["final_priority", "risk_class", "priority"], "MODERATE")
    active_fire = count_fire(df)

    avg_ndvi = avg_col(df, "ndvi")
    avg_ndmi = avg_col(df, "ndmi")

    total_carbon = sum_col(df, "ecosystem_carbon_total_ton")
    carbon_change = sum_col(df, "carbon_change_ton")
    forest_area = sum_col(df, "area_ha")

    total_carbon_text = format_carbon(total_carbon)
    carbon_change_text = format_carbon(carbon_change)
    forest_area_text = format_number(forest_area, 1, " ha")

    weather = get_weather(df)
    priority_table = build_priority_table(df, limit=15)

    headline, interpretation = forest_status(avg_ndvi, avg_ndmi, critical_risk, high_risk, active_fire)

    system_status = "ACTIVE" if csv_found else "DATA MISSING"
    map_status = "READY" if geojson_found or csv_found else "NOT READY"

    html_page = f"""
<!DOCTYPE html>
<html>
<head>
    <title>FRIS Godda Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <meta http-equiv="refresh" content="300">

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
            width: 280px;
            padding: 25px;
            background: linear-gradient(180deg, #173f18, #071507);
            border-right: 1px solid rgba(255,255,255,0.15);
        }}

        .logo h1 {{
            color: #dfff00;
            font-size: 42px;
            margin: 0;
            letter-spacing: 1px;
        }}

        .logo p {{
            color: #c6ff6b;
            font-size: 13px;
            margin: 4px 0 30px;
            line-height: 1.4;
        }}

        .nav {{
            padding: 14px 16px;
            margin-bottom: 11px;
            border-radius: 15px;
            background: rgba(255,255,255,0.12);
            font-weight: bold;
        }}

        .nav.active {{
            background: #dfff00;
            color: #102000;
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

        .hero {{
            padding: 22px;
            border-radius: 24px;
            background: linear-gradient(135deg, rgba(223,255,0,0.20), rgba(255,255,255,0.08));
            border: 1px solid rgba(223,255,0,0.35);
            margin-bottom: 22px;
        }}

        .hero h2 {{
            margin: 0 0 8px;
            font-size: 28px;
        }}

        .hero p {{
            margin: 0;
            color: #d7ead2;
            line-height: 1.5;
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

        .kpis {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 15px;
            margin-bottom: 22px;
        }}

        .kpi {{
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.18);
            border-radius: 20px;
            padding: 18px;
        }}

        .kpi small {{
            color: #c8d8c8;
        }}

        .kpi h2 {{
            color: #dfff00;
            margin: 8px 0 0;
            font-size: 26px;
        }}

        .content {{
            display: grid;
            grid-template-columns: 1fr 360px;
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

        .note {{
            color: #d7ead2;
            line-height: 1.5;
            font-size: 14px;
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

        .footer {{
            margin-top: 18px;
            font-size: 13px;
            color: #c5d6c5;
        }}

        @media(max-width: 1100px) {{
            .layout {{
                flex-direction: column;
            }}

            .sidebar {{
                width: 100%;
            }}

            .topbar,
            .kpis,
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
            <p>Forest Resilience Information System<br>Godda Forest Division</p>
        </div>

        <div class="nav active">🏠 Situation Dashboard</div>
        <div class="nav">🗺️ Operational Map</div>
        <div class="nav">🔥 Fire Intelligence</div>
        <div class="nav">💧 Moisture Stress</div>
        <div class="nav">🌦️ Weather</div>
        <div class="nav">🌿 Carbon & Ecosystem</div>

        <div class="side-card">
            <b>System Readiness</b><br><br>

            System Status:
            <span class="{'ok' if csv_found else 'bad'}">{system_status}</span><br>

            Satellite Dataset:
            <span class="{'ok' if csv_found else 'bad'}">{'AVAILABLE' if csv_found else 'MISSING'}</span><br>

            Operational Map:
            <span class="{'ok' if geojson_found or csv_found else 'bad'}">{map_status}</span><br>

            Legacy Map File:
            <span class="{'ok' if old_map_found else 'bad'}">{'AVAILABLE' if old_map_found else 'OPTIONAL'}</span><br><br>

            <b>Analysed Area:</b><br>
            {forest_area_text}
        </div>
    </div>

    <div class="main">

        <div class="hero">
            <h2>{html.escape(headline)}</h2>
            <p>{html.escape(interpretation)}</p>
        </div>

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
                <a class="btn" href="/geojson" target="_blank">GeoJSON</a>
                <a class="btn" href="/debug" target="_blank">Debug</a>
            </div>
        </div>

        <div class="kpis">
            <div class="kpi"><small>Total Grids</small><h2>{total_grids}</h2></div>
            <div class="kpi"><small>Critical</small><h2>{critical_risk}</h2></div>
            <div class="kpi"><small>High Risk</small><h2>{high_risk}</h2></div>
            <div class="kpi"><small>Active Fire</small><h2>{active_fire}</h2></div>
            <div class="kpi"><small>Avg NDMI</small><h2>{avg_ndmi}</h2></div>
        </div>

        <div class="content">

            <div class="map-card">
                <h2>🗺️ FRIS Operational Grid Map</h2>
                <p class="note">
                    Grid colour represents operational priority. Red and orange grids should receive faster field attention.
                    Click any grid to see NDVI, NDMI, fire signal and navigation link.
                </p>
                <div id="fris-map"></div>
            </div>

            <div class="right">

                <div class="card">
                    <h3>📊 Forest Situation</h3>
                    <div class="row"><span>Total analysed grids</span><span class="value">{total_grids}</span></div>
                    <div class="row"><span>Moderate grids</span><span class="value">{moderate_risk}</span></div>
                    <div class="row"><span>High priority grids</span><span class="value">{high_risk}</span></div>
                    <div class="row"><span>Critical priority grids</span><span class="value">{critical_risk}</span></div>
                    <p class="note">This section converts satellite and field-support indicators into patrol-friendly priority counts.</p>
                </div>

                <div class="card">
                    <h3>💧 Vegetation & Moisture</h3>
                    <div class="row"><span>Average NDVI</span><span class="value">{avg_ndvi}</span></div>
                    <div class="row"><span>Average NDMI</span><span class="value">{avg_ndmi}</span></div>
                    <p class="note">
                        NDVI indicates vegetation greenness. NDMI indicates moisture condition. Low NDMI with weak NDVI may indicate drying stress.
                    </p>
                </div>

                <div class="card">
                    <h3>🔥 Fire Intelligence</h3>
                    <div class="row"><span>Detected fire signals</span><span class="value">{active_fire}</span></div>
                    <div class="row"><span>Operational response</span><span class="value">{'Immediate verification' if active_fire > 0 else 'Routine monitoring'}</span></div>
                    <p class="note">
                        Fire signals should be treated as field-verification alerts, not as final ground confirmation.
                    </p>
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
                    <h3>🌿 Carbon & Ecosystem</h3>
                    <div class="row"><span>Total ecosystem carbon</span><span class="value">{total_carbon_text}</span></div>
                    <div class="row"><span>Carbon change</span><span class="value">{carbon_change_text}</span></div>
                    <div class="row"><span>Assessment type</span><span class="value">Satellite assisted</span></div>
                    <div class="row"><span>Credit status</span><span class="value">Not certified</span></div>
                    <p class="note">
                        Carbon values are monitoring estimates. They are useful for trend observation, not direct certified carbon-credit claims.
                    </p>
                </div>

            </div>
        </div>

        <div class="table-card">
            <h2>🧭 Priority Grid Intelligence — Why Go There?</h2>
            <p class="note">
                This table explains the reason behind field attention: fire signal, vegetation stress, moisture stress,
                carbon decline or operational priority.
            </p>
            {priority_table}
        </div>

        <div class="footer">
            FRIS is a satellite-assisted forest operational intelligence system. Outputs support field prioritisation and should be combined with ground verification.
        </div>

    </div>
</div>

<script>
    var map = L.map("fris-map").setView([24.83, 87.22], 10);

    var carto = L.tileLayer(
        "https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png",
        {{
            attribution: "CartoDB",
            maxZoom: 19
        }}
    );

    var satellite = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}",
        {{
            attribution: "Esri Satellite",
            maxZoom: 19
        }}
    );

    satellite.addTo(map);

    function gridColor(props) {{
        var p = "";

        if (props.final_priority) {{
            p = String(props.final_priority).toUpperCase();
        }} else if (props.risk_class) {{
            p = String(props.risk_class).toUpperCase();
        }} else if (props.priority) {{
            p = String(props.priority).toUpperCase();
        }}

        if (p.includes("CRITICAL")) return "#ff0000";
        if (p.includes("HIGH")) return "#ff9900";
        if (p.includes("MEDIUM") || p.includes("MODERATE")) return "#ffd400";

        return "#00ff00";
    }}

    function safeNumber(value) {{
        var n = Number(value);
        if (isNaN(n)) return "N/A";
        return n.toFixed(3);
    }}

    function popupHtml(props) {{
        var grid = props.grid_id || "Grid";
        var priority = props.final_priority || props.risk_class || props.priority || "N/A";
        var ndvi = props.ndvi !== undefined && props.ndvi !== null ? safeNumber(props.ndvi) : "N/A";
        var ndmi = props.ndmi !== undefined && props.ndmi !== null ? safeNumber(props.ndmi) : "N/A";
        var fire = props.fire_count || props.active_fire || props.fire_detected || "0";
        var action = props.patrol_action || "Routine patrol";
        var link = props.google_maps_link || "#";

        return `
            <div style="font-family:Arial; min-width:240px;">
                <b>${{grid}}</b><br><br>
                <b>Priority:</b> ${{priority}}<br>
                <b>NDVI:</b> ${{ndvi}}<br>
                <b>NDMI:</b> ${{ndmi}}<br>
                <b>Fire Signal:</b> ${{fire}}<br>
                <b>Recommended Action:</b> ${{action}}<br><br>
                <a href="${{link}}" target="_blank">Open navigation</a>
            </div>
        `;
    }}

    fetch("/geojson")
        .then(function(response) {{
            return response.json();
        }})
        .then(function(data) {{
            if (!data.features || data.features.length === 0) {{
                alert("No grid features found. Check CSV latitude/longitude columns or GeoJSON geometry.");
                return;
            }}

            var layer = L.geoJSON(data, {{
                style: function(feature) {{
                    var props = feature.properties || {{}};
                    var color = gridColor(props);

                    return {{
                        color: color,
                        weight: 2,
                        fillColor: color,
                        fillOpacity: 0.55
                    }};
                }},
                onEachFeature: function(feature, layer) {{
                    var props = feature.properties || {{}};
                    layer.bindPopup(popupHtml(props));
                }}
            }}).addTo(map);

            try {{
                map.fitBounds(layer.getBounds(), {{
                    padding: [20, 20]
                }});
            }} catch (e) {{
                console.log("Could not fit bounds:", e);
            }}

            L.control.layers(
                {{
                    "Satellite": satellite,
                    "CartoDB Light": carto
                }},
                {{
                    "FRIS Grid Layer": layer
                }},
                {{
                    collapsed: false
                }}
            ).addTo(map);
        }})
        .catch(function(error) {{
            console.log("GeoJSON loading error:", error);
            alert("GeoJSON could not load. Open /debug and /geojson to check.");
        }});
</script>

</body>
</html>
"""

    return Response(html_page, mimetype="text/html")


# =============================
# ROUTES
# =============================

@app.route("/geojson")
def geojson():
    if os.path.exists(GEOJSON_FILE):
        try:
            with open(GEOJSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            features = data.get("features", [])

            if len(features) > 0:
                response = jsonify(data)
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                return response

        except Exception:
            pass

    df = read_csv()
    data = make_csv_grid_geojson(df)

    response = jsonify(data)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


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
        "old_folium_map_found": os.path.exists(MAP_FILE),
        "csv_last_update": get_file_update_time(CSV_FILE),
        "csv_age": get_file_age_minutes(CSV_FILE),
        "next_expected_run": next_expected_run(),
        "total_grids": len(df) if df is not None else 0,
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
        "old_folium_map_found": os.path.exists(MAP_FILE),
        "csv_last_update": get_file_update_time(CSV_FILE),
        "csv_age": get_file_age_minutes(CSV_FILE),
        "next_expected_run": next_expected_run(),
        "total_grids": len(df) if df is not None else 0,
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
    app.run(host="0.0.0.0", port=5000, debug=True)