from flask import Flask, render_template_string, send_file, abort
import pandas as pd
from pathlib import Path
from datetime import datetime

app = Flask(__name__)

# =========================================================
# FRIS DASHBOARD SETTINGS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

POSSIBLE_DATA_DIRS = [
    BASE_DIR / "data",
    BASE_DIR / "output",
    Path(r"C:\cfris_app\data"),
    Path(r"C:\cfris\output"),
]

CSV_NAME = "fris_latest.csv"
MAP_NAME = "fris_latest_map.html"


# =========================================================
# DATA HELPERS
# =========================================================

def find_file(filename):
    for folder in POSSIBLE_DATA_DIRS:
        path = folder / filename
        if path.exists():
            return path
    return None


def safe_value(row, col, default=""):
    if col in row and pd.notna(row[col]):
        return row[col]
    return default


def load_data():
    csv_path = find_file(CSV_NAME)

    if csv_path is None:
        return pd.DataFrame(), None

    df = pd.read_csv(csv_path)

    required_cols = [
        "grid_id",
        "final_priority",
        "final_risk_score",
        "risk_class",
        "health_class",
        "moisture_class",
        "moisture_class_calibrated",
        "ndvi",
        "ndmi",
        "forest_pct",
        "fire_count",
        "fire_frp_sum",
        "fire_frp_max",
        "fire_intensity_class",
        "lat",
        "lon",
        "google_maps_link",
        "patrol_action",
        "recommended_action",
        "field_inference",
        "hansen_loss_pct",
        "hansen_treecover2000_pct",
        "mining_pressure_class",
        "mining_pressure_score",
        "ecosystem_carbon_co2e_total",
        "carbon_status",
        "preliminary_carbon_opportunity_co2e",
        "carbon_credit_claim_status",
        "ecological_memory_class",
        "ecological_memory_score",
        "ecological_memory_inference",
        "soil_type",
        "soil_moisture_retention_class",
        "soil_drying_speed",
        "temperature_c",
        "rainfall_24h_mm",
        "wind_speed_kmph",
        "weather_fire_spread_class",
        "system_run_timestamp_local",
    ]

    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    df["final_priority"] = df["final_priority"].fillna("LOW").astype(str).str.upper()

    priority_order = {
        "FIRE_CHECK": 1,
        "CRITICAL": 1,
        "HIGH": 2,
        "MEDIUM": 3,
        "MODERATE": 3,
        "LOW": 4,
    }

    df["priority_rank"] = df["final_priority"].map(priority_order).fillna(9)

    if "final_risk_score" in df.columns:
        df["final_risk_score"] = pd.to_numeric(df["final_risk_score"], errors="coerce").fillna(0)
    else:
        df["final_risk_score"] = 0

    df = df.sort_values(by=["priority_rank", "final_risk_score"], ascending=[True, False])

    return df, csv_path


def build_watchlist(df):
    if df.empty:
        return pd.DataFrame()

    work = df.copy()

    for col in ["hansen_loss_pct", "forest_pct", "ndvi", "ndmi", "final_risk_score"]:
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)

    watch_rows = []

    for _, row in work.iterrows():
        grid_id = str(row.get("grid_id", ""))
        forest_pct = row["forest_pct"]
        ndvi = row["ndvi"]
        ndmi = row["ndmi"]
        hansen_loss = row["hansen_loss_pct"]
        priority = str(row.get("final_priority", "LOW")).upper()
        mining_class = str(row.get("mining_pressure_class", "NONE")).upper()

        category = None
        reason = None
        action = None

        if hansen_loss >= 15 and forest_pct >= 85 and ndvi >= 0.40:
            category = "Historical Disturbance Watch"
            reason = (
                "Current forest condition appears stable, but historical forest-loss "
                "evidence is elevated compared with normal grids."
            )
            action = "Routine ecological monitoring and historical disturbance verification."

        elif forest_pct >= 85 and ndvi < 0.20:
            category = "Ecological Anomaly Alert"
            reason = (
                "Forest extent is high, but NDVI is abnormally low. This may indicate "
                "seasonal stress, shadow/cloud issue, degraded vegetation, or local disturbance."
            )
            action = "Priority field verification recommended before any conclusion."

        elif forest_pct >= 85 and ndvi < 0.40:
            category = "Vegetation Stress Watch"
            reason = (
                "Forest-dominant grid shows stressed vegetation signal. This may be seasonal, "
                "moisture-related, grazing-related, or disturbance-related."
            )
            action = "Monitor in next runs and verify if stress continues."

        elif mining_class in ["HIGH", "VERY_HIGH"] and forest_pct >= 85:
            category = "Mining Influence Watch"
            reason = (
                "Grid is near a mining influence zone. This does not prove illegal activity, "
                "but it should remain under ecological watch-list monitoring."
            )
            action = "Routine patrol and trend monitoring."

        elif priority in ["HIGH", "CRITICAL", "FIRE_CHECK"]:
            category = "Operational Verification Alert"
            reason = "Current FRIS priority is elevated."
            action = "Field verification according to patrol priority."

        if category:
            row_dict = row.to_dict()
            row_dict["watch_category"] = category
            row_dict["watch_reason"] = reason
            row_dict["watch_action"] = action
            watch_rows.append(row_dict)

    watch_df = pd.DataFrame(watch_rows)

    if watch_df.empty:
        return watch_df

    category_rank = {
        "Ecological Anomaly Alert": 1,
        "Operational Verification Alert": 2,
        "Historical Disturbance Watch": 3,
        "Vegetation Stress Watch": 4,
        "Mining Influence Watch": 5,
    }

    watch_df["watch_rank"] = watch_df["watch_category"].map(category_rank).fillna(9)
    watch_df = watch_df.sort_values(
        by=["watch_rank", "hansen_loss_pct", "final_risk_score"],
        ascending=[True, False, False],
    )

    return watch_df


