import os
import time
from datetime import datetime

import pandas as pd
from flask import Flask, render_template_string, send_from_directory, jsonify


app = Flask(__name__)

# ======================================================
# PATH CONFIGURATION
# Works on both Windows local system and Render
# ======================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

POSSIBLE_OUTPUT_DIRS = [
    os.path.join(BASE_DIR, "output"),
    os.path.join(BASE_DIR, "data"),
    os.path.join(BASE_DIR, "..", "output"),
    r"C:\fris_showcase\output",
    r"C:\cfris\output",
]

CSV_NAME = "fris_latest.csv"
GEOJSON_NAME = "fris_latest.geojson"
MAP_NAME = "fris_latest_map.html"


def find_output_dir():
    for folder in POSSIBLE_OUTPUT_DIRS:
        csv_path = os.path.join(folder, CSV_NAME)
        if os.path.exists(csv_path):
            return folder
    return os.path.join(BASE_DIR, "output")


def get_paths():
    output_dir = find_output_dir()
    return {
        "output_dir": output_dir,
        "csv": os.path.join(output_dir, CSV_NAME),
        "geojson": os.path.join(output_dir, GEOJSON_NAME),
        "map": os.path.join(output_dir, MAP_NAME),
    }


# ======================================================
# DATA LOADING
# CSV is loaded fresh on every request
# ======================================================

def load_fris_data():
    paths = get_paths()
    csv_path = paths["csv"]

    if not os.path.exists(csv_path):
        return None, paths

    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    return df, paths


def safe_col(df, possible_cols, default=None):
    for col in possible_cols:
        if col in df.columns:
            return col
    return default


def classify_counts(df, col):
    if col is None or col not in df.columns:
        return {}

    return df[col].fillna("Unknown").astype(str).value_counts().to_dict()


def make_inference(row):
    risk_col = safe_col(row.index.to_frame().T, ["risk_class", "final_priority", "patrol_priority"])
    health_col = safe_col(row.index.to_frame().T, ["health_class", "vegetation_health"])
    moisture_col = safe_col(row.index.to_frame().T, ["moisture_class", "moisture_status"])

    risk = str(row.get(risk_col, "")).upper() if risk_col else ""
    health = str(row.get(health_col, "")).upper() if health_col else ""
    moisture = str(row.get(moisture_col, "")).upper() if moisture_col else ""

    active_fire = str(row.get("active_fire", "False")).upper()

    if active_fire in ["TRUE", "1", "YES"]:
        return "Immediate visit required. Active fire signal detected."

    if "CRITICAL" in risk or "VERY HIGH" in risk:
        return "Immediate field verification required. Critical forest stress detected."

    if "HIGH" in risk:
        return "Same-day patrol recommended. Dryness or vegetation stress is high."

    if "MODERATE" in risk or "STRESSED" in health or "DRY" in moisture:
        return "Routine patrol with observation. Early stress signs may be present."

    return "Routine patrol. Forest condition appears normal in this grid."


def prepare_grid_table(df):
    df = df.copy()

    grid_col = safe_col(df, ["grid_id", "id"], "grid_id")
    lat_col = safe_col(df, ["lat_center", "lat", "latitude"], None)
    lon_col = safe_col(df, ["lon_center", "lon", "longitude"], None)
    ndvi_col = safe_col(df, ["NDVI", "ndvi"], None)
    ndmi_col = safe_col(df, ["NDMI", "ndmi"], None)
    forest_col = safe_col(df, ["forest_pct", "forest_percent", "forest_percentage"], None)
    risk_col = safe_col(df, ["risk_class", "final_priority", "patrol_priority"], None)
    health_col = safe_col(df, ["health_class", "vegetation_health"], None)
    moisture_col = safe_col(df, ["moisture_class", "moisture_status"], None)

    if grid_col not in df.columns:
        df["grid_id"] = range(1, len(df) + 1)
        grid_col = "grid_id"

    df["inference"] = df.apply(make_inference, axis=1)

    cols = [grid_col]

    for c in [lat_col, lon_col, ndvi_col, ndmi_col, forest_col, health_col, moisture_col, risk_col, "inference"]:
        if c and c in df.columns and c not in cols:
            cols.append(c)

    table = df[cols].copy()

    for c in table.columns:
        if pd.api.types.is_numeric_dtype(table[c]):
            table[c] = table[c].round(4)

    return table.head(500)


# ======================================================
# ROUTES
# ======================================================

