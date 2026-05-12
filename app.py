import os
import glob
import pandas as pd
from flask import Flask, render_template_string, send_file, request

app = Flask(__name__)

# =========================
# PATH SETTINGS
# =========================
OUTPUT_DIR = r"C:\cfris\output"
CSV_PATH = os.path.join(OUTPUT_DIR, "fris_latest.csv")
MAP_PATH = os.path.join(OUTPUT_DIR, "fris_latest_map.html")


# =========================
# DATA LOADER
# =========================
def load_fris_data():
    if not os.path.exists(CSV_PATH):
        return None

    df = pd.read_csv(CSV_PATH)

    # Clean missing values
    df = df.fillna("")

    # Numeric safety
    numeric_cols = [
        "final_risk_score",
        "forest_pct",
        "temperature_c",
        "rainfall_24h_mm",
        "wind_speed_kmph",
        "wind_gust_kmph",
        "ecosystem_carbon_total_ton",
        "carbon_change_co2e_ton",
        "preliminary_carbon_opportunity_ton_co2e",
        "fire_frp_max",
        "history_days_available_365d",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def safe_value(df, col, default="Not Available"):
    if df is None or col not in df.columns or len(df) == 0:
        return default
    val = df[col].iloc[0]
    return val if val != "" else default


def get_summary(df):
    if df is None or len(df) == 0:
        return {}

    summary = {
        "total_grids": len(df),
        "high_priority": int((df.get("final_priority", "") == "HIGH").sum()) if "final_priority" in df.columns else 0,
        "medium_priority": int((df.get("final_priority", "") == "MEDIUM").sum()) if "final_priority" in df.columns else 0,
        "fire_check": int((df.get("final_priority", "") == "FIRE_CHECK").sum()) if "final_priority" in df.columns else 0,
        "low_priority": int((df.get("final_priority", "") == "LOW").sum()) if "final_priority" in df.columns else 0,
        "total_carbon": round(df["ecosystem_carbon_total_ton"].sum(), 2) if "ecosystem_carbon_total_ton" in df.columns else 0,
        "carbon_opportunity": round(df["preliminary_carbon_opportunity_ton_co2e"].sum(), 2) if "preliminary_carbon_opportunity_ton_co2e" in df.columns else 0,
        "temperature": safe_value(df, "temperature_c"),
        "rainfall": safe_value(df, "rainfall_24h_mm"),
        "wind": safe_value(df, "wind_speed_kmph"),
        "gust": safe_value(df, "wind_gust_kmph"),
        "weather_class": safe_value(df, "weather_fire_spread_class"),
        "memory_class": safe_value(df, "ecological_memory_class"),
        "mrv_confidence": safe_value(df, "mrv_confidence"),
    }

    return summary


# =========================
# ROUTES
# =========================
@app.route("/")
def dashboard():
    df = load_fris_data()

    if df is None:
        return """
        <h2>FRIS Godda Dashboard</h2>
        <p>No FRIS CSV found.</p>
        <p>Expected file:</p>
        <b>C:\\cfris\\output\\fris_latest.csv</b>
        """

    summary = get_summary(df)

    # Sorting
    if "final_risk_score" in df.columns:
        df = df.sort_values(by="final_risk_score", ascending=False)

    # Filter
    priority_filter = request.args.get("priority", "ALL")

    if priority_filter != "ALL" and "final_priority" in df.columns:
        df = df[df["final_priority"] == priority_filter]

    # Search grid
    search_grid = request.args.get("grid", "").strip()

    if search_grid and "grid_id" in df.columns:
        df = df[df["grid_id"].astype(str).str.contains(search_grid, case=False, na=False)]

    top_df = df.head(100)

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Godda FRIS Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">

        <style>
            body {
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f3f6f4;
                color: #1f2d24;
            }

            .header {
                background: linear-gradient(135deg, #064e3b, #15803d);
                color: white;
                padding: 28px;
                text-align: center;
            }

            .header h1 {
                margin: 0;
                font-size: 34px;
            }

            .header p {
                margin-top: 8px;
                font-size: 15px;
                opacity: 0.95;
            }

            .container {
                padding: 22px;
            }

            .cards {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 16px;
                margin-bottom: 24px;
            }

            .card {
                background: white;
                border-radius: 16px;
                padding: 18px;
                box-shadow: 0 4px 14px rgba(0,0,0,0.08);
            }

            .card h3 {
                margin: 0;
                font-size: 14px;
                color: #64748b;
            }

            .card .value {
                margin-top: 10px;
                font-size: 26px;
                font-weight: bold;
                color: #064e3b;
            }

            .section-title {
                margin-top: 30px;
                margin-bottom: 12px;
                font-size: 22px;
                color: #064e3b;
            }

            .filters {
                background: white;
                padding: 16px;
                border-radius: 14px;
                margin-bottom: 18px;
                box-shadow: 0 3px 12px rgba(0,0,0,0.06);
            }

            select, input, button {
                padding: 10px;
                border-radius: 8px;
                border: 1px solid #cbd5e1;
                margin: 4px;
            }

            button {
                background: #15803d;
                color: white;
                cursor: pointer;
                border: none;
            }

            button:hover {
                background: #166534;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                background: white;
                border-radius: 14px;
                overflow: hidden;
                box-shadow: 0 4px 14px rgba(0,0,0,0.07);
            }

            th {
                background: #064e3b;
                color: white;
                padding: 12px;
                font-size: 13px;
            }

            td {
                padding: 10px;
                border-bottom: 1px solid #e5e7eb;
                font-size: 13px;
                text-align: center;
            }

            tr:hover {
                background: #f0fdf4;
            }

            .badge {
                padding: 5px 10px;
                border-radius: 20px;
                font-weight: bold;
                font-size: 12px;
            }

            .FIRE_CHECK {
                background: #fee2e2;
                color: #991b1b;
            }

            .HIGH {
                background: #ffedd5;
                color: #9a3412;
            }

            .MEDIUM {
                background: #fef9c3;
                color: #854d0e;
            }

            .LOW {
                background: #dcfce7;
                color: #166534;
            }

            .map-box {
                background: white;
                padding: 18px;
                border-radius: 16px;
                box-shadow: 0 4px 14px rgba(0,0,0,0.07);
                margin-bottom: 24px;
            }

            .map-link {
                display: inline-block;
                background: #2563eb;
                color: white;
                padding: 12px 18px;
                border-radius: 10px;
                text-decoration: none;
                margin-top: 10px;
            }

            .note {
                background: #ecfdf5;
                border-left: 5px solid #15803d;
                padding: 14px;
                border-radius: 10px;
                margin-top: 20px;
                font-size: 14px;
            }

            @media(max-width: 700px) {
                .header h1 {
                    font-size: 24px;
                }

                table {
                    display: block;
                    overflow-x: auto;
                }
            }
        </style>
    </head>

    <body>

        <div class="header">
            <h1>Godda FRIS Dashboard</h1>
            <p>Forest Resilience Information System | Live Forest Health, Fire, Carbon & Patrol Intelligence</p>
        </div>

        <div class="container">

            <div class="cards">
                <div class="card">
                    <h3>Total Forest Grids</h3>
                    <div class="value">{{ summary.total_grids }}</div>
                </div>

                <div class="card">
                    <h3>Fire Check Grids</h3>
                    <div class="value">{{ summary.fire_check }}</div>
                </div>

                <div class="card">
                    <h3>Medium Priority</h3>
                    <div class="value">{{ summary.medium_priority }}</div>
                </div>

                <div class="card">
                    <h3>Estimated Ecosystem Carbon</h3>
                    <div class="value">{{ summary.total_carbon }} tC</div>
                </div>

                <div class="card">
                    <h3>Carbon Opportunity</h3>
                    <div class="value">{{ summary.carbon_opportunity }} tCO₂e</div>
                </div>

                <div class="card">
                    <h3>MRV Confidence</h3>
                    <div class="value" style="font-size:18px;">{{ summary.mrv_confidence }}</div>
                </div>
            </div>

            <h2 class="section-title">Weather & Ecological Context</h2>

            <div class="cards">
                <div class="card">
                    <h3>Temperature</h3>
                    <div class="value">{{ summary.temperature }} °C</div>
                </div>

                <div class="card">
                    <h3>Rainfall 24h</h3>
                    <div class="value">{{ summary.rainfall }} mm</div>
                </div>

                <div class="card">
                    <h3>Wind Speed</h3>
                    <div class="value">{{ summary.wind }} km/h</div>
                </div>

                <div class="card">
                    <h3>Wind Gust</h3>
                    <div class="value">{{ summary.gust }} km/h</div>
                </div>

                <div class="card">
                    <h3>Weather Fire Class</h3>
                    <div class="value" style="font-size:18px;">{{ summary.weather_class }}</div>
                </div>

                <div class="card">
                    <h3>Memory Class</h3>
                    <div class="value" style="font-size:18px;">{{ summary.memory_class }}</div>
                </div>
            </div>

            <h2 class="section-title">FRIS Latest Map</h2>

            <div class="map-box">
                <p>Open the latest generated Godda FRIS map.</p>
                <a class="map-link" href="/map" target="_blank">Open Latest FRIS Map</a>
            </div>

            <h2 class="section-title">Grid-wise FRIS Information</h2>

            <div class="filters">
                <form method="get">
                    <select name="priority">
                        <option value="ALL">All Priorities</option>
                        <option value="FIRE_CHECK">Fire Check</option>
                        <option value="HIGH">High</option>
                        <option value="MEDIUM">Medium</option>
                        <option value="LOW">Low</option>
                    </select>

                    <input type="text" name="grid" placeholder="Search Grid ID e.g. GD-06-34">

                    <button type="submit">Filter</button>
                    <a href="/" style="margin-left:10px;">Reset</a>
                </form>
            </div>

            <table>
                <tr>
                    <th>Grid ID</th>
                    <th>Priority</th>
                    <th>Risk Score</th>
                    <th>Forest %</th>
                    <th>Health</th>
                    <th>Moisture</th>
                    <th>Fire FRP</th>
                    <th>Carbon tC</th>
                    <th>MRV</th>
                    <th>Action</th>
                    <th>Map</th>
                </tr>

                {% for row in rows %}
                <tr>
                    <td>{{ row.get("grid_id", "") }}</td>

                    <td>
                        <span class="badge {{ row.get('final_priority', '') }}">
                            {{ row.get("final_priority", "") }}
                        </span>
                    </td>

                    <td>{{ row.get("final_risk_score", "") }}</td>
                    <td>{{ row.get("forest_pct", "") }}</td>
                    <td>{{ row.get("health_class", "") }}</td>
                    <td>{{ row.get("moisture_class_calibrated", "") }}</td>
                    <td>{{ row.get("fire_frp_max", "") }}</td>
                    <td>{{ row.get("ecosystem_carbon_total_ton", "") }}</td>
                    <td>{{ row.get("mrv_confidence", "") }}</td>
                    <td style="text-align:left;">{{ row.get("patrol_action", "") }}</td>

                    <td>
                        {% if row.get("google_maps_link", "") %}
                            <a href="{{ row.get('google_maps_link') }}" target="_blank">Go</a>
                        {% else %}
                            -
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </table>

            <div class="note">
                <b>Important:</b> FRIS carbon output is MRV-support intelligence only. It should not be presented as verified carbon credit issuance without third-party MRV validation.
            </div>

        </div>

    </body>
    </html>
    """

    rows = top_df.to_dict(orient="records")

    return render_template_string(html, summary=summary, rows=rows)


@app.route("/map")
def show_map():
    if os.path.exists(MAP_PATH):
        return send_file(MAP_PATH)

    return """
    <h2>FRIS Map Not Found</h2>
    <p>Expected file:</p>
    <b>C:\\cfris\\output\\fris_latest_map.html</b>
    """


@app.route("/download-csv")
def download_csv():
    if os.path.exists(CSV_PATH):
        return send_file(CSV_PATH, as_attachment=True)

    return "CSV not found."


# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)