def get_summary(df):
    if df.empty:
        return {
            "total": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "fire": 0,
            "watch": 0,
            "run_time": "No data",
        }

    priority = df["final_priority"].astype(str).str.upper()

    fire_count = 0
    if "fire_count" in df.columns:
        fire_count = pd.to_numeric(df["fire_count"], errors="coerce").fillna(0).gt(0).sum()

    run_time = "Available"
    if "system_run_timestamp_local" in df.columns:
        values = df["system_run_timestamp_local"].dropna().astype(str)
        if len(values) > 0:
            run_time = values.iloc[-1]

    watch_df = build_watchlist(df)

    return {
        "total": len(df),
        "critical": priority.isin(["CRITICAL", "FIRE_CHECK"]).sum(),
        "high": priority.eq("HIGH").sum(),
        "medium": priority.isin(["MEDIUM", "MODERATE"]).sum(),
        "low": priority.eq("LOW").sum(),
        "fire": int(fire_count),
        "watch": len(watch_df),
        "run_time": run_time,
    }


# =========================================================
# HTML
# =========================================================

BASE_STYLE = """
<style>
    body {
        margin: 0;
        font-family: Arial, sans-serif;
        background: #f4f7f4;
        color: #1f2d1f;
    }
    .topbar {
        background: linear-gradient(135deg, #103d1b, #1b5e20);
        color: white;
        padding: 22px;
        text-align: center;
    }
    .topbar h1 {
        margin: 0;
        font-size: 28px;
    }
    .topbar p {
        margin: 6px 0 0 0;
        opacity: 0.9;
    }
    .container {
        max-width: 1150px;
        margin: auto;
        padding: 18px;
    }
    .nav {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        justify-content: center;
        margin: 18px 0;
    }
    .nav a {
        background: #1b5e20;
        color: white;
        padding: 12px 16px;
        border-radius: 12px;
        text-decoration: none;
        font-weight: bold;
    }
    .nav a.secondary {
        background: #455a64;
    }
    .summary-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 12px;
        margin: 18px 0;
    }
    .summary-card {
        background: white;
        border-radius: 16px;
        padding: 18px;
        box-shadow: 0 3px 10px rgba(0,0,0,0.10);
        text-align: center;
    }
    .summary-card h3 {
        margin: 0;
        font-size: 26px;
        color: #1b5e20;
    }
    .summary-card p {
        margin: 6px 0 0 0;
        color: #555;
    }
    .grid-card {
        background: white;
        border-radius: 16px;
        padding: 18px;
        margin: 14px 0;
        box-shadow: 0 3px 10px rgba(0,0,0,0.10);
        border-left: 8px solid #2e7d32;
    }
    .grid-card.high, .grid-card.critical, .grid-card.fire_check {
        border-left-color: #b71c1c;
    }
    .grid-card.medium, .grid-card.moderate {
        border-left-color: #ef6c00;
    }
    .grid-title {
        font-size: 20px;
        font-weight: bold;
        color: #103d1b;
        margin-bottom: 8px;
    }
    .badge {
        display: inline-block;
        padding: 6px 10px;
        border-radius: 999px;
        color: white;
        font-size: 13px;
        font-weight: bold;
        margin: 3px 4px 3px 0;
        background: #2e7d32;
    }
    .badge.high, .badge.critical, .badge.fire_check {
        background: #b71c1c;
    }
    .badge.medium, .badge.moderate {
        background: #ef6c00;
    }
    .badge.watch {
        background: #6a1b9a;
    }
    .badge.info {
        background: #455a64;
    }
    .data-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 8px;
        margin-top: 12px;
    }
    .data-item {
        background: #f1f5f1;
        padding: 10px;
        border-radius: 10px;
        font-size: 14px;
    }
    .button {
        display: inline-block;
        padding: 10px 14px;
        background: #1b5e20;
        color: white;
        border-radius: 10px;
        text-decoration: none;
        margin: 8px 6px 0 0;
        font-weight: bold;
    }
    .button.secondary {
        background: #455a64;
    }
    .button.warning {
        background: #6a1b9a;
    }
    .note {
        background: #fff8e1;
        border-left: 6px solid #f9a825;
        padding: 14px;
        border-radius: 12px;
        margin: 16px 0;
        line-height: 1.45;
    }
    .safe {
        background: #e8f5e9;
        border-left: 6px solid #2e7d32;
        padding: 14px;
        border-radius: 12px;
        margin: 16px 0;
        line-height: 1.45;
    }
    iframe {
        width: 100%;
        height: 78vh;
        border: 0;
        border-radius: 16px;
        box-shadow: 0 3px 10px rgba(0,0,0,0.16);
    }
</style>
"""

HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Godda FRIS Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """ + BASE_STYLE + """
</head>
<body>
    <div class="topbar">
        <h1>Godda FRIS Dashboard</h1>
        <p>Forest Resilience Information System | Operational + Ecological Watch-List</p>
    </div>

    <div class="container">
        <div class="nav">
            <a href="/priority">Today Priority Grids</a>
            <a href="/watchlist">Ecological Watch-List</a>
            <a href="/map">Open FRIS Map</a>
            <a class="secondary" href="/download">Download CSV</a>
        </div>

        {% if summary.total == 0 %}
            <div class="note">
                <b>No CSV found.</b><br>
                Keep <b>fris_latest.csv</b> inside the data folder.
            </div>
        {% endif %}

        <div class="summary-grid">
            <div class="summary-card"><h3>{{ summary.total }}</h3><p>Total Forest Grids</p></div>
            <div class="summary-card"><h3>{{ summary.critical }}</h3><p>Critical / Fire Check</p></div>
            <div class="summary-card"><h3>{{ summary.high }}</h3><p>High Priority</p></div>
            <div class="summary-card"><h3>{{ summary.medium }}</h3><p>Medium Priority</p></div>
            <div class="summary-card"><h3>{{ summary.low }}</h3><p>Low Priority</p></div>
            <div class="summary-card"><h3>{{ summary.watch }}</h3><p>Watch-List Grids</p></div>
        </div>

        <div class="safe">
            <b>Latest Run:</b> {{ summary.run_time }}<br><br>
            FRIS separates urgent patrol priority from ecological interpretation.  
            The watch-list is informative and verification-based. It does not prove illegal activity.
        </div>
    </div>
