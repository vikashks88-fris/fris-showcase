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
# CUSTOM STYLE
# =====================================================

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(135deg, #07130c 0%, #10251a 45%, #f4f8f5 45%, #f4f8f5 100%);
    }

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 1rem;
    }

    h1 {
        color: #f4fff7;
        font-size: 42px;
        font-weight: 900;
        letter-spacing: 1px;
    }

    .subtitle {
        color: #d7eadb;
        font-size: 16px;
        margin-top: -12px;
        margin-bottom: 22px;
    }

    .status-box {
        background: rgba(220, 255, 230, 0.95);
        color: #14532d;
        padding: 14px 18px;
        border-radius: 12px;
        border-left: 6px solid #22c55e;
        font-weight: 600;
        margin-bottom: 18px;
    }

    .metric-card {
        background: rgba(255,255,255,0.95);
        padding: 18px;
        border-radius: 18px;
        box-shadow: 0 8px 25px rgba(0,0,0,0.12);
        border: 1px solid rgba(0,0,0,0.04);
    }

    .metric-title {
        font-size: 13px;
        color: #64748b;
        font-weight: 600;
    }

    .metric-value {
        font-size: 34px;
        color: #123524;
        font-weight: 900;
        margin-top: 4px;
    }

    .section-card {
        background: white;
        padding: 18px;
        border-radius: 18px;
        box-shadow: 0 8px 25px rgba(0,0,0,0.10);
    }

    .alert-card {
        background: #fff7ed;
        border-left: 6px solid #f97316;
        padding: 14px 18px;
        border-radius: 12px;
        margin-bottom: 10px;
        color: #7c2d12;
        font-weight: 600;
    }

    .critical-card {
        background: #fef2f2;
        border-left: 6px solid #dc2626;
        padding: 14px 18px;
        border-radius: 12px;
        margin-bottom: 10px;
        color: #7f1d1d;
        font-weight: 600;
    }

    .healthy-card {
        background: #ecfdf5;
        border-left: 6px solid #16a34a;
        padding: 14px 18px;
        border-radius: 12px;
        margin-bottom: 10px;
        color: #14532d;
        font-weight: 600;
    }

    [data-testid="stSidebar"] {
        background-color: #f8fafc;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =====================================================
# PATH SETTINGS
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

st.title("🌳 FRIS Command Dashboard")

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

try:
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip()

except Exception as e:
    st.error(f"CSV loading failed: {e}")
    st.stop()

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

def filter_values(column_name, fallback):
    if column_name in df.columns:
        values = sorted(df[column_name].dropna().astype(str).unique())
        return values if values else [fallback]
    return [fallback]

health_values = filter_values("health_class", "UNKNOWN")
moisture_values = filter_values("moisture_class", "UNKNOWN")
risk_values = filter_values("risk_class", "LOW")

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

filtered_df = df.copy()

if "health_class" in filtered_df.columns:
    filtered_df = filtered_df[
        filtered_df["health_class"].astype(str).isin(health_filter)
    ]

if "moisture_class" in filtered_df.columns:
    filtered_df = filtered_df[
        filtered_df["moisture_class"].astype(str).isin(moisture_filter)
    ]

if "risk_class" in filtered_df.columns:
    filtered_df = filtered_df[
        filtered_df["risk_class"].astype(str).isin(risk_filter)
    ]

# =====================================================
# METRIC CALCULATION
# =====================================================

total_grids = len(filtered_df)

critical_grids = 0
high_grids = 0
fire_alerts = 0
healthy_grids = 0
stressed_grids = 0

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
    health_upper = filtered_df["health_class"].astype(str).str.upper()
    healthy_grids = int((health_upper == "HEALTHY").sum())
    stressed_grids = int((health_upper == "STRESSED").sum())

# =====================================================
# TOP METRIC CARDS
# =====================================================

m1, m2, m3, m4, m5 = st.columns(5)

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

map_tab, command_tab, priority_tab, data_tab, carbon_tab = st.tabs(
    [
        "🛰️ Satellite Map",
        "🎛️ Command Center",
        "🚨 Priority Grids",
        "📋 Grid Data",
        "🧪 Carbon / MRV"
    ]
)

# =====================================================
# SATELLITE MAP TAB
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

        st.code(
            """
data/
├── fris_latest.csv
└── fris_latest_map.html
            """
        )

    st.markdown("</div>", unsafe_allow_html=True)

# =====================================================
# COMMAND CENTER TAB
# =====================================================

with command_tab:

    left, right = st.columns([2, 1])

    with left:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Operational Intelligence Summary")

        if critical_grids > 0:
            st.markdown(
                f"""
                <div class="critical-card">
                {critical_grids} critical forest grids detected. Immediate field attention recommended.
                </div>
                """,
                unsafe_allow_html=True
            )

        if high_grids > 0:
            st.markdown(
                f"""
                <div class="alert-card">
                {high_grids} high-risk grids found. Patrol planning should prioritize these areas.
                </div>
                """,
                unsafe_allow_html=True
            )

        if fire_alerts > 0:
            st.markdown(
                f"""
                <div class="critical-card">
                {fire_alerts} active fire alert signals detected. Verification required.
                </div>
                """,
                unsafe_allow_html=True
            )

        if critical_grids == 0 and high_grids == 0 and fire_alerts == 0:
            st.markdown(
                """
                <div class="healthy-card">
                No critical or high-risk forest grids detected in current filtered data. Routine monitoring is sufficient.
                </div>
                """,
                unsafe_allow_html=True
            )

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Field Action Logic")

        st.write("🔴 Critical: Immediate field verification")
        st.write("🟠 High: Patrol within 24 hours")
        st.write("🟡 Moderate: Monitoring required")
        st.write("🟢 Low: Routine monitoring")

        st.markdown("</div>", unsafe_allow_html=True)

# =====================================================
# PRIORITY GRID TAB
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
# GRID DATA TAB
# =====================================================

with data_tab:

    st.subheader("Complete FRIS Grid Data")

    st.dataframe(
        filtered_df,
        use_container_width=True
    )

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

st.caption(
    "FRIS • Forest Resilience Information System • Satellite-Based Forest Intelligence • Godda"
)