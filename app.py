import os
import pandas as pd
import streamlit as st
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

# =====================================================
# PAGE CONFIG
# =====================================================

st.set_page_config(
    page_title="Godda FRIS Dashboard",
    layout="wide"
)

# =====================================================
# CUSTOM CSS
# =====================================================

st.markdown(
    """
    <style>

    .main {
        background-color: #f7f9fc;
    }

    .stMetric {
        background-color: white;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0px 2px 8px rgba(0,0,0,0.08);
    }

    h1 {
        color: #1f3d2b;
    }

    .block-container {
        padding-top: 1rem;
    }

    </style>
    """,
    unsafe_allow_html=True
)

# =====================================================
# DATA PATHS
# =====================================================

SEARCH_PATHS = [
    "data",
    "output",
    "/opt/render/project/src/data",
    "/opt/render/project/src/output",
    "C:/cfris/output",
]

csv_path = None

for folder in SEARCH_PATHS:

    csv_test = os.path.join(folder, "fris_latest.csv")

    if os.path.exists(csv_test):
        csv_path = csv_test
        break

# =====================================================
# HEADER
# =====================================================

st.title("🌳 Godda FRIS Dashboard")

st.caption(
    "Forest Health • Moisture Stress • Fire Alert • Patrol Priority • Carbon / MRV"
)

# =====================================================
# FILE CHECK
# =====================================================

if csv_path is None:

    st.error("FRIS CSV not found.")

    st.code(
        """
fris_showcase/
├── app.py
├── requirements.txt
└── data/
    └── fris_latest.csv
        """
    )

    st.stop()

# =====================================================
# LOAD CSV
# =====================================================

try:

    df = pd.read_csv(csv_path)

    st.success("FRIS data loaded successfully.")

except Exception as e:

    st.error(f"CSV loading failed: {e}")

    st.stop()

# =====================================================
# SAFE COLUMN FUNCTION
# =====================================================

def safe_column(name, default=None):

    if name in df.columns:
        return df[name]

    return pd.Series([default] * len(df))

# =====================================================
# IMPORTANT COLUMNS
# =====================================================

health = safe_column("health_class", "UNKNOWN")
moisture = safe_column("moisture_class", "UNKNOWN")
risk = safe_column("risk_class", "LOW")

# =====================================================
# SIDEBAR FILTERS
# =====================================================

st.sidebar.header("FRIS Filters")

health_filter = st.sidebar.multiselect(
    "Health Class",
    sorted(health.dropna().unique()),
    default=list(sorted(health.dropna().unique()))
)

moisture_filter = st.sidebar.multiselect(
    "Moisture Class",
    sorted(moisture.dropna().unique()),
    default=list(sorted(moisture.dropna().unique()))
)

risk_filter = st.sidebar.multiselect(
    "Risk Class",
    sorted(risk.dropna().unique()),
    default=list(sorted(risk.dropna().unique()))
)

# =====================================================
# FILTERED DATA
# =====================================================

filtered_df = df[
    health.isin(health_filter)
    & moisture.isin(moisture_filter)
    & risk.isin(risk_filter)
]

# =====================================================
# TOP METRICS
# =====================================================

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Forest Grids", len(filtered_df))

with col2:

    critical_count = len(
        filtered_df[
            filtered_df.get("risk_class", "LOW") == "CRITICAL"
        ]
    )

    st.metric("Critical", critical_count)

with col3:

    stressed_count = len(
        filtered_df[
            filtered_df.get("health_class", "") == "STRESSED"
        ]
    )

    st.metric("Stress", stressed_count)

with col4:

    fire_count = len(
        filtered_df[
            filtered_df.get("active_fire", 0) == 1
        ]
    )

    st.metric("Fire Alerts", fire_count)

with col5:

    healthy_count = len(
        filtered_df[
            filtered_df.get("health_class", "") == "HEALTHY"
        ]
    )

    st.metric("Healthy", healthy_count)

# =====================================================
# TABS
# =====================================================

map_tab, grid_tab, health_tab, carbon_tab = st.tabs(
    [
        "🗺 Operational Map",
        "📋 Grid Data",
        "🌿 Forest Health",
        "🧪 Carbon / MRV"
    ]
)

# =====================================================
# MAP TAB
# =====================================================