</body>
</html>
"""

PRIORITY_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Today Priority Grids</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """ + BASE_STYLE + """
</head>
<body>
    <div class="topbar">
        <h1>Today Priority Grids</h1>
        <p>Operational patrol and field-response layer</p>
    </div>

    <div class="container">
        <div class="nav">
            <a href="/">Home</a>
            <a href="/watchlist">Ecological Watch-List</a>
            <a href="/map">Map</a>
        </div>

        {% if rows|length == 0 %}
            <div class="note">No CSV data found.</div>
        {% endif %}

        {% for row in rows %}
        <div class="grid-card {{ row.final_priority|lower }}">
            <div class="grid-title">Grid: {{ row.grid_id }}</div>

            <span class="badge {{ row.final_priority|lower }}">Priority: {{ row.final_priority }}</span>
            <span class="badge info">Risk Score: {{ row.final_risk_score }}</span>

            <div class="data-grid">
                <div class="data-item"><b>Health:</b> {{ row.health_class }}</div>
                <div class="data-item"><b>Moisture:</b> {{ row.moisture_class_calibrated or row.moisture_class }}</div>
                <div class="data-item"><b>NDVI:</b> {{ row.ndvi }}</div>
                <div class="data-item"><b>NDMI:</b> {{ row.ndmi }}</div>
                <div class="data-item"><b>Forest %:</b> {{ row.forest_pct }}</div>
                <div class="data-item"><b>Fire Count:</b> {{ row.fire_count }}</div>
                <div class="data-item"><b>Fire Class:</b> {{ row.fire_intensity_class }}</div>
                <div class="data-item"><b>Mining:</b> {{ row.mining_pressure_class }}</div>
            </div>

            <p><b>Action:</b> {{ row.patrol_action or row.recommended_action }}</p>

            <a class="button" href="/detail/{{ row.grid_id }}">View Detail</a>

            {% if row.google_maps_link %}
            <a class="button secondary" href="{{ row.google_maps_link }}" target="_blank">Navigate</a>
            {% endif %}
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

WATCHLIST_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Ecological Watch-List</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """ + BASE_STYLE + """
</head>
<body>
    <div class="topbar">
        <h1>Ecological Watch-List</h1>
        <p>Separate informative layer for disturbance verification and ecological anomaly monitoring</p>
    </div>

    <div class="container">
        <div class="nav">
            <a href="/">Home</a>
            <a href="/priority">Today Priority Grids</a>
            <a href="/map">Map</a>
        </div>

        <div class="note">
            <b>Important:</b> This section is not an accusation or legal proof layer.  
            It only highlights grids needing ecological verification because of historical disturbance evidence, unusual NDVI behavior, vegetation stress, or influence-zone signals.
        </div>

        {% if rows|length == 0 %}
            <div class="safe">
                No major ecological watch-list grid found from the current CSV.
            </div>
        {% endif %}

        {% for row in rows %}
        <div class="grid-card">
            <div class="grid-title">Grid: {{ row.grid_id }}</div>

            <span class="badge watch">{{ row.watch_category }}</span>
            <span class="badge info">Priority: {{ row.final_priority }}</span>
            <span class="badge info">Risk: {{ row.final_risk_score }}</span>

            <div class="data-grid">
                <div class="data-item"><b>Forest %:</b> {{ row.forest_pct }}</div>
                <div class="data-item"><b>NDVI:</b> {{ row.ndvi }}</div>
                <div class="data-item"><b>NDMI:</b> {{ row.ndmi }}</div>
                <div class="data-item"><b>Health:</b> {{ row.health_class }}</div>
                <div class="data-item"><b>Moisture:</b> {{ row.moisture_class_calibrated or row.moisture_class }}</div>
                <div class="data-item"><b>Hansen Loss %:</b> {{ row.hansen_loss_pct }}</div>
                <div class="data-item"><b>Mining:</b> {{ row.mining_pressure_class }}</div>
                <div class="data-item"><b>Fire:</b> {{ row.fire_intensity_class }}</div>
            </div>

            <p><b>Why Listed:</b> {{ row.watch_reason }}</p>
            <p><b>Recommended Action:</b> {{ row.watch_action }}</p>

            {% if row.field_inference %}
            <p><b>FRIS Field Inference:</b> {{ row.field_inference }}</p>
            {% endif %}

            <a class="button warning" href="/detail/{{ row.grid_id }}">View Full Detail</a>

            {% if row.google_maps_link %}
            <a class="button secondary" href="{{ row.google_maps_link }}" target="_blank">Navigate</a>
            {% endif %}
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

DETAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Grid Detail</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """ + BASE_STYLE + """
</head>
<body>
    <div class="topbar">
        <h1>Grid Detail: {{ row.grid_id }}</h1>
        <p>Complete operational and ecological interpretation</p>
    </div>

    <div class="container">
        <div class="nav">
            <a href="/">Home</a>
            <a href="/priority">Priority</a>
            <a href="/watchlist">Watch-List</a>
            <a href="/map">Map</a>
        </div>

        <div class="grid-card {{ row.final_priority|lower }}">
            <span class="badge {{ row.final_priority|lower }}">Priority: {{ row.final_priority }}</span>
            <span class="badge info">Risk Score: {{ row.final_risk_score }}</span>

            <div class="data-grid">
                <div class="data-item"><b>Forest %:</b> {{ row.forest_pct }}</div>
                <div class="data-item"><b>NDVI:</b> {{ row.ndvi }}</div>
                <div class="data-item"><b>Health:</b> {{ row.health_class }}</div>
                <div class="data-item"><b>NDMI:</b> {{ row.ndmi }}</div>
                <div class="data-item"><b>Moisture:</b> {{ row.moisture_class_calibrated or row.moisture_class }}</div>
                <div class="data-item"><b>Fire Count:</b> {{ row.fire_count }}</div>
                <div class="data-item"><b>Fire FRP Max:</b> {{ row.fire_frp_max }}</div>
                <div class="data-item"><b>Fire Class:</b> {{ row.fire_intensity_class }}</div>
                <div class="data-item"><b>Hansen Loss %:</b> {{ row.hansen_loss_pct }}</div>
                <div class="data-item"><b>Mining:</b> {{ row.mining_pressure_class }}</div>
                <div class="data-item"><b>Carbon Status:</b> {{ row.carbon_status }}</div>
                <div class="data-item"><b>Carbon CO₂e:</b> {{ row.ecosystem_carbon_co2e_total }}</div>
                <div class="data-item"><b>Soil:</b> {{ row.soil_type }}</div>
                <div class="data-item"><b>Rain 24h:</b> {{ row.rainfall_24h_mm }}</div>
                <div class="data-item"><b>Temperature:</b> {{ row.temperature_c }}</div>
                <div class="data-item"><b>Wind:</b> {{ row.wind_speed_kmph }}</div>
            </div>

            <p><b>Patrol Action:</b> {{ row.patrol_action or row.recommended_action }}</p>
            <p><b>Field Inference:</b> {{ row.field_inference }}</p>
            <p><b>Ecological Memory:</b> {{ row.ecological_memory_class }} | Score: {{ row.ecological_memory_score }}</p>
            <p><b>Memory Inference:</b> {{ row.ecological_memory_inference }}</p>

            <div class="note">
                FRIS is satellite-assisted decision support. Field verification is required before legal, enforcement, compensation, or carbon-credit decisions.
            </div>

            {% if row.google_maps_link %}
            <a class="button" href="{{ row.google_maps_link }}" target="_blank">Open in Google Maps</a>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

MAP_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>FRIS Map</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    """ + BASE_STYLE + """
</head>
<body>
    <div class="topbar">
        <h1>FRIS Map</h1>
        <p>Latest generated operational map</p>
    </div>

    <div class="container">
        <div class="nav">
            <a href="/">Home</a>
            <a href="/priority">Priority</a>
            <a href="/watchlist">Watch-List</a>
        </div>

        {% if map_found %}
            <iframe src="/mapfile"></iframe>
        {% else %}
            <div class="note">
                Map file not found. Keep <b>fris_latest_map.html</b> inside data or output folder.
            </div>
        {% endif %}
    </div>
</body>
</html>
"""


