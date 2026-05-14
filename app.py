from flask import Flask, Response, send_from_directory, jsonify
import os
import html
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CSV_FILE = os.path.join(DATA_DIR, "fris_latest.csv")
MAP_FILE = os.path.join(DATA_DIR, "fris_latest_map.html")
GEOJSON_FILE = os.path.join(DATA_DIR, "fris_latest.geojson")

IST = ZoneInfo("Asia/Kolkata")


# =============================
# TIME
# =============================

def ist_now():
    return datetime.now(IST)


def format_ist(dt):
    return dt.strftime("%d %B %Y, %I:%M:%S %p IST")


def get_file_update_time(file_path):
    if not os.path.exists(file_path):
        return "File not found"
    ts = os.path.getmtime(file_path)
    return format_ist(datetime.fromtimestamp(ts, IST))


def get_file_age_minutes(file_path):
    if not os.path.exists(file_path):
        return "N/A"

    modified = datetime.fromtimestamp(os.path.getmtime(file_path), IST)
    diff = ist_now() - modified
    minutes = int(diff.total_seconds() // 60)

    if minutes < 1:
        return "Updated just now"
    if minutes == 1:
        return "Updated 1 minute ago"
    return f"Updated {minutes} minutes ago"


def next_expected_run():
    now = ist_now()

    morning = now.replace(hour=9, minute=30, second=0, microsecond=0)
    evening = now.replace(hour=19, minute=30, second=0, microsecond=0)

    if now < morning:
        return format_ist(morning)

    if now < evening:
        return format_ist(evening)

    tomorrow = now + timedelta(days=1)
    return format_ist(tomorrow.replace(hour=9, minute=30, second=0, microsecond=0))


# =============================
# BASIC HELPERS
# =============================

def read_csv():
    if not os.path.exists(CSV_FILE):
        return None

    try:
        return pd.read_csv(CSV_FILE)
    except Exception:
        return None


def safe_float(value, default=None):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def safe_text(value, default="N/A"):
    try:
        if pd.isna(value):
            return default
        text = str(value).strip()
        return text if text else default
    except Exception:
        return default


def get_first_value(df, columns, default="N/A"):
    if df is None or df.empty:
        return default

    for col in columns:
        if col in df.columns:
            values = df[col].dropna()
            if len(values) > 0:
                return values.iloc[0]

    return default


def avg_col(df, col):
    if df is None or df.empty or col not in df.columns:
        return "N/A"

    value = pd.to_numeric(df[col], errors="coerce").mean()

    if pd.isna(value):
        return "N/A"

    return round(float(value), 3)


def sum_col(df, col):
    if df is None or df.empty or col not in df.columns:
        return "N/A"

    value = pd.to_numeric(df[col], errors="coerce").sum()

    if pd.isna(value):
        return "N/A"

    return value


def count_contains(df, columns, keyword):
    if df is None or df.empty:
        return 0

    total = 0

    for col in columns:
        if col in df.columns:
            total += df[col].astype(str).str.upper().str.contains(
                keyword.upper(),
                na=False
            ).sum()

    return int(total)


def format_number(value, decimals=1, suffix=""):
    try:
        value = float(value)
        return f"{value:,.{decimals}f}{suffix}"
    except Exception:
        return "N/A"


def format_carbon(value):
    try:
        value = float(value)
        return f"{value:,.0f} tons"
    except Exception:
        return "N/A"


# =============================
# WEATHER
# =============================

def get_csv_weather(df):
    temperature = get_first_value(df, ["temperature_c", "temperature", "temp_c"], None)
    rainfall_now = get_first_value(df, ["rainfall_current_mm", "rainfall", "rain_mm"], None)
    rainfall_24h = get_first_value(df, ["rainfall_24h_mm"], None)
    wind = get_first_value(df, ["wind_speed_kmph", "wind_kmph", "wind_speed"], None)
    gust = get_first_value(df, ["wind_gust_kmph"], None)
    spread = get_first_value(df, ["weather_fire_spread_class"], "N/A")
    note = get_first_value(df, ["weather_operational_note"], "N/A")
    provider = get_first_value(df, ["weather_provider"], "CSV Weather")
    weather_time = get_first_value(df, ["weather_time"], "N/A")

    if temperature is not None and rainfall_now is not None and wind is not None:
        return {
            "source": safe_text(provider),
            "status": "CSV Weather",
            "temperature": format_number(temperature, 1, "°C"),
            "rainfall": format_number(rainfall_now, 1, " mm"),
            "rainfall_24h": format_number(rainfall_24h, 1, " mm") if rainfall_24h is not None else "N/A",
            "wind": format_number(wind, 1, " km/h"),
            "gust": format_number(gust, 1, " km/h") if gust is not None else "N/A",
            "spread": safe_text(spread),
            "note": safe_text(note),
            "weather_time": safe_text(weather_time)
        }

    return None


def get_live_weather_api():
    lat = 24.83
    lon = 87.22

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}"
        f"&longitude={lon}"
        "&current=temperature_2m,precipitation,rain,wind_speed_10m,wind_gusts_10m"
        "&timezone=Asia%2FKolkata"
        "&temperature_unit=celsius"
        "&wind_speed_unit=kmh"
        "&precipitation_unit=mm"
    )

    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        current = data.get("current", {})

        temp = current.get("temperature_2m")
        rain = current.get("rain", current.get("precipitation"))
        wind = current.get("wind_speed_10m")
        gust = current.get("wind_gusts_10m")
        weather_time = current.get("time", "N/A")

        return {
            "source": "Open-Meteo Live API",
            "status": "Live API",
            "temperature": format_number(temp, 1, "°C"),
            "rainfall": format_number(rain, 1, " mm"),
            "rainfall_24h": "N/A",
            "wind": format_number(wind, 1, " km/h"),
            "gust": format_number(gust, 1, " km/h"),
            "spread": "Live weather only",
            "note": "Weather fetched from API. FRIS grid values still come from CSV.",
            "weather_time": safe_text(weather_time)
        }

    except Exception:
        return {
            "source": "Weather unavailable",
            "status": "API Error",
            "temperature": "N/A",
            "rainfall": "N/A",
            "rainfall_24h": "N/A",
            "wind": "N/A",
            "gust": "N/A",
            "spread": "N/A",
            "note": "Weather API could not be reached.",
            "weather_time": "N/A"
        }


