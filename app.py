import streamlit as st
import pandas as pd
from pathlib import Path
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Godda FRIS Dashboard",
    page_icon="🌳",
    layout="wide"
)

# ---------------- AUTO REFRESH ----------------
st_autorefresh(interval=60000, key="fris_auto_refresh")

# ---------------- PATHS ----------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

CSV_PATH = DATA_DIR / "fris_latest.csv"
MAP_PATH = DATA_DIR / "fris_latest_map.html"
GEOJSON_PATH = DATA_DIR / "fris_latest.geojson"

# ---------------- LOAD CSV ----------------
@st.cache_data(ttl=60)
def load_csv(path):
    if not path.exists():
        return None

    try:
        df = pd.read_csv(path)
        if df.empty:
            return None
        return df
    except Exception:
        return None


df = load_csv(CSV_PATH)

# ---------------- HEADER ----------------
st.title("🌳 Godda FRIS Dashboard")
st.caption("Forest Resilience Information System | Live Forest Health, Moisture, Fire & Patrol Monitoring")

# ---------------- FILE CHECK ----------------
if df is None:
    st.error("FRIS CSV not found or empty.")
    st.info("Keep your files inside the data folder:")
    st.code(
        """
fris-showcase/
├── app.py
├── requirements.txt
└── data/
    ├── fris_latest.csv
    ├── fris_latest.geojson
    └── fris_latest_map.html
        """
    )
    st.stop()

# ---------------- SAFE COLUMN FINDER ----------------
def get_col(possible_names):
    for name in possible_names:
        if name in df.columns:
            return name
    return None


grid_col = get_col(["grid_id", "grid", "id"])
risk_col = get_col(["risk_class", "final_priority", "patrol_priority", "priority"])
health_col = get_col(["health_class", "forest_health", "health"])
moisture_col = get_col(["moisture_class", "moisture_status", "moisture"])
ndvi_col = get_col(["ndvi", "NDVI"])
ndmi_col = get_col(["ndmi", "NDMI"])
fire_col = get_col(["active_fire", "fire_detected", "fire_status"])
action_col = get_col(["patrol_action", "recommended_action", "action"])
lat_col = get_col(["lat_center", "latitude", "lat"])
lon_col = get_col(["lon_center", "longitude", "lon"])

# ---------------- SIDEBAR ----------------
st.sidebar.title("FRIS Controls")

filtered_df = df.copy()

if risk_col:
    risk_options = sorted(filtered_df[risk_col].dropna().astype(str).unique())
    selected_risk = st.sidebar.multiselect("Filter by Risk", risk_options, default=risk_options)
    filtered_df = filtered_df[filtered_df[risk_col].astype(str).isin(selected_risk)]

if health_col:
    health_options = sorted(filtered_df[health_col].dropna().astype(str).unique())
    selected_health = st.sidebar.multiselect("Filter by Health", health_options, default=health_options)
    filtered_df = filtered_df[filtered_df[health_col].astype(str).isin(selected_health)]

if moisture_col:
    moisture_options = sorted(filtered_df[moisture_col].dropna().astype(str).unique())
    selected_moisture = st.sidebar.multiselect("Filter by Moisture", moisture_options, default=moisture_options)
    filtered_df = filtered_df[filtered_df[moisture_col].astype(str).isin(selected_moisture)]

st.sidebar.markdown("---")
st.sidebar.write("Total Records:", len(df))
st.sidebar.write("Filtered Records:", len(filtered_df))

# ---------------- KPI CARDS ----------------
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("Total Forest Grids", len(df))

with c2:
    st.metric("Visible Grids", len(filtered_df))

with c3:
    if fire_col:
        fire_count = filtered_df[fire_col].astype(str).str.lower().isin(
            ["yes", "true", "1", "active", "fire"]
        ).sum()
        st.metric("Active Fire Grids", int(fire_count))
    else:
        st.metric("Active Fire Grids", "N/A")

with c4:
    if risk_col:
        high_count = filtered_df[risk_col].astype(str).str.upper().isin(
            ["HIGH", "CRITICAL", "VERY HIGH"]
        ).sum()
        st.metric("High/Critical Risk", int(high_count))
    else:
        st.metric("High/Critical Risk", "N/A")

# ---------------- MAIN TABS ----------------
tab1, tab2, tab3, tab4 = st.tabs(
    ["🗺️ FRIS Map", "📊 Summary", "🚨 Priority Grids", "📄 Raw Data"]
)

# ---------------- MAP TAB ----------------
with tab1:
    st.subheader("FRIS Operational Map")

    if MAP_PATH.exists():
        with open(MAP_PATH, "r", encoding="utf-8") as f:
            map_html = f.read()
        components.html(map_html, height=700, scrolling=True)
    else:
        st.warning("Map file not found: data/fris_latest_map.html")

# ---------------- SUMMARY TAB ----------------
with tab2:
    st.subheader("Forest Condition Summary")

    col_a, col_b = st.columns(2)

    with col_a:
        if risk_col:
            st.write("Risk Class Distribution")
            st.bar_chart(filtered_df[risk_col].astype(str).value_counts())

        if health_col:
            st.write("Health Class Distribution")
            st.bar_chart(filtered_df[health_col].astype(str).value_counts())

    with col_b:
        if moisture_col:
            st.write("Moisture Class Distribution")
            st.bar_chart(filtered_df[moisture_col].astype(str).value_counts())

        if ndvi_col:
            st.write("NDVI Summary")
            st.dataframe(filtered_df[[ndvi_col]].describe())

        if ndmi_col:
            st.write("NDMI Summary")
            st.dataframe(filtered_df[[ndmi_col]].describe())

# ---------------- PRIORITY TAB ----------------
with tab3:
    st.subheader("Priority Grids for Field Action")

    display_cols = []

    for col in [
        grid_col,
        risk_col,
        health_col,
        moisture_col,
        ndvi_col,
        ndmi_col,
        fire_col,
        action_col,
        lat_col,
        lon_col,
    ]:
        if col and col not in display_cols:
            display_cols.append(col)

    priority_df = filtered_df.copy()

    if risk_col:
        priority_df["_risk_order"] = priority_df[risk_col].astype(str).str.upper().map(
            {
                "CRITICAL": 1,
                "VERY HIGH": 2,
                "HIGH": 3,
                "MEDIUM": 4,
                "MODERATE": 4,
                "LOW": 5,
            }
        ).fillna(9)

        priority_df = priority_df.sort_values("_risk_order")

    if display_cols:
        st.dataframe(priority_df[display_cols], use_container_width=True)
    else:
        st.dataframe(priority_df, use_container_width=True)

# ---------------- RAW DATA TAB ----------------
with tab4:
    st.subheader("Complete FRIS CSV Data")
    st.dataframe(filtered_df, use_container_width=True)

    csv_download = filtered_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download Filtered CSV",
        data=csv_download,
        file_name="fris_filtered_data.csv",
        mime="text/csv"
    )

# ---------------- FOOTER ----------------
st.markdown("---")
st.caption("FRIS Dashboard | Godda Forest Division | Auto-refresh every 60 seconds")