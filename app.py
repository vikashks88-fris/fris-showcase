import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import folium


# ============================================================
# GODDA FRIS DASHBOARD
# ============================================================

st.set_page_config(
    page_title="Godda FRIS Dashboard",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

CSV_PATH = DATA_DIR / "fris_latest.csv"
GEOJSON_PATH = DATA_DIR / "fris_latest.geojson"
MAP_PATH = DATA_DIR / "fris_latest_map.html"


# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
    <style>
    .main {
        background-color: #f7faf7;
    }

    h1, h2, h3 {
        color: #2f3e35;
    }

    .success-box {
        background-color: #e9f7ef;
        color: #1e5631;
        padding: 14px 18px;
        border-radius: 10px;
        border-left: 5px solid #2e7d32;
        margin-bottom: 18px;
    }

    .error-box {
        background-color: #fdecea;
        color: #8a1f11;
        padding: 14px 18px;
        border-radius: 10px;
        border-left: 5px solid #c62828;
        margin-bottom: 18px;
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

st.sidebar.markdown("### Data folder:")
st.sidebar.code(str(DATA_DIR))

st.sidebar.markdown("### Required files:")

def sidebar_file_check(path: Path, name: str):
    if path.exists():
        st.sidebar.success(f"✅ {name}")
    else:
        st.sidebar.error(f"❌ {name}")

sidebar_file_check(CSV_PATH, "fris_latest.csv")
sidebar_file_check(GEOJSON_PATH, "fris_latest.geojson")
sidebar_file_check(MAP_PATH, "fris_latest_map.html")

st.sidebar.divider()

if st.sidebar.button("🔄 Refresh now"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(f"Last refresh: {time.strftime('%Y-%m-%d %H:%M:%S')}")


# ============================================================
# LOAD CSV
# ============================================================

@st.cache_data(ttl=60)
def load_csv(path):
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
# HELPERS
# ============================================================

def find_col(names):
    for name in names:
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

    s = df[col].astype(str).str.upper()
    total = 0

    for keyword in keywords:
        total += s.str.contains(keyword.upper(), na=False).sum()

    return int(total)


def existing_cols(cols):
    return [c for c in cols if c and c in df.columns]


# ============================================================
# COLUMN DETECTION
# ============================================================

grid_col = find_col(["grid_id", "grid", "cell_id", "id"])
risk_col = find_col(["risk_class", "final_priority", "patrol_priority", "priority_class"])
health_col = find_col(["health_class", "forest_health", "health_status"])
moisture_col = find_col(["moisture_class", "moisture_status", "ndmi_class"])
fire_col = find_col(["active_fire", "fire_alert", "fire_detected", "fire_status"])

lat_col = find_col(["lat_center", "latitude", "lat", "center_lat"])
lon_col = find_col(["lon_center", "longitude", "lon", "center_lon"])

ndvi_col = find_col(["NDVI", "ndvi", "mean_ndvi"])
ndmi_col = find_col(["NDMI", "ndmi", "mean_ndmi"])


# ============================================================
# METRICS
# ============================================================

total_grids = len(df)
critical_grids = safe_count(risk_col, ["CRITICAL", "VERY HIGH"])
high_grids = safe_count(risk_col, ["HIGH"])

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
m3.metric("High Priority Grids", high_grids)
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
# TAB 1 — LIVE GEOJSON MAP
# ============================================================

with tab_map:
    st.subheader("FRIS Operational Map")

    if not GEOJSON_PATH.exists():
        st.error("GeoJSON file not found: fris_latest.geojson")

    else:
        try:
            with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
                geojson_data = json.load(f)

            # Default Godda center
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

            def style_function(feature):
                props = feature.get("properties", {})

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

                fire = str(
                    props.get("active_fire")
                    or props.get("fire_alert")
                    or ""
                ).upper()

                color = "#2e7d32"

                if "TRUE" in fire or "ACTIVE" in fire or fire == "1":
                    color = "#b91c1c"
                elif "CRITICAL" in risk:
                    color = "#dc2626"
                elif "HIGH" in risk:
                    color = "#f97316"
                elif "MODERATE" in risk or "MEDIUM" in risk:
                    color = "#facc15"
                elif "STRESSED" in health:
                    color = "#f59e0b"

                return {
                    "fillColor": color,
                    "color": color,
                    "weight": 1,
                    "fillOpacity": 0.55,
                }

            possible_popup_fields = [
                "grid_id",
                "risk_class",
                "final_priority",
                "health_class",
                "moisture_class",
                "NDVI",
                "NDMI",
                "active_fire",
                "fire_count",
                "patrol_action",
                "recommended_response_time",
            ]

            sample_props = {}

            if geojson_data.get("features"):
                sample_props = geojson_data["features"][0].get("properties", {})

            popup_fields = [c for c in possible_popup_fields if c in sample_props]

            if popup_fields:
                popup = folium.GeoJsonPopup(
                    fields=popup_fields,
                    aliases=[c.replace("_", " ").title() for c in popup_fields],
                    localize=True,
                    labels=True,
                    max_width=350,
                )
            else:
                popup = None

            folium.GeoJson(
                geojson_data,
                name="FRIS Grids",
                style_function=style_function,
                popup=popup,
                tooltip=folium.GeoJsonTooltip(
                    fields=popup_fields[:4] if popup_fields else [],
                    aliases=[c.replace("_", " ").title() for c in popup_fields[:4]]
                    if popup_fields else [],
                    sticky=True,
                ) if popup_fields else None,
            ).add_to(m)

            folium.LayerControl(collapsed=False).add_to(m)

            map_html = m._repr_html_()
            components.html(map_html, height=760, scrolling=True)

        except Exception as e:
            st.error(f"Map rendering failed: {e}")


# ============================================================
# TAB 2 — PRIORITY GRIDS
# ============================================================

with tab_priority:
    st.subheader("Priority Patrol Grids")

    if not risk_col:
        st.warning("No risk / priority column found.")
        st.dataframe(df, use_container_width=True, height=550)

    else:
        priority_df = df[
            df[risk_col]
            .astype(str)
            .str.upper()
            .str.contains("CRITICAL|HIGH|VERY HIGH", na=False)
        ].copy()

        if priority_df.empty:
            st.info("No critical or high-priority grids found.")
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
                    "patrol_action",
                    "recommended_response_time",
                    "google_maps_link",
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
        placeholder="Example: HIGH, STRESSED, GD-10-20, fire...",
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
st.caption("FRIS Dashboard | Forest Resilience Information System | Godda Forest Division Pilot")