def get_weather(df):
    csv_weather = get_csv_weather(df)

    if csv_weather:
        return csv_weather

    return get_live_weather_api()


# =============================
# WHY GO THERE LOGIC
# =============================

def make_why_go(row):
    reasons = []

    grid_id = safe_text(row.get("grid_id"), "Grid")
    fire_detected = safe_text(row.get("fire_detected"), "").upper()
    fire_count = safe_float(row.get("fire_count"), 0) or 0
    final_priority = safe_text(row.get("final_priority"), "").upper()
    ndvi = safe_float(row.get("ndvi"))
    ndmi = safe_float(row.get("ndmi"))
    mining_risk = safe_float(row.get("mining_risk"), 0) or 0
    carbon_change = safe_float(row.get("carbon_change_ton"), 0) or 0
    weather_spread = safe_text(row.get("weather_fire_spread_class"), "").upper()
    field_inference = safe_text(row.get("field_inference"), "")
    memory_inference = safe_text(row.get("ecological_memory_inference"), "")

    if fire_detected in ["TRUE", "YES", "ACTIVE", "1"] or fire_count > 0:
        reasons.append("active fire or thermal signal needs immediate verification")

    if "CRITICAL" in final_priority:
        reasons.append("grid is marked CRITICAL priority")
    elif "HIGH" in final_priority:
        reasons.append("grid is marked HIGH priority")

    if ndmi is not None:
        if ndmi < 0.05:
            reasons.append("low NDMI shows dry vegetation and moisture stress")
        elif ndmi < 0.15:
            reasons.append("NDMI indicates early drying stage")

    if ndvi is not None:
        if ndvi < 0.20:
            reasons.append("low NDVI indicates severe vegetation stress")
        elif ndvi < 0.35:
            reasons.append("NDVI indicates moderate vegetation stress")

    if mining_risk >= 60:
        reasons.append("mining pressure or nearby disturbance risk is high")
    elif mining_risk >= 35:
        reasons.append("mining influence may require field observation")

    if carbon_change < 0:
        reasons.append("carbon change is negative, possible biomass decline")

    if "HIGH" in weather_spread or "CRITICAL" in weather_spread:
        reasons.append("weather condition supports fire spread watch")

    if field_inference and field_inference.upper() not in ["N/A", "NONE"]:
        reasons.append(field_inference)

    if memory_inference and memory_inference.upper() not in ["N/A", "NONE"]:
        reasons.append(memory_inference)

    if not reasons:
        return f"{grid_id}: routine patrol only; no strong stress signal found."

    clean = []

    for r in reasons:
        if r not in clean:
            clean.append(r)

    return f"{grid_id}: " + "; ".join(clean[:4]) + "."


