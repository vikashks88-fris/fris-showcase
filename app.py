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
# STYLE
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
    test_path = os.path.join(folder, "fris_latest.csv")

    if os.path.exists(test_path):
        csv_path = test_path
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

    st.markdown("Keep your file like this:")

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
# LOAD DATA
# =====================================================

try:
    df = pd.read_csv(csv_path)
    st.success("FRIS data loaded successfully.")
except Exception as e:
    st.error(f"CSV loading failed: {e}")
    st.stop()

# =====================================================
# CLEAN DATA
# =====================================================

df.columns = df.columns.str.strip()

for col in df.columns:
    if df[col].dtype == "object":
        df[col] = df[col].astype(str).str.strip()

# =====================================================
# SAFE COLUMN FUNCTION
# =====================================================

def safe_column(name, default):
    if name in df.columns:
        return df[name]
    return pd.Series([default] * len(df))


# =====================================================
# DEFAULT COLUMNS
# =====================================================

health_col = safe_column("health_class", "UNKNOWN")
moisture_col = safe_column("moisture_class", "UNKNOWN")
risk_col = safe_column("risk_class", "LOW")

# =====================================================
# SIDEBAR FILTERS
# =====================================================

st.sidebar.header("FRIS Filters")

health_values = sorted(health_col.dropna().unique())
moisture_values = sorted(moisture_col.dropna().unique())
risk_values = sorted(risk_col.dropna().unique())

health_filter = st.sidebar.multiselect(
    "Health Class",
    health_values,
    default=health_values
)

moisture_filter = st.sidebar.multiselect(
    "Moisture Class",
    moisture_values,
    default=moisture_values
)

risk_filter = st.sidebar.multiselect(
    "Risk Class",
    risk_values,
    default=risk_values
)

# =====================================================
# FILTER DATA
# =====================================================

filtered_df = df[
    health_col.isin(health_filter)
    & moisture_col.isin(moisture_filter)
    & risk_col.isin(risk_filter)
].copy()

# =====================================================
# METRICS
# =====================================================

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Forest Grids", len(filtered_df))

with col2:
    if "risk_class" in filtered_df.columns:
        critical_count = len(
            filtered_df[
                filtered_df["risk_class"].astype(str).str.upper() == "CRITICAL"
            ]
        )
    else:
        critical_count = 0

    st.metric("Critical", critical_count)

with col3:
    if "health_class" in filtered_df.columns:
        stressed_count = len(
            filtered_df[
                filtered_df["health_class"].astype(str).str.upper() == "STRESSED"
            ]
        )
    else:
        stressed_count = 0

    st.metric("Stress", stressed_count)

with col4:
    if "active_fire" in filtered_df.columns:
        fire_count = len(
            filtered_df[
                filtered_df["active_fire"].astype(str).isin(["1", "TRUE", "True", "true"])
            ]
        )
    else:
        fire_count = 0

    st.metric("Fire Alerts", fire_count)

with col5:
    if "health_class" in filtered_df.columns:
        healthy_count = len(
            filtered_df[
                filtered_df["health_class"].astype(str).str.upper() == "HEALTHY"
            ]
        )
    else:
        healthy_count = 0

    st.metric("Healthy", healthy_count)

# =====================================================
# TABS
# =====================================================

map_tab, priority_tab, data_tab, health_tab, carbon_tab = st.tabs(
    [
        "🗺 Map",
        "🚨 Priority Grids",
        "📋 Grid Data",
        "🌿 Forest Health",
        "🧪 Carbon / MRV"
    ]
)

# =====================================================
# HELPER FUNCTIONS
# =====================================================

def get_value(row, column_name, default="N/A"):
    if column_name in row:
        value = row[column_name]
        if pd.isna(value):
            return default
        return value
    return default


def marker_color(row):
    risk_value = str(get_value(row, "risk_class", "LOW")).upper()
    health_value = str(get_value(row, "health_class", "")).upper()

    if risk_value == "CRITICAL":
        return "red"

    if risk_value == "HIGH":
        return "orange"

    if risk_value == "MODERATE":
        return "beige"

    if health_value == "STRESSED":
        return "orange"

    return "green"


def inference_text(row):
    risk_value = str(get_value(row, "risk_class", "LOW")).upper()
    health_value = str(get_value(row, "health_class", "")).upper()
    moisture_value = str(get_value(row, "moisture_class", "")).upper()
    fire_value = str(get_value(row, "active_fire", "0")).upper()

    if fire_value in ["1", "TRUE", "YES"]:
        return "Active fire signal detected. Immediate field verification recommended."

    if risk_value == "CRITICAL":
        return "Critical ecological stress detected. Priority patrol required."

    if risk_value == "HIGH":
        return "High-risk forest grid. Patrol within 24 hours."

    if health_value == "STRESSED":
        return "Vegetation stress detected. Monitoring and field check recommended."

    if moisture_value in ["DRY", "LOW", "STRESSED", "CRITICAL"]:
        return "Moisture stress visible. Fire vulnerability may increase."

    return "Healthy forest condition. Routine monitoring sufficient."


