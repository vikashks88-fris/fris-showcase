from flask import Flask, Response, send_from_directory
import os
import pandas as pd
from datetime import datetime, time

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CSV_FILE = os.path.join(DATA_DIR, "fris_latest.csv")
MAP_FILE = os.path.join(DATA_DIR, "fris_latest_map.html")
GEOJSON_FILE = os.path.join(DATA_DIR, "fris_latest.geojson")


def read_csv():
    if not os.path.exists(CSV_FILE):
        return None
    try:
        return pd.read_csv(CSV_FILE)
    except Exception:
        return None


def get_col_value(df, possible_cols, default="N/A"):
    if df is None or df.empty:
        return default

    for col in possible_cols:
        if col in df.columns:
            value = df[col].dropna()
            if len(value) > 0:
                return str(value.iloc[0])
    return default


def count_keyword(df, possible_cols, keyword):
    if df is None or df.empty:
        return 0

    total = 0
    for col in possible_cols:
        if col in df.columns:
            total += df[col].astype(str).str.upper().str.contains(keyword.upper(), na=False).sum()
    return int(total)


def get_file_time(path):
    if not os.path.exists(path):
        return "File not found"

    modified = datetime.fromtimestamp(os.path.getmtime(path))
    return modified.strftime("%d %B %Y, %I:%M %p IST")


def next_fris_run():
    now = datetime.now()
    morning = time(9, 30)
    evening = time(19, 30)

    if now.time() < morning:
        return "Today 09:30 AM"
    elif now.time() < evening:
        return "Today 07:30 PM"
    else:
        return "Tomorrow 09:30 AM"


