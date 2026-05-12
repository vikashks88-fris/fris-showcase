from flask import Flask, render_template_string
import pandas as pd
import os
import json

app = Flask(__name__)

# =========================================================
# SIMPLE RENDER-FRIENDLY FILES
# =========================================================

CSV_FILE = "output/fris_latest.csv"
MAP_FILE = "output/fris_latest_map.html"
GEOJSON_FILE = "output/fris_latest.geojson"

# =========================================================
# LOAD CSV
# =========================================================

def load_data():
    if os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE)
            return df
        except Exception as e:
            print("CSV ERROR:", e)
            return None
    return None

# =========================================================
# MAIN DASHBOARD
# =========================================================

@app.route("/")
def home():

    df = load_data()

    if df is None:
        return """
        <h1>Godda FRIS Dashboard</h1>
        <h3>No FRIS CSV found.</h3>

        <p>Required files inside output folder:</p>

        <ul>
            <li>fris_latest.csv</li>
            <li>fris_latest.geojson</li>
            <li>fris_latest_map.html</li>
        </ul>
        """

    # =====================================================
    # SAFE COLUMN CHECKS
    # =====================================================

    total_grids = len(df)

    critical = len(df[df["risk_class"].astype(str).str.upper() == "CRITICAL"]) \
        if "risk_class" in df.columns else 0

    high = len(df[df["risk_class"].astype(str).str.upper() == "HIGH"]) \
        if "risk_class" in df.columns else 0

    moderate = len(df[df["risk_class"].astype(str).str.upper() == "MODERATE"]) \
        if "risk_class" in df.columns else 0

    low = len(df[df["risk_class"].astype(str).str.upper() == "LOW"]) \
        if "risk_class" in df.columns else 0

    active_fire = len(df[df["active_fire"].astype(str).str.upper() == "YES"]) \
        if "active_fire" in df.columns else 0

    avg_ndvi = round(df["ndvi"].mean(), 3) \
        if "ndvi" in df.columns else 0

    avg_ndmi = round(df["ndmi"].mean(), 3) \
        if "ndmi" in df.columns else 0

    # =====================================================
    # TOP PRIORITY TABLE
    # =====================================================

    display_columns = []

    preferred_cols = [
        "grid_id",
        "risk_class",
        "health_class",
        "moisture_class",
        "ndvi",
        "ndmi",
        "fire_count",
        "patrol_action",
        "inference",
    ]

    for c in preferred_cols:
        if c in df.columns:
            display_columns.append(c)

    top_rows = df.head(25)[display_columns].to_html(
        classes="table",
        index=False
    )

    # =====================================================
    # MAP
    # =====================================================

    map_html = ""

    if os.path.exists(MAP_FILE):
        with open(MAP_FILE, "r", encoding="utf-8") as f:
            map_html = f.read()
    else:
        map_html = """
        <div style='padding:20px;color:red;font-size:20px;'>
        FRIS map HTML not found.
        </div>
        """

    # =====================================================
    # DASHBOARD HTML
    # =====================================================

    html = f"""
    <!DOCTYPE html>
    <html>

    <head>

        <title>Godda FRIS Dashboard</title>

        <style>

            body {{
                margin:0;
                font-family:Arial;
                background:#0f172a;
                color:white;
            }}

            .header {{
                background:#111827;
                padding:20px;
                text-align:center;
                font-size:32px;
                font-weight:bold;
            }}

            .sub {{
                text-align:center;
                color:#cbd5e1;
                margin-top:-10px;
                padding-bottom:15px;
            }}

            .cards {{
                display:grid;
                grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
                gap:20px;
                padding:20px;
            }}

            .card {{
                background:#1e293b;
                padding:20px;
                border-radius:15px;
                box-shadow:0px 0px 10px rgba(0,0,0,0.3);
            }}

            .card h2 {{
                margin:0;
                font-size:18px;
                color:#cbd5e1;
            }}

            .card p {{
                font-size:32px;
                margin-top:10px;
                font-weight:bold;
            }}

            .section {{
                padding:20px;
            }}

            .table {{
                width:100%;
                border-collapse:collapse;
                background:white;
                color:black;
            }}

            .table th {{
                background:#111827;
                color:white;
                padding:10px;
            }}

            .table td {{
                padding:8px;
                border:1px solid #ddd;
            }}

            iframe {{
                width:100%;
                height:700px;
                border:none;
                border-radius:15px;
            }}

        </style>

    </head>

    <body>

        <div class="header">
            GODDA FOREST DIVISION FRIS
        </div>

        <div class="sub">
            Forest Resilience Information System
        </div>

        <div class="cards">

            <div class="card">
                <h2>Total Forest Grids</h2>
                <p>{total_grids}</p>
            </div>

            <div class="card">
                <h2>Critical Risk</h2>
                <p>{critical}</p>
            </div>

            <div class="card">
                <h2>High Risk</h2>
                <p>{high}</p>
            </div>

            <div class="card">
                <h2>Moderate Risk</h2>
                <p>{moderate}</p>
            </div>

            <div class="card">
                <h2>Low Risk</h2>
                <p>{low}</p>
            </div>

            <div class="card">
                <h2>Active Fire Grids</h2>
                <p>{active_fire}</p>
            </div>

            <div class="card">
                <h2>Average NDVI</h2>
                <p>{avg_ndvi}</p>
            </div>

            <div class="card">
                <h2>Average NDMI</h2>
                <p>{avg_ndmi}</p>
            </div>

        </div>

        <div class="section">

            <h1>Operational Forest Intelligence</h1>

            <p>
            FRIS combines Sentinel-2 vegetation condition,
            moisture stress, fire alerts,
            and patrol intelligence for Godda Forest Division.
            </p>

        </div>

        <div class="section">

            <h1>Priority Grid Table</h1>

            {top_rows}

        </div>

        <div class="section">

            <h1>FRIS Operational Map</h1>

            {map_html}

        </div>

    </body>

    </html>
    """

    return render_template_string(html)

# =========================================================
# RUN APP
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)