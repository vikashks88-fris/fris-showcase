import os
import pandas as pd
from flask import Flask, render_template_string, send_file, request, redirect, url_for

app = Flask(__name__)

# =====================================================
# SMART PATH FIX — WINDOWS + RENDER
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

POSSIBLE_OUTPUT_DIRS = [
    os.path.join(BASE_DIR, "output"),          # Render / GitHub
    os.path.join(BASE_DIR, "data"),            # Alternative Render folder
    r"C:\cfris\output",                        # Windows FRIS output
    os.path.join(BASE_DIR, "..", "output"),
]

def find_output_dir():
    for folder in POSSIBLE_OUTPUT_DIRS:
        csv_path = os.path.join(folder, "fris_latest.csv")
        if os.path.exists(csv_path):
            return folder
    return os.path.join(BASE_DIR, "output")

OUTPUT_DIR = find_output_dir()
CSV_PATH = os.path.join(OUTPUT_DIR, "fris_latest.csv")
MAP_PATH = os.path.join(OUTPUT_DIR, "fris_latest_map.html")
GEOJSON_PATH = os.path.join(OUTPUT_DIR, "fris_latest.geojson")


# =====================================================
# DATA LOADING
# =====================================================

def load_data():
    if not os.path.exists(CSV_PATH):
        return None

    try:
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print("CSV READ ERROR:", e)
        return None

    df = df.fillna("")

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
        "gedi_agbd_ton_per_ha",
        "hansen_loss_pct",
        "elevation_m",
        "slope_deg",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def safe_first(df, col, default="Not Available"):
    if df is None or len(df) == 0 or col not in df.columns:
        return default
    val = df[col].iloc[0]
    return val if val != "" else default


def count_value(df, col, value):
    if df is None or col not in df.columns:
        return 0
    return int((df[col] == value).sum())


def summary_data(df):
    if df is None or len(df) == 0:
        return {}

    return {
        "total_grids": len(df),
        "fire_check": count_value(df, "final_priority", "FIRE_CHECK"),
        "high": count_value(df, "final_priority", "HIGH"),
        "medium": count_value(df, "final_priority", "MEDIUM"),
        "low": count_value(df, "final_priority", "LOW"),
        "carbon": round(df["ecosystem_carbon_total_ton"].sum(), 2) if "ecosystem_carbon_total_ton" in df.columns else 0,
        "carbon_opportunity": round(df["preliminary_carbon_opportunity_ton_co2e"].sum(), 2) if "preliminary_carbon_opportunity_ton_co2e" in df.columns else 0,
        "temperature": safe_first(df, "temperature_c"),
        "rainfall": safe_first(df, "rainfall_24h_mm"),
        "wind": safe_first(df, "wind_speed_kmph"),
        "gust": safe_first(df, "wind_gust_kmph"),
        "weather_class": safe_first(df, "weather_fire_spread_class"),
        "memory_class": safe_first(df, "ecological_memory_class"),
        "mrv": safe_first(df, "mrv_confidence"),
        "output_dir": OUTPUT_DIR,
    }


def prepare_rows(df, limit=150):
    if df is None:
        return []

    if "final_risk_score" in df.columns:
        df = df.sort_values("final_risk_score", ascending=False)

    priority = request.args.get("priority", "ALL")
    search = request.args.get("grid", "").strip()

    if priority != "ALL" and "final_priority" in df.columns:
        df = df[df["final_priority"] == priority]

    if search and "grid_id" in df.columns:
        df = df[df["grid_id"].astype(str).str.contains(search, case=False, na=False)]

    return df.head(limit).to_dict(orient="records")


# =====================================================
# ROUTES
# =====================================================

@app.route("/")
def home():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    df = load_data()

    if df is None:
        return render_template_string(MISSING_TEMPLATE, folders=POSSIBLE_OUTPUT_DIRS)

    return render_template_string(
        TEMPLATE,
        active="dashboard",
        title="Dashboard",
        section="dashboard",
        summary=summary_data(df),
        rows=prepare_rows(df),
        map_exists=os.path.exists(MAP_PATH),
        csv_exists=os.path.exists(CSV_PATH),
    )


