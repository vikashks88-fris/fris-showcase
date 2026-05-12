import os
import time
from datetime import datetime

import pandas as pd
from flask import Flask, render_template_string, send_from_directory, jsonify

app = Flask(__name__)

# ======================================================
# PATH CONFIGURATION
# ======================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")

CSV_NAME = "fris_latest.csv"
GEOJSON_NAME = "fris_latest.geojson"
MAP_NAME = "fris_latest_map.html"

CSV_PATH = os.path.join(DATA_DIR, CSV_NAME)
GEOJSON_PATH = os.path.join(DATA_DIR, GEOJSON_NAME)
MAP_PATH = os.path.join(DATA_DIR, MAP_NAME)


# ======================================================
# LOAD DATA
# ======================================================

def load_fris_data():
    paths = {
        "output_dir": DATA_DIR,
        "csv": CSV_PATH,
        "geojson": GEOJSON_PATH,
        "map": MAP_PATH,
    }

    if not os.path.exists(CSV_PATH):
        return None, paths

    try:
        df = pd.read_csv(CSV_PATH)
        df.columns = df.columns.str.strip()
        return df, paths

    except Exception as e:
        print("CSV LOAD ERROR:", e)
        return None, paths


# ======================================================
# SAFE COLUMN FINDER
# ======================================================

def safe_col(df, possible_cols):
    for col in possible_cols:
        if col in df.columns:
            return col
    return None


# ======================================================
# COUNTS
# ======================================================

def classify_counts(df, col):
    if col is None:
        return {}

    return (
        df[col]
        .fillna("Unknown")
        .astype(str)
        .value_counts()
        .to_dict()
    )


# ======================================================
# INFERENCE ENGINE
# ======================================================

def make_inference(row):
    risk = str(row.get("risk_class", "")).upper()
    health = str(row.get("health_class", "")).upper()
    moisture = str(row.get("moisture_class", "")).upper()
    fire = str(row.get("active_fire", "")).upper()

    if fire in ["TRUE", "1", "YES"]:
        return "Immediate field response required due to active fire signal."

    if "CRITICAL" in risk:
        return "Critical ecological stress detected. Immediate patrol recommended."

    if "HIGH" in risk:
        return "High stress zone. Same-day patrol recommended."

    if "MODERATE" in risk:
        return "Moderate ecological stress. Routine monitoring advised."

    if "STRESSED" in health:
        return "Vegetation stress detected. Monitor trend carefully."

    if "DRY" in moisture:
        return "Moisture stress increasing. Watch for future fire vulnerability."

    return "Routine patrol. Forest condition appears stable."


# ======================================================
# PREPARE GRID TABLE
# ======================================================

def prepare_table(df):
    df = df.copy()

    if "inference" not in df.columns:
        df["inference"] = df.apply(make_inference, axis=1)

    possible_cols = [
        "grid_id",
        "lat_center",
        "lon_center",
        "ndvi",
        "ndmi",
        "NDVI",
        "NDMI",
        "forest_pct",
        "health_class",
        "moisture_class",
        "risk_class",
        "active_fire",
        "fire_count",
        "patrol_action",
        "inference",
        "google_maps_link",
    ]

    wanted_cols = [col for col in possible_cols if col in df.columns]

    if not wanted_cols:
        return pd.DataFrame({"message": ["No matching FRIS columns found."]})

    table = df[wanted_cols].copy()

    for col in table.columns:
        if pd.api.types.is_numeric_dtype(table[col]):
            table[col] = table[col].round(4)

    return table.head(500)


# ======================================================
# MAIN DASHBOARD
# ======================================================

@app.route("/")
def dashboard():
    df, paths = load_fris_data()

    if df is None:
        return render_template_string(ERROR_TEMPLATE)

    risk_col = safe_col(df, ["risk_class"])
    health_col = safe_col(df, ["health_class"])
    moisture_col = safe_col(df, ["moisture_class"])

    risk_counts = classify_counts(df, risk_col)
    health_counts = classify_counts(df, health_col)
    moisture_counts = classify_counts(df, moisture_col)

    fire_count = 0

    if "active_fire" in df.columns:
        fire_count = (
            df["active_fire"]
            .astype(str)
            .str.upper()
            .isin(["TRUE", "1", "YES"])
            .sum()
        )

    grid_table = prepare_table(df)

    map_exists = os.path.exists(MAP_PATH)

    last_update = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    map_url = f"/map?t={int(time.time())}"

    return render_template_string(
        DASHBOARD_TEMPLATE,
        total_grids=len(df),
        fire_count=fire_count,
        risk_counts=risk_counts,
        health_counts=health_counts,
        moisture_counts=moisture_counts,
        grid_table=grid_table,
        map_exists=map_exists,
        map_url=map_url,
        last_update=last_update,
    )


# ======================================================
# MAP ROUTE
# ======================================================

@app.route("/map")
def show_map():
    if not os.path.exists(MAP_PATH):
        return "FRIS map file not found inside data folder."

    return send_from_directory(DATA_DIR, MAP_NAME)


# ======================================================
# JSON DATA API
# ======================================================

@app.route("/data")
def data_api():
    df, paths = load_fris_data()

    if df is None:
        return jsonify({"error": "CSV not found inside data folder"})

    return jsonify(df.fillna("").to_dict(orient="records"))


# ======================================================
# HEALTH CHECK
# ======================================================

@app.route("/health")
def health():
    return jsonify({
        "csv_exists": os.path.exists(CSV_PATH),
        "geojson_exists": os.path.exists(GEOJSON_PATH),
        "map_exists": os.path.exists(MAP_PATH),
        "data_dir": DATA_DIR,
        "time": datetime.now().isoformat()
    })


