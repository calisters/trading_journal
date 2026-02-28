"""
Trading Journal - Main Streamlit Application
"""

import logging
import sys
from pathlib import Path

# ── Logging setup (must be first) ─────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

import streamlit as st

# ── Page config (must come before any other st. call) ─────────────────────────
st.set_page_config(
    page_title="Trading Journal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Sora:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Sora', sans-serif;
        background-color: #0f1923;
        color: #e2e8f0;
    }
    .stMetric {
        background: #1a2535;
        border-radius: 10px;
        padding: 12px 16px;
        border: 1px solid #2d3d50;
    }
    .stMetric label { color: #7b8fa1 !important; font-size: 0.75rem; }
    .stMetric [data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.3rem;
        color: #e2e8f0;
    }
    h1, h2, h3 { font-family: 'Sora', sans-serif; font-weight: 600; }
    h1 { color: #3b82f6; }
    .stButton > button {
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 8px;
        font-family: 'Sora', sans-serif;
        font-weight: 600;
        padding: 0.5rem 1.5rem;
    }
    .stButton > button:hover { background: #2563eb; }
    .stDataFrame { border: 1px solid #2d3d50; border-radius: 8px; }
    [data-testid="stSidebar"] { background: #111d2e; }
    .stTabs [data-baseweb="tab"] {
        font-family: 'Sora', sans-serif;
        font-weight: 500;
    }
    div[data-testid="metric-container"] {
        background: #1a2535;
        border: 1px solid #2d3d50;
        border-radius: 10px;
        padding: 14px 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Initialise DB ─────────────────────────────────────────────────────────────
from db.database import get_engine
get_engine()  # ensures tables exist on first run

# ── Navigation ────────────────────────────────────────────────────────────────
from ui.upload import render_upload_page
from ui.dashboard import render_dashboard_page
from ui.insights import render_insights_page

with st.sidebar:
    st.markdown("## 📈 Trading Journal")
    st.markdown("---")
    page = st.radio(
        "Navigate",
        ["📂 Upload", "📊 Dashboard", "🔍 Insights"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("IBKR Trade Log Analyser")

if page == "📂 Upload":
    render_upload_page()
elif page == "📊 Dashboard":
    render_dashboard_page()
elif page == "🔍 Insights":
    render_insights_page()