@app.route("/")
def dashboard():
    df, paths = load_fris_data()

    if df is None:
        return render_template_string(ERROR_TEMPLATE, paths=paths, searched=POSSIBLE_OUTPUT_DIRS)

    total_grids = len(df)

    risk_col = safe_col(df, ["risk_class", "final_priority", "patrol_priority"])
    health_col = safe_col(df, ["health_class", "vegetation_health"])
    moisture_col = safe_col(df, ["moisture_class", "moisture_status"])

    risk_counts = classify_counts(df, risk_col)
    health_counts = classify_counts(df, health_col)
    moisture_counts = classify_counts(df, moisture_col)

    active_fire_count = 0
    if "active_fire" in df.columns:
        active_fire_count = df["active_fire"].astype(str).str.upper().isin(["TRUE", "1", "YES"]).sum()

    grid_table = prepare_grid_table(df)

    map_exists = os.path.exists(paths["map"])
    geojson_exists = os.path.exists(paths["geojson"])

    last_modified = datetime.fromtimestamp(os.path.getmtime(paths["csv"])).strftime("%d-%m-%Y %H:%M:%S")
    current_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    map_url = f"/map?t={int(time.time())}"

    return render_template_string(
        DASHBOARD_TEMPLATE,
        total_grids=total_grids,
        active_fire_count=active_fire_count,
        risk_counts=risk_counts,
        health_counts=health_counts,
        moisture_counts=moisture_counts,
        grid_table=grid_table,
        map_exists=map_exists,
        geojson_exists=geojson_exists,
        map_url=map_url,
        output_dir=paths["output_dir"],
        last_modified=last_modified,
        current_time=current_time,
        columns=list(df.columns),
    )


@app.route("/map")
def show_map():
    paths = get_paths()
    if not os.path.exists(paths["map"]):
        return "FRIS map file not found.", 404
    return send_from_directory(paths["output_dir"], MAP_NAME)


@app.route("/data")
def data_json():
    df, paths = load_fris_data()
    if df is None:
        return jsonify({"error": "CSV not found", "searched": POSSIBLE_OUTPUT_DIRS})
    return jsonify(df.fillna("").to_dict(orient="records"))


@app.route("/health")
def health():
    df, paths = load_fris_data()
    return jsonify({
        "csv_found": df is not None,
        "output_dir": paths["output_dir"],
        "csv_path": paths["csv"],
        "map_path": paths["map"],
        "geojson_path": paths["geojson"],
        "time": datetime.now().isoformat()
    })


# ======================================================
# HTML TEMPLATES
# ======================================================

ERROR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Godda FRIS Dashboard</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0f172a;
            color: white;
            padding: 40px;
        }
        .box {
            background: #1e293b;
            padding: 30px;
            border-radius: 18px;
            max-width: 900px;
        }
        code {
            color: #38bdf8;
        }
    </style>
</head>
<body>
    <div class="box">
        <h1>Godda FRIS Dashboard</h1>
        <h2>CSV not found</h2>

        <p>The app searched these folders:</p>
        <ul>
        {% for folder in searched %}
            <li><code>{{ folder }}</code></li>
        {% endfor %}
        </ul>

        <p>Required file:</p>
        <code>fris_latest.csv</code>

        <p>Correct structure:</p>
        <pre>
fris_showcase/
├── app.py
├── requirements.txt
└── output/
    ├── fris_latest.csv
    ├── fris_latest.geojson
    └── fris_latest_map.html
        </pre>
    </div>
