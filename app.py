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
    .main { background-color: #f7faf7; }

    h1, h2, h3 { color: #24382f; }

    .success-box {
        background-color: #e9f7ef;
        color: #1e5631;
        padding: 14px 18px;
        border-radius: 10px;
        border-left: 5px solid #2e7d32;
        margin-bottom: 18px;
    }

    .warning-box {
        background-color: #fff7ed;
        color: #9a3412;
        padding: 14px 18px;
        border-radius: 10px;
        border-left: 5px solid #f97316;
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

st.sidebar.markdown("### Data folder")
st.sidebar.code(str(DATA_DIR))

st.sidebar.markdown("### Required files")


def check_file(path: Path, name: str):
    if path.exists():
        st.sidebar.success(f"✅ {name}")
    else:
        st.sidebar.error(f"❌ {name}")


check_file(CSV_PATH, "fris_latest.csv")
check_file(GEOJSON_PATH, "fris_latest.geojson")
check_file(MAP_PATH, "fris_latest_map.html")

st.sidebar.divider()

if st.sidebar.button("🔄 Refresh now"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(f"Last refresh: {time.strftime('%Y-%m-%d %H:%M:%S')}")


# ============================================================
# LOAD CSV
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


def clean_number(value, digits=4):
    try:
        if pd.isna(value):
            return "N/A"
        return round(float(value), digits)
    except Exception:
        return value


# ============================================================
# COLUMN DETECTION
# ============================================================

grid_col = find_col(["grid_id", "grid", "cell_id", "id"])

risk_col = find_col(
    [
        "final_priority",
        "risk_class",
        "patrol_priority",
        "priority_class",
        "risk_category",
    ]
)

health_col = find_col(
    [
        "health_class",
        "forest_health",
        "vegetation_health",
        "health_status",
    ]
)

moisture_col = find_col(
    [
        "moisture_class_calibrated",
        "moisture_class",
        "moisture_status",
        "ndmi_class",
    ]
)

fire_col = find_col(
    [
        "fire_detected",
        "active_fire",
        "fire_alert",
        "fire_status",
    ]
)

lat_col = find_col(["lat", "lat_center", "latitude", "center_lat"])
lon_col = find_col(["lon", "lon_center", "longitude", "center_lon"])

ndvi_col = find_col(["ndvi", "NDVI", "mean_ndvi"])
ndmi_col = find_col(["ndmi", "NDMI", "mean_ndmi"])


# ============================================================
# METRICS
# ============================================================

total_grids = len(df)
critical_grids = safe_count(risk_col, ["CRITICAL"])
high_grids = safe_count(risk_col, ["HIGH", "FIRE_CHECK"])

if fire_col:
    fire_text = df[fire_col].astype(str).str.upper()
    active_fires = int(fire_text.str.contains("TRUE|YES|ACTIVE|1", na=False).sum())
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
# TAB 1 — CSV POINT MAP
# ============================================================

with tab_map:
    st.subheader("FRIS Operational Map")

    st.markdown(
        """
        <div class="warning-box">
            Map is now rendered from CSV latitude/longitude points.
            This avoids GeoJSON format problems on Render.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not lat_col or not lon_col:
        st.error("Latitude / longitude columns not found in CSV.")
    else:
        try:
            map_df = df.copy()

            map_df[lat_col] = pd.to_numeric(map_df[lat_col], errors="coerce")
            map_df[lon_col] = pd.to_numeric(map_df[lon_col], errors="coerce")

            map_df = map_df.dropna(subset=[lat_col, lon_col])

            if map_df.empty:
                st.error("CSV has lat/lon columns, but no valid coordinates.")
            else:
                center_lat = float(map_df[lat_col].mean())
                center_lon = float(map_df[lon_col].mean())

                m = folium.Map(
                    location=[center_lat, center_lon],
                    zoom_start=10,
                    tiles="CartoDB positron",
                    control_scale=True,
                )

                folium.TileLayer(
                    tiles=(
                        "https://server.arcgisonline.com/ArcGIS/rest/services/"
                        "World_Imagery/MapServer/tile/{z}/{y}/{x}"
                    ),
                    attr="Esri World Imagery",
                    name="Satellite",
                    overlay=False,
                    control=True,
                ).add_to(m)

                # Limit markers for Render speed
                max_points = 700
                map_df = map_df.head(max_points)

                def marker_color(row):
                    priority = str(row.get(risk_col, "")).upper() if risk_col else ""
                    health = str(row.get(health_col, "")).upper() if health_col else ""
                    fire = str(row.get(fire_col, "")).upper() if fire_col else ""

                    if "TRUE" in fire or "ACTIVE" in fire or fire == "1":
                        return "red"
                    if "FIRE_CHECK" in priority or "CRITICAL" in priority:
                        return "red"
                    if "HIGH" in priority:
                        return "orange"
                    if "MEDIUM" in priority or "MODERATE" in priority:
                        return "lightred"
                    if "STRESSED" in health:
                        return "orange"
                    return "green"

                for _, row in map_df.iterrows():
                    grid_value = row.get(grid_col, "N/A") if grid_col else "N/A"
                    priority_value = row.get(risk_col, "N/A") if risk_col else "N/A"
                    health_value = row.get(health_col, "N/A") if health_col else "N/A"
                    moisture_value = row.get(moisture_col, "N/A") if moisture_col else "N/A"
                    ndvi_value = row.get(ndvi_col, "N/A") if ndvi_col else "N/A"
                    ndmi_value = row.get(ndmi_col, "N/A") if ndmi_col else "N/A"
                    fire_value = row.get(fire_col, "N/A") if fire_col else "N/A"

                    popup_text = f"""
                    <div style="font-family: Arial; font-size: 13px;">
                        <b>Grid:</b> {grid_value}<br>
                        <b>Priority:</b> {priority_value}<br>
                        <b>Health:</b> {health_value}<br>
                        <b>Moisture:</b> {moisture_value}<br>
                        <b>NDVI:</b> {clean_number(ndvi_value)}<br>
                        <b>NDMI:</b> {clean_number(ndmi_value)}<br>
                        <b>Fire:</b> {fire_value}<br>
                        <b>Action:</b> {row.get("patrol_action", "N/A")}<br>
                    </div>
                    """

                    folium.Marker(
                        location=[row[lat_col], row[lon_col]],
                        popup=folium.Popup(popup_text, max_width=350),
                        tooltip=f"{grid_value} | {priority_value}",
                        icon=folium.Icon(color=marker_color(row), icon="tree", prefix="fa"),
                    ).add_to(m)

                folium.LayerControl(collapsed=False).add_to(m)

                components.html(
                    m._repr_html_(),
                    height=760,
                    scrolling=True,
                )

                st.caption(
                    f"Showing {len(map_df)} FRIS grid points from CSV. "
                    "GeoJSON polygon rendering is bypassed for Render stability."
                )

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
            .str.contains("CRITICAL|HIGH|VERY HIGH|FIRE_CHECK", na=False)
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
                    "fire_count",
                    "fire_frp_sum",
                    "patrol_action",
                    "google_maps_link",
                    "field_inference",
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
        placeholder="Example: GD-06-34, FIRE_CHECK, STRESSED, mining, fire...",
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
            st.metric("Average NDVI", clean_number(ndvi_series.mean()))
            st.line_chart(ndvi_series.dropna().reset_index(drop=True))
        else:
            st.warning("NDVI column not found.")

    with n2:
        st.markdown("### NDMI")

        if ndmi_col:
            ndmi_series = safe_numeric(ndmi_col)
            st.metric("Average NDMI", clean_number(ndmi_series.mean()))
            st.line_chart(ndmi_series.dropna().reset_index(drop=True))
        else:
            st.warning("NDMI column not found.")

    st.divider()

    selected_columns = existing_cols(
        [
            grid_col,
            health_col,
            moisture_col,
            ndvi_col,
            ndmi_col,
            "forest_pct",
            "terrain_class",
            "soil_type",
            "field_inference",
        ]
    )

    if selected_columns:
        st.markdown("### Field Interpretation")
        st.dataframe(df[selected_columns], use_container_width=True, height=450)


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
                clean_number(safe_numeric(carbon_total_col).sum()),
            )
        else:
            st.metric("Estimated Ecosystem Carbon", "N/A")

    with cm2:
        if carbon_change_col:
            st.metric(
                "Carbon Change CO₂e",
                clean_number(safe_numeric(carbon_change_col).sum()),
            )
        else:
            st.metric("Carbon Change CO₂e", "N/A")

    with cm3:
        if credit_col:
            st.metric(
                "Potential Carbon Credits",
                clean_number(safe_numeric(credit_col).sum()),
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