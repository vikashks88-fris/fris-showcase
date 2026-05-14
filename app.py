from flask import Flask, Response
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


def get_value(df, columns, default="N/A"):
    if df is None or df.empty:
        return default

    for col in columns:
        if col in df.columns:
            val = df[col].dropna()
            if len(val) > 0:
                return str(val.iloc[0])
    return default


def count_keyword(df, columns, keyword):
    if df is None or df.empty:
        return 0

    count = 0
    for col in columns:
        if col in df.columns:
            count += df[col].astype(str).str.upper().str.contains(keyword.upper(), na=False).sum()
    return int(count)


def file_time(path):
    if not os.path.exists(path):
        return "File not found"
    return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d %B %Y, %I:%M %p")


def next_fris_run():
    now = datetime.now()
    if now.time() < time(9, 30):
        return "Today 09:30 AM"
    elif now.time() < time(19, 30):
        return "Today 07:30 PM"
    else:
        return "Tomorrow 09:30 AM"


@app.route("/")
def dashboard():
    df = read_csv()

    csv_exists = os.path.exists(CSV_FILE)
    map_exists = os.path.exists(MAP_FILE)
    geojson_exists = os.path.exists(GEOJSON_FILE)

    current_time = datetime.now().strftime("%d %B %Y, %I:%M:%S %p")
    last_update = file_time(CSV_FILE)

    total_grids = len(df) if df is not None else 0
    high_risk = count_keyword(df, ["risk_class", "final_priority", "priority", "patrol_priority"], "HIGH")
    critical_risk = count_keyword(df, ["risk_class", "final_priority", "priority", "patrol_priority"], "CRITICAL")
    active_fire = (
        count_keyword(df, ["active_fire", "fire_status", "fire_detected"], "TRUE")
        + count_keyword(df, ["active_fire", "fire_status", "fire_detected"], "YES")
        + count_keyword(df, ["active_fire", "fire_status", "fire_detected"], "ACTIVE")
    )

    ndvi = get_value(df, ["mean_ndvi", "ndvi", "NDVI"])
    ndmi = get_value(df, ["mean_ndmi", "ndmi", "NDMI"])
    temperature = get_value(df, ["temperature", "temp_c", "temperature_c"])
    rainfall = get_value(df, ["rainfall", "rain_mm", "rainfall_mm"])
    wind = get_value(df, ["wind", "wind_speed", "wind_kmph"])
    carbon = get_value(df, ["ecosystem_carbon_total_ton", "estimated_ecosystem_carbon_ton", "carbon_total_ton"])
    forest_area = get_value(df, ["forest_dominant_area_ha", "forest_area_ha", "total_forest_area_ha"])

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Godda FRIS Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="600">

    <style>
        body {{
            margin: 0;
            background: #07150c;
            color: white;
            font-family: Arial, sans-serif;
        }}

        .layout {{
            display: flex;
            min-height: 100vh;
        }}

        .sidebar {{
            width: 245px;
            background: linear-gradient(180deg, #0d2f16, #07150c);
            padding: 22px;
            border-right: 1px solid rgba(255,255,255,0.15);
        }}

        .logo {{
            font-size: 34px;
            font-weight: bold;
            color: #d6ff00;
            margin-bottom: 8px;
        }}

        .subtitle {{
            font-size: 12px;
            color: #baff75;
            margin-bottom: 28px;
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

        .side-card, .card, .map-card, .topbar {{
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 22px;
            padding: 18px;
        }}

        .main {{
            flex: 1;
            padding: 24px;
        }}

        .topbar {{
            display: flex;
            justify-content: space-between;
            gap: 18px;
            margin-bottom: 22px;
        }}

        .grid {{
            display: grid;
            grid-template-columns: 1fr 330px;
            gap: 22px;
        }}

        iframe {{
            width: 100%;
            height: 620px;
            border: none;
            border-radius: 18px;
            background: #183d22;
        }}

        .right {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        .row {{
            display: flex;
            justify-content: space-between;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            padding: 9px 0;
            font-size: 14px;
        }}

        .value {{
            color: #d6ff00;
            font-weight: bold;
            text-align: right;
        }}

        .btn {{
            background: #c8ff00;
            color: #07150c;
            padding: 10px 14px;
            border-radius: 12px;
            text-decoration: none;
            font-weight: bold;
            display: inline-block;
            margin-left: 8px;
        }}

        .good {{ color: #9dff5c; font-weight: bold; }}
        .bad {{ color: #ff6b6b; font-weight: bold; }}

        @media(max-width: 900px) {{
            .layout {{ flex-direction: column; }}
            .sidebar {{ width: auto; }}
            .topbar {{ flex-direction: column; }}
            .grid {{ grid-template-columns: 1fr; }}
            iframe {{ height: 520px; }}
        }}
    </style>
</head>

<body>
<div class="layout">

    <div class="sidebar">
        <div class="logo">FRIS</div>
        <div class="subtitle">Forest Resilience Information System</div>

        <div class="nav active">🏠 Dashboard</div>
        <div class="nav">🗺️ Risk Map</div>
        <div class="nav">🔥 Fire Intelligence</div>
        <div class="nav">💧 Moisture Stress</div>
        <div class="nav">🌿 Carbon MRV</div>

        <div class="side-card">
            <b>Godda Forest Division</b><br><br>
            CSV: <span class="{'good' if csv_exists else 'bad'}">{'Found' if csv_exists else 'Missing'}</span><br>
            Map: <span class="{'good' if map_exists else 'bad'}">{'Found' if map_exists else 'Missing'}</span><br>
            GeoJSON: <span class="{'good' if geojson_exists else 'bad'}">{'Found' if geojson_exists else 'Missing'}</span><br><br>
            Forest Area:<br>
            <b>{forest_area}</b>
        </div>
    </div>

    <div class="main">

        <div class="topbar">
            <div>
                <b>Current Dashboard Time</b><br>
                {current_time}
            </div>

            <div>
                <b>Last FRIS Data Update</b><br>
                {last_update}
            </div>

            <div>
                <b>Next Expected Run</b><br>
                {next_fris_run()}
            </div>

            <div>
                <a class="btn" href="/">Refresh</a>
                <a class="btn" href="/map" target="_blank">Open Map</a>
                <a class="btn" href="/debug-files" target="_blank">Debug</a>
            </div>
        </div>

        <div class="grid">

            <div class="map-card">
                <h2>FRIS Risk Map</h2>

                {
                    "<iframe src='/map'></iframe>"
                    if map_exists
                    else f"<div style='color:#ff7777;font-weight:bold;padding:30px;'>Map file missing.<br><br>Render searched:<br>{MAP_FILE}</div>"
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
                    <div class="row"><span>Carbon</span><span class="value">{carbon}</span></div>
                    <div class="row"><span>Status</span><span class="value">Satellite Assisted</span></div>
                </div>

            </div>
        </div>
    </div>
</div>
</body>
</html>
"""
    return Response(html, mimetype="text/html")


@app.route("/map")
def map_page():
    if not os.path.exists(MAP_FILE):
        return Response(
            f"""
            <h2 style="color:red;">Map file not found</h2>
            <p>Render searched this exact path:</p>
            <pre>{MAP_FILE}</pre>
            <p>Required file:</p>
            <pre>data/fris_latest_map.html</pre>
            """,
            mimetype="text/html"
        )

    try:
        with open(MAP_FILE, "r", encoding="utf-8") as f:
            map_html = f.read()

        return Response(map_html, mimetype="text/html")

    except Exception as e:
        return Response(
            f"""
            <h2 style="color:red;">Map file exists but could not be opened</h2>
            <pre>{str(e)}</pre>
            """,
            mimetype="text/html"
        )


@app.route("/debug-files")
def debug_files():
    try:
        base_files = os.listdir(BASE_DIR)
    except Exception as e:
        base_files = [f"Error reading BASE_DIR: {e}"]

    try:
        data_files = os.listdir(DATA_DIR)
    except Exception as e:
        data_files = [f"Error reading DATA_DIR: {e}"]

    html = f"""
    <h2>FRIS Render File Debug</h2>

    <h3>BASE_DIR</h3>
    <pre>{BASE_DIR}</pre>

    <h3>DATA_DIR</h3>
    <pre>{DATA_DIR}</pre>

    <h3>Files in BASE_DIR</h3>
    <pre>{base_files}</pre>

    <h3>Files in DATA_DIR</h3>
    <pre>{data_files}</pre>

    <h3>Expected Files</h3>
    <pre>
CSV: {CSV_FILE} -> {os.path.exists(CSV_FILE)}
MAP: {MAP_FILE} -> {os.path.exists(MAP_FILE)}
GEOJSON: {GEOJSON_FILE} -> {os.path.exists(GEOJSON_FILE)}
    </pre>
    """
    return Response(html, mimetype="text/html")


@app.route("/health")
def health():
    return {
        "status": "running",
        "csv_found": os.path.exists(CSV_FILE),
        "map_found": os.path.exists(MAP_FILE),
        "geojson_found": os.path.exists(GEOJSON_FILE),
        "base_dir": BASE_DIR,
        "data_dir": DATA_DIR
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)