@app.route("/map-view")
def map_view_page():
    df = load_data()

    if df is None:
        return render_template_string(MISSING_TEMPLATE, folders=POSSIBLE_OUTPUT_DIRS)

    return render_template_string(
        TEMPLATE,
        active="map",
        title="Map View",
        section="map",
        summary=summary_data(df),
        rows=[],
        map_exists=os.path.exists(MAP_PATH),
        csv_exists=os.path.exists(CSV_PATH),
    )


@app.route("/grid-analytics")
def grid_analytics():
    df = load_data()

    if df is None:
        return render_template_string(MISSING_TEMPLATE, folders=POSSIBLE_OUTPUT_DIRS)

    return render_template_string(
        TEMPLATE,
        active="grid",
        title="Grid Analytics",
        section="grid",
        summary=summary_data(df),
        rows=prepare_rows(df, limit=300),
        map_exists=os.path.exists(MAP_PATH),
        csv_exists=os.path.exists(CSV_PATH),
    )


@app.route("/fire-intelligence")
def fire_intelligence():
    df = load_data()

    if df is None:
        return render_template_string(MISSING_TEMPLATE, folders=POSSIBLE_OUTPUT_DIRS)

    fire_df = df.copy()

    if "final_priority" in fire_df.columns:
        fire_df = fire_df[
            (fire_df["final_priority"] == "FIRE_CHECK") |
            (fire_df.get("fire_frp_max", 0) != 0)
        ]

    return render_template_string(
        TEMPLATE,
        active="fire",
        title="Fire Intelligence",
        section="fire",
        summary=summary_data(df),
        rows=fire_df.head(200).to_dict(orient="records"),
        map_exists=os.path.exists(MAP_PATH),
        csv_exists=os.path.exists(CSV_PATH),
    )


@app.route("/carbon-analytics")
def carbon_analytics():
    df = load_data()

    if df is None:
        return render_template_string(MISSING_TEMPLATE, folders=POSSIBLE_OUTPUT_DIRS)

    carbon_df = df.copy()

    if "ecosystem_carbon_total_ton" in carbon_df.columns:
        carbon_df = carbon_df.sort_values("ecosystem_carbon_total_ton", ascending=False)

    return render_template_string(
        TEMPLATE,
        active="carbon",
        title="Carbon Analytics",
        section="carbon",
        summary=summary_data(df),
        rows=carbon_df.head(200).to_dict(orient="records"),
        map_exists=os.path.exists(MAP_PATH),
        csv_exists=os.path.exists(CSV_PATH),
    )


@app.route("/patrol-management")
def patrol_management():
    df = load_data()

    if df is None:
        return render_template_string(MISSING_TEMPLATE, folders=POSSIBLE_OUTPUT_DIRS)

    patrol_df = df.copy()

    if "final_risk_score" in patrol_df.columns:
        patrol_df = patrol_df.sort_values("final_risk_score", ascending=False)

    return render_template_string(
        TEMPLATE,
        active="patrol",
        title="Patrol Management",
        section="patrol",
        summary=summary_data(df),
        rows=patrol_df.head(100).to_dict(orient="records"),
        map_exists=os.path.exists(MAP_PATH),
        csv_exists=os.path.exists(CSV_PATH),
    )


@app.route("/reports")
def reports():
    df = load_data()

    if df is None:
        return render_template_string(MISSING_TEMPLATE, folders=POSSIBLE_OUTPUT_DIRS)

    return render_template_string(
        TEMPLATE,
        active="reports",
        title="Reports",
        section="reports",
        summary=summary_data(df),
        rows=[],
        map_exists=os.path.exists(MAP_PATH),
        csv_exists=os.path.exists(CSV_PATH),
    )


@app.route("/alerts")
def alerts():
    df = load_data()

    if df is None:
        return render_template_string(MISSING_TEMPLATE, folders=POSSIBLE_OUTPUT_DIRS)

    alert_df = df.copy()

    if "final_priority" in alert_df.columns:
        alert_df = alert_df[alert_df["final_priority"].isin(["FIRE_CHECK", "HIGH", "MEDIUM"])]

    return render_template_string(
        TEMPLATE,
        active="alerts",
        title="Alerts",
        section="alerts",
        summary=summary_data(df),
        rows=alert_df.head(150).to_dict(orient="records"),
        map_exists=os.path.exists(MAP_PATH),
        csv_exists=os.path.exists(CSV_PATH),
    )


