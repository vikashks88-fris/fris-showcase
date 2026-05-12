from flask import Flask, render_template_string, send_from_directory, jsonify
import os
import pandas as pd
import json
from datetime import datetime

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CSV_FILE = os.path.join(DATA_DIR, "fris_latest.csv")
GEOJSON_FILE = os.path.join(DATA_DIR, "fris_latest.geojson")
MAP_FILE = os.path.join(DATA_DIR, "fris_latest_map.html")


def safe_read_csv():
    if not os.path.exists(CSV_FILE):
        return None
    try:
        return pd.read_csv(CSV_FILE)
    except Exception:
        return None


def pick_col(df, names):
    for n in names:
        if n in df.columns:
            return n
    return None


def get_dashboard_data():
    df = safe_read_csv()

    if df is None or df.empty:
        return {
            "csv_found": False,
            "total_grids": 0,
            "critical": 0,
            "high": 0,
            "moderate": 0,
            "low": 0,
            "active_fire": 0,
            "avg_ndvi": 0,
            "avg_ndmi": 0,
            "last_updated": "CSV not found",
            "top_grids": [],
            "system_status": "NO DATA",
            "recommendation": "Place fris_latest.csv inside data folder.",
        }

    risk_col = pick_col(df, ["risk_class", "final_priority", "priority", "risk_level"])
    fire_col = pick_col(df, ["active_fire", "fire_status", "fire_count"])
    ndvi_col = pick_col(df, ["NDVI", "ndvi", "avg_ndvi"])
    ndmi_col = pick_col(df, ["NDMI", "ndmi", "avg_ndmi"])
    grid_col = pick_col(df, ["grid_id", "Grid_ID", "id"])
    action_col = pick_col(df, ["patrol_action", "recommended_action", "inference", "recommendation"])

    risk_series = df[risk_col].astype(str).str.upper() if risk_col else pd.Series(["LOW"] * len(df))

    critical = int(risk_series.str.contains("CRITICAL|VERY HIGH|FIRE", na=False).sum())
    high = int(risk_series.str.contains("HIGH", na=False).sum())
    moderate = int(risk_series.str.contains("MODERATE|MEDIUM", na=False).sum())
    low = int(risk_series.str.contains("LOW|NORMAL|HEALTHY", na=False).sum())

    if fire_col:
        fire_values = df[fire_col]
        if pd.api.types.is_numeric_dtype(fire_values):
            active_fire = int((fire_values.fillna(0) > 0).sum())
        else:
            active_fire = int(fire_values.astype(str).str.upper().str.contains("YES|TRUE|ACTIVE|FIRE", na=False).sum())
    else:
        active_fire = 0

    avg_ndvi = round(float(pd.to_numeric(df[ndvi_col], errors="coerce").mean()), 3) if ndvi_col else 0
    avg_ndmi = round(float(pd.to_numeric(df[ndmi_col], errors="coerce").mean()), 3) if ndmi_col else 0

    if active_fire > 0 or critical > 0:
        system_status = "ALERT"
        recommendation = "Immediate verification required in priority grids."
    elif high > 0:
        system_status = "WATCH"
        recommendation = "Same-day patrol recommended for high-risk grids."
    else:
        system_status = "NORMAL"
        recommendation = "Routine patrol and continuous satellite monitoring."

    priority_order = {
        "CRITICAL": 1,
        "VERY HIGH": 1,
        "FIRE": 1,
        "HIGH": 2,
        "MODERATE": 3,
        "MEDIUM": 3,
        "LOW": 4,
        "NORMAL": 4,
        "HEALTHY": 4,
    }

    temp = df.copy()
    if risk_col:
        temp["_rank"] = temp[risk_col].astype(str).str.upper().map(
            lambda x: min([v for k, v in priority_order.items() if k in x], default=5)
        )
    else:
        temp["_rank"] = 5

    temp = temp.sort_values("_rank").head(10)

    top_grids = []
    for _, row in temp.iterrows():
        top_grids.append({
            "grid": str(row[grid_col]) if grid_col else "N/A",
            "risk": str(row[risk_col]) if risk_col else "LOW",
            "action": str(row[action_col]) if action_col else recommendation,
        })

    return {
        "csv_found": True,
        "total_grids": int(len(df)),
        "critical": critical,
        "high": high,
        "moderate": moderate,
        "low": low,
        "active_fire": active_fire,
        "avg_ndvi": avg_ndvi,
        "avg_ndmi": avg_ndmi,
        "last_updated": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        "top_grids": top_grids,
        "system_status": system_status,
        "recommendation": recommendation,
    }