@app.route("/")
def dashboard():
    df = read_csv()

    csv_exists = os.path.exists(CSV_FILE)
    map_exists = os.path.exists(MAP_FILE)
    geojson_exists = os.path.exists(GEOJSON_FILE)

    current_time = datetime.now().strftime("%d %B %Y, %I:%M:%S %p IST")
    last_fris_update = get_file_time(CSV_FILE)
    next_run = next_fris_run()

    total_grids = len(df) if df is not None else 0

    high_risk = count_keyword(df, ["risk_class", "final_priority", "priority", "patrol_priority"], "HIGH")
    critical_risk = count_keyword(df, ["risk_class", "final_priority", "priority", "patrol_priority"], "CRITICAL")
    active_fire = (
        count_keyword(df, ["active_fire", "fire_status", "fire_detected"], "TRUE")
        + count_keyword(df, ["active_fire", "fire_status", "fire_detected"], "YES")
        + count_keyword(df, ["active_fire", "fire_status", "fire_detected"], "ACTIVE")
    )

    ndvi = get_col_value(df, ["mean_ndvi", "ndvi", "NDVI"])
    ndmi = get_col_value(df, ["mean_ndmi", "ndmi", "NDMI"])
    temperature = get_col_value(df, ["temperature", "temp_c", "temperature_c"], "N/A")
    rainfall = get_col_value(df, ["rainfall", "rain_mm", "rainfall_mm"], "N/A")
    wind = get_col_value(df, ["wind", "wind_speed", "wind_kmph"], "N/A")
    carbon = get_col_value(
        df,
        ["ecosystem_carbon_total_ton", "estimated_ecosystem_carbon_ton", "carbon_total_ton"],
        "N/A"
    )
    forest_area = get_col_value(
        df,
        ["forest_dominant_area_ha", "forest_area_ha", "total_forest_area_ha"],
        "N/A"
    )

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Godda FRIS Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <!-- Correct professional refresh: every 10 minutes, not every 30 seconds -->
    <meta http-equiv="refresh" content="600">

    <style>
        * {{
            box-sizing: border-box;
            font-family: Arial, sans-serif;
        }}

        body {{
            margin: 0;
            background: #07150c;
            color: white;
        }}

        .layout {{
            display: flex;
            min-height: 100vh;
        }}

        .sidebar {{
            width: 245px;
            background: linear-gradient(180deg, #0d2f16, #07150c);
            padding: 22px;
            border-right: 1px solid rgba(255,255,255,0.12);
        }}

        .logo {{
            display: flex;
            gap: 12px;
            align-items: center;
            margin-bottom: 28px;
        }}

        .logo-icon {{
            width: 48px;
            height: 48px;
            border-radius: 50%;
            background: #c8ff00;
            box-shadow: 0 0 20px #c8ff00;
        }}

        .logo h1 {{
            margin: 0;
            font-size: 28px;
        }}

        .logo small {{
            color: #baff75;
            font-size: 11px;
        }}

        .nav {{
            padding: 14px;
            margin-bottom: 12px;
            border-radius: 14px;
            background: rgba(255,255,255,0.08);
            font-weight: bold;
        }}

        .nav.active {{
            background: #9ee34d;
            color: #07150c;
        }}

        .side-card {{
            margin-top: 24px;
            padding: 16px;
            border-radius: 18px;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.14);
            font-size: 13px;
            line-height: 1.6;
        }}

        .main {{
            flex: 1;
            padding: 24px;
        }}

        .topbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 18px;
            padding: 18px 22px;
            margin-bottom: 22px;
            border-radius: 22px;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.14);
        }}

        .live {{
            color: #d6ff00;
            font-weight: bold;
        }}

        .manual-btn {{
            background: #c8ff00;
            color: #07150c;
            padding: 10px 14px;
            border-radius: 12px;
            text-decoration: none;
            font-weight: bold;
        }}

        .content-grid {{
            display: grid;
            grid-template-columns: 1fr 335px;
            gap: 22px;
        }}

        .map-card, .card {{
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 24px;
            padding: 18px;
        }}

        .map-head {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
        }}

        .map-head h2 {{
            margin: 0;
            font-size: 20px;
        }}

        iframe {{
            width: 100%;
            height: 610px;
            border: none;
            border-radius: 18px;
            background: #183d22;
        }}

        .right {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        .card h3 {{
            margin-top: 0;
            font-size: 17px;
        }}

        .row {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            padding: 9px 0;
            font-size: 14px;
        }}

        .value {{
            color: #d6ff00;
            font-weight: bold;
            text-align: right;
        }}

        .good {{
            color: #9dff5c;
            font-weight: bold;
        }}

        .bad {{
            color: #ff6b6b;
            font-weight: bold;
        }}

        .note {{
            color: #c7d6c7;
            font-size: 12px;
            line-height: 1.5;
            margin-top: 10px;
        }}

        .footer {{
            margin-top: 18px;
            color: #b7c9b7;
            font-size: 12px;
        }}

        @media(max-width: 900px) {{
            .layout {{
                flex-direction: column;
            }}

            .sidebar {{
                width: 100%;
            }}

            .topbar {{
                flex-direction: column;
                align-items: flex-start;
            }}

            .content-grid {{
                grid-template-columns: 1fr;
            }}

            iframe {{
                height: 520px;
            }}
        }}
    </style>
</head>