# =====================================================
# MAP TAB
# =====================================================

with map_tab:

    st.subheader("FRIS Operational Map")

    if "lat_center" in filtered_df.columns:
        center_lat = pd.to_numeric(filtered_df["lat_center"], errors="coerce").mean()
    else:
        center_lat = 24.0

    if "lon_center" in filtered_df.columns:
        center_lon = pd.to_numeric(filtered_df["lon_center"], errors="coerce").mean()
    else:
        center_lon = 87.2

    if pd.isna(center_lat):
        center_lat = 24.0

    if pd.isna(center_lon):
        center_lon = 87.2

    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=9,
        tiles="CartoDB positron"
    )

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Satellite",
        name="Satellite",
        overlay=False,
        control=True
    ).add_to(fmap)

    marker_cluster = MarkerCluster().add_to(fmap)

    for _, row in filtered_df.iterrows():

        lat = get_value(row, "lat_center", None)
        lon = get_value(row, "lon_center", None)

        try:
            lat = float(lat)
            lon = float(lon)
        except:
            continue

        popup_html = f"""
        <b>Grid:</b> {get_value(row, 'grid_id')}<br>
        <b>Health:</b> {get_value(row, 'health_class')}<br>
        <b>Moisture:</b> {get_value(row, 'moisture_class')}<br>
        <b>Risk:</b> {get_value(row, 'risk_class')}<br>
        <b>NDVI:</b> {get_value(row, 'ndvi')}<br>
        <b>NDMI:</b> {get_value(row, 'ndmi')}<br>
        <b>Fire:</b> {get_value(row, 'active_fire', 0)}<br>
        <b>Action:</b> {inference_text(row)}<br>
        """

        google_link = get_value(row, "google_maps_link", "")

        if google_link not in ["", "N/A", None]:
            popup_html += f"""
            <br>
            <a href="{google_link}" target="_blank">
            Open in Google Maps
            </a>
            """

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=350),
            icon=folium.Icon(
                color=marker_color(row),
                icon="tree",
                prefix="fa"
            )
        ).add_to(marker_cluster)

    folium.LayerControl().add_to(fmap)

    st_folium(
        fmap,
        width=None,
        height=700
    )

# =====================================================
# PRIORITY TAB
# =====================================================

with priority_tab:

    st.subheader("Priority Grids for Field Action")

    priority_df = filtered_df.copy()

    if "risk_class" in priority_df.columns:
        priority_df = priority_df[
            priority_df["risk_class"].astype(str).str.upper().isin(
                ["CRITICAL", "HIGH", "MODERATE"]
            )
        ]

    show_cols = [
        "grid_id",
        "health_class",
        "moisture_class",
        "risk_class",
        "ndvi",
        "ndmi",
        "active_fire",
        "patrol_action",
        "google_maps_link"
    ]

    available_cols = [
        col for col in show_cols
        if col in priority_df.columns
    ]

    if len(priority_df) > 0 and available_cols:
        st.dataframe(
            priority_df[available_cols],
            use_container_width=True
        )
    else:
        st.info("No priority grids found in current filtered data.")

# =====================================================
# DATA TAB
# =====================================================

with data_tab:

    st.subheader("Complete Grid Data")

    st.dataframe(
        filtered_df,
        use_container_width=True
    )

# =====================================================
# HEALTH TAB
# =====================================================

with health_tab:

    st.subheader("Forest Health Summary")

    if "health_class" in filtered_df.columns:
        st.markdown("### Health Class Distribution")
        st.bar_chart(filtered_df["health_class"].value_counts())

    if "moisture_class" in filtered_df.columns:
        st.markdown("### Moisture Class Distribution")
        st.bar_chart(filtered_df["moisture_class"].value_counts())

    if "risk_class" in filtered_df.columns:
        st.markdown("### Risk Class Distribution")
        st.bar_chart(filtered_df["risk_class"].value_counts())

# =====================================================
# CARBON TAB
# =====================================================

with carbon_tab:

    st.subheader("Carbon / MRV Summary")

    carbon_cols = [
        "estimated_ecosystem_carbon_ton",
        "carbon_change_ton",
        "carbon_change_co2e_ton",
        "gross_positive_co2e_gain_ton",
        "potential_credit_ton_co2e",
        "potential_carbon_credits",
        "mrv_confidence",
        "verification_status",
        "carbon_credit_claim_status"
    ]

    available_carbon_cols = [
        col for col in carbon_cols
        if col in filtered_df.columns
    ]

    if available_carbon_cols:
        st.dataframe(
            filtered_df[available_carbon_cols],
            use_container_width=True
        )
    else:
        st.info("Carbon / MRV columns not available in current CSV.")

# =====================================================
# FOOTER
# =====================================================

st.markdown("---")

st.caption(
    "FRIS • Forest Resilience Information System • Godda Forest Division"
)