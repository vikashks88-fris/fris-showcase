import time
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import folium
import geopandas as gpd


# ============================================================
# GODDA FRIS DASHBOARD
# Forest Resilience Information System
# ============================================================

st.set_page_config(
    page_title="Godda FRIS Dashboard",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# PATH SETTINGS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

CSV_PATH = DATA_DIR / "fris_latest.csv"
GEOJSON_PATH = DATA_DIR / "fris_latest.geojson"
MAP_PATH = DATA_DIR / "fris_latest_map.html"


# ============================================================
# PAGE STYLE
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

    .warning-box {
        background-color: #fff7ed;
        color: #9a3412;
        padding: 14px 18px;
        border-radius: 10px;
        border-left: 5px solid #f97316;
        margin-bottom: 18px;
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

st.sidebar.caption(f"Last page refresh: {time.strftime('%Y-%m-%d %H:%M:%S')}")


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
        Keep these files inside the `data` folder:

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


def safe_numeric(column_name):
    if column_name and column_name in df.columns:
        return pd.to_numeric(df[column_name], errors="coerce")
    return pd.Series(dtype="float64")


def safe_count(column_name, keywords):
    if not column_name or column_name not in df.columns:
        return 0

    text_data = df[column_name].astype(str).str.upper()

    count = 0
    for keyword in keywords:
        count += text_data.str.contains(keyword.upper(), na=False).sum()

    return int(count)


def existing_cols(columns):
    return [col for col in columns if col and col in df.columns]


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
        "vegetation_health",
        "health_status",
    ]
)

moisture_col = find_col(
    [
        "moisture_class",
        "moisture_status",
        "moisture_class_calibrated",
        "ndmi_class",
        "water_stress_class",
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

lat_col = find_col(
    [
        "lat",
        "lat_center",
        "latitude",
        "center_lat",
    ]
)

lon_col = find_col(
    [
        "lon",
        "lon_center",
        "longitude",
        "center_lon",
    ]
)

ndvi_col = find_col(["ndvi", "NDVI", "mean_ndvi"])
ndmi_col = find_col(["ndmi", "NDMI", "mean_ndmi"])


# ============================================================
# METRICS
# ============================================================

total_grids = len(df)
critical_grids = safe_count(risk_col, ["CRITICAL", "VERY HIGH"])
high_grids = safe_count(risk_col, ["HIGH", "FIRE_CHECK"])

if fire_col:
    fire_text = df[fire_col].astype(str).str.upper()
    active_fires = int(
        fire_text.str.contains("TRUE|YES|ACTIVE|1", na=False).sum()
    )
else:
    active_fires = 0


# ============================================================
# MAIN HEADER
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
m3.metric("High Priority / Fire Check Grids", high_grids)
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
# TAB 1 — LIGHTWEIGHT GEOJSON MAP
# ============================================================

with tab_map:
    st.subheader("FRIS Operational Map")

    st.markdown(
        """
        <div class="warning-box">
            Map is rendered from GeoJSON in lightweight mode for Render stability.
            First 300 grid polygons are shown to keep the dashboard fast.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not GEOJSON_PATH.exists():
        st.error("GeoJSON file not found: fris_latest.geojson")

    else:
        try:
            gdf = gpd.read_file(GEOJSON_PATH)

            if gdf.empty:
                st.error("GeoJSON loaded but contains no features.")
            else:
                # Keep map light for Render
                max_features = 300
                gdf_map = gdf.head(max_features).copy()

                # Ensure CRS is WGS84
                try:
                    if gdf_map.crs is not None and str(gdf_map.crs).upper() != "EPSG:4326":
                        gdf_map = gdf_map.to_crs(epsg=4326)
                except Exception:
                    pass

                # Center map
                if lat_col and lon_col:
                    lat_values = pd.to_numeric(df[lat_col], errors="coerce").dropna()
                    lon_values = pd.to_numeric(df[lon_col], errors="coerce").dropna()

                    if not lat_values.empty and not lon_values.empty:
                        center_lat = float(lat_values.mean())
                        center_lon = float(lon_values.mean())
                    else:
                        center_lat = float(gdf_map.geometry.centroid.y.mean())
                        center_lon = float(gdf_map.geometry.centroid.x.mean())
                else:
                    center_lat = float(gdf_map.geometry.centroid.y.mean())
                    center_lon = float(gdf_map.geometry.centroid.x.mean())

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

                folium.TileLayer(
                    tiles="CartoDB positron",
                    name="Light Map",
                    overlay=False,
                    control=True,
                ).add_to(m)

                def get_color(row):
                    priority = str(
                        row.get("final_priority", "")
                        or row.get("risk_class", "")
                        or row.get("patrol_priority", "")
                    ).upper()

                    health = str(row.get("health_class", "")).upper()
                    fire = str(
                        row.get("fire_detected", "")
                        or row.get("active_fire", "")
                    ).upper()

                    if "TRUE" in fire or "ACTIVE" in fire or fire == "1":
                        return "#b91c1c"

                    if "CRITICAL" in priority or "FIRE_CHECK" in priority:
                        return "#dc2626"

                    if "HIGH" in priority:
                        return "#f97316"

                    if "MEDIUM" in priority or "MODERATE" in priority:
                        return "#facc15"

                    if "STRESSED" in health:
                        return "#f59e0b"

                    return "#2e7d32"

                for _, row in gdf_map.iterrows():
                    color = get_color(row)

                    grid_value = row.get("grid_id", "N/A")
                    priority_value = (
                        row.get("final_priority", None)
                        or row.get("risk_class", None)
                        or row.get("patrol_priority", "N/A")
                    )

                    popup_text = f"""
                    <div style="font-family: Arial; font-size: 13px;">
                        <b>Grid:</b> {grid_value}<br>
                        <b>Priority:</b> {priority_value}<br>
                        <b>Health:</b> {row.get("health_class", "N/A")}<br>
                        <b>Moisture:</b> {row.get("moisture_class_calibrated", row.get("moisture_class", "N/A"))}<br>
                        <b>NDVI:</b> {clean_number(row.get("ndvi", row.get("NDVI", "N/A")))}<br>
                        <b>NDMI:</b> {clean_number(row.get("ndmi", row.get("NDMI", "N/A")))}<br>
                        <b>Fire:</b> {row.get("fire_detected", row.get("active_fire", "N/A"))}<br>
                        <b>Action:</b> {row.get("patrol_action", "N/A")}<br>
                    </div>
                    """

                    folium.GeoJson(
                        row.geometry,
                        style_function=lambda feature, color=color: {
                            "fillColor": color,
                            "color": color,
                            "weight": 1,
                            "fillOpacity": 0.55,
                        },
                        tooltip=f"Grid: {grid_value} | Priority: {priority_value}",
                        popup=folium.Popup(popup_text, max_width=350),
                    ).add_to(m)

                folium.LayerControl(collapsed=False).add_to(m)

                components.html(
                    m._repr_html_(),
                    height=760,
                    scrolling=True,
                )

                st.caption(
                    f"Showing {len(gdf_map)} of {len(gdf)} GeoJSON grid features. "
                    "This keeps Render stable. Full grid table remains available in the Grid Data tab."
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
                    "recommended_response_time",
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

st.caption(
    "FRIS Dashboard | Forest Resilience Information System | Godda Forest Division Pilot"
)