# ======================================================
# ERROR PAGE
# ======================================================

ERROR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Godda FRIS Dashboard</title>
    <style>
        body{
            background:#0f172a;
            color:white;
            font-family:Arial;
            padding:40px;
        }

        .box{
            background:#1e293b;
            padding:25px;
            border-radius:20px;
        }

        code{
            color:#38bdf8;
        }
    </style>
</head>

<body>
    <div class="box">
        <h1>Godda FRIS Dashboard</h1>
        <h2>CSV not found</h2>

        <p>Keep these files inside the <b>data</b> folder:</p>

        <ul>
            <li><code>fris_latest.csv</code></li>
            <li><code>fris_latest.geojson</code></li>
            <li><code>fris_latest_map.html</code></li>
        </ul>

        <p>Your GitHub structure should be:</p>

        <pre>
app.py
requirements.txt
data/
    fris_latest.csv
    fris_latest.geojson
    fris_latest_map.html
        </pre>
    </div>
</body>
</html>
"""


# ======================================================
# DASHBOARD TEMPLATE
# ======================================================

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Godda FRIS Dashboard</title>

    <meta http-equiv="refresh" content="60">

    <style>
        body{
            margin:0;
            background:#0f172a;
            color:white;
            font-family:Arial;
        }

        .sidebar{
            position:fixed;
            width:240px;
            height:100%;
            background:#020617;
            padding:20px;
        }

        .sidebar h2{
            color:#22c55e;
        }

        .sidebar a{
            display:block;
            color:#cbd5e1;
            padding:12px;
            text-decoration:none;
            margin-bottom:8px;
            border-radius:10px;
            background:#1e293b;
        }

        .main{
            margin-left:280px;
            padding:30px;
        }

        .cards{
            display:grid;
            grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));
            gap:20px;
        }

        .card{
            background:#1e293b;
            padding:20px;
            border-radius:20px;
        }

        .card h3{
            color:#94a3b8;
        }

        .number{
            font-size:34px;
            font-weight:bold;
        }

        .section{
            background:#1e293b;
            padding:20px;
            border-radius:20px;
            margin-top:25px;
        }

        .pill{
            display:inline-block;
            padding:10px 14px;
            margin:5px;
            background:#020617;
            border-radius:999px;
        }

        iframe{
            width:100%;
            height:650px;
            border:none;
            border-radius:15px;
            background:white;
        }

        table{
            width:100%;
            border-collapse:collapse;
            font-size:12px;
        }

        th{
            background:#020617;
            color:#22c55e;
            padding:10px;
            position:sticky;
            top:0;
        }

        td{
            padding:8px;
            border-bottom:1px solid #334155;
        }

        .table-wrap{
            max-height:500px;
            overflow:auto;
        }

        @media(max-width:800px){
            .sidebar{
                position:relative;
                width:auto;
                height:auto;
            }

            .main{
                margin-left:0;
                padding:15px;
            }
        }
    </style>
</head>

<body>

    <div class="sidebar">
        <h2>FRIS</h2>
        <a href="/">Dashboard</a>
        <a href="/map" target="_blank">Open Map</a>
        <a href="/data" target="_blank">JSON Data</a>
        <a href="/health" target="_blank">System Health</a>
    </div>

    <div class="main">

        <h1>Godda FRIS Dashboard</h1>
        <p>Forest Resilience Information System</p>
        <p>Last Updated: {{last_update}}</p>

        <div class="cards">

            <div class="card">
                <h3>Total Grids</h3>
                <div class="number">{{total_grids}}</div>
            </div>

            <div class="card">
                <h3>Active Fire Signals</h3>
                <div class="number">{{fire_count}}</div>
            </div>

            <div class="card">
                <h3>Map Status</h3>
                <div class="number">
                    {% if map_exists %}
                        OK
                    {% else %}
                        Missing
                    {% endif %}
                </div>
            </div>

            <div class="card">
                <h3>Dashboard Refresh</h3>
                <div class="number">60s</div>
            </div>

        </div>

        <div class="section">
            <h2>Risk Classification</h2>

            {% for k,v in risk_counts.items() %}
                <span class="pill">{{k}} : {{v}}</span>
            {% endfor %}
        </div>

        <div class="section">
            <h2>Forest Health</h2>

            {% for k,v in health_counts.items() %}
                <span class="pill">{{k}} : {{v}}</span>
            {% endfor %}
        </div>

        <div class="section">
            <h2>Moisture Status</h2>

            {% for k,v in moisture_counts.items() %}
                <span class="pill">{{k}} : {{v}}</span>
            {% endfor %}
        </div>

        <div class="section">
            <h2>Operational FRIS Map</h2>

            {% if map_exists %}
                <iframe src="{{map_url}}"></iframe>
            {% else %}
                <p>Map file missing inside data folder.</p>
            {% endif %}
        </div>

        <div class="section">
            <h2>Grid-wise Forest Intelligence</h2>

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            {% for col in grid_table.columns %}
                                <th>{{col}}</th>
                            {% endfor %}
                        </tr>
                    </thead>

                    <tbody>
                        {% for _, row in grid_table.iterrows() %}
                            <tr>
                                {% for col in grid_table.columns %}
                                    <td>{{row[col]}}</td>
                                {% endfor %}
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

    </div>

</body>
</html>
"""


# ======================================================
# RUN
# ======================================================

if __name__ == "__main__":
    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )