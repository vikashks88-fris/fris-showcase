from flask import Flask, Response, send_from_directory, jsonify
import os
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)

# -----------------------------
# FIXED PATHS
# -----------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CSV_FILE = os.path.join(DATA_DIR, "fris_latest.csv")
MAP_FILE = os.path.join(DATA_DIR, "fris_latest_map.html")
GEOJSON_FILE = os.path.join(DATA_DIR, "fris_latest.geojson")

IST = ZoneInfo("Asia/Kolkata")


# -----------------------------
# TIME FUNCTIONS
# -----------------------------

def ist_now():
    return datetime.now(IST)


def format_ist(dt):
    return dt.strftime("%d %B %Y, %I:%M:%S %p IST")


def get_file_update_time(file_path):
    if not os.path.exists(file_path):
        return "File not found"

    timestamp = os.path.getmtime(file_path)
    dt = datetime.fromtimestamp(timestamp, IST)
    return format_ist(dt)


def get_file_age_minutes(file_path):
    if not os.path.exists(file_path):
        return "N/A"

    modified = datetime.fromtimestamp(os.path.getmtime(file_path), IST)
    diff = ist_now() - modified
    minutes = int(diff.total_seconds() // 60)

    if minutes < 1:
        return "Updated just now"
    elif minutes == 1:
        return "Updated 1 minute ago"
    else:
        return f"Updated {minutes} minutes ago"


def next_expected_run():
    now = ist_now()

    morning = now.replace(hour=9, minute=30, second=0, microsecond=0)
    evening = now.replace(hour=19, minute=30, second=0, microsecond=0)

    if now < morning:
        return format_ist(morning)
    elif now < evening:
        return format_ist(evening)
    else:
        tomorrow = now + timedelta(days=1)
        next_run = tomorrow.replace(hour=9, minute=30, second=0, microsecond=0)
        return format_ist(next_run)


# -----------------------------
# CSV FUNCTIONS
# -----------------------------

def read_csv():
    if not os.path.exists(CSV_FILE):
        return None

    try:
        return pd.read_csv(CSV_FILE)
    except Exception:
        return None


def get_value(df, columns, default="N/A"):
    if df is None or df.empty:
        return default

    for col in columns:
        if col in df.columns:
            data = df[col].dropna()
            if len(data) > 0:
                return str(data.iloc[0])

    return default


def count_keyword(df, columns, keyword):
    if df is None or df.empty:
        return 0

    total = 0
    for col in columns:
        if col in df.columns:
            total += df[col].astype(str).str.upper().str.contains(keyword.upper(), na=False).sum()

    return int(total)


# -----------------------------
# DASHBOARD
# -----------------------------

@app.route("/")
def dashboard():
    df = read_csv()

    current_time = format_ist(ist_now())
    last_csv_update = get_file_update_time(CSV_FILE)
    csv_age = get_file_age_minutes(CSV_FILE)
    next_run = next_expected_run()

    csv_found = os.path.exists(CSV_FILE)
    map_found = os.path.exists(MAP_FILE)
    geojson_found = os.path.exists(GEOJSON_FILE)

    total_grids = len(df) if df is not None else 0

    high_risk = count_keyword(df, ["risk_class", "final_priority", "priority"], "HIGH")
    critical_risk = count_keyword(df, ["risk_class", "final_priority", "priority"], "CRITICAL")

    active_fire = (
        count_keyword(df, ["active_fire", "fire_status", "fire_detected"], "TRUE")
        + count_keyword(df, ["active_fire", "fire_status", "fire_detected"], "YES")
        + count_keyword(df, ["active_fire", "fire_status", "fire_detected"], "ACTIVE")
    )

    ndvi = get_value(df, ["ndvi", "mean_ndvi", "avg_ndvi"])
    ndmi = get_value(df, ["ndmi", "mean_ndmi", "avg_ndmi"])

    temperature = get_value(df, ["temperature", "temperature_c", "temp_c"], "N/A")
    rainfall = get_value(df, ["rainfall", "rainfall_mm", "rain_mm"], "N/A")
    wind = get_value(df, ["wind", "wind_speed", "wind_kmph"], "N/A")

    carbon = get_value(
        df,
        [
            "ecosystem_carbon_total_ton",
            "estimated_ecosystem_carbon_ton",
            "carbon_total_ton",
            "baseline_ecosystem_carbon_total_ton"
        ],
        "N/A"
    )

    forest_area = get_value(
        df,
        ["forest_dominant_area_ha", "forest_area_ha", "total_forest_area_ha"],
        "N/A"
    )

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>FRIS Godda Dashboard</title>
    <meta http-equiv="refresh" content="30">
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

        .logo {{
            margin-bottom: 35px;
        }}

        .logo h1 {{
            color: #dfff00;
            font-size: 38px;
            margin: 0;
        }}

        .logo p {{
            color: #c6ff6b;
            font-size: 13px;
            margin: 4px 0 0;
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
            background: #dfff00;
            color: #102000;
            padding: 12px 16px;
            border-radius: 14px;
            text-decoration: none;
            font-weight: bold;
            margin-left: 8px;
        }}

        .content {{
            display: grid;
            grid-template-columns: 1fr 330px;
            gap: 22px;
        }}

        .map-card, .card {{
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.18);
            border-radius: 24px;
            padding: 18px;
        }}

        .map-card h2 {{
            margin-top: 0;
            font-size: 24px;
        }}

        iframe {{
            width: 100%;
            height: 650px;
            border: none;
            border-radius: 18px;
            background: #1b5525;
        }}

        .right {{
            display: flex;
            flex-direction: column;
            gap: 15px;
        }}

        .card h3 {{
            margin-top: 0;
            font-size: 18px;
        }}

        .row {{
            display: flex;
            justify-content: space-between;
            padding: 9px 0;
            border-bottom: 1px solid rgba(255,255,255,0.12);
            font-size: 14px;
        }}

        .value {{
            color: #dfff00;
            font-weight: bold;
            text-align: right;
        }}

        .footer {{
            margin-top: 18px;
            font-size: 13px;
            color: #c5d6c5;
        }}

        @media(max-width: 900px) {{
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
            <h1>FRIS</h1>
            <p>Forest Resilience Information System</p>
        </div>

        <div class="nav active">🏠 Dashboard</div>
        <div class="nav">🗺️ Risk Map</div>
        <div class="nav">🔥 Fire Intelligence</div>
        <div class="nav">💧 Moisture Stress</div>
        <div class="nav">🌿 Carbon MRV</div>

        <div class="side-card">
            <b>Godda Forest Division</b><br><br>

            CSV:
            <span class="{'ok' if csv_found else 'bad'}">
                {'Found' if csv_found else 'Missing'}
            </span><br>

            Map:
            <span class="{'ok' if map_found else 'bad'}">
                {'Found' if map_found else 'Missing'}
            </span><br>

            GeoJSON:
            <span class="{'ok' if geojson_found else 'bad'}">
                {'Found' if geojson_found else 'Missing'}
            </span><br><br>

            <b>Forest Area:</b><br>
            {forest_area}
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
                <a class="btn" href="/map" target="_blank">Open Map</a>
                <a class="btn" href="/debug" target="_blank">Debug</a>
            </div>
        </div>

        <div class="content">

            <div class="map-card">
                <h2>FRIS Risk Map</h2>

                {
                    "<iframe src='/map' loading='lazy' allowfullscreen referrerpolicy='no-referrer'></iframe>"
                    if map_found
                    else "<div style='padding:40px;color:#ff6b6b;font-weight:bold;'>Map file missing. Keep fris_latest_map.html inside data folder.</div>"
                }
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
                    <h3>💧 NDVI / NDMI</h3>
                    <div class="row"><span>NDVI</span><span class="value">{ndvi}</span></div>
                    <div class="row"><span>NDMI</span><span class="value">{ndmi}</span></div>
                </div>

                <div class="card">
                    <h3>🌦️ Weather</h3>
                    <div class="row"><span>Temperature</span><span class="value">{temperature}</span></div>
                    <div class="row"><span>Rainfall</span><span class="value">{rainfall}</span></div>
                    <div class="row"><span>Wind</span><span class="value">{wind}</span></div>
                </div>

                <div class="card">
                    <h3>🌿 Carbon MRV</h3>
                    <div class="row"><span>Estimated Carbon</span><span class="value">{carbon}</span></div>
                    <div class="row"><span>Status</span><span class="value">Satellite Assisted</span></div>
                    <div class="row"><span>Claim Status</span><span class="value">Not Certified</span></div>
                </div>

            </div>
        </div>

        <div class="footer">
            Dashboard refreshes every 30 seconds. All displayed time is forced to Asia/Kolkata IST.
        </div>

    </div>

</div>
</body>
</html>
"""
    return Response(html, mimetype="text/html")


# -----------------------------
# MAP ROUTE
# -----------------------------

@app.route("/map")
def serve_map():
    if os.path.exists(MAP_FILE):
        return send_from_directory(DATA_DIR, "fris_latest_map.html")
    return Response("Map file not found in data folder.", mimetype="text/plain")


# -----------------------------
# DATA ROUTE
# -----------------------------

@app.route("/data/<path:filename>")
def serve_data(filename):
    return send_from_directory(DATA_DIR, filename)


# -----------------------------
# DEBUG ROUTE
# -----------------------------

@app.route("/debug")
def debug():
    return jsonify({
        "server_time_ist": format_ist(ist_now()),
        "csv_found": os.path.exists(CSV_FILE),
        "map_found": os.path.exists(MAP_FILE),
        "geojson_found": os.path.exists(GEOJSON_FILE),
        "csv_last_update": get_file_update_time(CSV_FILE),
        "csv_age": get_file_age_minutes(CSV_FILE),
        "next_expected_run": next_expected_run(),
        "base_dir": BASE_DIR,
        "data_dir": DATA_DIR,
        "csv_file": CSV_FILE,
        "map_file": MAP_FILE,
        "geojson_file": GEOJSON_FILE
    })


# -----------------------------
# LOCAL RUN
# -----------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)