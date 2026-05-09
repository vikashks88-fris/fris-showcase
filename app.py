from pathlib import Path
import pandas as pd
from flask import Flask, render_template_string, send_file, abort

app = Flask(__name__)

# =========================================================
# FRIS CARBON MRV DASHBOARD CONFIG
# =========================================================

FRIS_OUTPUT_DIR = Path(".")

CSV_PATH = FRIS_OUTPUT_DIR / "fris_latest.csv"
MAP_PATH = FRIS_OUTPUT_DIR / "fris_latest_map.html"
GEOJSON_PATH = FRIS_OUTPUT_DIR / "fris_latest.geojson"


# =========================================================
# HELPERS
# =========================================================

def safe_sum(df, col):
    if col not in df.columns:
        return 0
    return pd.to_numeric(df[col], errors="coerce").fillna(0).sum()


def safe_count(df, col, value):
    if col not in df.columns:
        return 0
    return int((df[col].astype(str) == value).sum())


def read_fris_csv():
    if not CSV_PATH.exists():
        return None

    df = pd.read_csv(CSV_PATH)

    numeric_cols = [
        "area_ha",
        "ecosystem_carbon_total_ton",
        "ecosystem_carbon_co2e_total",
        "biomass_carbon_total_ton",
        "potential_carbon_credits",
        "carbon_change_co2e_ton",
        "final_risk_score",
        "forest_pct",
        "ndvi",
        "ndmi",
        "agb_carbon_total_ton",
        "bgb_carbon_total_ton",
        "deadwood_carbon_total_ton",
        "litter_carbon_total_ton",
        "soil_carbon_total_ton",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def fmt_num(value):
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return "0.00"


# =========================================================
# ROUTES
# =========================================================

@app.route("/")
def dashboard():
    df = read_fris_csv()

    if df is None or df.empty:
        return render_template_string("""
        <h2>FRIS Carbon MRV Dashboard</h2>
        <p>No FRIS CSV found.</p>
        <p>Expected file:</p>
        <pre>{{ path }}</pre>
        """, path=str(CSV_PATH))

    total_area = safe_sum(df, "area_ha")
    ecosystem_carbon = safe_sum(df, "ecosystem_carbon_total_ton")
    ecosystem_co2e = safe_sum(df, "ecosystem_carbon_co2e_total")
    biomass_carbon = safe_sum(df, "biomass_carbon_total_ton")
    potential_credits = safe_sum(df, "potential_carbon_credits")
    carbon_change = safe_sum(df, "carbon_change_co2e_ton")

    high_mrv = safe_count(df, "mrv_confidence", "HIGH_MRV_CONFIDENCE")
    medium_mrv = safe_count(df, "mrv_confidence", "MEDIUM_MRV_CONFIDENCE")
    low_mrv = safe_count(df, "mrv_confidence", "LOW_MRV_CONFIDENCE")

    fire_grids = 0
    if "fire_detected" in df.columns:
        fire_grids = int(df["fire_detected"].astype(str).str.lower().isin(["true", "1"]).sum())

    priority_counts = {}
    if "final_priority" in df.columns:
        priority_counts = df["final_priority"].astype(str).value_counts().to_dict()

    carbon_pools = {
        "AGB Carbon": safe_sum(df, "agb_carbon_total_ton"),
        "BGB Carbon": safe_sum(df, "bgb_carbon_total_ton"),
        "Deadwood Carbon": safe_sum(df, "deadwood_carbon_total_ton"),
        "Litter Carbon": safe_sum(df, "litter_carbon_total_ton"),
        "Soil Carbon": safe_sum(df, "soil_carbon_total_ton"),
    }

    top_cols = [
        "grid_id",
        "final_priority",
        "final_risk_score",
        "forest_pct",
        "ndvi",
        "ndmi",
        "carbon_change_co2e_ton",
        "potential_carbon_credits",
        "mrv_confidence",
        "carbon_credit_claim_status",
        "patrol_action",
        "google_maps_link",
    ]

    available_cols = [c for c in top_cols if c in df.columns]

    if "final_risk_score" in df.columns:
        top_df = df.sort_values("final_risk_score", ascending=False).head(25)
    else:
        top_df = df.head(25)

    top_rows = top_df[available_cols].to_dict(orient="records")

    latest_time = ""
    if "system_run_timestamp_local" in df.columns:
        latest_time = str(df["system_run_timestamp_local"].iloc[0])

    return render_template_string(TEMPLATE,
        total_area=fmt_num(total_area),
        ecosystem_carbon=fmt_num(ecosystem_carbon),
        ecosystem_co2e=fmt_num(ecosystem_co2e),
        biomass_carbon=fmt_num(biomass_carbon),
        potential_credits=fmt_num(potential_credits),
        carbon_change=fmt_num(carbon_change),
        high_mrv=high_mrv,
        medium_mrv=medium_mrv,
        low_mrv=low_mrv,
        fire_grids=fire_grids,
        priority_counts=priority_counts,
        carbon_pools=carbon_pools,
        top_rows=top_rows,
        latest_time=latest_time,
        map_exists=MAP_PATH.exists(),
        csv_path=str(CSV_PATH),
        map_path=str(MAP_PATH),
    )


@app.route("/map")
def show_map():
    if not MAP_PATH.exists():
        abort(404)
    return send_file(MAP_PATH)


@app.route("/download-csv")
def download_csv():
    if not CSV_PATH.exists():
        abort(404)
    return send_file(CSV_PATH, as_attachment=True)


@app.route("/download-geojson")
def download_geojson():
    if not GEOJSON_PATH.exists():
        abort(404)
    return send_file(GEOJSON_PATH, as_attachment=True)


# =========================================================
# HTML TEMPLATE
# =========================================================

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>FRIS Carbon MRV Dashboard</title>
    <style>
        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #f4f6f8;
            color: #1f2937;
        }

        header {
            background: #0f172a;
            color: white;
            padding: 24px 32px;
        }

        header h1 {
            margin: 0;
            font-size: 28px;
        }

        header p {
            margin: 8px 0 0;
            color: #cbd5e1;
        }

        .container {
            padding: 24px 32px;
        }

        .warning {
            background: #fff7ed;
            border-left: 6px solid #f97316;
            padding: 14px 18px;
            margin-bottom: 22px;
            font-weight: bold;
        }

        .cards {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 24px;
        }

        .card {
            background: white;
            padding: 18px;
            border-radius: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }

        .card h3 {
            margin: 0;
            font-size: 14px;
            color: #64748b;
        }

        .card .value {
            margin-top: 10px;
            font-size: 24px;
            font-weight: bold;
            color: #111827;
        }

        .section {
            background: white;
            padding: 20px;
            border-radius: 14px;
            margin-bottom: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }

        .section h2 {
            margin-top: 0;
            font-size: 21px;
        }

        .grid-two {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        th {
            background: #e5e7eb;
            text-align: left;
            padding: 9px;
        }

        td {
            border-bottom: 1px solid #e5e7eb;
            padding: 8px;
            vertical-align: top;
        }

        a {
            color: #2563eb;
            text-decoration: none;
            font-weight: bold;
        }

        .map-frame {
            width: 100%;
            height: 680px;
            border: 0;
            border-radius: 12px;
        }

        .pill {
            display: inline-block;
            padding: 5px 9px;
            border-radius: 999px;
            background: #e0f2fe;
            margin: 4px;
            font-size: 13px;
        }

        .footer {
            color: #64748b;
            font-size: 13px;
            padding-bottom: 30px;
        }
    </style>
</head>
<body>

<header>
    <h1>FRIS Carbon MRV Intelligence Dashboard</h1>
    <p>Forest Resilience Information System | Carbon MRV Support Layer</p>
    <p>Latest Run: {{ latest_time }}</p>
</header>

<div class="container">

    <div class="warning">
        Carbon values shown here are indicative MRV-support estimates only.
        They are not verified carbon credits and must not be treated as issued credits.
    </div>

    <div class="cards">
        <div class="card">
            <h3>Total Forest Area</h3>
            <div class="value">{{ total_area }} ha</div>
        </div>
        <div class="card">
            <h3>Ecosystem Carbon</h3>
            <div class="value">{{ ecosystem_carbon }} t C</div>
        </div>
        <div class="card">
            <h3>Ecosystem CO₂e</h3>
            <div class="value">{{ ecosystem_co2e }} t CO₂e</div>
        </div>
        <div class="card">
            <h3>Potential Credits</h3>
            <div class="value">{{ potential_credits }}</div>
        </div>
        <div class="card">
            <h3>Biomass Carbon</h3>
            <div class="value">{{ biomass_carbon }} t C</div>
        </div>
        <div class="card">
            <h3>Carbon Change</h3>
            <div class="value">{{ carbon_change }} t CO₂e</div>
        </div>
        <div class="card">
            <h3>High MRV Confidence Grids</h3>
            <div class="value">{{ high_mrv }}</div>
        </div>
        <div class="card">
            <h3>Fire Alert Grids</h3>
            <div class="value">{{ fire_grids }}</div>
        </div>
    </div>

    <div class="grid-two">
        <div class="section">
            <h2>MRV Confidence Summary</h2>
            <p><span class="pill">High: {{ high_mrv }}</span></p>
            <p><span class="pill">Medium: {{ medium_mrv }}</span></p>
            <p><span class="pill">Low: {{ low_mrv }}</span></p>
        </div>

        <div class="section">
            <h2>Priority Summary</h2>
            {% for key, value in priority_counts.items() %}
                <span class="pill">{{ key }}: {{ value }}</span>
            {% endfor %}
        </div>
    </div>

    <div class="section">
        <h2>Carbon Pool Breakdown</h2>
        <table>
            <tr>
                <th>Carbon Pool</th>
                <th>Total Carbon</th>
            </tr>
            {% for name, value in carbon_pools.items() %}
            <tr>
                <td>{{ name }}</td>
                <td>{{ "{:,.2f}".format(value) }} tons C</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="section">
        <h2>Top Carbon + Risk Priority Grids</h2>
        <table>
            <tr>
                <th>Grid</th>
                <th>Priority</th>
                <th>Risk</th>
                <th>Forest %</th>
                <th>NDVI</th>
                <th>NDMI</th>
                <th>Carbon Change CO₂e</th>
                <th>Potential Credits</th>
                <th>MRV Confidence</th>
                <th>Credit Status</th>
                <th>Action</th>
                <th>Map</th>
            </tr>

            {% for r in top_rows %}
            <tr>
                <td>{{ r.get("grid_id", "") }}</td>
                <td>{{ r.get("final_priority", "") }}</td>
                <td>{{ r.get("final_risk_score", "") }}</td>
                <td>{{ r.get("forest_pct", "") }}</td>
                <td>{{ r.get("ndvi", "") }}</td>
                <td>{{ r.get("ndmi", "") }}</td>
                <td>{{ r.get("carbon_change_co2e_ton", "") }}</td>
                <td>{{ r.get("potential_carbon_credits", "") }}</td>
                <td>{{ r.get("mrv_confidence", "") }}</td>
                <td>{{ r.get("carbon_credit_claim_status", "") }}</td>
                <td>{{ r.get("patrol_action", "") }}</td>
                <td>
                    {% if r.get("google_maps_link") %}
                    <a href="{{ r.get('google_maps_link') }}" target="_blank">Open</a>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="section">
        <h2>Interactive FRIS Carbon MRV Map</h2>
        {% if map_exists %}
            <iframe class="map-frame" src="/map"></iframe>
        {% else %}
            <p>Map file not found: {{ map_path }}</p>
        {% endif %}
    </div>

    <div class="section">
        <h2>Downloads</h2>
        <p><a href="/download-csv">Download Latest CSV</a></p>
        <p><a href="/download-geojson">Download Latest GeoJSON</a></p>
    </div>

    <div class="footer">
        Source CSV: {{ csv_path }}<br>
        Source Map: {{ map_path }}
    </div>

</div>

</body>
</html>
"""


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)