@app.route("/")
def dashboard():
    data = get_dashboard_data()

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Godda FRIS Command Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: Inter, Segoe UI, Arial, sans-serif;
            background: radial-gradient(circle at top left, #1e3a2f, #060b13 45%, #020617);
            color: #e5f6ef;
        }

        .layout {
            display: grid;
            grid-template-columns: 250px 1fr;
            min-height: 100vh;
        }

        .sidebar {
            background: rgba(5, 15, 25, 0.88);
            backdrop-filter: blur(16px);
            padding: 25px 18px;
            border-right: 1px solid rgba(148, 255, 196, 0.15);
        }

        .brand {
            font-size: 30px;
            font-weight: 900;
            color: #39ff88;
            margin-bottom: 4px;
            letter-spacing: 1px;
        }

        .brand-sub {
            font-size: 12px;
            color: #9ca3af;
            margin-bottom: 28px;
        }

        .nav-item {
            padding: 14px 16px;
            margin-bottom: 12px;
            border-radius: 16px;
            background: rgba(148, 163, 184, 0.12);
            color: #d1fae5;
            font-weight: 700;
            cursor: pointer;
            transition: 0.25s;
            border: 1px solid rgba(255,255,255,0.05);
        }

        .nav-item:hover,
        .nav-item.active {
            background: linear-gradient(135deg, rgba(34,197,94,.35), rgba(14,165,233,.25));
            transform: translateX(4px);
            box-shadow: 0 0 25px rgba(34,197,94,.25);
        }

        .main {
            padding: 28px;
            overflow-x: hidden;
        }

        .topbar {
            display: flex;
            justify-content: space-between;
            gap: 20px;
            align-items: center;
            margin-bottom: 24px;
        }

        h1 {
            font-size: 34px;
            margin: 0;
            color: #ffffff;
        }

        .subtitle {
            color: #b7c7d8;
            margin-top: 8px;
            font-size: 15px;
        }

        .live-pill {
            padding: 12px 18px;
            border-radius: 999px;
            font-weight: 900;
            background: rgba(22,163,74,.18);
            color: #86efac;
            border: 1px solid rgba(134,239,172,.35);
            box-shadow: 0 0 25px rgba(34,197,94,.25);
        }

        .pulse {
            display: inline-block;
            width: 10px;
            height: 10px;
            background: #22c55e;
            border-radius: 50%;
            margin-right: 8px;
            box-shadow: 0 0 15px #22c55e;
        }

        .status-panel {
            display: grid;
            grid-template-columns: 1.5fr 1fr 1fr;
            gap: 18px;
            margin-bottom: 22px;
        }

        .panel {
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 24px;
            padding: 20px;
            box-shadow: 0 20px 45px rgba(0,0,0,.25);
        }

        .panel-title {
            color: #94a3b8;
            font-size: 13px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .08em;
            margin-bottom: 10px;
        }

        .system-status {
            font-size: 34px;
            font-weight: 950;
            color: {% if data.system_status == "ALERT" %}#f87171{% elif data.system_status == "WATCH" %}#facc15{% else %}#4ade80{% endif %};
        }

        .recommendation {
            color: #dbeafe;
            line-height: 1.5;
            font-size: 15px;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(160px, 1fr));
            gap: 18px;
            margin-bottom: 22px;
        }

        .card {
            background: linear-gradient(145deg, rgba(30,41,59,.95), rgba(15,23,42,.95));
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 24px;
            padding: 20px;
            min-height: 118px;
            box-shadow: 0 18px 38px rgba(0,0,0,.28);
        }

        .card .label {
            color: #cbd5e1;
            font-weight: 800;
            font-size: 14px;
            margin-bottom: 16px;
        }

        .card .value {
            font-size: 34px;
            font-weight: 950;
            color: #ffffff;
        }

        .red { border-left: 5px solid #ef4444; }
        .orange { border-left: 5px solid #f97316; }
        .yellow { border-left: 5px solid #facc15; }
        .green { border-left: 5px solid #22c55e; }
        .blue { border-left: 5px solid #38bdf8; }

        .content-grid {
            display: grid;
            grid-template-columns: 1.8fr .9fr;
            gap: 20px;
        }

        .map-box {
            height: 620px;
            border-radius: 26px;
            overflow: hidden;
            background: rgba(15,23,42,.8);
            border: 1px solid rgba(148,163,184,.2);
            box-shadow: 0 25px 55px rgba(0,0,0,.35);
        }

        .map-box iframe {
            width: 100%;
            height: 100%;
            border: none;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        th {
            text-align: left;
            color: #93c5fd;
            padding: 10px;
            border-bottom: 1px solid rgba(148,163,184,.25);
        }

        td {
            padding: 11px 10px;
            border-bottom: 1px solid rgba(148,163,184,.12);
            color: #e5e7eb;
            vertical-align: top;
        }

        .risk-badge {
            padding: 5px 9px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 900;
            background: rgba(59,130,246,.18);
            color: #bfdbfe;
        }

        .footer {
            margin-top: 22px;
            color: #94a3b8;
            font-size: 12px;
            text-align: center;
        }

        .error {
            background: rgba(239,68,68,.15);
            border: 1px solid rgba(239,68,68,.35);
            color: #fecaca;
            padding: 20px;
            border-radius: 20px;
            margin-bottom: 20px;
        }

        @media(max-width: 1000px) {
            .layout {
                grid-template-columns: 1fr;
            }

            .sidebar {
                display: none;
            }

            .kpi-grid,
            .status-panel,
            .content-grid {
                grid-template-columns: 1fr;
            }

            .map-box {
                height: 500px;
            }
        }
    </style>
</head>

<body>
<div class="layout">

    <aside class="sidebar">
        <div class="brand">FRIS</div>
        <div class="brand-sub">Forest Resilience Intelligence System</div>

        <div class="nav-item active">Command Overview</div>
        <div class="nav-item">Live Forest Risk</div>
        <div class="nav-item">Fire Monitoring</div>
        <div class="nav-item">Moisture Stress</div>
        <div class="nav-item">Carbon MRV</div>
        <div class="nav-item">Grid Intelligence</div>
        <div class="nav-item">Operational Map</div>
        <div class="nav-item">System Health</div>
    </aside>

    <main class="main">

        <div class="topbar">
            <div>
                <h1>Godda FRIS Command Dashboard</h1>
                <div class="subtitle">
                    Satellite-based forest health, fire, moisture and patrol intelligence platform
                </div>
                <div class="subtitle">
                    Last Updated: {{ data.last_updated }} | Data Folder: /data
                </div>
            </div>

            <div class="live-pill">
                <span class="pulse"></span> LIVE SYSTEM
            </div>
        </div>

        {% if not data.csv_found %}
        <div class="error">
            <b>No FRIS CSV found.</b><br>
            Keep your file here:<br>
            <code>fris_showcase/data/fris_latest.csv</code>
        </div>
        {% endif %}

        <section class="status-panel">
            <div class="panel">
                <div class="panel-title">Operational Status</div>
                <div class="system-status">{{ data.system_status }}</div>
            </div>

            <div class="panel">
                <div class="panel-title">Field Recommendation</div>
                <div class="recommendation">{{ data.recommendation }}</div>
            </div>

            <div class="panel">
                <div class="panel-title">Satellite Inputs</div>
                <div class="recommendation">
                    Sentinel-2 NDVI/NDMI<br>
                    FIRMS Fire Alerts<br>
                    Forest Grid Engine
                </div>
            </div>
        </section>

        <section class="kpi-grid">
            <div class="card blue">
                <div class="label">Total Forest Grids</div>
                <div class="value">{{ data.total_grids }}</div>
            </div>

            <div class="card red">
                <div class="label">Critical</div>
                <div class="value">{{ data.critical }}</div>
            </div>

            <div class="card orange">
                <div class="label">High Risk</div>
                <div class="value">{{ data.high }}</div>
            </div>

            <div class="card yellow">
                <div class="label">Moderate</div>
                <div class="value">{{ data.moderate }}</div>
            </div>

            <div class="card red">
                <div class="label">Active Fire</div>
                <div class="value">{{ data.active_fire }}</div>
            </div>

            <div class="card green">
                <div class="label">Average NDVI</div>
                <div class="value">{{ data.avg_ndvi }}</div>
            </div>

            <div class="card blue">
                <div class="label">Average NDMI</div>
                <div class="value">{{ data.avg_ndmi }}</div>
            </div>

            <div class="card green">
                <div class="label">Low / Normal</div>
                <div class="value">{{ data.low }}</div>
            </div>
        </section>

        <section class="content-grid">
            <div class="panel">
                <div class="panel-title">Operational FRIS Map</div>

                <div class="map-box">
                    {% if map_exists %}
                    <iframe src="/map"></iframe>
                    {% else %}
                    <div style="padding:30px;color:#fecaca;">
                        Map file not found.<br><br>
                        Keep file here:<br>
                        <code>fris_showcase/data/fris_latest_map.html</code>
                    </div>
                    {% endif %}
                </div>
            </div>

            <div class="panel">
                <div class="panel-title">Top Priority Grid Intelligence</div>

                <table>
                    <thead>
                        <tr>
                            <th>Grid</th>
                            <th>Risk</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for g in data.top_grids %}
                        <tr>
                            <td><b>{{ g.grid }}</b></td>
                            <td><span class="risk-badge">{{ g.risk }}</span></td>
                            <td>{{ g.action }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </section>

        <div class="footer">
            FRIS Engine | Godda Forest Division | Satellite + Field Intelligence Dashboard
        </div>

    </main>
</div>
</body>
</html>
""", data=data, map_exists=os.path.exists(MAP_FILE))


@app.route("/map")
def serve_map():
    return send_from_directory(DATA_DIR, "fris_latest_map.html")


@app.route("/api/data")
def api_data():
    return jsonify(get_dashboard_data())


@app.route("/api/geojson")
def api_geojson():
    if os.path.exists(GEOJSON_FILE):
        with open(GEOJSON_FILE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({"error": "GeoJSON not found"}), 404


if __name__ == "__main__":
    app.run(debug=True)