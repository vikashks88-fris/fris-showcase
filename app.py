import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Godda FRIS Dashboard",
    page_icon="🌳",
    layout="wide",
)


# =========================================================
# PATH SETTINGS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

CSV_PATH = DATA_DIR / "fris_latest.csv"
GEOJSON_PATH = DATA_DIR / "fris_latest.geojson"
MAP_PATH = DATA_DIR / "fris_latest_map.html"


# =========================================================
# AUTO REFRESH
# =========================================================

AUTO_REFRESH_SECONDS = 60

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

if time.time() - st.session_state.last_refresh > AUTO_REFRESH_SECONDS:
    st.session_state.last_refresh = time.time()
    st.rerun()


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def safe_col(df, col, default=None):
    if col in df.columns:
        return df[col]
    return pd.Series([default] * len(df))


def find_column(df, possible_names):
    for name in possible_names:
        if name in df.columns:
            return name
    return None


def classify_value(value):
    if pd.isna(value):
        return "UNKNOWN"
    return str(value).strip().upper()


def build_inference(row):
    risk = classify_value(row.get("risk_class", row.get("final_priority", "UNKNOWN")))
    health = classify_value(row.get("health_class", "UNKNOWN"))
    moisture = classify_value(row.get("moisture_class", "UNKNOWN"))
    active_fire = classify_value(row.get("active_fire", "NO"))

    ndvi = row.get("NDVI", row.get("ndvi", None))
    ndmi = row.get("NDMI", row.get("ndmi", None))

    reasons = []

    if active_fire in ["YES", "TRUE", "1", "ACTIVE"]:
        reasons.append("Active fire signal detected. Immediate field verification is required.")

    if risk in ["CRITICAL", "VERY HIGH"]:
        reasons.append("Critical priority grid. Visit immediately.")
    elif risk == "HIGH":
        reasons.append("High priority grid. Same-day patrol recommended.")
    elif risk == "MEDIUM":
        reasons.append("Moderate priority grid. Monitoring patrol recommended.")
    elif risk == "LOW":
        reasons.append("Low priority grid. Routine patrol is enough.")
    else:
        reasons.append("Priority unclear. Check satellite and field condition.")

    if health in ["STRESSED", "CRITICAL", "POOR"]:
        reasons.append("Vegetation health appears weak from NDVI/health classification.")

    if moisture in ["DRY", "CRITICAL", "LOW", "SEVERE"]:
        reasons.append("Moisture stress appears high from NDMI/moisture classification.")

    if ndvi is not None and pd.notna(ndvi):
        try:
            if float(ndvi) < 0.35:
                reasons.append("Low NDVI suggests weak vegetation greenness.")
        except Exception:
            pass

    if ndmi is not None and pd.notna(ndmi):
        try:
            if float(ndmi) < 0.10:
                reasons.append("Low NDMI suggests dry vegetation or moisture stress.")
        except Exception:
            pass

    return " ".join(reasons)


def load_data():
    if not CSV_PATH.exists():
        return None

    df = pd.read_csv(CSV_PATH)

    if "inference" not in df.columns:
        df["inference"] = df.apply(build_inference, axis=1)

    return df


def metric_card(label, value):
    st.metric(label=label, value=value)


# =========================================================
# LOAD CSV
# =========================================================

df = load_data()


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.title("🌳 Godda FRIS")
st.sidebar.caption("Forest Resilience Information System")

st.sidebar.markdown("---")
st.sidebar.write("**Data folder:**")
st.sidebar.code(str(DATA_DIR))

st.sidebar.write("**Required files:**")
st.sidebar.write("✅ fris_latest.csv")
st.sidebar.write("✅ fris_latest.geojson")
st.sidebar.write("✅ fris_latest_map.html")

st.sidebar.markdown("---")
refresh_now = st.sidebar.button("🔄 Refresh now")

if refresh_now:
    st.rerun()


# =========================================================
# FILE CHECK
# =========================================================

if df is None:
    st.title("Godda FRIS Dashboard")
    st.error("No FRIS CSV found.")

    st.write("Keep these files inside the `data` folder:")

    st.code(
        """
fris_showcase/
├── app.py
├── requirements.txt
└── data/
    ├── fris_latest.csv
    ├── fris_latest.geojson
    └── fris_latest_map.html
        """
    )

    st.stop()


# =========================================================
# MAIN HEADER
# =========================================================

st.title("🌳 Godda FRIS Dashboard")
st.caption("Forest Health • Moisture Stress • Fire Alert • Patrol Priority • Carbon / MRV")

st.success("FRIS data loaded successfully.")

st.markdown("---")


# =========================================================
# COLUMN DETECTION
# =========================================================

risk_col = find_column(df, ["risk_class", "final_priority", "patrol_priority"])
fire_col = find_column(df, ["active_fire", "fire_active"])
health_col = find_column(df, ["health_class", "forest_health"])
moisture_col = find_column(df, ["moisture_class", "moisture_status"])
grid_col = find_column(df, ["grid_id", "Grid_ID", "id"])
nav_col = find_column(df, ["google_maps_link", "navigation_link", "map_link"])


# =========================================================
# SUMMARY METRICS
# =========================================================

total_grids = len(df)

critical_count = 0
high_count = 0
fire_count = 0

if risk_col:
    risk_series = df[risk_col].astype(str).str.upper()
    critical_count = risk_series.str.contains("CRITICAL|VERY HIGH", na=False).sum()
    high_count = risk_series.str.contains("HIGH", na=False).sum()

if fire_col:
    fire_series = df[fire_col].astype(str).str.upper()
    fire_count = fire_series.isin(["YES", "TRUE", "1", "ACTIVE"]).sum()

col1, col2, col3, col4 = st.columns(4)

