import os
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# =====================================================
# PAGE CONFIG
# =====================================================

st.set_page_config(
    page_title="Godda FRIS Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================
# CLEAN CSS
# =====================================================

st.markdown(
    """
    <style>
    .stApp {
        background-color: #f4f8f5;
    }

    .block-container {
        padding-top: 1rem;
        max-width: 96%;
    }

    h1 {
        color: #163020;
        font-size: 40px;
        font-weight: 900;
    }

    .subtitle {
        color: #4b5563;
        font-size: 16px;
        margin-top: -12px;
        margin-bottom: 20px;
    }

    .status-box {
        background: #ecfdf5;
        color: #166534;
        padding: 14px 18px;
        border-radius: 12px;
        border-left: 6px solid #22c55e;
        font-weight: 600;
        margin-bottom: 18px;
    }

    .metric-card {
        background: white;
        padding: 18px;
        border-radius: 16px;
        box-shadow: 0 6px 18px rgba(0,0,0,0.08);
        border: 1px solid rgba(0,0,0,0.05);
    }

    .metric-title {
        font-size: 13px;
        color: #64748b;
        font-weight: 600;
    }

    .metric-value {
        font-size: 34px;
        color: #163020;
        font-weight: 900;
        margin-top: 4px;
    }

    .section-card {
        background: white;
        padding: 18px;
        border-radius: 18px;
        box-shadow: 0 6px 18px rgba(0,0,0,0.08);
        margin-bottom: 18px;
    }

    [data-testid="stSidebar"] {
        background-color: #ffffff;
    }

    iframe {
        border-radius: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =====================================================
# PATHS
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SEARCH_FOLDERS = [
    os.path.join(BASE_DIR, "data"),
    os.path.join(BASE_DIR, "output"),
    "data",
    "output",
    "/opt/render/project/src/data",
    "/opt/render/project/src/output",
]

csv_path = None
map_path = None

for folder in SEARCH_FOLDERS:
    csv_test = os.path.join(folder, "fris_latest.csv")
    map_test = os.path.join(folder, "fris_latest_map.html")

    if csv_path is None and os.path.exists(csv_test):
        csv_path = csv_test

    if map_path is None and os.path.exists(map_test):
        map_path = map_test

# =====================================================
# HEADER
# =====================================================

st.title("🌳 Godda FRIS Dashboard")

st.markdown(
    """
    <div class="subtitle">
    Forest Resilience Information System • Godda Forest Division • Satellite-Based Forest Intelligence
    </div>
    """,
    unsafe_allow_html=True
)

# =====================================================
# FILE CHECK
# =====================================================

if csv_path is None:
    st.error("fris_latest.csv not found.")

    st.code(
        """
fris_showcase/
├── app.py
├── requirements.txt
└── data/
    ├── fris_latest.csv
    └── fris_latest_map.html
        """
    )

    st.stop()

# =====================================================
# LOAD DATA
# =====================================================

df = pd.read_csv(csv_path)
df.columns = df.columns.str.strip()

for col in df.columns:
    if df[col].dtype == "object":
        df[col] = df[col].astype(str).str.strip()

st.markdown(
    """
    <div class="status-box">
    FRIS data loaded successfully. Operational forest intelligence is active.
    </div>
    """,
    unsafe_allow_html=True
)

# =====================================================
# SIDEBAR FILTERS
# =====================================================

st.sidebar.header("FRIS Filters")

filtered_df = df.copy()

if "health_class" in df.columns:
    health_values = sorted(df["health_class"].dropna().astype(str).unique())
    health_filter = st.sidebar.multiselect(
        "Health Class",
        health_values,
        default=health_values
    )
    filtered_df = filtered_df[
        filtered_df["health_class"].astype(str).isin(health_filter)
    ]

if "moisture_class" in df.columns:
    moisture_values = sorted(df["moisture_class"].dropna().astype(str).unique())
    moisture_filter = st.sidebar.multiselect(
        "Moisture Class",
        moisture_values,
        default=moisture_values
    )
    filtered_df = filtered_df[
        filtered_df["moisture_class"].astype(str).isin(moisture_filter)
    ]

if "risk_class" in df.columns:
    risk_values = sorted(df["risk_class"].dropna().astype(str).unique())
    risk_filter = st.sidebar.multiselect(
        "Risk Class",
        risk_values,
        default=risk_values
    )
    filtered_df = filtered_df[
        filtered_df["risk_class"].astype(str).isin(risk_filter)
    ]

# =====================================================
# METRICS
# =====================================================

total_grids = len(filtered_df)

critical_grids = 0
high_grids = 0
fire_alerts = 0
healthy_grids = 0

if "risk_class" in filtered_df.columns:
    risk_upper = filtered_df["risk_class"].astype(str).str.upper()
    critical_grids = int((risk_upper == "CRITICAL").sum())
    high_grids = int((risk_upper == "HIGH").sum())

if "active_fire" in filtered_df.columns:
    fire_alerts = int(
        filtered_df["active_fire"]
        .astype(str)
        .str.upper()
        .isin(["1", "TRUE", "YES"])
        .sum()
    )

if "health_class" in filtered_df.columns:
    healthy_grids = int(
        (filtered_df["health_class"].astype(str).str.upper() == "HEALTHY").sum()
    )

def metric_card(title, value):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

m1, m2, m3, m4, m5 = st.columns(5)

with m1:
    metric_card("Forest Grids", total_grids)

with m2:
    metric_card("Critical Zones", critical_grids)

with m3:
    metric_card("High Risk", high_grids)

with m4:
    metric_card("Fire Alerts", fire_alerts)

with m5:
    metric_card("Healthy Grids", healthy_grids)

st.markdown("<br>", unsafe_allow_html=True)

# =====================================================
# TABS
# =====================================================

map_tab, priority_tab, data_tab, health_tab, carbon_tab = st.tabs(
    [
        "🛰️ Satellite Map",
        "🚨 Priority Grids",
        "📋 Grid Data",
        "🌿 Forest Health",
        "🧪 Carbon / MRV"
    ]
)

# =====================================================
# MAP TAB
# =====================================================

with map_tab:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Satellite Operational Map")

    if map_path is not None:
        with open(map_path, "r", encoding="utf-8") as f:
            map_html = f.read()

        components.html(
            map_html,
            height=760,
            scrolling=True
        )
    else:
        st.warning("fris_latest_map.html not found inside data folder.")

    st.markdown("</div>", unsafe_allow_html=True)

# =====================================================
# PRIORITY TAB
# =====================================================

with priority_tab:
    st.subheader("Priority Grids for Field Action")

    priority_df = filtered_df.copy()

    if "risk_class" in priority_df.columns:
        priority_df = priority_df[
            priority_df["risk_class"]
            .astype(str)
            .str.upper()
            .isin(["CRITICAL", "HIGH", "MODERATE"])
        ]

    priority_cols = [
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

    available_priority_cols = [
        col for col in priority_cols if col in priority_df.columns
    ]

    if len(priority_df) > 0 and available_priority_cols:
        st.dataframe(
            priority_df[available_priority_cols],
            use_container_width=True
        )
    else:
        st.info("No priority grids found in current filter.")

# =====================================================
# DATA TAB
# =====================================================

with data_tab:
    st.subheader("Complete FRIS Grid Data")

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
        st.markdown("### Health Class")
        st.bar_chart(filtered_df["health_class"].value_counts())

    if "moisture_class" in filtered_df.columns:
        st.markdown("### Moisture Class")
        st.bar_chart(filtered_df["moisture_class"].value_counts())

    if "risk_class" in filtered_df.columns:
        st.markdown("### Risk Class")
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
        col for col in carbon_cols if col in filtered_df.columns
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
st.caption("FRIS • Forest Resilience Information System • Godda Forest Division")