with map_tab:

    st.subheader("FRIS Operational Map")

    # -------------------------------------------------

    if "lat_center" in filtered_df.columns:
        center_lat = filtered_df["lat_center"].mean()
    else:
        center_lat = 24.0

    if "lon_center" in filtered_df.columns:
        center_lon = filtered_df["lon_center"].mean()
    else:
        center_lon = 87.2

    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=9,
        tiles="CartoDB positron"
    )

    # =================================================
    # SATELLITE LAYER
    # =================================================

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellite",
        overlay=False,
        control=True
    ).add_to(fmap)

    marker_cluster = MarkerCluster().add_to(fmap)

    # =================================================
    # MARKER COLOR
    # =================================================

    def marker_color(row):

        risk_value = str(
            row.get("risk_class", "LOW")
        ).upper()

        if risk_value == "CRITICAL":
            return "red"

        if risk_value == "HIGH":
            return "orange"

        if risk_value == "MODERATE":
            return "yellow"

        return "green"

    # =================================================
    # INFERENCE LOGIC
    # =================================================

    def inference_text(row):

        risk_value = str(
            row.get("risk_class", "LOW")
        ).upper()

        fire_value = row.get("active_fire", 0)

        health_value = str(
            row.get("health_class", "")
        ).upper()

        if fire_value == 1:
            return "Active fire signal detected. Immediate verification recommended."

        if risk_value == "CRITICAL":
            return "Critical ecological stress detected. Priority patrol required."

        if risk_value == "HIGH":
            return "Dry vegetation stress increasing. Patrol within 24 hours."

        if health_value == "STRESSED":
            return "Vegetation decline observed. Monitoring recommended."

        return "Healthy forest condition. Routine monitoring sufficient."

    # =================================================
    # ADD MARKERS
    # =================================================

    for _, row in filtered_df.iterrows():

        lat = row.get("lat_center")
        lon = row.get("lon_center")

        if pd.isna(lat) or pd.isna(lon):
            continue

        popup_html = f"""
        <b>Grid:</b> {row.get('grid_id', 'N/A')}<br>
        <b>Health:</b> {row.get('health_class', 'N/A')}<br>
        <b>Moisture:</b> {row.get('moisture_class', 'N/A')}<br>
        <b>Risk:</b> {row.get('risk_class', 'N/A')}<br>
        <b>NDVI:</b> {row.get('ndvi', 'N/A')}<br>
        <b>NDMI:</b> {row.get('ndmi', 'N/A')}<br>
        <b>Fire:</b> {row.get('active_fire', 0)}<br>
        <b>Action:</b> {inference_text(row)}<br>
        """

        if "google_maps_link" in row:

            popup_html += f"""
            <br>
            <a href='{row.get('google_maps_link')}'
            target='_blank'>
            Open in Google Maps
            </a>
            """

        folium.CircleMarker(
            location=[lat, lon],
            radius=7,
            popup=popup_html,
            color=marker_color(row),
            fill=True,
            fill_opacity=0.8
        ).add_to(marker_cluster)

    folium.LayerControl().add_to(fmap)

    st_folium(
        fmap,
        width=None,
        height=700
    )

# =====================================================
# GRID TAB
# =====================================================

with grid_tab:

    st.subheader("Grid Operational Data")

    st.dataframe(
        filtered_df,
        use_container_width=True
    )

# =====================================================
# HEALTH TAB
# =====================================================

with health_tab:

    st.subheader("Forest Health Overview")

    if "health_class" in filtered_df.columns:

        health_counts = (
            filtered_df["health_class"]
            .value_counts()
        )

        st.bar_chart(health_counts)

    if "moisture_class" in filtered_df.columns:

        moisture_counts = (
            filtered_df["moisture_class"]
            .value_counts()
        )

        st.bar_chart(moisture_counts)

# =====================================================
# CARBON TAB
# =====================================================

with carbon_tab:

    st.subheader("Carbon / MRV Summary")

    carbon_cols = [
        "estimated_ecosystem_carbon_ton",
        "carbon_change_ton",
        "potential_carbon_credits",
        "mrv_confidence"
    ]

    available_cols = [
        c for c in carbon_cols
        if c in filtered_df.columns
    ]

    if available_cols:

        st.dataframe(
            filtered_df[available_cols],
            use_container_width=True
        )

    else:

        st.info(
            "Carbon / MRV columns not available in current CSV."
        )

# =====================================================
# FOOTER
# =====================================================

st.markdown("---")

st.caption(
    "FRIS • Forest Resilience Information System • Godda Forest Division"
)