</body>
</html>
"""


DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Godda FRIS Dashboard</title>
    <meta http-equiv="refresh" content="60">

    <style>
        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #0f172a;
            color: #e5e7eb;
        }

        .layout {
            display: flex;
            min-height: 100vh;
        }

        .sidebar {
            width: 260px;
            background: #020617;
            padding: 24px;
            border-right: 1px solid #334155;
            position: fixed;
            height: 100vh;
            overflow-y: auto;
        }

        .sidebar h2 {
            color: #22c55e;
            margin-bottom: 30px;
        }

        .sidebar a {
            display: block;
            color: #cbd5e1;
            text-decoration: none;
            padding: 12px 14px;
            margin-bottom: 8px;
            border-radius: 10px;
            background: #0f172a;
        }

        .sidebar a:hover {
            background: #1e293b;
            color: white;
        }

        .main {
            margin-left: 310px;
            padding: 30px;
            width: calc(100% - 310px);
        }

        .hero {
            background: linear-gradient(135deg, #064e3b, #14532d, #0f172a);
            padding: 28px;
            border-radius: 24px;
            margin-bottom: 24px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.35);
        }

        .hero h1 {
            margin: 0;
            font-size: 34px;
        }

        .hero p {
            color: #d1fae5;
        }

        .cards {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 18px;
            margin-bottom: 28px;
        }

        .card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 20px;
            padding: 20px;
        }

        .card h3 {
            margin: 0;
            color: #94a3b8;
            font-size: 14px;
        }

        .card .number {
            font-size: 32px;
            font-weight: bold;
            margin-top: 10px;
            color: white;
        }

        .section {
            background: #1e293b;
            border: 1px solid #334155;
            padding: 22px;
            border-radius: 22px;
            margin-bottom: 24px;
        }

        .section h2 {
            margin-top: 0;
            color: #86efac;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        th {
            background: #020617;
            color: #86efac;
            padding: 10px;
            text-align: left;
            position: sticky;
            top: 0;
        }

        td {
            border-bottom: 1px solid #334155;
            padding: 9px;
            color: #e5e7eb;
        }

        tr:hover {
            background: #334155;
        }

        .table-wrap {
            max-height: 520px;
            overflow: auto;
            border-radius: 14px;
            border: 1px solid #334155;
        }

        .pill {
            display: inline-block;
            background: #020617;
            border: 1px solid #334155;
            padding: 8px 12px;
            border-radius: 999px;
            margin: 5px;
        }

        iframe {
            width: 100%;
            height: 650px;
            border: none;
            border-radius: 18px;
            background: white;
        }

        .small {
            color: #94a3b8;
            font-size: 13px;
        }

        .ok {
            color: #22c55e;
        }

        .warn {
            color: #facc15;
        }

        @media (max-width: 1000px) {
            .sidebar {
                position: relative;
                width: auto;
                height: auto;
            }

            .layout {
                display: block;
            }

            .main {
                margin-left: 0;
                width: auto;
            }

            .cards {
                grid-template-columns: repeat(2, 1fr);
            }
        }
    </style>
</head>

<body>
<div class="layout">

    <div class="sidebar">
        <h2>FRIS</h2>
        <a href="#summary">Dashboard Summary</a>
        <a href="#risk">Risk Classification</a>
        <a href="#health">Forest Health</a>
        <a href="#moisture">Moisture Status</a>
        <a href="#map">Operational Map</a>
        <a href="#grid">Grid-wise Intelligence</a>
        <a href="/data" target="_blank">View Raw JSON</a>
        <a href="/health" target="_blank">System Health</a>
    </div>

    <div class="main">

        <div class="hero" id="summary">
            <h1>Godda FRIS Dashboard</h1>
            <p>Forest Resilience Information System — live CSV-based forest monitoring dashboard.</p>
            <p class="small">
                CSV last modified: {{ last_modified }} |
                Dashboard refreshed: {{ current_time }}
            </p>
            <p class="small">Reading from: {{ output_dir }}</p>
        </div>

        <div class="cards">
            <div class="card">
                <h3>Total Forest Grids</h3>
                <div class="number">{{ total_grids }}</div>
            </div>

            <div class="card">
                <h3>Active Fire Signals</h3>
                <div class="number">{{ active_fire_count }}</div>
            </div>

            <div class="card">
                <h3>Map Status</h3>
                <div class="number">{% if map_exists %}<span class="ok">OK</span>{% else %}<span class="warn">Missing</span>{% endif %}</div>
            </div>

            <div class="card">
                <h3>GeoJSON Status</h3>
                <div class="number">{% if geojson_exists %}<span class="ok">OK</span>{% else %}<span class="warn">Missing</span>{% endif %}</div>
            </div>
        </div>

        <div class="section" id="risk">
            <h2>Risk Classification</h2>
            {% for k, v in risk_counts.items() %}
                <span class="pill">{{ k }} : {{ v }}</span>
            {% endfor %}
        </div>

        <div class="section" id="health">
            <h2>Forest Health</h2>
            {% for k, v in health_counts.items() %}
                <span class="pill">{{ k }} : {{ v }}</span>
            {% endfor %}
        </div>

        <div class="section" id="moisture">
            <h2>Moisture Status</h2>
            {% for k, v in moisture_counts.items() %}
                <span class="pill">{{ k }} : {{ v }}</span>
            {% endfor %}
        </div>

        <div class="section" id="map">
            <h2>Operational FRIS Map</h2>
            {% if map_exists %}
                <iframe src="{{ map_url }}"></iframe>
            {% else %}
                <p class="warn">Map file not found: fris_latest_map.html</p>
            {% endif %}
        </div>

        <div class="section" id="grid">
            <h2>Grid-wise Intelligence</h2>
            <p class="small">Showing first 500 grids. CSV is reloaded fresh every time dashboard refreshes.</p>

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            {% for col in grid_table.columns %}
                                <th>{{ col }}</th>
                            {% endfor %}
                        </tr>
                    </thead>
                    <tbody>
                        {% for _, row in grid_table.iterrows() %}
                        <tr>
                            {% for col in grid_table.columns %}
                                <td>{{ row[col] }}</td>
                            {% endfor %}
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

    </div>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)