def make_action(row):
    fire_detected = safe_text(row.get("fire_detected"), "").upper()
    fire_count = safe_float(row.get("fire_count"), 0) or 0
    final_priority = safe_text(row.get("final_priority"), "").upper()
    ndmi = safe_float(row.get("ndmi"))
    ndvi = safe_float(row.get("ndvi"))
    patrol_action = safe_text(row.get("patrol_action"), "")

    if patrol_action and patrol_action.upper() not in ["N/A", "NONE"]:
        return patrol_action

    if fire_detected in ["TRUE", "YES", "ACTIVE", "1"] or fire_count > 0:
        return "Immediate field verification"

    if "CRITICAL" in final_priority:
        return "Same-day patrol required"

    if "HIGH" in final_priority:
        return "Patrol within 24 hours"

    if ndmi is not None and ndvi is not None and ndmi < 0.10 and ndvi < 0.35:
        return "Moisture and vegetation stress check"

    if ndmi is not None and ndmi < 0.10:
        return "Monitor drying forest sector"

    return "Routine patrol"


def priority_rank(row):
    priority = safe_text(row.get("final_priority"), "").upper()
    fire_count = safe_float(row.get("fire_count"), 0) or 0
    fire_detected = safe_text(row.get("fire_detected"), "").upper()
    score = safe_float(row.get("final_risk_score"), 0) or 0

    rank = 0

    if "CRITICAL" in priority:
        rank += 5000
    elif "HIGH" in priority:
        rank += 3000
    elif "MEDIUM" in priority or "MODERATE" in priority:
        rank += 1000

    if fire_detected in ["TRUE", "YES", "ACTIVE", "1"] or fire_count > 0:
        rank += 2000

    rank += score

    return rank


def build_priority_table(df, limit=15):
    if df is None or df.empty:
        return "<div class='empty'>CSV not loaded.</div>"

    work = df.copy()
    work["_rank"] = work.apply(priority_rank, axis=1)
    work = work.sort_values("_rank", ascending=False).head(limit)

    rows = ""

    for _, row in work.iterrows():
        grid_id = safe_text(row.get("grid_id"))
        priority = safe_text(row.get("final_priority"))
        ndvi = safe_float(row.get("ndvi"))
        ndmi = safe_float(row.get("ndmi"))
        fire_count = safe_float(row.get("fire_count"), 0) or 0
        risk_score = safe_float(row.get("final_risk_score"), 0)
        maps = safe_text(row.get("google_maps_link"), "#")

        why = make_why_go(row)
        action = make_action(row)

        ndvi_text = "N/A" if ndvi is None else f"{ndvi:.3f}"
        ndmi_text = "N/A" if ndmi is None else f"{ndmi:.3f}"
        risk_text = "N/A" if risk_score is None else f"{risk_score:.1f}"

        maps_link = maps if maps.startswith("http") else "#"

        rows += f"""
        <tr>
            <td><b>{html.escape(grid_id)}</b></td>
            <td>{html.escape(priority)}</td>
            <td>{ndvi_text}</td>
            <td>{ndmi_text}</td>
            <td>{int(fire_count)}</td>
            <td>{risk_text}</td>
            <td>{html.escape(why)}</td>
            <td>{html.escape(action)}</td>
            <td><a href="{html.escape(maps_link)}" target="_blank">Open</a></td>
        </tr>
        """

    return f"""
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Grid</th>
                    <th>Priority</th>
                    <th>NDVI</th>
                    <th>NDMI</th>
                    <th>Fire</th>
                    <th>Risk</th>
                    <th>Why go there?</th>
                    <th>Action</th>
                    <th>Map</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
    """


# =============================
# DASHBOARD
# =============================

