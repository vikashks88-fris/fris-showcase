import os
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="Godda FRIS Dashboard",
    page_icon="🌲",
    layout="wide"
)

# Auto refresh every 60 seconds
st_autorefresh(interval=60000, key="fris_auto_refresh")

# --------------------------------------------------
# FILE PATHS
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")

CSV_FILE = os.path.join(DATA_DIR, "fris_latest.csv")
GEOJSON_FILE = os.path.join(DATA_DIR, "fris_latest.geojson")
MAP_FILE = os.path.join(DATA_DIR, "fris_latest_map.html")

# --------------------------------------------------
# SAFE CSV LOADER
# --------------------------------------------------
def load_csv():
    if not os.path.exists(CSV_FILE):
        return None, f"CSV not found at: {CSV_FILE}"

    try:
        df = pd.read_csv(CSV_FILE)

        if df.empty:
            return None, "CSV file is empty."

        return df, None

    except Exception as e:
        return None, f"CSV reading error: {e}"


df, csv_error = load_csv()

# --------------------------------------------------
# STOP SAFELY IF CSV ERROR
# --------------------------------------------------
if df is None:
    st.title("🌲 Godda FRIS Dashboard")
    st.error("FRIS CSV not loaded.")
    st.write(csv_error)

    st.info("Keep files exactly like this:")

    st.code(
        """
fris-showcase/
├── app.py
├── requirements.txt
└── data/
    ├── fris_latest.csv
    ├── fris_latest.geojson
    └── fris_latest_map.html
        """,
        language="text"
    )

    st.stop()

# --------------------------------------------------
# SAFE COLUMN FUNCTION
# --------------------------------------------------
def get_col(possible_names):
    for name in possible_names:
        if name in df.columns:
            return name
    return None


grid_col = get_col(["grid_id", "Grid ID", "GRID_ID"])
risk_col = get_col(["risk_class", "final_priority", "priority_class", "Risk Class"])
health_col = get_col(["health_class", "forest_health", "vegetation_health"])
moisture_col = get_col(["moisture_class", "moisture_status"])
ndvi_col = get_col(["ndvi", "NDVI"])
ndmi_col = get_col(["ndmi", "NDMI"])
fire_col = get_col(["active_fire", "fire_detected", "fire_status"])
action_col = get_col(["patrol_action", "recommended_action", "action"])
lat_col = get_col(["lat_center", "latitude", "lat"])
lon_col = get_col(["lon_center", "longitude", "lon"])

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.title("🌲 FRIS Control Panel")

st.sidebar.success("CSV loaded successfully")

st.sidebar.write("### Data Status")
st.sidebar.write(f"Total Records: **{len(df)}**")

if risk_col:
    risk_options = ["All"] + sorted(df[risk_col].dropna().astype(str).unique().tolist())
    selected_risk = st.sidebar.selectbox("Filter by Risk", risk_options)
else:
    selected_risk = "All"

if grid_col:
    search_grid = st.sidebar.text_input("Search Grid ID")
else:
    search_grid = ""

# --------------------------------------------------
# APPLY FILTERS
# --------------------------------------------------
filtered_df = df.copy()

if risk_col and selected_risk != "All":
    filtered_df = filtered_df[filtered_df[risk_col].astype(str) == selected_risk]

if grid_col and search_grid:
    filtered_df = filtered_df[
        filtered_df[grid_col].astype(str).str.contains(search_grid, case=False, na=False)
    ]

# --------------------------------------------------
# TITLE
# --------------------------------------------------
st.title("🌲 Godda FRIS Dashboard")
st.caption("Forest Resilience Information System | Live Forest Health, Moisture, Fire & Patrol Intelligence")

# --------------------------------------------------
# TOP METRICS
# --------------------------------------------------
m1, m2, m3, m4 = st.columns(4)

m1.metric("Total Grids", len(df))
m2.metric("Filtered Grids", len(filtered_df))

if risk_col:
    high_count = df[df[risk_col].astype(str).str.upper().str.contains("HIGH", na=False)].shape[0]
    critical_count = df[df[risk_col].astype(str).str.upper().str.contains("CRITICAL", na=False)].shape[0]
else:
    high_count = 0
    critical_count = 0

m3.metric("High Risk", high_count)
m4.metric("Critical Risk", critical_count)

# --------------------------------------------------
# MAP SECTION
# --------------------------------------------------
st.subheader("🗺️ FRIS Operational Map")

if os.path.exists(MAP_FILE):
    with open(MAP_FILE, "r", encoding="utf-8") as f:
        map_html = f.read()

    st.components.v1.html(map_html, height=650, scrolling=True)
else:
    st.warning("Map file not found: data/fris_latest_map.html")

# --------------------------------------------------
# GRID-WISE INFORMATION
# --------------------------------------------------
st.subheader("📍 Grid-wise Forest Intelligence")

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
    lon_col
]:
    if col and col not in display_cols:
        display_cols.append(col)

if display_cols:
    st.dataframe(
        filtered_df[display_cols],
        use_container_width=True,
        height=400
    )
else:
    st.dataframe(filtered_df, use_container_width=True, height=400)

# --------------------------------------------------
# RISK SUMMARY
# --------------------------------------------------
if risk_col:
    st.subheader("⚠️ Risk Summary")

    risk_summary = (
        df[risk_col]
        .fillna("UNKNOWN")
        .astype(str)
        .value_counts()
        .reset_index()
    )

    risk_summary.columns = ["Risk Class", "Grid Count"]

    st.dataframe(risk_summary, use_container_width=True)

# --------------------------------------------------
# ACTION / INFERENCE SECTION
# --------------------------------------------------
st.subheader("🚶 Patrol & Field Action Guidance")

if action_col:
    action_df = filtered_df[[grid_col, risk_col, action_col]].copy() if grid_col and risk_col else filtered_df[[action_col]].copy()
    st.dataframe(action_df, use_container_width=True, height=350)
else:
    st.info("No patrol action column found in CSV.")

# --------------------------------------------------
# DOWNLOAD SECTION
# --------------------------------------------------
st.subheader("⬇️ Download FRIS Data")

csv_download = filtered_df.to_csv(index=False).encode("utf-8")

st.download_button(
    label="Download Filtered CSV",
    data=csv_download,
    file_name="filtered_fris_data.csv",
    mime="text/csv"
)

# --------------------------------------------------
# FOOTER
# --------------------------------------------------
st.divider()
st.caption("FRIS Dashboard | Godda Forest Division | Data refreshes automatically every 60 seconds")