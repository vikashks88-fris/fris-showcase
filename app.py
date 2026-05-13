import json
import time
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


# ============================================================
# GODDA FRIS DASHBOARD - UPGRADED VERSION
# Auto-refresh + Better Risk Colors + Google Maps Navigation
# ============================================================

st.set_page_config(
    page_title="Godda FRIS Dashboard",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# AUTO REFRESH
# ============================================================

AUTO_REFRESH_SECONDS = 60

st.markdown(
    f"""
    <meta http-equiv="refresh" content="{AUTO_REFRESH_SECONDS}">
    """,
    unsafe_allow_html=True,
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

CSV_PATH = DATA_DIR / "fris_latest.csv"
GEOJSON_PATH = DATA_DIR / "fris_latest.geojson"
MAP_HTML_PATH = DATA_DIR / "fris_latest_map.html"


# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
    <style>
    .main {
        background-color: #f6faf7;
    }

    h1, h2, h3 {
        color: #24382f;
        font-weight: 700;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    .success-box {
        background-color: #e8f7ee;
        color: #1f5f36;
        padding: 14px 18px;
        border-radius: 12px;
        border-left: 6px solid #2e7d32;
        margin-bottom: 18px;
        font-weight: 500;
    }

    .info-box {
        background-color: #eef6ff;
        color: #1d4f73;
        padding: 14px 18px;
        border-radius: 12px;
        border-left: 6px solid #2563eb;
        margin-bottom: 18px;
        font-weight: 500;
    }

    .warning-box {
        background-color: #fff7e6;
        color: #7a4d00;
        padding: 14px 18px;
        border-radius: 12px;
        border-left: 6px solid #f59e0b;
        margin-bottom: 18px;
        font-weight: 500;
    }

    .metric-card {
        background: white;
        padding: 16px;
        border-radius: 14px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    }

    .small-note {
        font-size: 13px;
        color: #6b7280;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🌳 Godda FRIS")
st.sidebar.caption("Forest Resilience Information System")
st.sidebar.divider()

st.sidebar.markdown("### Data folder")
st.sidebar.code(str(DATA_DIR))

st.sidebar.markdown("### Required files")


def sidebar_file_check(path: Path, name: str):
    if path.exists():
        st.sidebar.success(f"✅ {name}")
    else:
        st.sidebar.error(f"❌ {name}")


sidebar_file_check(CSV_PATH, "fris_latest.csv")
sidebar_file_check(GEOJSON_PATH, "fris_latest.geojson")
sidebar_file_check(MAP_HTML_PATH, "fris_latest_map.html")

st.sidebar.divider()
st.sidebar.markdown("### Refresh")
st.sidebar.write(f"Auto-refresh: every {AUTO_REFRESH_SECONDS} seconds")

if st.sidebar.button("🔄 Refresh now"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(f"Last page load: {time.strftime('%Y-%m-%d %H:%M:%S')}")


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data(ttl=60)
def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


if not CSV_PATH.exists():
    st.title("🌳 Godda FRIS Dashboard")
    st.error("No FRIS CSV found.")
    st.markdown(
        """
        Correct GitHub structure:

        ```text
        fris-showcase/
        ├── app.py
        ├── requirements.txt
        └── data/
            ├── fris_latest.csv
            ├── fris_latest.geojson
            └── fris_latest_map.html
        ```
        """
    )
    st.stop()


try:
    df = load_csv(CSV_PATH)
except Exception as e:
    st.error(f"CSV loading failed: {e}")
    st.stop()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def find_col(possible_names):
    for name in possible_names:
        if name in df.columns:
            return name
    return None


def safe_numeric(col):
    if col and col in df.columns:
        return pd.to_numeric(df[col], errors="coerce")
    return pd.Series(dtype="float64")


def safe_count(col, keywords):
    if not col or col not in df.columns:
        return 0

    text = df[col].astype(str).str.upper()
    total = 0

    for keyword in keywords:
        total += text.str.contains(keyword.upper(), na=False).sum()

    return int(total)


def existing_cols(cols):
    final_cols = []
    for col in cols:
        if col and col in df.columns and col not in final_cols:
            final_cols.append(col)
    return final_cols


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value)


def make_navigation_link(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
        return f"https://www.google.com/maps?q={lat},{lon}"
    except Exception:
        return ""


# ============================================================
# COLUMN DETECTION
# ============================================================

grid_col = find_col(["grid_id", "grid", "cell_id", "id"])

risk_col = find_col(
    [
        "risk_class",
        "final_priority",
        "patrol_priority",
        "priority_class",
        "risk_category",
    ]
)

health_col = find_col(
    [
        "health_class",
        "forest_health",
        "health_status",
        "vegetation_health",
    ]
)

moisture_col = find_col(
    [
        "moisture_class",
        "moisture_status",
        "ndmi_class",
        "water_stress_class",
    ]
)

fire_col = find_col(
    [
        "active_fire",
        "fire_alert",
        "fire_detected",
        "fire_status",
    ]
)

lat_col = find_col(["lat_center", "latitude", "lat", "center_lat"])
lon_col = find_col(["lon_center", "longitude", "lon", "center_lon"])

ndvi_col = find_col(["NDVI", "ndvi", "mean_ndvi"])
ndmi_col = find_col(["NDMI", "ndmi", "mean_ndmi"])

action_col = find_col(
    [
        "patrol_action",
        "recommended_action",
        "action",
        "field_action",
    ]
)

response_col = find_col(
    [
        "recommended_response_time",
        "response_time",
        "patrol_response_time",
    ]
)

google_link_col = find_col(
    [
        "google_maps_link",
        "navigation_link",
        "map_link",
    ]
)


# ============================================================
# DERIVED NAVIGATION LINK
# ============================================================

if google_link_col is None and lat_col and lon_col:
    df["google_maps_link"] = df.apply(
        lambda r: make_navigation_link(r[lat_col], r[lon_col]),
        axis=1,
    )
    google_link_col = "google_maps_link"


# ============================================================
# METRICS
# ============================================================

total_grids = len(df)
critical_grids = safe_count(risk_col, ["CRITICAL", "VERY HIGH"])
high_grids = safe_count(risk_col, ["HIGH", "FIRE CHECK"])

if fire_col:
    fire_text = df[fire_col].astype(str).str.upper()
    active_fires = int(
        fire_text.str.contains("TRUE|YES|ACTIVE|1", na=False).sum()
    )
else:
    active_fires = 0


# ============================================================
# HEADER
# ============================================================

st.title("🌳 Godda FRIS Dashboard")
st.caption("Forest Health • Moisture Stress • Fire Alert • Patrol Priority • Carbon / MRV")

st.markdown(
    """
    <div class="success-box">
        FRIS data loaded successfully.
    </div>
    """,
    unsafe_allow_html=True,
)

m1, m2, m3, m4 = st.columns(4)

m1.metric("Total Forest Grids", total_grids)
m2.metric("Critical Grids", critical_grids)
m3.metric("High / Fire Check Grids", high_grids)
m4.metric("Active Fire Alerts", active_fires)


# ============================================================
# TABS
# ============================================================

tab_map, tab_priority, tab_grid, tab_health, tab_carbon = st.tabs(
    [
        "🗺️ Map",
        "🚨 Priority Grids",
        "📊 Grid Data",
        "🌿 Forest Health",
        "🧾 Carbon / MRV",
    ]
)


# ============================================================
# TAB 1 — LIVE MAP FROM CSV + GEOJSON
# ============================================================

with tab_map:
    st.subheader("FRIS Operational Map")

    if not GEOJSON_PATH.exists():
        st.error("GeoJSON file not found: fris_latest.geojson")
    else:
        try:
            with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
                geojson_data = json.load(f)

            center_lat = 24.83
            center_lon = 87.21

            if lat_col and lon_col:
                lat_values = pd.to_numeric(df[lat_col], errors="coerce").dropna()
                lon_values = pd.to_numeric(df[lon_col], errors="coerce").dropna()

                if not lat_values.empty and not lon_values.empty:
                    center_lat = lat_values.mean()
                    center_lon = lon_values.mean()

            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=10,
                tiles="CartoDB positron",
                control_scale=True,
            )

            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/"
                      "World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri World Imagery",
                name="Satellite",
                overlay=False,
                control=True,
            ).add_to(m)

            folium.TileLayer(
                tiles="CartoDB positron",
                name="Light Map",
                overlay=False,
                control=True,
            ).add_to(m)

            # ------------------------------------------------------------
            # COLOR LOGIC
            # ------------------------------------------------------------

            def choose_color(props):
                risk = str(
                    props.get("risk_class")
                    or props.get("final_priority")
                    or props.get("patrol_priority")
                    or ""
                ).upper()

                health = str(
                    props.get("health_class")
                    or props.get("forest_health")
                    or ""
                ).upper()

                moisture = str(
                    props.get("moisture_class")
                    or props.get("moisture_status")
                    or ""
                ).upper()

                fire = str(
                    props.get("active_fire")
                    or props.get("fire_alert")
                    or ""
                ).upper()

                try:
                    ndvi_value = float(
                        props.get("NDVI")
                        or props.get("ndvi")
                        or props.get("mean_ndvi")
                        or 0
                    )
                except Exception:
                    ndvi_value = 0

                try:
                    ndmi_value = float(
                        props.get("NDMI")
                        or props.get("ndmi")
                        or props.get("mean_ndmi")
                        or 0
                    )
                except Exception:
                    ndmi_value = 0

                # Red: active fire or critical
                if (
                    "TRUE" in fire
                    or "ACTIVE" in fire
                    or fire == "1"
                    or "CRITICAL" in risk
                    or "VERY HIGH" in risk
                ):
                    return "#dc2626"

                # Orange: high risk, fire check, severe dryness
                if (
                    "HIGH" in risk
                    or "FIRE CHECK" in risk
                    or "SEVERE" in moisture
                    or ndmi_value < -0.10
                ):
                    return "#f97316"

                # Yellow: moderate dryness or stressed vegetation
                if (
                    "MODERATE" in risk
                    or "MEDIUM" in risk
                    or "MODERATE" in moisture
                    or "DRY" in moisture
                    or "STRESSED" in health
                    or ndvi_value < 0.35
                ):
                    return "#facc15"

                # Green: normal
                return "#22c55e"


            def style_function(feature):
                props = feature.get("properties", {})
                color = choose_color(props)

                return {
                    "fillColor": color,
                    "color": color,
                    "weight": 1,
                    "fillOpacity": 0.55,
                }

            # ------------------------------------------------------------
            # CUSTOM POPUP WITH NAVIGATION LINK
            # ------------------------------------------------------------

            def popup_html(props):
                grid_value = clean_text(
                    props.get("grid_id")
                    or props.get("grid")
                    or props.get("cell_id")
                    or "Unknown Grid"
                )

                risk_value = clean_text(
                    props.get("risk_class")
                    or props.get("final_priority")
                    or props.get("patrol_priority")
                    or "N/A"
                )

                health_value = clean_text(
                    props.get("health_class")
                    or props.get("forest_health")
                    or "N/A"
                )

                moisture_value = clean_text(
                    props.get("moisture_class")
                    or props.get("moisture_status")
                    or "N/A"
                )

                ndvi_value = clean_text(
                    props.get("NDVI")
                    or props.get("ndvi")
                    or props.get("mean_ndvi")
                    or "N/A"
                )

                ndmi_value = clean_text(
                    props.get("NDMI")
                    or props.get("ndmi")
                    or props.get("mean_ndmi")
                    or "N/A"
                )

                fire_value = clean_text(
                    props.get("active_fire")
                    or props.get("fire_alert")
                    or "False"
                )

                action_value = clean_text(
                    props.get("patrol_action")
                    or props.get("recommended_action")
                    or "Routine monitoring"
                )

                response_value = clean_text(
                    props.get("recommended_response_time")
                    or props.get("response_time")
                    or ""
                )

                link_value = clean_text(
                    props.get("google_maps_link")
                    or props.get("navigation_link")
                    or ""
                )

                if not link_value:
                    lat = props.get("lat_center") or props.get("latitude") or props.get("lat")
                    lon = props.get("lon_center") or props.get("longitude") or props.get("lon")
                    link_value = make_navigation_link(lat, lon)

                nav_button = ""
                if link_value:
                    nav_button = f"""
                    <a href="{link_value}" target="_blank"
                       style="
                       display:inline-block;
                       background:#2563eb;
                       color:white;
                       padding:6px 10px;
                       border-radius:6px;
                       text-decoration:none;
                       margin-top:8px;
                       font-weight:bold;
                       ">
                       Open in Google Maps
                    </a>
                    """

                return f"""
                <div style="font-family:Arial; font-size:13px; width:260px;">
                    <h4 style="margin-bottom:6px;">🌳 {grid_value}</h4>
                    <b>Priority:</b> {risk_value}<br>
                    <b>Health:</b> {health_value}<br>
                    <b>Moisture:</b> {moisture_value}<br>
                    <b>NDVI:</b> {ndvi_value}<br>
                    <b>NDMI:</b> {ndmi_value}<br>
                    <b>Fire:</b> {fire_value}<br>
                    <b>Action:</b> {action_value}<br>
                    <b>Response:</b> {response_value}<br>
                    {nav_button}
                </div>
                """

            # ------------------------------------------------------------
            # ADD GEOJSON LAYER
            # ------------------------------------------------------------

            geo_layer = folium.GeoJson(
                geojson_data,
                name="FRIS Risk Grid",
                style_function=style_function,
            ).add_to(m)

            for feature in geojson_data.get("features", []):
                props = feature.get("properties", {})
                geom = feature.get("geometry", {})

                if not geom:
                    continue

                try:
                    temp_layer = folium.GeoJson(
                        feature,
                        style_function=style_function,
                    )

                    temp_layer.add_child(
                        folium.Popup(
                            popup_html(props),
                            max_width=320,
                        )
                    )

                    temp_layer.add_to(m)

                except Exception:
                    continue

            # ------------------------------------------------------------
            # ADD POINT MARKERS FROM CSV
            # ------------------------------------------------------------

            if lat_col and lon_col:
                for _, row in df.iterrows():
                    try:
                        lat = float(row[lat_col])
                        lon = float(row[lon_col])

                        row_dict = row.to_dict()
                        color = choose_color(row_dict)

                        grid_value = clean_text(
                            row.get(grid_col, "Grid")
                            if grid_col else "Grid"
                        )

                        folium.CircleMarker(
                            location=[lat, lon],
                            radius=5,
                            color=color,
                            fill=True,
                            fill_color=color,
                            fill_opacity=0.9,
                            popup=folium.Popup(
                                popup_html(row_dict),
                                max_width=320,
                            ),
                            tooltip=grid_value,
                        ).add_to(m)

                    except Exception:
                        continue

            folium.LayerControl(collapsed=False).add_to(m)

            legend_html = """
            <div style="
                position: fixed;
                bottom: 35px;
                left: 35px;
                width: 210px;
                background-color: white;
                z-index:9999;
                font-size:13px;
                padding: 10px;
                border:2px solid #999;
                border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,0.25);
            ">
            <b>FRIS Priority Legend</b><br>
            <span style="color:#22c55e;">●</span> Low / Healthy<br>
            <span style="color:#facc15;">●</span> Moderate / Stressed<br>
            <span style="color:#f97316;">●</span> High / Fire Check<br>
            <span style="color:#dc2626;">●</span> Critical / Active Fire<br>
            </div>
            """

            m.get_root().html.add_child(folium.Element(legend_html))

            components.html(m._repr_html_(), height=780, scrolling=True)

        except Exception as e:
            st.error(f"Map rendering failed: {e}")


# ============================================================
# TAB 2 — PRIORITY GRIDS
# ============================================================

with tab_priority:
    st.subheader("Priority Patrol Grids")

    if not risk_col:
        st.warning("No risk / priority column found.")
        st.dataframe(df, use_container_width=True, height=600)
    else:
        priority_df = df[
            df[risk_col]
            .astype(str)
            .str.upper()
            .str.contains("CRITICAL|HIGH|VERY HIGH|FIRE CHECK", na=False)
        ].copy()

        if priority_df.empty:
            st.info("No critical, high, or fire-check grids found.")
        else:
            show_cols = existing_cols(
                [
                    grid_col,
                    risk_col,
                    health_col,
                    moisture_col,
                    fire_col,
                    ndvi_col,
                    ndmi_col,
                    lat_col,
                    lon_col,
                    action_col,
                    response_col,
                    google_link_col,
                ]
            )

            st.dataframe(
                priority_df[show_cols] if show_cols else priority_df,
                use_container_width=True,
                height=600,
            )


# ============================================================
# TAB 3 — GRID DATA
# ============================================================

with tab_grid:
    st.subheader("Grid-wise FRIS Data")

    search_text = st.text_input(
        "Search grid / keyword",
        placeholder="Example: HIGH, FIRE CHECK, STRESSED, GD-35-38...",
    )

    filtered_df = df.copy()

    if search_text.strip():
        mask = filtered_df.astype(str).apply(
            lambda row: row.str.contains(search_text, case=False, na=False).any(),
            axis=1,
        )
        filtered_df = filtered_df[mask]

    st.write(f"Showing {len(filtered_df)} of {len(df)} records")

    st.dataframe(
        filtered_df,
        use_container_width=True,
        height=650,
    )


# ============================================================
# TAB 4 — FOREST HEALTH
# ============================================================

with tab_health:
    st.subheader("Forest Health & Moisture Summary")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### Health Classification")

        if health_col:
            health_summary = df[health_col].astype(str).value_counts().reset_index()
            health_summary.columns = ["Health Class", "Grid Count"]

            st.dataframe(health_summary, use_container_width=True)
            st.bar_chart(health_summary.set_index("Health Class"))
        else:
            st.warning("Health column not found.")

    with c2:
        st.markdown("### Moisture Classification")

        if moisture_col:
            moisture_summary = df[moisture_col].astype(str).value_counts().reset_index()
            moisture_summary.columns = ["Moisture Class", "Grid Count"]

            st.dataframe(moisture_summary, use_container_width=True)
            st.bar_chart(moisture_summary.set_index("Moisture Class"))
        else:
            st.warning("Moisture column not found.")

    st.divider()

    n1, n2 = st.columns(2)

    with n1:
        st.markdown("### NDVI")

        if ndvi_col:
            ndvi_series = safe_numeric(ndvi_col)
            st.metric("Average NDVI", round(ndvi_series.mean(), 4))
            st.line_chart(ndvi_series.dropna().reset_index(drop=True))
        else:
            st.warning("NDVI column not found.")

    with n2:
        st.markdown("### NDMI")

        if ndmi_col:
            ndmi_series = safe_numeric(ndmi_col)
            st.metric("Average NDMI", round(ndmi_series.mean(), 4))
            st.line_chart(ndmi_series.dropna().reset_index(drop=True))
        else:
            st.warning("NDMI column not found.")


# ============================================================
# TAB 5 — CARBON / MRV
# ============================================================

with tab_carbon:
    st.subheader("Carbon / MRV Summary")

    carbon_total_col = find_col(
        [
            "ecosystem_carbon_total_ton",
            "estimated_ecosystem_carbon_ton",
            "carbon_total_ton",
            "baseline_ecosystem_carbon_total_ton",
        ]
    )

    carbon_change_col = find_col(
        [
            "carbon_change_co2e_ton",
            "carbon_change_ton",
            "carbon_change_CO2e",
        ]
    )

    credit_col = find_col(
        [
            "potential_carbon_credits",
            "potential_credit_ton_co2e",
            "carbon_credit_potential",
        ]
    )

    cm1, cm2, cm3 = st.columns(3)

    with cm1:
        if carbon_total_col:
            st.metric(
                "Estimated Ecosystem Carbon",
                round(safe_numeric(carbon_total_col).sum(), 4),
            )
        else:
            st.metric("Estimated Ecosystem Carbon", "N/A")

    with cm2:
        if carbon_change_col:
            st.metric(
                "Carbon Change CO₂e",
                round(safe_numeric(carbon_change_col).sum(), 4),
            )
        else:
            st.metric("Carbon Change CO₂e", "N/A")

    with cm3:
        if credit_col:
            st.metric(
                "Potential Carbon Credits",
                round(safe_numeric(credit_col).sum(), 4),
            )
        else:
            st.metric("Potential Carbon Credits", "N/A")

    carbon_cols = [
        col
        for col in df.columns
        if any(
            key in col.lower()
            for key in [
                "carbon",
                "co2",
                "co2e",
                "credit",
                "mrv",
                "baseline",
                "verification",
                "gedi",
                "hansen",
            ]
        )
    ]

    if carbon_cols:
        st.dataframe(
            df[carbon_cols],
            use_container_width=True,
            height=550,
        )
    else:
        st.warning("No Carbon / MRV related columns found.")


# ============================================================
# FOOTER
# ============================================================

st.divider()
st.caption(
    "FRIS Dashboard | Forest Resilience Information System | Godda Forest Division Pilot"
)