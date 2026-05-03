from flask import Flask, render_template_string, send_file, abort
from pathlib import Path
import pandas as pd

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "fris_latest.csv"
MAP_PATH = BASE_DIR / "fris_master_map_latest.html"


def load_data():
    if not CSV_PATH.exists():
        return pd.DataFrame()

    df = pd.read_csv(CSV_PATH)
    df = df.fillna("")
    return df


def get(row, *names):
    for name in names:
        if name in row and str(row[name]).strip() != "":
            return row[name]
    return ""


HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>FRIS Lite v2</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f4f7f3;
            text-align: center;
            padding: 60px;
        }
        .box {
            background: white;
            padding: 35px;
            border-radius: 20px;
            max-width: 600px;
            margin: auto;
            box-shadow: 0 4px 15px rgba(0,0,0,0.12);
        }
        h1 { color: #55765a; }
        a {
            display: block;
            margin: 18px;
            padding: 18px;
            color: white;
            text-decoration: none;
            border-radius: 10px;
            font-weight: bold;
        }
        .green { background: #2f6b2f; }
        .red { background: #c94b4b; }
        .blue { background: #3d5963; }
    </style>
</head>
<body>
<div class="box">
    <h1>FRIS Lite v2</h1>
    <p>Forest Resilience Information System</p>

    <a class="green" href="/priority">Today Action Priority</a>
    <a class="red" href="/top10">Top 10 Urgent Grids</a>
    <a class="blue" href="/download-csv">Download CSV</a>
    <a class="blue" href="/map">Open FRIS Map</a>
</div>
</body>
</html>
"""


LIST_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ title }}</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f4f7f3;
            padding: 30px;
        }
        h1 {
            text-align: center;
            color: #55765a;
        }
        .card {
            background: white;
            padding: 20px;
            margin: 18px auto;
            max-width: 800px;
            border-radius: 14px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.10);
        }
        .high { color: #c0392b; font-weight: bold; }
        .medium { color: #d68910; font-weight: bold; }
        .low { color: #2874a6; font-weight: bold; }
        a.btn {
            display: inline-block;
            background: #2f6b2f;
            color: white;
            padding: 10px 16px;
            margin-top: 10px;
            border-radius: 8px;
            text-decoration: none;
        }
        .home {
            text-align:center;
            margin-bottom:20px;
        }
    </style>
</head>
<body>

<div class="home">
    <a href="/">← Home</a>
</div>

<h1>{{ title }}</h1>

{% if rows|length == 0 %}
    <p style="text-align:center;">No CSV data found.</p>
{% endif %}

{% for item in rows %}
<div class="card">
    <b>Grid:</b> {{ item.grid_id }}<br>
    <b>Priority:</b>
    <span class="{{ item.priority_class }}">{{ item.priority }}</span><br>
    <b>Risk:</b> {{ item.risk }}<br>
    <b>Health:</b> {{ item.health }}<br>
    <b>Moisture:</b> {{ item.moisture }}<br>
    <b>Fire Count:</b> {{ item.fire_count }}<br>
    <b>FRP:</b> {{ item.frp }}<br>
    <a class="btn" href="/detail/{{ item.index }}">View Detail</a>
    {% if item.maps_link %}
        <a class="btn" href="{{ item.maps_link }}" target="_blank">Navigate</a>
    {% endif %}
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
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f4f7f3;
            padding: 40px;
        }
        .card {
            background: white;
            padding: 30px;
            max-width: 900px;
            margin: auto;
            border-radius: 16px;
            box-shadow: 0 3px 12px rgba(0,0,0,0.12);
        }
        h1 { color: #55765a; }
        a {
            display: block;
            text-align: center;
            margin-top: 18px;
            padding: 14px;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: bold;
        }
        .green { background: #2f6b2f; }
        .dark { background: #3d5963; }
    </style>
</head>
<body>

<div class="card">
    <h1>Grid Detail: {{ item.grid_id }}</h1>

    <p><b>Priority:</b> {{ item.priority }}</p>
    <p><b>Risk Class:</b> {{ item.risk }}</p>
    <p><b>Health Class:</b> {{ item.health }}</p>
    <p><b>Moisture Class:</b> {{ item.moisture }}</p>
    <p><b>Fire Count:</b> {{ item.fire_count }}</p>
    <p><b>FRP Sum:</b> {{ item.frp }}</p>
    <p><b>Latitude:</b> {{ item.lat }}</p>
    <p><b>Longitude:</b> {{ item.lon }}</p>
    <p><b>Recommended Action:</b> {{ item.action }}</p>

    {% if item.maps_link %}
        <a class="green" href="{{ item.maps_link }}" target="_blank">Open in Google Maps</a>
    {% endif %}

    <a class="dark" href="/priority">Back to Priority List</a>
</div>

</body>
</html>
"""


def prepare_rows(df):
    rows = []

    for index, row in df.iterrows():
        priority = get(row, "final_priority", "priority", "Priority", "risk_class", "Risk Class")

        priority_class = str(priority).lower()
        if "high" in priority_class or "critical" in priority_class:
            priority_class = "high"
        elif "medium" in priority_class or "moderate" in priority_class:
            priority_class = "medium"
        else:
            priority_class = "low"

        lat = get(row, "lat", "latitude", "Latitude", "grid_center_lat", "center_lat")
        lon = get(row, "lon", "longitude", "Longitude", "grid_center_lon", "center_lon")

        maps_link = get(
            row,
            "google_maps_link",
            "Google Maps Link",
            "maps_link",
            "navigation_link",
            "Navigation Link"
        )

        if not maps_link and lat != "" and lon != "":
            maps_link = f"https://www.google.com/maps?q={lat},{lon}"

        rows.append({
            "index": index,
            "grid_id": get(row, "grid_id", "Grid ID", "grid", "Grid"),
            "priority": priority,
            "priority_class": priority_class,
            "risk": get(row, "risk_class", "Risk Class", "final_risk_class", "risk"),
            "health": get(row, "health_class", "Health Class", "health_status"),
            "moisture": get(row, "moisture_class", "Moisture Class", "moisture_status"),
            "fire_count": get(row, "fire_count", "Fire Count", "fires", "active_fire_count"),
            "frp": get(row, "frp_sum", "FRP Sum", "fire_frp_sum", "FRP", "fire_frp"),
            "lat": lat,
            "lon": lon,
            "action": get(row, "recommended_action", "Recommended Action", "patrol_action", "action"),
            "maps_link": maps_link
        })

    return rows


@app.route("/")
def home():
    return render_template_string(HOME_HTML)


@app.route("/priority")
def priority():
    df = load_data()
    rows = prepare_rows(df)

    priority_order = {"high": 0, "medium": 1, "low": 2}
    rows = sorted(rows, key=lambda x: priority_order.get(x["priority_class"], 3))

    return render_template_string(
        LIST_HTML,
        title="Today Priority Grids",
        rows=rows
    )


@app.route("/top10")
def top10():
    df = load_data()
    rows = prepare_rows(df)

    priority_order = {"high": 0, "medium": 1, "low": 2}
    rows = sorted(rows, key=lambda x: priority_order.get(x["priority_class"], 3))[:10]

    return render_template_string(
        LIST_HTML,
        title="Top 10 Urgent Grids",
        rows=rows
    )


@app.route("/detail/<int:index>")
def detail(index):
    df = load_data()

    if df.empty or index < 0 or index >= len(df):
        abort(404)

    rows = prepare_rows(df)
    item = rows[index]

    return render_template_string(DETAIL_HTML, item=item)


@app.route("/download-csv")
def download_csv():
    if not CSV_PATH.exists():
        return "CSV file not found. Please upload fris_latest.csv to GitHub root folder.", 404

    return send_file(
        CSV_PATH,
        as_attachment=True,
        download_name="fris_latest.csv"
    )


@app.route("/map")
def open_map():
    if not MAP_PATH.exists():
        return "Map file not found. Please upload fris_master_map_latest.html to GitHub root folder.", 404

    return send_file(
        MAP_PATH,
        mimetype="text/html"
    )


if __name__ == "__main__":
    app.run(debug=True)