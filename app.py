import json
import time
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


# ============================================================
# PAGE CONFIG
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

st.markdown(
    """
    <meta http-equiv="refresh" content="60">
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


# ============================================================
# STYLING
# ============================================================

st.markdown(
    """
    <style>

    .main {
        background-color: #f4f8f4;
    }

    .stMetric {
        background: white;
        padding: 16px;
        border-radius: 14px;
        box-shadow: 0px 2px 10px rgba(0,0,0,0.06);
    }

    h1, h2, h3 {
        color: #2d3748;
    }

    .success-box {
        background-color: #e6ffed;
        border-left: 5px solid #22c55e;
        padding: 14px;
        border-radius: 10px;
        margin-bottom: 20px;
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

st.sidebar.markdown("### Data Folder")
st.sidebar.code(str(DATA_DIR))

st.sidebar.markdown("### Required Files")


def check_file(path, name):
    if path.exists():
        st.sidebar.success(f"✅ {name}")
    else:
        st.sidebar.error(f"❌ {name}")


check_file(CSV_PATH, "fris_latest.csv")
check_file(GEOJSON_PATH, "fris_latest.geojson")

st.sidebar.divider()

if st.sidebar.button("🔄 Refresh Now"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(
    f"Last refresh: {time.strftime('%Y-%m-%d %H:%M:%S')}"
)


# ============================================================
# LOAD CSV
# ============================================================

@st.cache_data(ttl=60)
def load_csv():
    return pd.read_csv(CSV_PATH)


if not CSV_PATH.exists():
    st.error("fris_latest.csv not found inside data folder.")
    st.stop()

try:
    df = load_csv()
except Exception as e:
    st.error(f"CSV loading failed: {e}")
    st.stop()


# ============================================================
# COLUMN FINDER
# ============================================================

def find_col(possible):
    for c in possible:
        if c in df.columns:
            return c
    return None


grid_col = find_col(["grid_id"])
risk_col = find_col(["risk_class", "final_priority"])
health_col = find_col(["health_class"])
moisture_col = find_col(["moisture_class"])
fire_col = find_col(["active_fire"])

lat_col = find_col(["lat_center", "latitude", "lat"])
lon_col = find_col(["lon_center", "longitude", "lon"])

ndvi_col = find_col(["NDVI", "ndvi"])
ndmi_col = find_col(["NDMI", "ndmi"])


# ============================================================
# METRICS
# ============================================================

total_grids = len(df)

critical_grids = 0
high_grids = 0
active_fire = 0

if risk_col:
    risk_text = df[risk_col].astype(str).str.upper()

    critical_grids = risk_text.str.contains(
        "CRITICAL|VERY HIGH",
        na=False
    ).sum()

    high_grids = risk_text.str.contains(
        "HIGH",
        na=False
    ).sum()

if fire_col:
    fire_text = df[fire_col].astype(str).str.upper()

    active_fire = fire_text.str.contains(
        "TRUE|YES|ACTIVE|1",
        na=False
    ).sum()


# ============================================================
# HEADER
# ============================================================

st.title("🌳 Godda FRIS Dashboard")

st.caption(
    "Forest Health • Moisture Stress • Fire Alert • "
    "Patrol Priority • Carbon / MRV"
)

st.markdown(
    """
    <div class="success-box">
    FRIS data loaded successfully.
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# METRIC ROW
# ============================================================

m1, m2, m3, m4 = st.columns(4)

m1.metric("Total Forest Grids", int(total_grids))
m2.metric("Critical Grids", int(critical_grids))
m3.metric("High / Fire Check Grids", int(high_grids))
m4.metric("Active Fire Alerts", int(active_fire))


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
# MAP TAB
# ============================================================

with tab_map:

    st.subheader("FRIS Operational Map")

    if not GEOJSON_PATH.exists():
        st.error("GeoJSON file not found.")
    else:

        try:

            with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
                geojson_data = json.load(f)

            # ====================================================
            # MAP CENTER
            # ====================================================

            center_lat = 24.83
            center_lon = 87.21

            if lat_col and lon_col:

                lat_values = pd.to_numeric(
                    df[lat_col],
                    errors="coerce"
                ).dropna()

                lon_values = pd.to_numeric(
                    df[lon_col],
                    errors="coerce"
                ).dropna()

                if len(lat_values) > 0 and len(lon_values) > 0:
                    center_lat = lat_values.mean()
                    center_lon = lon_values.mean()

            # ====================================================
            # CREATE MAP
            # ====================================================

            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=10,
                tiles=None,
                control_scale=True,
            )

            # ====================================================
            # SATELLITE
            # ====================================================

            folium.TileLayer(
                tiles="https://server.arcgisonline.com/"
                      "ArcGIS/rest/services/World_Imagery/"
                      "MapServer/tile/{z}/{y}/{x}",
                attr="Esri",
                name="Satellite",
                overlay=False,
                control=True,
            ).add_to(m)

            # ====================================================
            # CARTODB
            # ====================================================

            folium.TileLayer(
                "CartoDB positron",
                name="CartoDB",
                overlay=False,
                control=True,
            ).add_to(m)

            # ====================================================
            # STYLE FUNCTION
            # ====================================================

            def style_function(feature):

                props = feature.get("properties", {})

                risk = str(
                    props.get("risk_class", "")
                ).upper()

                health = str(
                    props.get("health_class", "")
                ).upper()

                fire = str(
                    props.get("active_fire", "")
                ).upper()

                color = "#22c55e"

                # FIRE
                if (
                    "TRUE" in fire
                    or "ACTIVE" in fire
                    or fire == "1"
                ):
                    color = "#ff0000"

                # CRITICAL
                elif "CRITICAL" in risk:
                    color = "#dc2626"

                # HIGH
                elif "HIGH" in risk:
                    color = "#f97316"

                # MODERATE
                elif (
                    "MODERATE" in risk
                    or "MEDIUM" in risk
                ):
                    color = "#facc15"

                # STRESSED
                elif "STRESSED" in health:
                    color = "#eab308"

                return {
                    "fillColor": color,
                    "color": color,
                    "weight": 1,
                    "fillOpacity": 0.55,
                }

            # ====================================================
            # POPUP
            # ====================================================

            def popup_html(props):

                lat = props.get("lat_center", "")
                lon = props.get("lon_center", "")

                google_link = (
                    f"https://www.google.com/maps?q={lat},{lon}"
                )

                return f"""
                <div style="width:250px;">

                <b>Grid:</b> {props.get('grid_id', '')}<br>

                <b>Priority:</b>
                {props.get('risk_class', '')}<br>

                <b>Health:</b>
                {props.get('health_class', '')}<br>

                <b>Moisture:</b>
                {props.get('moisture_class', '')}<br>

                <b>NDVI:</b>
                {props.get('NDVI', '')}<br>

                <b>NDMI:</b>
                {props.get('NDMI', '')}<br>

                <b>Fire:</b>
                {props.get('active_fire', '')}<br>

                <b>Action:</b>
                {props.get('patrol_action', '')}<br><br>

                <a href="{google_link}"
                   target="_blank">

                   🧭 Open in Google Maps

                </a>

                </div>
                """

            # ====================================================
            # GEOJSON
            # ====================================================

            geojson_layer = folium.GeoJson(
                geojson_data,
                style_function=style_function,
                tooltip=folium.GeoJsonTooltip(
                    fields=[
                        c for c in [
                            "grid_id",
                            "risk_class",
                            "health_class",
                        ]
                        if c in df.columns
                    ]
                ),
                name="FRIS Grids",
            )

            geojson_layer.add_to(m)

            # ====================================================
            # POPUPS
            # ====================================================

            for feature in geojson_data["features"]:

                props = feature.get("properties", {})

                geometry = feature.get("geometry", {})

                if geometry.get("type") == "Polygon":

                    coords = geometry["coordinates"][0]

                    lat = sum([p[1] for p in coords]) / len(coords)
                    lon = sum([p[0] for p in coords]) / len(coords)

                    popup = folium.Popup(
                        popup_html(props),
                        max_width=300
                    )

                    folium.Marker(
                        [lat, lon],
                        popup=popup,
                        icon=folium.Icon(
                            color="green",
                            icon="tree-deciduous",
                            prefix="glyphicon",
                        ),
                    ).add_to(m)

            # ====================================================
            # LAYER CONTROL
            # ====================================================

            folium.LayerControl().add_to(m)

            # ====================================================
            # RENDER
            # ====================================================

            map_html = m._repr_html_()

            components.html(
                map_html,
                height=800,
                scrolling=True,
            )

        except Exception as e:

            st.error(f"Map rendering failed: {e}")


# ============================================================
# PRIORITY TAB
# ============================================================

with tab_priority:

    st.subheader("Priority Patrol Grids")

    if risk_col:

        priority_df = df[
            df[risk_col]
            .astype(str)
            .str.upper()
            .str.contains(
                "CRITICAL|HIGH|VERY HIGH",
                na=False
            )
        ]

        if len(priority_df) == 0:
            st.info("No critical grids found.")
        else:
            st.dataframe(
                priority_df,
                use_container_width=True,
                height=600,
            )
    else:
        st.warning("Risk column not found.")


# ============================================================
# GRID TAB
# ============================================================

with tab_grid:

    st.subheader("Grid Data")

    search = st.text_input(
        "Search Grid / Risk / Health"
    )

    filtered_df = df.copy()

    if search:

        mask = filtered_df.astype(str).apply(
            lambda row: row.str.contains(
                search,
                case=False,
                na=False
            ).any(),
            axis=1
        )

        filtered_df = filtered_df[mask]

    st.dataframe(
        filtered_df,
        use_container_width=True,
        height=650,
    )


# ============================================================
# HEALTH TAB
# ============================================================

with tab_health:

    st.subheader("Forest Health Summary")

    c1, c2 = st.columns(2)

    with c1:

        if health_col:

            health_summary = (
                df[health_col]
                .astype(str)
                .value_counts()
            )

            st.bar_chart(health_summary)

    with c2:

        if moisture_col:

            moisture_summary = (
                df[moisture_col]
                .astype(str)
                .value_counts()
            )

            st.bar_chart(moisture_summary)

    st.divider()

    n1, n2 = st.columns(2)

    with n1:

        if ndvi_col:

            ndvi_series = pd.to_numeric(
                df[ndvi_col],
                errors="coerce"
            )

            st.metric(
                "Average NDVI",
                round(ndvi_series.mean(), 4)
            )

            st.line_chart(
                ndvi_series.dropna()
            )

    with n2:

        if ndmi_col:

            ndmi_series = pd.to_numeric(
                df[ndmi_col],
                errors="coerce"
            )

            st.metric(
                "Average NDMI",
                round(ndmi_series.mean(), 4)
            )

            st.line_chart(
                ndmi_series.dropna()
            )


# ============================================================
# CARBON TAB
# ============================================================

with tab_carbon:

    st.subheader("Carbon / MRV Summary")

    carbon_cols = [
        c for c in df.columns
        if (
            "carbon" in c.lower()
            or "co2" in c.lower()
            or "credit" in c.lower()
            or "mrv" in c.lower()
        )
    ]

    if carbon_cols:

        cm1, cm2, cm3 = st.columns(3)

        total_carbon = 0
        carbon_change = 0
        credits = 0

        if "ecosystem_carbon_co2e_total" in df.columns:
            total_carbon = pd.to_numeric(
                df["ecosystem_carbon_co2e_total"],
                errors="coerce"
            ).sum()

        if "carbon_change_from_365d" in df.columns:
            carbon_change = pd.to_numeric(
                df["carbon_change_from_365d"],
                errors="coerce"
            ).sum()

        if "potential_carbon_credits" in df.columns:
            credits = pd.to_numeric(
                df["potential_carbon_credits"],
                errors="coerce"
            ).sum()

        cm1.metric(
            "Estimated Ecosystem Carbon",
            round(total_carbon, 2)
        )

        cm2.metric(
            "Carbon Change CO₂e",
            round(carbon_change, 2)
        )

        cm3.metric(
            "Potential Carbon Credits",
            round(credits, 2)
        )

        st.dataframe(
            df[carbon_cols],
            use_container_width=True,
            height=550,
        )

    else:
        st.warning("No Carbon / MRV columns found.")


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "FRIS Dashboard | Forest Resilience Information System "
    "| Godda Forest Division"
)