@app.route("/")
def dashboard():
    df = read_csv()

    current_time = format_ist(ist_now())
    last_csv_update = get_file_update_time(CSV_FILE)
    csv_age = get_file_age_minutes(CSV_FILE)
    next_run = next_expected_run()

    csv_found = os.path.exists(CSV_FILE)
    map_found = os.path.exists(MAP_FILE)
    geojson_found = os.path.exists(GEOJSON_FILE)

    total_grids = len(df) if df is not None else 0

    high_risk = count_contains(df, ["final_priority", "risk_class", "priority"], "HIGH")
    critical_risk = count_contains(df, ["final_priority", "risk_class", "priority"], "CRITICAL")

    active_fire = (
        count_contains(df, ["fire_detected", "active_fire", "fire_status"], "TRUE")
        + count_contains(df, ["fire_detected", "active_fire", "fire_status"], "YES")
        + count_contains(df, ["fire_detected", "active_fire", "fire_status"], "ACTIVE")
    )

    avg_ndvi = avg_col(df, "ndvi")
    avg_ndmi = avg_col(df, "ndmi")

    total_carbon = sum_col(df, "ecosystem_carbon_total_ton")
    total_carbon_text = format_carbon(total_carbon)

    carbon_change = sum_col(df, "carbon_change_ton")
    carbon_change_text = format_carbon(carbon_change)

    forest_area = sum_col(df, "area_ha")
    forest_area_text = format_number(forest_area, 1, " ha")

    weather = get_weather(df)

    priority_table = build_priority_table(df, limit=15)

    map_version = int(datetime.now().timestamp())

    iframe_html = ""

    if map_found:
        iframe_html = f"""
        <iframe
            id="fris-map-frame"
            src="/map?v={map_version}"
            loading="eager"
            allowfullscreen
            referrerpolicy="no-referrer">
        </iframe>
        """
    else:
        iframe_html = """
        <div style="padding:40px;color:#ff6b6b;font-weight:bold;">
            Map file missing. Keep fris_latest_map.html inside data folder.
        </div>
        """

    html_page = f"""
<!DOCTYPE html>
<html>
<head>
    <title>FRIS Godda Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <style>
        * {{
            box-sizing: border-box;
            font-family: Arial, sans-serif;
        }}

        body {{
            margin: 0;
            background: #061307;
            color: white;
        }}

        .layout {{
            display: flex;
            min-height: 100vh;
        }}

        .sidebar {{
            width: 270px;
            padding: 25px;
            background: linear-gradient(180deg, #173f18, #071507);
            border-right: 1px solid rgba(255,255,255,0.15);
        }}

        .logo h1 {{
            color: #dfff00;
            font-size: 38px;
            margin: 0;
        }}

        .logo p {{
            color: #c6ff6b;
            font-size: 13px;
            margin: 4px 0 30px;
        }}

        .nav {{
            padding: 15px;
            margin-bottom: 13px;
            border-radius: 15px;
            background: rgba(255,255,255,0.12);
            font-weight: bold;
        }}

        .nav.active {{
            background: #dfff00;
            color: #102000;
        }}

        .side-card {{
            margin-top: 25px;
            padding: 18px;
            border-radius: 18px;
            background: rgba(255,255,255,0.12);
            border: 1px solid rgba(255,255,255,0.18);
            font-size: 14px;
            line-height: 1.7;
        }}

        .ok {{
            color: #dfff00;
            font-weight: bold;
        }}

        .bad {{
            color: #ff6b6b;
            font-weight: bold;
        }}

        .main {{
            flex: 1;
            padding: 25px;
        }}

        .topbar {{
            display: grid;
            grid-template-columns: repeat(3, 1fr) auto;
            gap: 15px;
            align-items: center;
            padding: 18px;
            border-radius: 22px;
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.18);
            margin-bottom: 22px;
        }}

        .time-box {{
            font-size: 14px;
            line-height: 1.4;
        }}

        .time-box b {{
            display: block;
            color: white;
        }}

        .time-box span {{
            color: #dfff00;
            font-weight: bold;
        }}

        .btn {{
            display: inline-block;
            background: #dfff00;
            color: #102000;
            padding: 12px 16px;
            border-radius: 14px;
            text-decoration: none;
            font-weight: bold;
            margin: 4px;
        }}

        .content {{
            display: grid;
            grid-template-columns: 1fr 340px;
            gap: 22px;
        }}

        .map-card,
        .card,
        .table-card {{
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.18);
            border-radius: 24px;
            padding: 18px;
        }}

        iframe {{
            width: 100%;
            height: 650px;
            border: none;
            border-radius: 18px;
            background: #1b5525;
        }}

        .right {{
            display: flex;
            flex-direction: column;
            gap: 15px;
        }}

        .card h3,
        .map-card h2,
        .table-card h2 {{
            margin-top: 0;
        }}

        .row {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 9px 0;
            border-bottom: 1px solid rgba(255,255,255,0.12);
            font-size: 14px;
        }}

        .value {{
            color: #dfff00;
            font-weight: bold;
            text-align: right;
        }}

        .table-card {{
            margin-top: 22px;
        }}

        .table-wrap {{
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}

        th {{
            background: rgba(223,255,0,0.18);
            color: #dfff00;
            text-align: left;
            padding: 10px;
            white-space: nowrap;
        }}

        td {{
            padding: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.12);
            vertical-align: top;
        }}

        td a {{
            color: #dfff00;
            font-weight: bold;
        }}

        .footer {{
            margin-top: 18px;
            font-size: 13px;
            color: #c5d6c5;
        }}

        @media(max-width: 1000px) {{
            .layout {{
                flex-direction: column;
            }}

            .sidebar {{
                width: 100%;
            }}

            .topbar {{
                grid-template-columns: 1fr;
            }}

            .content {{
                grid-template-columns: 1fr;
            }}

            iframe {{
                height: 520px;
            }}
        }}
    </style>
</head>

<body>
<div class="layout">

    <div class="sidebar">
        <div class="logo">
            <h1>FRIS</h1>
            <p>Forest Resilience Information System</p>
        </div>

        <div class="nav active">🏠 Dashboard</div>
        <div class="nav">🗺️ Risk Map</div>
        <div class="nav">🔥 Fire Intelligence</div>
        <div class="nav">💧 Moisture Stress</div>
        <div class="nav">🌦️ Weather</div>
        <div class="nav">🌿 Carbon MRV</div>

        <div class="side-card">
            <b>Godda Forest Division</b><br><br>

            CSV:
            <span class="{'ok' if csv_found else 'bad'}">{'Found' if csv_found else 'Missing'}</span><br>

            Map:
            <span class="{'ok' if map_found else 'bad'}">{'Found' if map_found else 'Missing'}</span><br>

            GeoJSON:
            <span class="{'ok' if geojson_found else 'bad'}">{'Found' if geojson_found else 'Missing'}</span><br><br>

            <b>Analysed Area:</b><br>
            {forest_area_text}
        </div>
    </div>

    <div class="main">

        <div class="topbar">
            <div class="time-box">
                <b>Current Dashboard Time</b>
                <span>{current_time}</span>
            </div>

            <div class="time-box">
                <b>Last FRIS Data Update</b>
                <span>{last_csv_update}</span><br>
                <small>{csv_age}</small>
            </div>

            <div class="time-box">
                <b>Next Expected Run</b>
                <span>{next_run}</span>
            </div>

            <div>
                <a class="btn" href="/">Refresh</a>
                <a class="btn" href="/map" target="_blank">Open Map</a>
                <a class="btn" href="/debug" target="_blank">Debug</a>
            </div>
        </div>

        <div class="content">

            <div class="map-card">
                <h2>FRIS Risk Map</h2>
                {iframe_html}
            </div>

            <div class="right">

                <div class="card">
                    <h3>📊 Operational Summary</h3>
                    <div class="row"><span>Total Grids</span><span class="value">{total_grids}</span></div>
                    <div class="row"><span>High Risk</span><span class="value">{high_risk}</span></div>
                    <div class="row"><span>Critical Risk</span><span class="value">{critical_risk}</span></div>
                    <div class="row"><span>Active Fire</span><span class="value">{active_fire}</span></div>
                </div>

                <div class="card">
                    <h3>💧 Forest Condition</h3>
                    <div class="row"><span>Average NDVI</span><span class="value">{avg_ndvi}</span></div>
                    <div class="row"><span>Average NDMI</span><span class="value">{avg_ndmi}</span></div>
                </div>

                <div class="card">
                    <h3>🌦️ Weather</h3>
                    <div class="row"><span>Source</span><span class="value">{html.escape(weather['source'])}</span></div>
                    <div class="row"><span>Status</span><span class="value">{html.escape(weather['status'])}</span></div>
                    <div class="row"><span>Temperature</span><span class="value">{weather['temperature']}</span></div>
                    <div class="row"><span>Rainfall Now</span><span class="value">{weather['rainfall']}</span></div>
                    <div class="row"><span>Rainfall 24h</span><span class="value">{weather['rainfall_24h']}</span></div>
                    <div class="row"><span>Wind</span><span class="value">{weather['wind']}</span></div>
                    <div class="row"><span>Gust</span><span class="value">{weather['gust']}</span></div>
                    <div class="row"><span>Fire Spread</span><span class="value">{html.escape(weather['spread'])}</span></div>
                </div>

                <div class="card">
                    <h3>🌿 Carbon MRV</h3>
                    <div class="row"><span>Total Carbon</span><span class="value">{total_carbon_text}</span></div>
                    <div class="row"><span>Carbon Change</span><span class="value">{carbon_change_text}</span></div>
                    <div class="row"><span>Status</span><span class="value">Satellite Assisted</span></div>
                    <div class="row"><span>Claim Status</span><span class="value">Not Certified</span></div>
                </div>

            </div>
        </div>

        <div class="table-card">
            <h2>🧭 Priority Grid Intelligence — Why Go There?</h2>
            {priority_table}
        </div>

        <div class="footer">
            Dashboard no longer hard-refreshes every 30 seconds. Only the map iframe refreshes safely.
            Time is forced to Asia/Kolkata IST.
        </div>

    </div>

</div>

<script>
    setInterval(function() {{
        fetch("/health")
            .then(function(response) {{
                return response.json();
            }})
            .then(function(data) {{
                console.log("FRIS live check:", data);

                var iframe = document.getElementById("fris-map-frame");

                if (iframe && data.map_found === true) {{
                    iframe.src = "/map?v=" + Date.now();
                }}
            }})
            .catch(function(error) {{
                console.log("FRIS live check error:", error);
            }});
    }}, 30000);
</script>

</body>
</html>
"""

    return Response(html_page, mimetype="text/html")


