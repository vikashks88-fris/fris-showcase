from flask import Flask, render_template_string, send_file, jsonify
from pathlib import Path
from datetime import datetime
import pandas as pd
import os

app = Flask(__name__)

BASE_DIR = Path(r"C:\fris_hazaribagh_west")
OUTPUT_DIR = BASE_DIR / "output"

CSV_FILE = OUTPUT_DIR / "fris_latest.csv"
MAP_FILE = OUTPUT_DIR / "fris_latest_map.html"


def safe_num(value, default=0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def load_fris_data():
    if not CSV_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(CSV_FILE)
    df.columns = df.columns.str.strip()

    if "final_risk_score" not in df.columns:
        df["final_risk_score"] = 0

    df["final_risk_score"] = pd.to_numeric(df["final_risk_score"], errors="coerce").fillna(0)

    return df


def simple_inference(row):
    priority = str(row.get("final_priority", "LOW")).upper()
    health = str(row.get("health_class", "UNKNOWN")).upper()
    moisture = str(row.get("moisture_class_calibrated", "UNKNOWN")).upper()
    fire = str(row.get("fire_intensity_class", "NO_FIRE")).upper()
    terrain = str(row.get("terrain_class", "UNKNOWN")).upper()
    memory = str(row.get("ecological_memory_class", "EARLY_TIMESTAMPED_MEMORY")).upper()

    lat = row.get("lat", "")
    lon = row.get("lon", "")

    reasons = []

    if fire != "NO_FIRE":
        reasons.append("active fire signal found")
    if health in ["STRESSED", "CRITICAL"]:
        reasons.append("vegetation health is weak")
    if moisture in ["DRY_STRESS", "SEVERE_DRYNESS", "DRIER_THAN_NORMAL"]:
        reasons.append("moisture stress is visible")
    if memory in ["CHRONIC_RISK_GRID", "YEARLY_DEGRADATION_SIGNAL", "REPEATED_YEARLY_STRESS"]:
        reasons.append("history shows repeated stress")
    if terrain in ["STEEP_TERRAIN", "MODERATE_SLOPE"]:
        reasons.append("terrain may make patrol difficult")

    if not reasons:
        why = "Routine monitoring only. No strong emergency signal."
    else:
        why = "Go because " + ", ".join(reasons) + "."

    if lat != "" and lon != "":
        where = f"Go to grid center near latitude {lat}, longitude {lon}."
    else:
        where = "Use the map link or grid ID to locate this area."

    if fire != "NO_FIRE":
        action = "Immediate fire verification."
    elif priority in ["CRITICAL", "HIGH", "FIRE_CHECK"]:
        action = "Same-day field check."
    elif moisture in ["DRY_STRESS", "SEVERE_DRYNESS"]:
        action = "Check during routine patrol."
    else:
        action = "Routine monitoring."

    return why, where, action


@app.route("/")
def dashboard():
    df = load_fris_data()

    if df.empty:
        return render_template_string("""
        <html>
        <head>
            <title>FRIS Hazaribagh West</title>
            <style>
                body { font-family: Arial; background:#f4f6f8; padding:40px; }
                .box { background:white; padding:30px; border-radius:16px; max-width:800px; margin:auto; }
            </style>
        </head>
        <body>
            <div class="box">
                <h1>FRIS Hazaribagh West Dashboard</h1>
                <p>No FRIS CSV found.</p>
                <p>Expected file:</p>
                <b>{{ csv }}</b>
            </div>
        </body>
        </html>
        """, csv=str(CSV_FILE))

    total_grids = len(df)
    high_grids = len(df[df.get("final_priority", "").astype(str).str.upper().isin(["HIGH", "CRITICAL", "FIRE_CHECK"])]) if "final_priority" in df.columns else 0
    fire_grids = len(df[df.get("fire_count", 0).fillna(0).astype(float) > 0]) if "fire_count" in df.columns else 0

    forest_area = round(total_grids * 100, 2)

    avg_risk = round(df["final_risk_score"].mean(), 2)

    top = df.sort_values("final_risk_score", ascending=False).head(20).copy()

    rows = []
    for _, r in top.iterrows():
        why, where, action = simple_inference(r)
        rows.append({
            "grid_id": r.get("grid_id", ""),
            "priority": r.get("final_priority", "LOW"),
            "score": round(safe_num(r.get("final_risk_score")), 2),
            "health": r.get("health_class", ""),
            "moisture": r.get("moisture_class_calibrated", ""),
            "fire": r.get("fire_intensity_class", "NO_FIRE"),
            "terrain": r.get("terrain_class", ""),
            "action": action,
            "why": why,
            "where": where,
            "map": r.get("google_maps_link", "#")
        })

    updated = datetime.now().strftime("%d %b %Y, %I:%M %p")

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>FRIS Hazaribagh West</title>
        <meta http-equiv="refresh" content="120">
        <style>
            body {
                margin:0;
                font-family: Arial, sans-serif;
                background:#eef2f3;
                color:#1f2937;
            }
            header {
                background:#123524;
                color:white;
                padding:24px 36px;
            }
            header h1 {
                margin:0;
                font-size:28px;
            }
            header p {
                margin:6px 0 0;
                opacity:0.9;
            }
            .container {
                padding:24px 36px;
            }
            .cards {
                display:grid;
                grid-template-columns: repeat(4, 1fr);
                gap:16px;
                margin-bottom:24px;
            }
            .card {
                background:white;
                border-radius:16px;
                padding:18px;
                box-shadow:0 4px 14px rgba(0,0,0,0.08);
            }
            .card h2 {
                margin:0;
                font-size:26px;
                color:#14532d;
            }
            .card p {
                margin:6px 0 0;
                color:#555;
            }
            .mapbox {
                background:white;
                border-radius:16px;
                padding:12px;
                box-shadow:0 4px 14px rgba(0,0,0,0.08);
                margin-bottom:24px;
            }
            iframe {
                width:100%;
                height:520px;
                border:0;
                border-radius:12px;
            }
            table {
                width:100%;
                border-collapse:collapse;
                background:white;
                border-radius:16px;
                overflow:hidden;
                box-shadow:0 4px 14px rgba(0,0,0,0.08);
            }
            th {
                background:#14532d;
                color:white;
                text-align:left;
                padding:12px;
                font-size:14px;
            }
            td {
                padding:12px;
                border-bottom:1px solid #e5e7eb;
                vertical-align:top;
                font-size:14px;
            }
            .LOW { color:#166534; font-weight:bold; }
            .MEDIUM { color:#ca8a04; font-weight:bold; }
            .HIGH { color:#ea580c; font-weight:bold; }
            .CRITICAL, .FIRE_CHECK { color:#dc2626; font-weight:bold; }
            a {
                color:#2563eb;
                text-decoration:none;
                font-weight:bold;
            }
            .footer {
                margin-top:20px;
                color:#555;
                font-size:13px;
            }
            @media(max-width:900px){
                .cards { grid-template-columns: repeat(2, 1fr); }
            }
        </style>
    </head>
    <body>
        <header>
            <h1>FRIS Hazaribagh West Dashboard</h1>
            <p>Dynamic forest health, moisture, fire and patrol intelligence dashboard</p>
        </header>

        <div class="container">
            <div class="cards">
                <div class="card">
                    <h2>{{ total_grids }}</h2>
                    <p>Forest grids</p>
                </div>
                <div class="card">
                    <h2>{{ forest_area }} ha</h2>
                    <p>Approx. forest-dominant area</p>
                </div>
                <div class="card">
                    <h2>{{ high_grids }}</h2>
                    <p>High priority grids</p>
                </div>
                <div class="card">
                    <h2>{{ fire_grids }}</h2>
                    <p>Active fire grids</p>
                </div>
            </div>

            <div class="mapbox">
                <h2>Live FRIS Map</h2>
                <iframe src="/map?ts={{ updated }}"></iframe>
            </div>

            <h2>Top 20 Field Attention Grids</h2>
            <table>
                <tr>
                    <th>Grid</th>
                    <th>Priority</th>
                    <th>Score</th>
                    <th>Condition</th>
                    <th>Action</th>
                    <th>Why to go</th>
                    <th>Where to go</th>
                    <th>Map</th>
                </tr>
                {% for r in rows %}
                <tr>
                    <td><b>{{ r.grid_id }}</b></td>
                    <td class="{{ r.priority }}">{{ r.priority }}</td>
                    <td>{{ r.score }}</td>
                    <td>
                        Health: {{ r.health }}<br>
                        Moisture: {{ r.moisture }}<br>
                        Fire: {{ r.fire }}<br>
                        Terrain: {{ r.terrain }}
                    </td>
                    <td><b>{{ r.action }}</b></td>
                    <td>{{ r.why }}</td>
                    <td>{{ r.where }}</td>
                    <td><a href="{{ r.map }}" target="_blank">Open</a></td>
                </tr>
                {% endfor %}
            </table>

            <div class="footer">
                Last dashboard refresh: {{ updated }} |
                CSV read dynamically from {{ csv_path }}
            </div>
        </div>
    </body>
    </html>
    """,
    total_grids=total_grids,
    forest_area=forest_area,
    high_grids=high_grids,
    fire_grids=fire_grids,
    avg_risk=avg_risk,
    rows=rows,
    updated=updated,
    csv_path=str(CSV_FILE)
    )


@app.route("/map")
def map_view():
    if MAP_FILE.exists():
        return send_file(MAP_FILE)
    return "<h2>FRIS map not found</h2><p>Expected: C:\\fris_hazaribagh_west\\output\\fris_latest_map.html</p>"


@app.route("/api/latest")
def api_latest():
    df = load_fris_data()
    if df.empty:
        return jsonify({"status": "no_csv", "path": str(CSV_FILE)})

    return jsonify({
        "status": "ok",
        "total_grids": len(df),
        "csv": str(CSV_FILE),
        "map": str(MAP_FILE),
        "updated": datetime.now().isoformat()
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)