@app.route("/history")
def history():
    df = load_data()

    if df is None:
        return render_template_string(MISSING_TEMPLATE, folders=POSSIBLE_OUTPUT_DIRS)

    return render_template_string(
        TEMPLATE,
        active="history",
        title="History",
        section="history",
        summary=summary_data(df),
        rows=prepare_rows(df),
        map_exists=os.path.exists(MAP_PATH),
        csv_exists=os.path.exists(CSV_PATH),
    )


@app.route("/settings")
def settings():
    df = load_data()

    if df is None:
        return render_template_string(MISSING_TEMPLATE, folders=POSSIBLE_OUTPUT_DIRS)

    return render_template_string(
        TEMPLATE,
        active="settings",
        title="Settings",
        section="settings",
        summary=summary_data(df),
        rows=[],
        map_exists=os.path.exists(MAP_PATH),
        csv_exists=os.path.exists(CSV_PATH),
    )


@app.route("/open-map")
def open_map():
    if os.path.exists(MAP_PATH):
        return send_file(MAP_PATH)
    return "<h2>Map not found</h2><p>Expected fris_latest_map.html inside output folder.</p>"


@app.route("/download-csv")
def download_csv():
    if os.path.exists(CSV_PATH):
        return send_file(CSV_PATH, as_attachment=True)
    return "CSV not found."


@app.route("/download-geojson")
def download_geojson():
    if os.path.exists(GEOJSON_PATH):
        return send_file(GEOJSON_PATH, as_attachment=True)
    return "GeoJSON not found."


# =====================================================
# HTML TEMPLATE
# =====================================================

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Godda FRIS | {{ title }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">

<style>
* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f4f7f5;
    color: #0f172a;
}

