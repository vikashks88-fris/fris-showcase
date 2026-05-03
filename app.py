from flask import Flask, render_template_string, send_file
import pandas as pd
from pathlib import Path

app = Flask(__name__)

CSV_PATH = Path(r"C:\cfris_app\data\fris_latest.csv")
MAP_PATH = Path(r"C:\cfris\output\fris_master_map_latest.html")


def load_data():
    if not CSV_PATH.exists():
        return pd.DataFrame()

    df = pd.read_csv(CSV_PATH)
    df.columns = df.columns.str.strip().str.lower()

    new_df = pd.DataFrame()

    new_df["grid_id"] = df.get("grid_id", "")
    new_df["lat"] = df.get("lat", "")
    new_df["lon"] = df.get("lon", "")

    new_df["final_priority"] = df.get(
        "corrected_final_priority",
        df.get("final_priority", df.get("patrol_priority", ""))
    )

    new_df["risk_class"] = df.get(
        "corrected_fire_class",
        df.get("risk_class", df.get("fire_intensity_class", ""))
    )

    new_df["health_class"] = df.get(
        "corrected_health_class",
        df.get("health_class", "")
    )

    new_df["moisture_class"] = df.get(
        "corrected_moisture_class",
        df.get("moisture_class_calibrated", df.get("moisture_class", ""))
    )

    new_df["fire_count"] = pd.to_numeric(df.get("fire_count", 0), errors="coerce").fillna(0)

    new_df["frp_sum"] = pd.to_numeric(
        df.get("fire_frp_sum", df.get("frp_sum", 0)),
        errors="coerce"
    ).fillna(0)

    new_df["final_risk_score"] = pd.to_numeric(
        df.get("corrected_final_risk_score", df.get("final_risk_score", 0)),
        errors="coerce"
    ).fillna(0)

    new_df["mining_class"] = df.get(
        "corrected_mining_class",
        df.get("mining_pressure_class", "")
    )

    new_df["forest_pct"] = df.get("forest_pct", "")
    new_df["ndvi"] = df.get("ndvi", "")
    new_df["ndmi"] = df.get("ndmi", "")

    new_df["recommended_action"] = df.get(
        "corrected_patrol_action",
        df.get("recommended_action", df.get("patrol_action", ""))
    )

    new_df["google_maps_link"] = df.get("google_maps_link", "")

    missing_link = new_df["google_maps_link"].astype(str).str.strip().isin(["", "nan", "none"])

    new_df.loc[missing_link, "google_maps_link"] = (
        "https://www.google.com/maps?q="
        + new_df["lat"].astype(str)
        + ","
        + new_df["lon"].astype(str)
    )

    priority_order = {
        "CRITICAL": 1,
        "FIRE_CHECK": 2,
        "HIGH": 3,
        "MEDIUM": 4,
        "MODERATE": 4,
        "LOW": 5
    }

    new_df["priority_rank"] = (
        new_df["final_priority"]
        .astype(str)
        .str.upper()
        .map(priority_order)
        .fillna(9)
    )

    new_df = new_df.sort_values(
        by=["priority_rank", "final_risk_score", "fire_count", "frp_sum"],
        ascending=[True, False, False, False]
    )

    return new_df


HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>FRIS Lite v2</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: Arial; background:#f4f7f4; margin:0; padding:20px; }
.card { background:white; padding:25px; border-radius:18px; max-width:520px; margin:auto; text-align:center; box-shadow:0 4px 12px rgba(0,0,0,.12); }
h1 { color:#1b5e20; margin-bottom:4px; }
a { display:block; background:#1b5e20; color:white; padding:16px; margin:14px 0; border-radius:12px; text-decoration:none; font-size:18px; font-weight:bold; }
.secondary { background:#455a64; }
.red { background:#b71c1c; }
</style>
</head>
<body>
<div class="card">
<h1>FRIS Lite v2</h1>
<p>Forest Resilience Information System</p>

<a href="/priority">Today Action Priority</a>
<a class="red" href="/top10">Top 10 Urgent Grids</a>
<a class="secondary" href="/download">Download CSV</a>
<a class="secondary" href="/map">Open FRIS Map</a>
</div>
</body>
</html>
"""


PRIORITY_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>FRIS Priority</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family:Arial; background:#f4f7f4; padding:15px; }
h2 { color:#1b5e20; text-align:center; }
.summary { display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-bottom:14px; }
.box { background:white; border-radius:12px; padding:12px; text-align:center; box-shadow:0 2px 8px rgba(0,0,0,.12); }
.box b { font-size:22px; display:block; color:#1b5e20; }
.grid-card { background:white; padding:16px; margin:12px 0; border-radius:14px; box-shadow:0 3px 9px rgba(0,0,0,.12); }
.priority { font-size:18px; font-weight:bold; }
.critical,.fire_check,.high { color:#b71c1c; }
.medium,.moderate { color:#ef6c00; }
.low { color:#2e7d32; }
.button { display:inline-block; padding:10px 14px; background:#1b5e20; color:white; border-radius:10px; text-decoration:none; margin-top:8px; }
.nav { text-align:center; margin-bottom:12px; }
.nav a { color:#1b5e20; font-weight:bold; }
</style>
</head>
<body>

<div class="nav"><a href="/">← Home</a></div>
<h2>{{ title }}</h2>

<div class="summary">
  <div class="box">Critical<b>{{ total_critical }}</b></div>
  <div class="box">High<b>{{ total_high }}</b></div>
  <div class="box">Fire<b>{{ total_fire }}</b></div>
</div>

{% if rows|length == 0 %}
<p>No priority CSV data found. Check C:\\cfris_app\\data\\fris_latest.csv</p>
{% endif %}

{% for row in rows %}
<div class="grid-card">
  <div><b>Grid:</b> {{ row.grid_id }}</div>
  <div class="priority {{ row.final_priority|lower }}">Priority: {{ row.final_priority }}</div>
  <div><b>Risk Score:</b> {{ row.final_risk_score }}</div>
  <div><b>Risk:</b> {{ row.risk_class }}</div>
  <div><b>Health:</b> {{ row.health_class }}</div>
  <div><b>Moisture:</b> {{ row.moisture_class }}</div>
  <div><b>Fire Count:</b> {{ row.fire_count }}</div>
  <div><b>FRP:</b> {{ row.frp_sum }}</div>
  <div><b>Action:</b> {{ row.recommended_action }}</div>

  <a class="button" href="/detail/{{ row.app_index }}">View Detail</a>
  <a class="button" href="{{ row.google_maps_link }}" target="_blank">Navigate</a>
</div>
{% endfor %}

</body>
</html>
"""


DETAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Grid Detail</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family:Arial; background:#f4f7f4; padding:15px; }
.card { background:white; padding:20px; border-radius:16px; box-shadow:0 3px 9px rgba(0,0,0,.12); }
h2 { color:#1b5e20; }
.item { margin:10px 0; font-size:17px; }
a { display:block; background:#1b5e20; color:white; padding:14px; margin-top:12px; border-radius:10px; text-decoration:none; text-align:center; font-weight:bold; }
.back { background:#455a64; }
</style>
</head>
<body>
<div class="card">
<h2>Grid Detail: {{ row.grid_id }}</h2>

<div class="item"><b>Priority:</b> {{ row.final_priority }}</div>
<div class="item"><b>Final Risk Score:</b> {{ row.final_risk_score }}</div>
<div class="item"><b>Risk Class:</b> {{ row.risk_class }}</div>
<div class="item"><b>Health Class:</b> {{ row.health_class }}</div>
<div class="item"><b>Moisture Class:</b> {{ row.moisture_class }}</div>
<div class="item"><b>Fire Count:</b> {{ row.fire_count }}</div>
<div class="item"><b>FRP Sum:</b> {{ row.frp_sum }}</div>
<div class="item"><b>Mining Class:</b> {{ row.mining_class }}</div>
<div class="item"><b>Forest %:</b> {{ row.forest_pct }}</div>
<div class="item"><b>NDVI:</b> {{ row.ndvi }}</div>
<div class="item"><b>NDMI:</b> {{ row.ndmi }}</div>
<div class="item"><b>Latitude:</b> {{ row.lat }}</div>
<div class="item"><b>Longitude:</b> {{ row.lon }}</div>
<div class="item"><b>Recommended Action:</b> {{ row.recommended_action }}</div>

<a href="{{ row.google_maps_link }}" target="_blank">Open in Google Maps</a>
<a class="back" href="/priority">Back to Priority List</a>
</div>
</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(HOME_HTML)


@app.route("/priority")
def priority():
    df = load_data()

    if df.empty:
        rows = []
        total_critical = total_high = total_fire = 0
    else:
        total_critical = (df["final_priority"].astype(str).str.upper() == "CRITICAL").sum()
        total_high = (df["final_priority"].astype(str).str.upper() == "HIGH").sum()
        total_fire = (df["fire_count"] > 0).sum()

        important = ["CRITICAL", "FIRE_CHECK", "HIGH", "MEDIUM", "MODERATE"]
        df = df[df["final_priority"].astype(str).str.upper().isin(important)].copy()
        df["app_index"] = df.index
        rows = df.to_dict(orient="records")

    return render_template_string(
        PRIORITY_HTML,
        rows=rows,
        title="Today's Action Priority",
        total_critical=total_critical,
        total_high=total_high,
        total_fire=total_fire
    )


@app.route("/top10")
def top10():
    df = load_data()

    if df.empty:
        rows = []
        total_critical = total_high = total_fire = 0
    else:
        total_critical = (df["final_priority"].astype(str).str.upper() == "CRITICAL").sum()
        total_high = (df["final_priority"].astype(str).str.upper() == "HIGH").sum()
        total_fire = (df["fire_count"] > 0).sum()

        df = df.head(10).copy()
        df["app_index"] = df.index
        rows = df.to_dict(orient="records")

    return render_template_string(
        PRIORITY_HTML,
        rows=rows,
        title="Top 10 Urgent Grids",
        total_critical=total_critical,
        total_high=total_high,
        total_fire=total_fire
    )


@app.route("/detail/<int:index>")
def detail(index):
    df = load_data()

    if df.empty or index not in df.index:
        return "Grid not found", 404

    row = df.loc[index].to_dict()
    return render_template_string(DETAIL_HTML, row=row)


@app.route("/download")
def download():
    if not CSV_PATH.exists():
        return "CSV file not found", 404

    return send_file(CSV_PATH, as_attachment=True)


@app.route("/map")
def open_map():
    if not MAP_PATH.exists():
        return "Latest map not found. Create fris_master_map_latest.html inside C:\\cfris\\output", 404

    return send_file(MAP_PATH)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)