with col1:
    metric_card("Total Forest Grids", total_grids)

with col2:
    metric_card("Critical Grids", critical_count)

with col3:
    metric_card("High Priority Grids", high_count)

with col4:
    metric_card("Active Fire Alerts", fire_count)


st.markdown("---")


# =========================================================
# TABS
# =========================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "🗺️ Map",
        "🚨 Priority Grids",
        "📊 Grid Data",
        "🌿 Forest Health",
        "🧾 Carbon / MRV",
    ]
)


# =========================================================
# TAB 1 - MAP
# =========================================================

with tab1:
    st.subheader("FRIS Operational Map")

    if MAP_PATH.exists():
        with open(MAP_PATH, "r", encoding="utf-8") as f:
            map_html = f.read()

        components.html(map_html, height=700, scrolling=True)
    else:
        st.warning("Map file not found: `data/fris_latest_map.html`")


# =========================================================
# TAB 2 - PRIORITY GRIDS
# =========================================================

with tab2:
    st.subheader("Priority Patrol Grids")

    priority_df = df.copy()

    if risk_col:
        priority_df["_risk_sort"] = priority_df[risk_col].astype(str).str.upper()

        priority_df = priority_df[
            priority_df["_risk_sort"].str.contains(
                "CRITICAL|VERY HIGH|HIGH|MEDIUM", na=False
            )
        ]

        priority_df["_rank"] = priority_df["_risk_sort"].map(
            {
                "CRITICAL": 1,
                "VERY HIGH": 1,
                "HIGH": 2,
                "MEDIUM": 3,
                "MODERATE": 3,
                "LOW": 4,
            }
        ).fillna(5)

        priority_df = priority_df.sort_values("_rank")

    display_cols = []

    for c in [
        grid_col,
        risk_col,
        fire_col,
        health_col,
        moisture_col,
        "NDVI",
        "NDMI",
        "ndvi",
        "ndmi",
        "patrol_action",
        "recommended_response_time",
        "inference",
        nav_col,
    ]:
        if c and c in priority_df.columns and c not in display_cols:
            display_cols.append(c)

    if len(priority_df) == 0:
        st.info("No high or medium priority grids found.")
    else:
        st.dataframe(priority_df[display_cols].head(100), use_container_width=True)


# =========================================================
# TAB 3 - GRID DATA
# =========================================================

with tab3:
    st.subheader("Grid-wise FRIS Data")

    search = st.text_input("Search grid ID / risk / health / inference")

    filtered_df = df.copy()

    if search:
        search_lower = search.lower()
        filtered_df = filtered_df[
            filtered_df.astype(str)
            .apply(lambda row: row.str.lower().str.contains(search_lower).any(), axis=1)
        ]

    st.dataframe(filtered_df, use_container_width=True)

    csv_download = filtered_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="⬇️ Download filtered CSV",
        data=csv_download,
        file_name="fris_filtered_data.csv",
        mime="text/csv",
    )


# =========================================================
# TAB 4 - FOREST HEALTH
# =========================================================

with tab4:
    st.subheader("Forest Health and Moisture Summary")

    c1, c2 = st.columns(2)

    with c1:
        if health_col:
            st.write("### Vegetation Health")
            st.bar_chart(df[health_col].astype(str).value_counts())
        else:
            st.info("Health classification column not found.")

    with c2:
        if moisture_col:
            st.write("### Moisture Status")
            st.bar_chart(df[moisture_col].astype(str).value_counts())
        else:
            st.info("Moisture classification column not found.")

    ndvi_col = find_column(df, ["NDVI", "ndvi"])
    ndmi_col = find_column(df, ["NDMI", "ndmi"])

    c3, c4 = st.columns(2)

    with c3:
        if ndvi_col:
            st.write("### NDVI Distribution")
            st.line_chart(df[ndvi_col])

    with c4:
        if ndmi_col:
            st.write("### NDMI Distribution")
            st.line_chart(df[ndmi_col])


# =========================================================
# TAB 5 - CARBON / MRV
# =========================================================

with tab5:
    st.subheader("Carbon / MRV Summary")

    carbon_cols = [
        "baseline_ecosystem_carbon_total_ton",
        "baseline_ecosystem_carbon_co2e_total",
        "ecosystem_carbon_total_ton",
        "ecosystem_carbon_co2e_total",
        "carbon_change_ton",
        "carbon_change_co2e_ton",
        "gross_positive_co2e_gain_ton",
        "potential_credit_ton_co2e",
        "potential_carbon_credits",
        "carbon_change_status",
        "mrv_confidence",
        "verification_status",
        "carbon_credit_claim_status",
    ]

    available_carbon_cols = [c for c in carbon_cols if c in df.columns]

    if not available_carbon_cols:
        st.info("Carbon / MRV columns not found in this CSV.")
    else:
        latest = df.iloc[-1]

        m1, m2, m3 = st.columns(3)

        with m1:
            if "ecosystem_carbon_total_ton" in df.columns:
                st.metric(
                    "Estimated Ecosystem Carbon",
                    latest["ecosystem_carbon_total_ton"],
                )

        with m2:
            if "carbon_change_co2e_ton" in df.columns:
                st.metric(
                    "Carbon Change CO₂e",
                    latest["carbon_change_co2e_ton"],
                )

        with m3:
            if "potential_carbon_credits" in df.columns:
                st.metric(
                    "Potential Carbon Credits",
                    latest["potential_carbon_credits"],
                )

        st.dataframe(df[available_carbon_cols], use_container_width=True)


# =========================================================
# FOOTER
# =========================================================

st.markdown("---")
st.caption(
    "FRIS Dashboard | Godda Forest Division | Satellite-assisted forest monitoring system"
)