<body>
<div class="layout">

    <div class="sidebar">
        <div class="logo">
            <div class="logo-icon"></div>
            <div>
                <h1>FRIS</h1>
                <small>Forest Resilience<br>Information System</small>
            </div>
        </div>

        <div class="nav active">🏠 Dashboard</div>
        <div class="nav">🗺️ Risk Map</div>
        <div class="nav">🔥 Fire Intelligence</div>
        <div class="nav">💧 Moisture Stress</div>
        <div class="nav">🌦️ Weather</div>
        <div class="nav">🌿 Carbon MRV</div>
        <div class="nav">🧠 FRIS Memory</div>

        <div class="side-card">
            <b>System Area</b><br>
            Godda Forest Division<br>
            Jharkhand<br><br>

            <b>Forest Area</b><br>
            {forest_area}<br><br>

            <b>CSV</b><br>
            <span class="{'good' if csv_exists else 'bad'}">
                {'Found' if csv_exists else 'Missing'}
            </span><br>

            <b>Map</b><br>
            <span class="{'good' if map_exists else 'bad'}">
                {'Found' if map_exists else 'Missing'}
            </span><br>

            <b>GeoJSON</b><br>
            <span class="{'good' if geojson_exists else 'bad'}">
                {'Found' if geojson_exists else 'Missing'}
            </span>
        </div>
    </div>

    <div class="main">

        <div class="topbar">
            <div>
                <span class="live">● CURRENT DASHBOARD TIME</span><br>
                <b>{current_time}</b><br>
                <small>Clock updates when dashboard reloads.</small>
            </div>

            <div>
                <b>Last FRIS Data Update:</b><br>
                {last_fris_update}<br>
                <small>Based on latest CSV file modification time.</small>
            </div>

            <div>
                <b>Next Expected FRIS Run:</b><br>
                {next_run}<br>
                <small>Standard schedule: 09:30 AM and 07:30 PM.</small>
            </div>

            <a class="manual-btn" href="/">Refresh Now</a>
        </div>

        <div class="content-grid">

            <div class="map-card">
                <div class="map-head">
                    <h2>LIVE FRIS RISK MAP<br><small>1 km operational forest grid</small></h2>
                    <a class="manual-btn" href="/map" target="_blank">Open Full Map</a>
                </div>

                {
                    "<iframe src='/map'></iframe>"
                    if map_exists
                    else "<div style='padding:40px;color:#ff7777;font-weight:bold;'>Map file missing. Keep fris_latest_map.html inside data folder.</div>"
                }

                <div class="note">
                    Satellite intelligence updates after each FRIS engine run.
                    The dashboard refreshes every 10 minutes only to check whether a new CSV/map has arrived.
                </div>
            </div>

            <div class="right">

                <div class="card">
                    <h3>📊 Operational Summary</h3>
                    <div class="row"><span>Total Grids</span><span class="value">{total_grids}</span></div>
                    <div class="row"><span>High Risk</span><span class="value">{high_risk}</span></div>
                    <div class="row"><span>Critical Risk</span><span class="value">{critical_risk}</span></div>
                    <div class="row"><span>Active Fire</span><span class="value">{active_fire}</span></div>
                </div>

                <div class="card">
                    <h3>💧 Vegetation & Moisture</h3>
                    <div class="row"><span>NDVI</span><span class="value">{ndvi}</span></div>
                    <div class="row"><span>NDMI</span><span class="value">{ndmi}</span></div>
                    <div class="row"><span>Status</span><span class="value">From latest FRIS run</span></div>
                </div>

                <div class="card">
                    <h3>🌦️ Weather Layer</h3>
                    <div class="row"><span>Temperature</span><span class="value">{temperature}</span></div>
                    <div class="row"><span>Rainfall</span><span class="value">{rainfall}</span></div>
                    <div class="row"><span>Wind</span><span class="value">{wind}</span></div>
                    <div class="note">
                        Weather values shown here come from your latest CSV.
                        For true live weather, connect a weather API later.
                    </div>
                </div>

                <div class="card">
                    <h3>🌿 Carbon MRV</h3>
                    <div class="row"><span>Estimated Carbon</span><span class="value">{carbon}</span></div>
                    <div class="row"><span>MRV Mode</span><span class="value">Satellite Assisted</span></div>
                    <div class="row"><span>Credit Claim</span><span class="value">Not Certified</span></div>
                </div>

            </div>
        </div>

        <div class="footer">
            FRIS is a batch-updated forest intelligence system. Core satellite/grid outputs update after the FRIS engine run, not every second.
        </div>

    </div>
</div>
</body>
</html>
"""
    return Response(html, mimetype="text/html")


@app.route("/map")
def serve_map():
    if os.path.exists(MAP_FILE):
        return send_from_directory(DATA_DIR, "fris_latest_map.html")
    return Response("Map file not found. Keep fris_latest_map.html inside data folder.", mimetype="text/plain")


@app.route("/data/<path:filename>")
def serve_data(filename):
    return send_from_directory(DATA_DIR, filename)


@app.route("/health")
def health():
    return {
        "status": "running",
        "csv_found": os.path.exists(CSV_FILE),
        "map_found": os.path.exists(MAP_FILE),
        "geojson_found": os.path.exists(GEOJSON_FILE),
        "csv_last_update": get_file_time(CSV_FILE),
        "next_expected_fris_run": next_fris_run()
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)