.sidebar {
    position: fixed;
    top: 0;
    left: 0;
    width: 260px;
    height: 100vh;
    background: linear-gradient(180deg, #022c22, #031b16);
    color: white;
    padding: 22px 16px;
    overflow-y: auto;
}

.logo {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 26px;
}

.logo-icon {
    font-size: 42px;
}

.logo-title {
    font-size: 24px;
    font-weight: bold;
    line-height: 1.1;
}

.logo-small {
    font-size: 12px;
    color: #bbf7d0;
}

.nav a {
    display: block;
    padding: 13px 14px;
    margin-bottom: 8px;
    color: #e5e7eb;
    text-decoration: none;
    border-radius: 12px;
    font-size: 15px;
}

.nav a:hover,
.nav a.active {
    background: linear-gradient(135deg, #16a34a, #15803d);
    color: white;
}

.quick {
    margin-top: 28px;
    background: rgba(255,255,255,0.06);
    padding: 14px;
    border-radius: 16px;
}

.quick h3 {
    margin: 0 0 12px 0;
    font-size: 15px;
    color: #86efac;
}

.quick a {
    display: block;
    color: white;
    text-decoration: none;
    background: rgba(255,255,255,0.08);
    padding: 10px;
    border-radius: 10px;
    margin-bottom: 8px;
    font-size: 14px;
}

.main {
    margin-left: 260px;
    min-height: 100vh;
}

.hero {
    background: linear-gradient(135deg, #064e3b, #022c22);
    color: white;
    padding: 34px 36px;
}

.hero h1 {
    margin: 0;
    font-size: 34px;
}

.hero p {
    margin-top: 8px;
    color: #dcfce7;
}

.content {
    padding: 28px;
}

.cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 16px;
    margin-bottom: 22px;
}

.card {
    background: white;
    padding: 18px;
    border-radius: 18px;
    box-shadow: 0 4px 18px rgba(15,23,42,0.08);
    border: 1px solid #e5e7eb;
}

.card h3 {
    margin: 0;
    font-size: 13px;
    color: #64748b;
}

.value {
    margin-top: 10px;
    font-size: 25px;
    font-weight: bold;
    color: #064e3b;
}

.panel {
    background: white;
    padding: 20px;
    border-radius: 18px;
    box-shadow: 0 4px 18px rgba(15,23,42,0.08);
    border: 1px solid #e5e7eb;
    margin-bottom: 22px;
}

.panel h2 {
    margin-top: 0;
    color: #064e3b;
}

.btn {
    display: inline-block;
    padding: 12px 18px;
    border-radius: 12px;
    text-decoration: none;
    color: white;
    background: #15803d;
    margin: 5px 8px 5px 0;
    font-weight: bold;
}

.btn.blue {
    background: #2563eb;
}

.btn.purple {
    background: #7c3aed;
}

.btn.gray {
    background: #334155;
}

.filters {
    margin-bottom: 16px;
}

select,
input,
button {
    padding: 11px;
    border-radius: 10px;
    border: 1px solid #cbd5e1;
    margin: 4px;
}

button {
    background: #15803d;
    color: white;
    border: none;
    cursor: pointer;
    font-weight: bold;
}

table {
    width: 100%;
    border-collapse: collapse;
    background: white;
    border-radius: 14px;
    overflow: hidden;
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
    border-radius: 999px;
    font-weight: bold;
    font-size: 12px;
}

.FIRE_CHECK {
    background: #fee2e2;
    color: #991b1b;
}

.HIGH {
    background: #ffedd5;
    color: #c2410c;
}

.MEDIUM {
    background: #fef9c3;
    color: #a16207;
}

.LOW {
    background: #dcfce7;
    color: #166534;
}

.note {
    background: #ecfdf5;
    border-left: 5px solid #16a34a;
    padding: 14px;
    border-radius: 12px;
    margin-top: 18px;
}

.small {
    font-size: 12px;
    color: #64748b;
}

@media(max-width: 900px) {
    .sidebar {
        position: relative;
        width: 100%;
        height: auto;
    }

    .main {
        margin-left: 0;
    }

    table {
        display: block;
        overflow-x: auto;
    }
}
</style>
</head>

<body>

<div class="sidebar">
    <div class="logo">
        <div class="logo-icon">🌳</div>
        <div>
            <div class="logo-title">GODDA<br>FRIS</div>
            <div class="logo-small">Forest Resilience System</div>
        </div>
    </div>

    <div class="nav">
        <a href="/dashboard" class="{{ 'active' if active == 'dashboard' else '' }}">🏠 Dashboard</a>
        <a href="/map-view" class="{{ 'active' if active == 'map' else '' }}">🗺️ Map View</a>
        <a href="/grid-analytics" class="{{ 'active' if active == 'grid' else '' }}">📊 Grid Analytics</a>
        <a href="/fire-intelligence" class="{{ 'active' if active == 'fire' else '' }}">🔥 Fire Intelligence</a>
        <a href="/carbon-analytics" class="{{ 'active' if active == 'carbon' else '' }}">🌿 Carbon Analytics</a>
        <a href="/patrol-management" class="{{ 'active' if active == 'patrol' else '' }}">🚶 Patrol Management</a>
        <a href="/reports" class="{{ 'active' if active == 'reports' else '' }}">📄 Reports</a>
        <a href="/alerts" class="{{ 'active' if active == 'alerts' else '' }}">🔔 Alerts</a>
        <a href="/history" class="{{ 'active' if active == 'history' else '' }}">🕒 History</a>
        <a href="/settings" class="{{ 'active' if active == 'settings' else '' }}">⚙️ Settings</a>
    </div>

    <div class="quick">
        <h3>Quick Actions</h3>
        <a href="/open-map" target="_blank">🗺️ Open Latest Map</a>
        <a href="/download-csv">⬇️ Download CSV</a>
        <a href="/download-geojson">⬇️ Download GeoJSON</a>
    </div>
</div>

<div class="main">
    <div class="hero">
        <h1>Godda FRIS {{ title }}</h1>
        <p>Forest Health, Fire, Carbon & Patrol Intelligence System</p>
    </div>

    <div class="content">

        <p class="small">Active data folder: {{ summary.output_dir }}</p>

        {% if section == "dashboard" %}
            {{ dashboard_section(summary, rows) | safe }}
        {% elif section == "map" %}
            {{ map_section(map_exists) | safe }}
        {% elif section == "grid" %}
            {{ table_section(rows, "Grid Analytics") | safe }}
        {% elif section == "fire" %}
            {{ table_section(rows, "Fire Intelligence") | safe }}
        {% elif section == "carbon" %}
            {{ table_section(rows, "Carbon Analytics") | safe }}
        {% elif section == "patrol" %}
            {{ table_section(rows, "Patrol Management") | safe }}
        {% elif section == "reports" %}
            {{ reports_section(summary, csv_exists, map_exists) | safe }}
        {% elif section == "alerts" %}
            {{ table_section(rows, "Active Alerts") | safe }}
        {% elif section == "history" %}
            {{ history_section(summary, rows) | safe }}
        {% elif section == "settings" %}
            {{ settings_section(summary) | safe }}
        {% endif %}

        <div class="note">
            <b>Note:</b> FRIS carbon output is MRV-support intelligence only. It is not a verified carbon credit issuance claim.
        </div>

    </div>
</div>

</body>
</html>
"""


# =====================================================
# TEMPLATE HELPERS
# =====================================================

@app.context_processor
def inject_helpers():

    def cards(summary):
        return f"""
        <div class="cards">
            <div class="card"><h3>Total Forest Grids</h3><div class="value">{summary['total_grids']}</div></div>
            <div class="card"><h3>Fire Check</h3><div class="value" style="color:#dc2626;">{summary['fire_check']}</div></div>
            <div class="card"><h3>High Priority</h3><div class="value" style="color:#ea580c;">{summary['high']}</div></div>
            <div class="card"><h3>Medium Priority</h3><div class="value" style="color:#ca8a04;">{summary['medium']}</div></div>
            <div class="card"><h3>Ecosystem Carbon</h3><div class="value">{summary['carbon']} tC</div></div>
            <div class="card"><h3>Carbon Opportunity</h3><div class="value" style="color:#7c3aed;">{summary['carbon_opportunity']} tCO₂e</div></div>
        </div>
        """

    def weather_cards(summary):
        return f"""
        <div class="cards">
            <div class="card"><h3>Temperature</h3><div class="value" style="color:#dc2626;">{summary['temperature']} °C</div></div>
            <div class="card"><h3>Rainfall 24h</h3><div class="value" style="color:#2563eb;">{summary['rainfall']} mm</div></div>
            <div class="card"><h3>Wind</h3><div class="value" style="color:#0f766e;">{summary['wind']} km/h</div></div>
            <div class="card"><h3>Wind Gust</h3><div class="value">{summary['gust']} km/h</div></div>
            <div class="card"><h3>Weather Fire Class</h3><div class="value" style="font-size:17px;">{summary['weather_class']}</div></div>
            <div class="card"><h3>MRV Confidence</h3><div class="value" style="font-size:17px;">{summary['mrv']}</div></div>
        </div>
        """

    def table_section(rows, heading):
        html = f"""
        <div class="panel">
            <h2>{heading}</h2>

            <div class="filters">
                <form method="get">
                    <select name="priority">
                        <option value="ALL">All Priorities</option>
                        <option value="FIRE_CHECK">Fire Check</option>
                        <option value="HIGH">High</option>
                        <option value="MEDIUM">Medium</option>
                        <option value="LOW">Low</option>
                    </select>

                    <input type="text" name="grid" placeholder="Search Grid ID">
                    <button type="submit">Filter</button>
                    <a href="{request.path}">Reset</a>
                </form>
            </div>

            <table>
                <tr>
                    <th>Grid ID</th>
                    <th>Priority</th>
                    <th>Risk</th>
                    <th>Forest %</th>
                    <th>Health</th>
                    <th>Moisture</th>
                    <th>Fire FRP</th>
                    <th>Carbon tC</th>
                    <th>MRV</th>
                    <th>Action</th>
                    <th>Map</th>
                </tr>
        """

        for row in rows:
            priority = row.get("final_priority", "")
            html += f"""
            <tr>
                <td>{row.get("grid_id", "")}</td>
                <td><span class="badge {priority}">{priority}</span></td>
                <td>{row.get("final_risk_score", "")}</td>
                <td>{row.get("forest_pct", "")}</td>
                <td>{row.get("health_class", "")}</td>
                <td>{row.get("moisture_class_calibrated", "")}</td>
                <td>{row.get("fire_frp_max", "")}</td>
                <td>{row.get("ecosystem_carbon_total_ton", "")}</td>
                <td>{row.get("mrv_confidence", "")}</td>
                <td style="text-align:left;">{row.get("patrol_action", "")}</td>
                <td><a href="{row.get("google_maps_link", "#")}" target="_blank">Go</a></td>
            </tr>
            """

        html += "</table></div>"
        return html

    def dashboard_section(summary, rows):
        return f"""
        {cards(summary)}
        <div class="panel">
            <h2>Weather & MRV Context</h2>
            {weather_cards(summary)}
        </div>
        <div class="panel">
            <h2>Latest Outputs</h2>
            <a class="btn blue" href="/open-map" target="_blank">Open Latest FRIS Map</a>
            <a class="btn purple" href="/download-csv">Download Latest CSV</a>
            <a class="btn gray" href="/download-geojson">Download GeoJSON</a>
        </div>
        {table_section(rows, "Grid-wise Information")}
        """

    def map_section(map_exists):
        if map_exists:
            return """
            <div class="panel">
                <h2>Latest FRIS Map</h2>
                <p>Open the latest generated operational map.</p>
                <a class="btn blue" href="/open-map" target="_blank">Open Full Map</a>
                <iframe src="/open-map" style="width:100%;height:650px;border:1px solid #ddd;border-radius:14px;margin-top:15px;"></iframe>
            </div>
            """
        return """
        <div class="panel">
            <h2>Map Not Found</h2>
            <p>Place <b>fris_latest_map.html</b> inside the output folder.</p>
        </div>
        """

    def reports_section(summary, csv_exists, map_exists):
        return f"""
        {cards(summary)}
        <div class="panel">
            <h2>Reports</h2>
            <p>Download latest FRIS operational files.</p>
            <a class="btn purple" href="/download-csv">Download CSV</a>
            <a class="btn gray" href="/download-geojson">Download GeoJSON</a>
            <a class="btn blue" href="/open-map" target="_blank">Open Map</a>
        </div>
        """

    def history_section(summary, rows):
        return f"""
        <div class="panel">
            <h2>History Status</h2>
            <p><b>Memory Class:</b> {summary['memory_class']}</p>
            <p><b>MRV Confidence:</b> {summary['mrv']}</p>
            <p><b>Active data folder:</b> {summary['output_dir']}</p>
        </div>
        {table_section(rows, "Latest History-Based Grid View")}
        """

    def settings_section(summary):
        return f"""
        <div class="panel">
            <h2>System Settings</h2>
            <p><b>Output Folder:</b> {summary['output_dir']}</p>
            <p><b>CSV Path:</b> {CSV_PATH}</p>
            <p><b>Map Path:</b> {MAP_PATH}</p>
            <p><b>GeoJSON Path:</b> {GEOJSON_PATH}</p>
        </div>
        """

    return dict(
        dashboard_section=dashboard_section,
        table_section=table_section,
        map_section=map_section,
        reports_section=reports_section,
        history_section=history_section,
        settings_section=settings_section,
    )


# =====================================================
# MISSING CSV PAGE
# =====================================================

MISSING_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Godda FRIS Missing CSV</title>
<style>
body {
    font-family: Arial;
    background: #f4f7f5;
    padding: 30px;
}
.box {
    background: white;
    padding: 25px;
    border-radius: 18px;
    max-width: 850px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.08);
}
code {
    background: #f1f5f9;
    padding: 4px 8px;
    border-radius: 6px;
}
</style>
</head>
<body>
<div class="box">
<h2>Godda FRIS Dashboard</h2>
<h3>CSV not found</h3>

<p>The app searched these folders:</p>

<ul>
{% for folder in folders %}
<li><code>{{ folder }}</code></li>
{% endfor %}
</ul>

<p>Required file:</p>
<code>fris_latest.csv</code>

<p>For Render, keep this structure:</p>

<pre>
fris_showcase/
├── app.py
├── requirements.txt
└── output/
    ├── fris_latest.csv
    ├── fris_latest_map.html
    └── fris_latest.geojson
</pre>
</div>
</body>
</html>
"""


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)