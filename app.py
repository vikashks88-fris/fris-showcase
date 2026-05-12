from flask import Flask, render_template_string
import pandas as pd
import os

app = Flask(__name__)

# =========================================================
# GODDA FRIS DASHBOARD FILES
# Files must be inside the data folder
# =========================================================

CSV_FILE = "data/fris_latest.csv"
MAP_FILE = "data/fris_latest_map.html"
GEOJSON_FILE = "data/fris_latest.geojson"


# =========================================================
# LOAD CSV SAFELY
# =========================================================

def load_data():
    if not os.path.exists(CSV_FILE):
        return None

    try:
        df = pd.read_csv(CSV_FILE)
        return df
    except Exception as e:
        print("CSV loading error:", e)
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
        <p>Keep the files inside the <b>data</b> folder:</p>
        <ul>
            <li>fris_latest.csv</li>
            <li>fris_latest.geojson</li>
            <li>fris_latest_map.html</li>
        </ul>
        """

    total_grids = len(df)

    def count_value(column, value):
        if column not in df.columns:
            return 0
        return len(df[df[column].astype(str).str.upper() == value])

    critical = count_value("risk_class", "CRITICAL")
    high = count_value("risk_class", "HIGH")
    moderate = count_value("risk_class", "MODERATE")
    low = count_value("risk_class", "LOW")
    active_fire = count_value("active_fire", "YES")

    avg_ndvi = round(pd.to_numeric(df["ndvi"], errors="coerce").mean(), 3) if "ndvi" in df.columns else 0
    avg_ndmi = round(pd.to_numeric(df["ndmi"], errors="coerce").mean(), 3) if "ndmi" in df.columns else 0

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
        "google_maps_link"
    ]

    display_cols = [c for c in preferred_cols if c in df.columns]

    if display_cols:
        table_html = df[display_cols].head(30).to_html(classes="table", index=False, escape=False)
    else:
        table_html = "<p>No display columns found in CSV.</p>"

    if os.path.exists(MAP_FILE):
        with open(MAP_FILE, "r", encoding="utf-8") as f:
            map_html = f.read()
    else:
        map_html = "<h3 style='color:red;'>FRIS map file not found inside data folder.</h3>"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Godda FRIS Dashboard</title>

        <style>
            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: #0f172a;
                color: white;
            }}

            .header {{
                background: #111827;
                padding: 24px;
                text-align: center;
                font-size: 32px;
                font-weight: bold;
            }}

            .sub {{
                text-align: center;
                color: #cbd5e1;
                padding-bottom: 18px;
                background: #111827;
            }}

            .cards {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 18px;
                padding: 24px;
            }}

            .card {{
                background: #1e293b;
                padding: 20px;
                border-radius: 16px;
                box-shadow: 0 4px 14px rgba(0,0,0,0.35);
            }}

            .card h2 {{
                margin: 0;
                font-size: 16px;
                color: #cbd5e1;
            }}

            .card p {{
                margin: 12px 0 0;
                font-size: 32px;
                font-weight: bold;
            }}

            .section {{
                padding: 24px;
            }}

            .note {{
                background: #1e293b;
                padding: 18px;
                border-radius: 14px;
                line-height: 1.6;
            }}

            .table {{
                width: 100%;
                border-collapse: collapse;
                background: white;
                color: black;
                font-size: 14px;
            }}

            .table th {{
                background: #111827;
                color: white;
                padding: 10px;
                text-align: left;
            }}

            .table td {{
                padding: 8px;
                border: 1px solid #ddd;
            }}

            .map-box {{
                background: white;
                border-radius: 16px;
                overflow: hidden;
            }}
        </style>
    </head>

    <body>

        <div class="header">
            GODDA FOREST DIVISION FRIS DASHBOARD
        </div>

        <div class="sub">
            Forest Resilience Information System | Operational Forest Health, Fire & Patrol Intelligence
        </div>

        <div class="cards">
            <div class="card"><h2>Total Forest Grids</h2><p>{total_grids}</p></div>
            <div class="card"><h2>Critical Risk</h2><p>{critical}</p></div>
            <div class="card"><h2>High Risk</h2><p>{high}</p></div>
            <div class="card"><h2>Moderate Risk</h2><p>{moderate}</p></div>
            <div class="card"><h2>Low Risk</h2><p>{low}</p></div>
            <div class="card"><h2>Active Fire Grids</h2><p>{active_fire}</p></div>
            <div class="card"><h2>Average NDVI</h2><p>{avg_ndvi}</p></div>
            <div class="card"><h2>Average NDMI</h2><p>{avg_ndmi}</p></div>
        </div>

        <div class="section">
            <h2>Operational Summary</h2>
            <div class="note">
                This dashboard reads the latest Godda FRIS CSV and map from the data folder.
                It shows forest grid status, vegetation health, moisture stress, active fire indication,
                and patrol priority information.
            </div>
        </div>

        <div class="section">
            <h2>Priority Grid Table</h2>
            {table_html}
        </div>

        <div class="section">
            <h2>FRIS Operational Map</h2>
            <div class="map-box">
                {map_html}
            </div>
        </div>

    </body>
    </html>
    """

    return render_template_string(html)


# =========================================================
# RUN LOCALLY
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)