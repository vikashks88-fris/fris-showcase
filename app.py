import os
from datetime import datetime
import pandas as pd
from flask import Flask, render_template_string, send_from_directory, request, Response

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CSV_FILE = os.path.join(DATA_DIR, "fris_latest.csv")
MAP_FILE = os.path.join(DATA_DIR, "fris_latest_map.html")


# =====================================================
# HELPERS
# =====================================================

def load_csv():
    df = pd.read_csv(CSV_FILE)
    df.columns = df.columns.str.strip()

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip()

    return df


def file_modified_time(path):
    if not os.path.exists(path):
        return "Not available"

    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts).strftime("%d %b %Y, %I:%M:%S %p")


def metric_count(df, column, value):
    if column not in df.columns:
        return 0

    return int(
        (df[column].astype(str).str.upper() == value.upper()).sum()
    )


def fire_count(df):
    if "active_fire" not in df.columns:
        return 0

    return int(
        df["active_fire"]
        .astype(str)
        .str.upper()
        .isin(["1", "TRUE", "YES"])
        .sum()
    )


def filter_dataframe(df):
    search = request.args.get("search", "").strip()
    health = request.args.get("health", "").strip()
    moisture = request.args.get("moisture", "").strip()
    risk = request.args.get("risk", "").strip()

    filtered = df.copy()

    if search and "grid_id" in filtered.columns:
        filtered = filtered[
            filtered["grid_id"].astype(str).str.contains(search, case=False, na=False)
        ]

    if health and "health_class" in filtered.columns:
        filtered = filtered[
            filtered["health_class"].astype(str).str.upper() == health.upper()
        ]

    if moisture and "moisture_class" in filtered.columns:
        filtered = filtered[
            filtered["moisture_class"].astype(str).str.upper() == moisture.upper()
        ]

    if risk and "risk_class" in filtered.columns:
        filtered = filtered[
            filtered["risk_class"].astype(str).str.upper() == risk.upper()
        ]

    return filtered


def unique_values(df, column):
    if column not in df.columns:
        return []

    return sorted(df[column].dropna().astype(str).unique())


def priority_dataframe(df):
    if "risk_class" not in df.columns:
        return pd.DataFrame()

    return df[
        df["risk_class"]
        .astype(str)
        .str.upper()
        .isin(["CRITICAL", "HIGH", "MODERATE"])
    ].copy()


# =====================================================
# MAIN DASHBOARD
# =====================================================