# =========================================================
# ROUTES
# =========================================================

@app.route("/")
def home():
    df, _ = load_data()
    summary = get_summary(df)
    return render_template_string(HOME_HTML, summary=summary)


@app.route("/priority")
def priority():
    df, _ = load_data()

    if df.empty:
        rows = []
    else:
        rows = df.to_dict(orient="records")

    return render_template_string(PRIORITY_HTML, rows=rows)


@app.route("/watchlist")
def watchlist():
    df, _ = load_data()
    watch_df = build_watchlist(df)

    if watch_df.empty:
        rows = []
    else:
        rows = watch_df.to_dict(orient="records")

    return render_template_string(WATCHLIST_HTML, rows=rows)


@app.route("/detail/<grid_id>")
def detail(grid_id):
    df, _ = load_data()

    if df.empty or "grid_id" not in df.columns:
        abort(404)

    matched = df[df["grid_id"].astype(str) == str(grid_id)]

    if matched.empty:
        abort(404)

    row = matched.iloc[0].to_dict()
    return render_template_string(DETAIL_HTML, row=row)


@app.route("/map")
def map_page():
    map_path = find_file(MAP_NAME)
    return render_template_string(MAP_HTML, map_found=map_path is not None)


@app.route("/mapfile")
def mapfile():
    map_path = find_file(MAP_NAME)

    if map_path is None:
        return "Map file not found", 404

    return send_file(map_path)


@app.route("/download")
def download():
    _, csv_path = load_data()

    if csv_path is None:
        return "CSV file not found", 404

    return send_file(csv_path, as_attachment=True)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)