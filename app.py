import os
import json
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_folium import st_folium
import folium
import plotly.express as px


# =========================
# PAGE CONFIG
# =========================

st.set_page_config(
    page_title="Godda FRIS Dashboard",
    page_icon="🌳",
    layout="wide"
)

st_autorefresh(interval=30000, key="fris_refresh")


# =========================
# PATH CONFIG
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CSV_FILE = os.path.join(DATA_DIR, "fris_latest.csv")
GEOJSON_FILE = os.path.join(DATA_DIR, "fris_latest.geojson")


# =========================
# HELPER FUNCTIONS
# =========================

@st.cache_data(ttl=30)
def load_csv(path):
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


@st.cache_data(ttl=30)
def load_geojson(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_col(df, names):
    for name in names:
        if name in df.columns:
            return name
    return None


def normalize_risk(value):
    value = str(value).upper()

    if "CRITICAL" in value:
        return "CRITICAL"
    if "HIGH" in value:
        return "HIGH"
    if "MODERATE" in value or "MEDIUM" in value:
        return "MODERATE"
    if "LOW" in value:
        return "LOW"

    return "UNKNOWN"


def risk_hex(value):
    risk = normalize_risk(value)

    if risk == "CRITICAL":
        return "#d73027"
    if risk == "HIGH":
        return "#fc8d59"
    if risk == "MODERATE":
        return "#fee08b"
    if risk == "LOW":
        return "#1a9850"

    return "#999999"


def risk_color(value):
    risk = normalize_risk(value)

    if risk == "CRITICAL":
        return "red"
    if risk == "HIGH":
        return "orange"
    if risk == "MODERATE":
        return "yellow"
    if risk == "LOW":
        return "green"

    return "gray"


def make_reason(row):
    reasons = []

    ndvi = row.get("NDVI", row.get("ndvi", None))
    ndmi = row.get("NDMI", row.get("ndmi", None))

    try:
        if pd.notna(ndvi):
            ndvi = float(ndvi)
            if ndvi < 0.35:
                reasons.append("low vegetation health")
            elif ndvi < 0.50:
                reasons.append("moderate vegetation stress")
    except Exception:
        pass

    try:
        if pd.notna(ndmi):
            ndmi = float(ndmi)
            if ndmi < 0.00:
                reasons.append("severe moisture stress")
            elif ndmi < 0.15:
                reasons.append("dryness signal")
    except Exception:
        pass

    for c in ["active_fire", "fire_active", "fire_detected"]:
        if c in row.index:
            if str(row.get(c)).lower() in ["true", "1", "yes", "y"]:
                reasons.append("active fire alert")

    for c in [
        "mining_pressure",
        "mine_pressure",
        "mining_influence",
        "mine_influence",
        "distance_to_mine_m"
    ]:
        if c in row.index and pd.notna(row.get(c)):
            reasons.append(
                "ecological pressure near anthropogenic/mining influence zone"
            )
            break

    if not reasons:
        return "Routine monitoring recommended"

    return ", ".join(reasons).capitalize()


def make_action(row):
    risk = normalize_risk(
        row.get(
            "risk_class",
            row.get("final_priority", row.get("patrol_priority", ""))
        )
    )

    if risk == "CRITICAL":
        return "Immediate field verification"
    if risk == "HIGH":
        return "Same-day priority patrol"
    if risk == "MODERATE":
        return "Monitor within 24–48 hours"
    if risk == "LOW":
        return "Routine patrol"

    return "Review grid"


def build_map(df, geojson_data, lat_col, lon_col, grid_col, risk_col):
    if lat_col and lon_col and not df.empty:
        center_lat = df[lat_col].astype(float).mean()
        center_lon = df[lon_col].astype(float).mean()
    else:
        center_lat = 24.8
        center_lon = 87.2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=10,
        tiles=None
    )

    folium.TileLayer(
        tiles="CartoDB positron",
        name="CartoDB Light",
        control=True
    ).add_to(m)

    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri Satellite",
        name="Satellite",
        control=True
    ).add_to(m)

    if geojson_data:

        def style_function(feature):
            props = feature.get("properties", {})
            risk_value = props.get(
                risk_col,
                props.get("risk_class", props.get("final_priority", "UNKNOWN"))
            )

            return {
                "fillColor": risk_hex(risk_value),
                "color": "#333333",
                "weight": 0.5,
                "fillOpacity": 0.45
            }

        def popup_function(feature):
            props = feature.get("properties", {})

            grid = props.get(grid_col, props.get("grid_id", "Unknown"))
            risk = props.get(
                risk_col,
                props.get("risk_class", props.get("final_priority", "Unknown"))
            )
            ndvi = props.get("NDVI", props.get("ndvi", "NA"))
            ndmi = props.get("NDMI", props.get("ndmi", "NA"))

            html = f"""
            <b>Grid:</b> {grid}<br>
            <b>Risk:</b> {risk}<br>
            <b>NDVI:</b> {ndvi}<br>
            <b>NDMI:</b> {ndmi}<br>
            <b>Note:</b> Satellite-assisted ecological monitoring
            """

            return folium.Popup(html, max_width=320)

        folium.GeoJson(
            geojson_data,
            name="FRIS Grid Layer",
            style_function=style_function,
            popup=popup_function
        ).add_to(m)

    if lat_col and lon_col:
        for _, row in df.iterrows():
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
            except Exception:
                continue

            risk = row.get(risk_col, "UNKNOWN") if risk_col else "UNKNOWN"
            grid = row.get(grid_col, "Unknown Grid") if grid_col else "Unknown Grid"

            popup_html = f"""
            <b>Grid:</b> {grid}<br>
            <b>Risk:</b> {risk}<br>
            <b>Reason:</b> {row.get("reason_to_go", "Review grid")}<br>
            <b>Action:</b> {row.get("recommended_action", "Review")}
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=4,
                color=risk_color(risk),
                fill=True,
                fill_opacity=0.75,
                popup=folium.Popup(popup_html, max_width=350)
            ).add_to(m)

    folium.LayerControl().add_to(m)

    return m


# =========================
# HEADER
# =========================

st.title("🌳 Godda FRIS Dynamic Dashboard")

st.caption(
    "Forest health, moisture stress, fire alerts, ecological pressure, "
    "and preliminary carbon-readiness monitoring."
)

st.info(
    "Mining/industrial influence is shown only as ecological pressure context. "
    "It does not confirm mining damage or legal responsibility."
)


# =========================
# FILE CHECK
# =========================

if not os.path.exists(CSV_FILE):
    st.error("No FRIS CSV found.")

    st.write("Keep files like this:")

    st.code(
        """
