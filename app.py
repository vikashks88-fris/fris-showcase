import os
import time
from datetime import datetime

import pandas as pd
from flask import Flask, render_template_string, send_from_directory, jsonify

app = Flask(__name__)

# ======================================================
# FILE NAMES
# ======================================================

CSV_NAME = "fris_latest.csv"
GEOJSON_NAME = "fris_latest.geojson"
MAP_NAME = "fris_latest_map.html"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SEARCH_DIRS = [
    os.path.join(BASE_DIR, "data"),
    BASE_DIR,
    os.path.join(BASE_DIR, "output"),
]


# ======================================================
# FIND FILES
# ======================================================

def find_file(filename):
    for folder in SEARCH_DIRS:
        file_path = os.path.join(folder, filename)
        if os.path.exists(file_path):
            return file_path, folder
    return None, None


def get_paths():
    csv_path, csv_folder = find_file(CSV_NAME)
    geojson_path, geojson_folder = find_file(GEOJSON_NAME)
    map_path, map_folder = find_file(MAP_NAME)

    return {
        "csv": csv_path,
        "csv_folder": csv_folder,
        "geojson": geojson_path,
        "geojson_folder": geojson_folder,
        "map": map_path,
        "map_folder": map_folder,
    }


# ======================================================
# LOAD CSV
# ======================================================

def load_fris_data():
    paths = get_paths()

    if paths["csv"] is None:
        return None, paths

    try:
        df = pd.read_csv(paths["csv"])
        df.columns = df.columns.str.strip()
        return df, paths

    except Exception as e:
        print("CSV LOAD ERROR:", e)
        return None, paths


# ======================================================
# BASIC HELPERS
# ======================================================

def count_value(df, column, value):
    if column not in df.columns:
        return 0

    return (
        df[column]
        .astype(str)
        .str.upper()
        .eq(value)
        .sum()
    )


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


def prepare_table(df):
    df = df.copy()

    if "inference" not in df.columns:
        df["inference"] = df.apply(make_inference, axis=1)

    preferred_cols = [
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

    cols = [c for c in preferred_cols if c in df.columns]

    if not cols:
        return pd.DataFrame({"message": ["CSV loaded, but expected FRIS columns were not found."]})

    table = df[cols].copy()

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
        return render_template_string(
            ERROR_TEMPLATE,
            searched=SEARCH_DIRS
        )

    total_grids = len(df)

    critical = count_value(df, "risk_class", "CRITICAL")
    high = count_value(df, "risk_class", "HIGH")
    moderate = count_value(df, "risk_class", "MODERATE")
    low = count_value(df, "risk_class", "LOW")

    fire_count = 0

    if "active_fire" in df.columns:
        fire_count = (
            df["active_fire"]
            .astype(str)
            .str.upper()
            .isin(["TRUE", "1", "YES"])
            .sum()
        )

    avg_ndvi = 0
    avg_ndmi = 0

    ndvi_col = "ndvi" if "ndvi" in df.columns else "NDVI" if "NDVI" in df.columns else None
    ndmi_col = "ndmi" if "ndmi" in df.columns else "NDMI" if "NDMI" in df.columns else None

    if ndvi_col:
        avg_ndvi = round(pd.to_numeric(df[ndvi_col], errors="coerce").mean(), 3)

    if ndmi_col:
        avg_ndmi = round(pd.to_numeric(df[ndmi_col], errors="coerce").mean(), 3)

    grid_table = prepare_table(df)

    map_exists = paths["map"] is not None

    map_url = f"/map?t={int(time.time())}"

    last_update = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    return render_template_string(
        DASHBOARD_TEMPLATE,
        total_grids=total_grids,
        critical=critical,
        high=high,
        moderate=moderate,
        low=low,
        fire_count=fire_count,
        avg_ndvi=avg_ndvi,
        avg_ndmi=avg_ndmi,
        grid_table=grid_table,
        map_exists=map_exists,
        map_url=map_url,
        last_update=last_update,
        csv_folder=paths["csv_folder"],
    )


# ======================================================
# MAP ROUTE
# ======================================================

@app.route("/map")
def show_map():
    paths = get_paths()

    if paths["map"] is None:
        return "FRIS map file not found."

    return send_from_directory(paths["map_folder"], MAP_NAME)


# ======================================================
# JSON API
# ======================================================

@app.route("/data")
def data_api():
    df, paths = load_fris_data()

    if df is None:
        return jsonify({"error": "CSV not found"})

    return jsonify(df.fillna("").to_dict(orient="records"))


# ======================================================
# HEALTH CHECK
# ======================================================

@app.route("/health")
def health():
    paths = get_paths()

    return jsonify({
        "csv_exists": paths["csv"] is not None,
        "csv_path": paths["csv"],
        "geojson_exists": paths["geojson"] is not None,
        "geojson_path": paths["geojson"],
        "map_exists": paths["map"] is not None,
        "map_path": paths["map"],
        "searched_folders": SEARCH_DIRS,
        "time": datetime.now().isoformat(),
    })


# ======================================================
# ERROR TEMPLATE
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

        <p>The app searched these folders:</p>

        <ul>
            {% for folder in searched %}
                <li><code>{{folder}}</code></li>
            {% endfor %}
        </ul>

        <p>Upload <b>fris_latest.csv</b> in any one of these folders:</p>

        <ul>
            <li><code>data/fris_latest.csv</code></li>
            <li><code>fris_latest.csv</code></li>
            <li><code>output/fris_latest.csv</code></li>
        </ul>
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
        <p>CSV Loaded From: {{csv_folder}}</p>

        <div class="cards">

            <div class="card">
                <h3>Total Grids</h3>
                <div class="number">{{total_grids}}</div>
            </div>

            <div class="card">
                <h3>Critical</h3>
                <div class="number">{{critical}}</div>
            </div>

            <div class="card">
                <h3>High</h3>
                <div class="number">{{high}}</div>
            </div>

            <div class="card">
                <h3>Moderate</h3>
                <div class="number">{{moderate}}</div>
            </div>

            <div class="card">
                <h3>Low</h3>
                <div class="number">{{low}}</div>
            </div>

            <div class="card">
                <h3>Active Fire</h3>
                <div class="number">{{fire_count}}</div>
            </div>

            <div class="card">
                <h3>Average NDVI</h3>
                <div class="number">{{avg_ndvi}}</div>
            </div>

            <div class="card">
                <h3>Average NDMI</h3>
                <div class="number">{{avg_ndmi}}</div>
            </div>

        </div>

        <div class="section">
            <h2>Operational FRIS Map</h2>

            {% if map_exists %}
                <iframe src="{{map_url}}"></iframe>
            {% else %}
                <p>Map file missing.</p>
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