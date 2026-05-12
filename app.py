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

POSSIBLE_OUTPUT_DIRS = [

    # RENDER / GITHUB
    os.path.join(BASE_DIR, "data"),

    # OPTIONAL
    BASE_DIR,
    os.path.join(BASE_DIR, "output"),

    # WINDOWS LOCAL
    r"C:\fris_showcase",
    r"C:\fris_showcase\data",

    r"C:\cfris",
    r"C:\cfris\output",
]

CSV_NAME = "fris_latest.csv"
GEOJSON_NAME = "fris_latest.geojson"
MAP_NAME = "fris_latest_map.html"

# ======================================================
# FIND FILE LOCATION
# ======================================================

def find_output_dir():

    for folder in POSSIBLE_OUTPUT_DIRS:

        csv_path = os.path.join(folder, CSV_NAME)

        if os.path.exists(csv_path):
            return folder

    return os.path.join(BASE_DIR, "data")


def get_paths():

    output_dir = find_output_dir()

    return {
        "output_dir": output_dir,
        "csv": os.path.join(output_dir, CSV_NAME),
        "geojson": os.path.join(output_dir, GEOJSON_NAME),
        "map": os.path.join(output_dir, MAP_NAME),
    }

# ======================================================
# LOAD DATA
# ======================================================

def load_fris_data():

    paths = get_paths()

    if not os.path.exists(paths["csv"]):
        return None, paths

    try:

        df = pd.read_csv(paths["csv"])

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
# PREPARE TABLE
# ======================================================

def prepare_table(df):

    df = df.copy()

    df["inference"] = df.apply(make_inference, axis=1)

    wanted_cols = []

    possible = [
        "grid_id",
        "lat_center",
        "lon_center",
        "NDVI",
        "NDMI",
        "forest_pct",
        "health_class",
        "moisture_class",
        "risk_class",
        "active_fire",
        "inference",
    ]

    for col in possible:

        if col in df.columns:
            wanted_cols.append(col)

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

        return f"""
        <h1>Godda FRIS Dashboard</h1>

        <h3>CSV not found.</h3>

        <p>Expected inside data folder:</p>

        <ul>
            <li>fris_latest.csv</li>
            <li>fris_latest.geojson</li>
            <li>fris_latest_map.html</li>
        </ul>
        """

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

    map_exists = os.path.exists(paths["map"])

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
        output_dir=paths["output_dir"],
    )

# ======================================================
# MAP ROUTE
# ======================================================

@app.route("/map")
def show_map():

    paths = get_paths()

    if not os.path.exists(paths["map"]):
        return "FRIS map file not found."

    return send_from_directory(
        paths["output_dir"],
        MAP_NAME
    )

# ======================================================
# DATA API
# ======================================================

@app.route("/data")
def data_api():

    df, paths = load_fris_data()

    if df is None:
        return jsonify({"error": "CSV not found"})

    return jsonify(
        df.fillna("").to_dict(orient="records")
    )

# ======================================================
# HEALTH CHECK
# ======================================================

@app.route("/health")
def health():

    paths = get_paths()

    return jsonify({

        "csv_exists": os.path.exists(paths["csv"]),
        "geojson_exists": os.path.exists(paths["geojson"]),
        "map_exists": os.path.exists(paths["map"]),
        "output_dir": paths["output_dir"],
        "time": datetime.now().isoformat()
    })

# ======================================================
# TEMPLATE
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

.main{
    padding:30px;
}

.card{
    background:#1e293b;
    padding:20px;
    border-radius:20px;
    margin-bottom:20px;
}

iframe{
    width:100%;
    height:700px;
    border:none;
    border-radius:20px;
    background:white;
}

table{
    width:100%;
    border-collapse:collapse;
}

th{
    background:#111827;
    color:#22c55e;
    padding:10px;
}

td{
    padding:8px;
    border-bottom:1px solid #334155;
}

</style>

</head>

<body>

<div class="main">

<h1>Godda FRIS Dashboard</h1>

<p>Forest Resilience Information System</p>

<p>Last Updated: {{last_update}}</p>

<div class="card">

<h2>Total Grids: {{total_grids}}</h2>

<h2>Active Fire Signals: {{fire_count}}</h2>

</div>

<div class="card">

<h2>FRIS Operational Map</h2>

{% if map_exists %}

<iframe src="{{map_url}}"></iframe>

{% else %}

<p>Map file missing.</p>

{% endif %}

</div>

<div class="card">

<h2>Grid Intelligence</h2>

{{grid_table.to_html(index=False)}}

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