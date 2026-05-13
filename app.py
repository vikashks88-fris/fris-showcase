import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


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
# BASIC STYLE
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

    .stMetric {
        background: white;
        padding: 18px;
        border-radius: 14px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }

    .success-box {
        background-color: #e9f7ef;
        color: #1e5631;
        padding: 14px 18px;
        border-radius: 10px;
        border-left: 5px solid #2e7d32;
        margin-bottom: 18px;
    }

    .warn-box {
        background-color: #fff4e5;
        color: #7a4a00;
        padding: 14px 18px;
        border-radius: 10px;
        border-left: 5px solid #f59e0b;
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

    .small-text {
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

def file_status(path: Path, label: str):
    if path.exists():
        st.sidebar.success(f"✅ {label}")
    else:
        st.sidebar.error(f"❌ {label}")

file_status(CSV_PATH, "fris_latest.csv")
file_status(GEOJSON_PATH, "fris_latest.geojson")
file_status(MAP_PATH, "fris_latest_map.html")

st.sidebar.divider()

if st.sidebar.button("🔄 Refresh now"):
    st.rerun()

st.sidebar.caption(f"Last page refresh: {time.strftime('%Y-%m-%d %H:%M:%S')}")


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
    """
    Finds the first matching column from a list of possible names.
    """
    for name in possible_names:
        if name in df.columns:
            return name
    return None


def safe_count(column_name, value_keywords):
    """
    Counts rows where column contains any keyword.
    """
    if column_name is None:
        return 0

    series = df[column_name].astype(str).str.upper()

    count = 0
    for keyword in value_keywords:
        count += series.str.contains(keyword.upper(), na=False).sum()

    return int(count)


def safe_numeric(column_name):
    """
    Converts a column to numeric safely.
    """
    if column_name is None:
        return pd.Series(dtype="float64")

    return pd.to_numeric(df[column_name], errors="coerce")


def get_first_existing(columns):
    for col in columns:
        if col in df.columns:
            return col
    return None


# ============================================================
# COLUMN DETECTION
# ============================================================

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

grid_col = find_col(
    [
        "grid_id",
        "grid",
        "cell_id",
        "id",
    ]
)

lat_col = find_col(
    [
        "lat_center",
        "latitude",
        "lat",
        "center_lat",
    ]
)

lon_col = find_col(
    [
        "lon_center",
        "longitude",
        "lon",
        "center_lon",
    ]
)

ndvi_col = find_col(["NDVI", "ndvi", "mean_ndvi"])
ndmi_col = find_col(["NDMI", "ndmi", "mean_ndmi"])


# ============================================================
# METRIC CALCULATIONS
# ============================================================

total_grids = len(df)

critical_grids = safe_count(risk_col, ["CRITICAL", "VERY HIGH"])
high_grids = safe_count(risk_col, ["HIGH"])

if fire_col:
    fire_series = df[fire_col].astype(str).str.upper()
    active_fires = int(
        fire_series.isin(["TRUE", "YES", "1", "ACTIVE"]).sum()
        + fire_series.str.contains("ACTIVE", na=False).sum()
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

m1.metric("Total Forest Grids", f"{total_grids}")
m2.metric("Critical Grids", f"{critical_grids}")
m3.metric("High Priority Grids", f"{high_grids}")
m4.metric("Active Fire Alerts", f"{active_fires}")


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
# TAB 1 — MAP
# ============================================================

with tab_map:
    st.subheader("FRIS Operational Map")

    if not MAP_PATH.exists():
        st.error("Map file not found: fris_latest_map.html")
    else:
        try:
            with open(MAP_PATH, "r", encoding="utf-8") as f:
                map_html = f.read()

            if len(map_html.strip()) < 100:
                st.warning("Map HTML file exists, but it looks empty or incomplete.")
            else:
                components.html(
                    map_html,
                    height=750,
                    scrolling=True,
                )

        except UnicodeDecodeError:
            try:
                with open(MAP_PATH, "r", encoding="latin-1") as f:
                    map_html = f.read()

                components.html(
                    map_html,
                    height=750,
                    scrolling=True,
                )

            except Exception as e:
                st.error(f"Map loading failed: {e}")

        except Exception as e:
            st.error(f"Map loading failed: {e}")


# ============================================================
# TAB 2 — PRIORITY GRIDS
# ============================================================

with tab_priority:
    st.subheader("Priority Patrol Grids")

    if risk_col is None:
        st.warning("No risk / priority column found in CSV.")
        st.dataframe(df, use_container_width=True, height=500)
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
            show_cols = []

            for col in [
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
            ]:
                if col and col in priority_df.columns and col not in show_cols:
                    show_cols.append(col)

            st.dataframe(
                priority_df[show_cols] if show_cols else priority_df,
                use_container_width=True,
                height=550,
            )


# ============================================================
# TAB 3 — GRID DATA
# ============================================================

with tab_grid:
    st.subheader("Grid-wise FRIS Data")

    search_text = st.text_input(
        "Search grid / keyword",
        placeholder="Example: GD-10-20, HIGH, STRESSED, fire...",
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
        height=600,
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
            st.warning("No health classification column found.")

    with c2:
        st.markdown("### Moisture Classification")

        if moisture_col:
            moisture_summary = df[moisture_col].astype(str).value_counts().reset_index()
            moisture_summary.columns = ["Moisture Class", "Grid Count"]
            st.dataframe(moisture_summary, use_container_width=True)
            st.bar_chart(moisture_summary.set_index("Moisture Class"))
        else:
            st.warning("No moisture classification column found.")

    st.divider()

    st.markdown("### NDVI / NDMI Overview")

    n1, n2 = st.columns(2)

    with n1:
        if ndvi_col:
            ndvi_series = safe_numeric(ndvi_col)
            st.metric("Average NDVI", round(ndvi_series.mean(), 4))
            st.line_chart(ndvi_series.dropna().reset_index(drop=True))
        else:
            st.warning("NDVI column not found.")

    with n2:
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

    carbon_total_col = get_first_existing(
        [
            "ecosystem_carbon_total_ton",
            "estimated_ecosystem_carbon_ton",
            "carbon_total_ton",
            "baseline_ecosystem_carbon_total_ton",
        ]
    )

    carbon_change_col = get_first_existing(
        [
            "carbon_change_co2e_ton",
            "carbon_change_ton",
            "carbon_change_CO2e",
        ]
    )

    credit_col = get_first_existing(
        [
            "potential_carbon_credits",
            "potential_credit_ton_co2e",
            "carbon_credit_potential",
        ]
    )

    cm1, cm2, cm3 = st.columns(3)

    with cm1:
        if carbon_total_col:
            total_carbon = safe_numeric(carbon_total_col).sum()
            st.metric("Estimated Ecosystem Carbon", round(total_carbon, 4))
        else:
            st.metric("Estimated Ecosystem Carbon", "N/A")

    with cm2:
        if carbon_change_col:
            total_change = safe_numeric(carbon_change_col).sum()
            st.metric("Carbon Change CO₂e", round(total_change, 4))
        else:
            st.metric("Carbon Change CO₂e", "N/A")

    with cm3:
        if credit_col:
            total_credit = safe_numeric(credit_col).sum()
            st.metric("Potential Carbon Credits", round(total_credit, 4))
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
            height=500,
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