@app.route("/")
def dashboard():

    if not os.path.exists(CSV_FILE):
        return """
        <h2>FRIS CSV not found</h2>
        <pre>
fris_showcase/
├── app.py
├── requirements.txt
└── data/
    ├── fris_latest.csv
    └── fris_latest_map.html
        </pre>
        """

    df = load_csv()
    filtered_df = filter_dataframe(df)

    total_grids = len(filtered_df)
    critical = metric_count(filtered_df, "risk_class", "CRITICAL")
    high = metric_count(filtered_df, "risk_class", "HIGH")
    moderate = metric_count(filtered_df, "risk_class", "MODERATE")
    healthy = metric_count(filtered_df, "health_class", "HEALTHY")
    stressed = metric_count(filtered_df, "health_class", "STRESSED")
    fire = fire_count(filtered_df)

    priority_df = priority_dataframe(filtered_df)

    priority_cols = [
        "grid_id",
        "health_class",
        "moisture_class",
        "risk_class",
        "ndvi",
        "ndmi",
        "active_fire",
        "patrol_action",
        "google_maps_link"
    ]

    available_priority_cols = [
        c for c in priority_cols if c in priority_df.columns
    ]

    if available_priority_cols and len(priority_df) > 0:
        priority_html = priority_df[available_priority_cols].head(30).to_html(
            classes="data-table",
            index=False,
            escape=False
        )
    else:
        priority_html = "<p>No priority grids found.</p>"

    all_table_html = filtered_df.to_html(
        classes="data-table",
        index=False,
        escape=False
    )

    health_values = unique_values(df, "health_class")
    moisture_values = unique_values(df, "moisture_class")
    risk_values = unique_values(df, "risk_class")

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Godda FRIS Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">

        <style>
            * {
                box-sizing: border-box;
            }

            body {
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f4f8f5;
                color: #1f2937;
            }

            header {
                background: linear-gradient(135deg, #0f2f1f, #1f5c3a);
                color: white;
                padding: 28px 36px;
            }

            header h1 {
                margin: 0;
                font-size: 38px;
                font-weight: 900;
            }

            header p {
                margin-top: 8px;
                color: #d1fae5;
                font-size: 16px;
            }

            .time-box {
                margin-top: 12px;
                font-size: 16px;
                font-weight: bold;
                color: #bbf7d0;
            }

            .container {
                padding: 24px 36px;
            }

            .status {
                background: #ecfdf5;
                border-left: 6px solid #22c55e;
                padding: 14px 18px;
                border-radius: 12px;
                color: #166534;
                font-weight: bold;
                margin-bottom: 20px;
            }

            .filters {
                background: white;
                padding: 18px;
                border-radius: 16px;
                box-shadow: 0 6px 18px rgba(0,0,0,0.08);
                margin-bottom: 22px;
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 12px;
            }

            input, select, button {
                padding: 11px;
                border-radius: 10px;
                border: 1px solid #cbd5e1;
                width: 100%;
                font-size: 14px;
            }

            button {
                background: #14532d;
                color: white;
                font-weight: bold;
                cursor: pointer;
            }

            .clear-btn {
                background: #64748b;
                text-align: center;
                text-decoration: none;
                color: white;
                padding: 11px;
                border-radius: 10px;
                font-weight: bold;
            }

            .metrics {
                display: grid;
                grid-template-columns: repeat(6, 1fr);
                gap: 18px;
                margin-bottom: 24px;
            }

            .card {
                background: white;
                padding: 20px;
                border-radius: 16px;
                box-shadow: 0 6px 18px rgba(0,0,0,0.08);
            }

            .card-title {
                color: #64748b;
                font-size: 13px;
                font-weight: bold;
            }

            .card-value {
                margin-top: 8px;
                font-size: 34px;
                font-weight: 900;
                color: #14532d;
            }

            .section {
                background: white;
                padding: 20px;
                border-radius: 16px;
                box-shadow: 0 6px 18px rgba(0,0,0,0.08);
                margin-bottom: 24px;
            }

            .section h2 {
                margin-top: 0;
                color: #163020;
            }

            iframe {
                width: 100%;
                height: 720px;
                border: none;
                border-radius: 14px;
            }

            .table-wrapper {
                overflow-x: auto;
                max-height: 680px;
                overflow-y: auto;
            }

            table.data-table {
                border-collapse: collapse;
                width: 100%;
                font-size: 13px;
            }

            table.data-table th {
                background: #14532d;
                color: white;
                padding: 10px;
                position: sticky;
                top: 0;
                z-index: 2;
                white-space: nowrap;
            }

            table.data-table td {
                padding: 8px;
                border-bottom: 1px solid #e5e7eb;
                white-space: nowrap;
            }

            table.data-table tr:nth-child(even) {
                background: #f8fafc;
            }

            .download {
                display: inline-block;
                background: #14532d;
                color: white;
                padding: 12px 16px;
                border-radius: 10px;
                text-decoration: none;
                font-weight: bold;
                margin-bottom: 12px;
            }

            .freshness {
                color: #64748b;
                font-size: 14px;
                margin-bottom: 10px;
            }

            .footer {
                text-align: center;
                padding: 20px;
                color: #6b7280;
            }

            @media(max-width: 1000px) {
                .metrics {
                    grid-template-columns: repeat(2, 1fr);
                }

                .filters {
                    grid-template-columns: 1fr;
                }

                header h1 {
                    font-size: 28px;
                }

                .container {
                    padding: 18px;
                }
            }
        </style>
    </head>

    <body>

        <header>
            <h1>🌳 Godda FRIS Dashboard</h1>
            <p>Forest Resilience Information System • Satellite-Based Forest Intelligence • Godda Forest Division</p>

            <div class="time-box">
                Live Time: <span id="clock"></span>
            </div>
        </header>

        <div class="container">

            <div class="status">
                FRIS data loaded successfully. Operational dashboard is active.
            </div>

            <form class="filters" method="GET">
                <input type="text" name="search" placeholder="Search Grid ID" value="{{ request.args.get('search', '') }}">

                <select name="health">
                    <option value="">All Health</option>
                    {% for v in health_values %}
                        <option value="{{ v }}" {% if request.args.get('health') == v %}selected{% endif %}>{{ v }}</option>
                    {% endfor %}
                </select>

                <select name="moisture">
                    <option value="">All Moisture</option>
                    {% for v in moisture_values %}
                        <option value="{{ v }}" {% if request.args.get('moisture') == v %}selected{% endif %}>{{ v }}</option>
                    {% endfor %}
                </select>

                <select name="risk">
                    <option value="">All Risk</option>
                    {% for v in risk_values %}
                        <option value="{{ v }}" {% if request.args.get('risk') == v %}selected{% endif %}>{{ v }}</option>
                    {% endfor %}
                </select>

                <button type="submit">Apply Filter</button>
            </form>

            <div style="margin-bottom:18px;">
                <a class="clear-btn" href="/">Clear Filters</a>
            </div>

            <div class="metrics">
                <div class="card">
                    <div class="card-title">Forest Grids</div>
                    <div class="card-value">{{ total_grids }}</div>
                </div>

                <div class="card">
                    <div class="card-title">Critical</div>
                    <div class="card-value">{{ critical }}</div>
                </div>

                <div class="card">
                    <div class="card-title">High Risk</div>
                    <div class="card-value">{{ high }}</div>
                </div>

                <div class="card">
                    <div class="card-title">Moderate</div>
                    <div class="card-value">{{ moderate }}</div>
                </div>

                <div class="card">
                    <div class="card-title">Fire Alerts</div>
                    <div class="card-value">{{ fire }}</div>
                </div>

                <div class="card">
                    <div class="card-title">Healthy</div>
                    <div class="card-value">{{ healthy }}</div>
                </div>
            </div>

            <div class="section">
                <h2>🛰️ Satellite Operational Map</h2>
                <div class="freshness">Map file last updated: {{ map_time }}</div>

                {% if map_exists %}
                    <iframe src="/map"></iframe>
                {% else %}
                    <p>fris_latest_map.html not found inside data folder.</p>
                {% endif %}
            </div>

            <div class="section">
                <h2>🚨 Priority Grids</h2>
                <p>Shows CRITICAL, HIGH and MODERATE risk grids from current filter.</p>

                <div class="table-wrapper">
                    {{ priority_html|safe }}
                </div>
            </div>

            <div class="section">
                <h2>📋 Complete FRIS CSV Parameters</h2>
                <div class="freshness">CSV file last updated: {{ csv_time }}</div>
                <a class="download" href="/download">Download Latest CSV</a>

                <div class="table-wrapper">
                    {{ all_table_html|safe }}
                </div>
            </div>

        </div>

        <div class="footer">
            FRIS • Forest Resilience Information System • Godda Forest Division
        </div>

        <script>
            function updateClock() {
                const now = new Date();

                const options = {
                    timeZone: "Asia/Kolkata",
                    year: "numeric",
                    month: "short",
                    day: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                    hour12: true
                };

                document.getElementById("clock").innerHTML =
                    now.toLocaleString("en-IN", options) + " IST";
            }

            updateClock();
            setInterval(updateClock, 1000);
        </script>

    </body>
    </html>
    """

    return render_template_string(
        html,
        request=request,
        total_grids=total_grids,
        critical=critical,
        high=high,
        moderate=moderate,
        stressed=stressed,
        fire=fire,
        healthy=healthy,
        priority_html=priority_html,
        all_table_html=all_table_html,
        health_values=health_values,
        moisture_values=moisture_values,
        risk_values=risk_values,
        csv_time=file_modified_time(CSV_FILE),
        map_time=file_modified_time(MAP_FILE),
        map_exists=os.path.exists(MAP_FILE)
    )


# =====================================================
# MAP ROUTE
# =====================================================

@app.route("/map")
def map_view():
    return send_from_directory(DATA_DIR, "fris_latest_map.html")


# =====================================================
# DOWNLOAD ROUTE
# =====================================================

@app.route("/download")
def download_csv():
    return send_from_directory(DATA_DIR, "fris_latest.csv", as_attachment=True)


# =====================================================
# HEALTH CHECK ROUTE
# =====================================================

@app.route("/health")
def health_check():
    return {
        "status": "running",
        "csv_exists": os.path.exists(CSV_FILE),
        "map_exists": os.path.exists(MAP_FILE),
        "csv_last_updated": file_modified_time(CSV_FILE),
        "map_last_updated": file_modified_time(MAP_FILE)
    }


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)