# =============================
# MAP ROUTES
# =============================

@app.route("/map")
def serve_map():
    if not os.path.exists(MAP_FILE):
        return Response(
            "Map file not found in data folder.",
            mimetype="text/plain"
        )

    try:
        response = send_from_directory(DATA_DIR, "fris_latest_map.html")

        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return response

    except Exception as e:
        return Response(
            f"Map loading error: {str(e)}",
            mimetype="text/plain"
        )


@app.route("/data/<path:filename>")
def serve_data(filename):
    response = send_from_directory(DATA_DIR, filename)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/health")
def health():
    df = read_csv()

    return jsonify({
        "status": "running",
        "server_time_ist": format_ist(ist_now()),
        "csv_found": os.path.exists(CSV_FILE),
        "map_found": os.path.exists(MAP_FILE),
        "geojson_found": os.path.exists(GEOJSON_FILE),
        "csv_last_update": get_file_update_time(CSV_FILE),
        "csv_age": get_file_age_minutes(CSV_FILE),
        "next_expected_run": next_expected_run(),
        "total_grids": len(df) if df is not None else 0
    })


@app.route("/debug")
def debug():
    df = read_csv()
    weather = get_weather(df)

    return jsonify({
        "server_time_ist": format_ist(ist_now()),
        "csv_found": os.path.exists(CSV_FILE),
        "map_found": os.path.exists(MAP_FILE),
        "geojson_found": os.path.exists(GEOJSON_FILE),
        "csv_last_update": get_file_update_time(CSV_FILE),
        "csv_age": get_file_age_minutes(CSV_FILE),
        "next_expected_run": next_expected_run(),
        "total_grids": len(df) if df is not None else 0,
        "weather": weather,
        "base_dir": BASE_DIR,
        "data_dir": DATA_DIR,
        "csv_file": CSV_FILE,
        "map_file": MAP_FILE,
        "geojson_file": GEOJSON_FILE
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)