fris_showcase/
├── app.py
├── requirements.txt
└── data/
    ├── fris_latest.csv
    └── fris_latest.geojson
        """,
        language="text"
    )

    st.stop()


df = load_csv(CSV_FILE)

if df is None or df.empty:
    st.error("CSV file is empty or unreadable.")
    st.stop()


geojson_data = load_geojson(GEOJSON_FILE)


# =========================
# COLUMN DETECTION
# =========================

risk_col = get_col(df, ["risk_class", "final_priority", "patrol_priority"])
health_col = get_col(df, ["health_class", "forest_health", "vegetation_health"])
moisture_col = get_col(df, ["moisture_class", "moisture_status"])
grid_col = get_col(df, ["grid_id", "grid", "id"])
lat_col = get_col(df, ["lat_center", "latitude", "lat"])
lon_col = get_col(df, ["lon_center", "longitude", "lon"])
maps_col = get_col(df, ["google_maps_link", "maps_link", "navigation_link"])

if risk_col:
    df["risk_normalized"] = df[risk_col].apply(normalize_risk)
else:
    df["risk_normalized"] = "UNKNOWN"

df["reason_to_go"] = df.apply(make_reason, axis=1)
df["recommended_action"] = df.apply(make_action, axis=1)


# =========================
# SIDEBAR FILTERS
# =========================

st.sidebar.title("🔎 FRIS Filters")

risk_options = ["ALL"] + sorted(df["risk_normalized"].dropna().unique().tolist())

selected_risk = st.sidebar.selectbox("Risk Class", risk_options)
search_grid = st.sidebar.text_input("Search Grid ID")

show_only_fire = st.sidebar.checkbox("Show only fire-related grids", value=False)
show_only_pressure = st.sidebar.checkbox(
    "Show only ecological pressure grids",
    value=False
)

filtered_df = df.copy()

if selected_risk != "ALL":
    filtered_df = filtered_df[filtered_df["risk_normalized"] == selected_risk]

if search_grid and grid_col:
    filtered_df = filtered_df[
        filtered_df[grid_col]
        .astype(str)
        .str.contains(search_grid, case=False, na=False)
    ]

if show_only_fire:
    fire_cols = [c for c in filtered_df.columns if "fire" in c.lower()]

    if fire_cols:
        mask = pd.Series(False, index=filtered_df.index)

        for c in fire_cols:
            mask = mask | filtered_df[c].astype(str).str.lower().isin(
                ["true", "1", "yes", "y"]
            )

        filtered_df = filtered_df[mask]

if show_only_pressure:
    pressure_cols = [
        c for c in filtered_df.columns
        if "mine" in c.lower()
        or "mining" in c.lower()
        or "pressure" in c.lower()
        or "disturbance" in c.lower()
    ]

    if pressure_cols:
        filtered_df = filtered_df[
            filtered_df[pressure_cols].notna().any(axis=1)
        ]


# =========================
# METRICS
# =========================

total_grids = len(filtered_df)
critical = int((filtered_df["risk_normalized"] == "CRITICAL").sum())
high = int((filtered_df["risk_normalized"] == "HIGH").sum())
moderate = int((filtered_df["risk_normalized"] == "MODERATE").sum())
low = int((filtered_df["risk_normalized"] == "LOW").sum())

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Visible Grids", total_grids)
c2.metric("Critical", critical)
c3.metric("High", high)
c4.metric("Moderate", moderate)
c5.metric("Low", low)


# =========================
# TABS
# =========================

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "🗺️ Live Map",
        "📊 Live Charts",
        "📋 Grid Table",
        "⛏️ Ecological Pressure",
        "🌱 Carbon Readiness"
    ]
)


# =========================
# TAB 1: LIVE MAP
# =========================

with tab1:
    st.subheader("Live Dynamic FRIS Map")

    if filtered_df.empty:
        st.warning("No grids match the selected filters.")
    else:
        live_map = build_map(
            filtered_df,
            geojson_data,
            lat_col,
            lon_col,
            grid_col,
            risk_col
        )

        st_folium(live_map, width=None, height=720)


# =========================
# TAB 2: LIVE CHARTS
# =========================

with tab2:
    st.subheader("Real-Time FRIS Charts")

    risk_chart = (
        filtered_df["risk_normalized"]
        .value_counts()
        .reset_index()
    )

    risk_chart.columns = ["Risk Class", "Count"]

    fig_risk = px.bar(
        risk_chart,
        x="Risk Class",
        y="Count",
        title="Risk Class Distribution"
    )

    st.plotly_chart(fig_risk, use_container_width=True)

    ndvi_col = get_col(filtered_df, ["NDVI", "ndvi"])
    ndmi_col = get_col(filtered_df, ["NDMI", "ndmi"])

    if ndvi_col:
        fig_ndvi = px.histogram(
            filtered_df,
            x=ndvi_col,
            title="NDVI Distribution"
        )
        st.plotly_chart(fig_ndvi, use_container_width=True)

    if ndmi_col:
        fig_ndmi = px.histogram(
            filtered_df,
            x=ndmi_col,
            title="NDMI Distribution"
        )
        st.plotly_chart(fig_ndmi, use_container_width=True)


# =========================
# TAB 3: GRID TABLE
# =========================

with tab3:
    st.subheader("Grid-Wise Field Intelligence")

    display_cols = []

    for c in [
        grid_col,
        risk_col,
        health_col,
        moisture_col,
        "NDVI",
        "ndvi",
        "NDMI",
        "ndmi",
        "reason_to_go",
        "recommended_action",
        maps_col
    ]:
        if c and c in filtered_df.columns and c not in display_cols:
            display_cols.append(c)

    if display_cols:
        st.dataframe(filtered_df[display_cols], use_container_width=True)
    else:
        st.dataframe(filtered_df, use_container_width=True)

    st.download_button(
        "Download Filtered FRIS CSV",
        filtered_df.to_csv(index=False),
        file_name="filtered_fris_output.csv",
        mime="text/csv"
    )


# =========================
# TAB 4: ECOLOGICAL PRESSURE
# =========================

with tab4:
    st.subheader("Ecological Pressure Monitoring")

    pressure_cols = [
        c for c in filtered_df.columns
        if "mine" in c.lower()
        or "mining" in c.lower()
        or "pressure" in c.lower()
        or "disturbance" in c.lower()
    ]

    if pressure_cols:
        st.dataframe(filtered_df[pressure_cols], use_container_width=True)
    else:
        st.info("No ecological pressure columns found in this CSV.")

    st.warning(
        "This section does not confirm mining damage. "
        "It only shows ecological pressure indicators where available."
    )

    st.markdown(
        """
        **Safe wording:**  
        Ecological stress observed near anthropogenic/mining influence zone.

        **Avoid wording:**  
        Mining damage confirmed.
        """
    )


# =========================
# TAB 5: CARBON READINESS
# =========================

with tab5:
    st.subheader("Preliminary Carbon Opportunity")

    carbon_cols = [
        c for c in filtered_df.columns
        if "carbon" in c.lower()
        or "co2" in c.lower()
        or "credit" in c.lower()
        or "biomass" in c.lower()
        or "gedi" in c.lower()
        or "hansen" in c.lower()
    ]

    if carbon_cols:
        st.dataframe(filtered_df[carbon_cols], use_container_width=True)
    else:
        st.info("No carbon-related columns found in this CSV.")

    st.error(
        "These estimates are satellite-assisted preliminary ecological indicators "
        "and do not represent verified carbon credits or certified MRV outputs."
    )


# =========================
# FOOTER
# =========================

st.divider()

st.caption(
    "FRIS — Forest Resilience Information System | Dynamic dashboard refreshed every 30 seconds"
)