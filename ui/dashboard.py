"""
Dashboard page — Calendar-first view.
"""

import calendar
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics.metrics import (
    compute_daily_pnl,
    compute_equity_curve,
    compute_summary_metrics,
    load_trades_df,
)
from db.database import get_session

logger = logging.getLogger(__name__)

# ── Design tokens ──────────────────────────────────────────────────────────────
G  = "#30D158"
R  = "#FF453A"
B  = "#0A84FF"
BG = "#0A0A0F"
S1 = "#1C1C1E"
S2 = "#2C2C2E"
T1 = "#FFFFFF"
T2 = "#EBEBF5"
T3 = "#8E8E93"
SEP = "rgba(255,255,255,0.07)"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {{
    font-family: 'DM Sans', -apple-system, sans-serif !important;
    background-color: {BG} !important;
    color: {T1} !important;
}}

.block-container {{ padding-top: 1.5rem !important; padding-bottom: 2rem !important; max-width: 1400px !important; }}
#MainMenu, footer {{ visibility: hidden; }}

.section-title {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: {T3};
    margin: 0 0 12px 0;
    padding: 0;
}}

.clean-divider {{
    border: none;
    border-top: 1px solid {SEP};
    margin: 28px 0;
}}

.stSelectbox label, .stDateInput label, .stSlider label {{
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    color: {T3} !important;
}}
div[data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; border: 1px solid {SEP}; }}
</style>
"""


@st.cache_data(ttl=60, show_spinner=False)
def _load_data() -> pd.DataFrame:
    session = get_session()
    try:
        return load_trades_df(session)
    finally:
        session.close()


def _chart_layout(h=300, margin=None, yaxis_title="", xaxis_title=""):
    m = margin or dict(l=4, r=4, t=4, b=4)
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=h,
        margin=m,
        font=dict(family="DM Sans, sans-serif", color=T3, size=11),
        xaxis=dict(
            title=xaxis_title,
            showgrid=False,
            zeroline=False,
            showline=False,
            tickfont=dict(color=T3, size=10),
            title_font=dict(color=T3),
        ),
        yaxis=dict(
            title=yaxis_title,
            showgrid=True,
            gridcolor=SEP,
            zeroline=True,
            zerolinecolor="rgba(255,255,255,0.1)",
            zerolinewidth=1,
            showline=False,
            tickfont=dict(color=T3, size=10),
            title_font=dict(color=T3),
        ),
        legend=dict(font=dict(color=T3)),
        hovermode="x unified",
    )


def render_dashboard_page():
    st.markdown(CSS, unsafe_allow_html=True)

    df_all = _load_data()
    if df_all.empty:
        st.info("No trades yet — add entries via Manual Entry or upload IBKR files.")
        return

    # ── Sidebar filters ───────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown('<div class="section-title">Filters</div>', unsafe_allow_html=True)
        min_date = df_all["exit_time"].min().date()
        max_date = df_all["exit_time"].max().date()
        date_range = st.date_input("Date range", value=(min_date, max_date),
                                   min_value=min_date, max_value=max_date)
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            d_from, d_to = date_range
        else:
            d_from, d_to = min_date, max_date

    # ── Apply filters ─────────────────────────────────────────────────────────
    df = df_all.copy()
    df = df[(df["exit_time"].dt.date >= d_from) & (df["exit_time"].dt.date <= d_to)]

    if df.empty:
        st.warning("No trades match current filters.")
        return

    metrics = compute_summary_metrics(df)

    # ── Calendar ──────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Daily Return Calendar</div>', unsafe_allow_html=True)
    cal_mode = st.radio(
        "calendar_mode",
        ["Gross %", "Net %"],
        horizontal=True,
        label_visibility="collapsed",
    )
    daily = compute_daily_pnl(df)
    if not daily.empty:
        _render_calendar(daily, mode=cal_mode)

    st.markdown("<hr class='clean-divider'>", unsafe_allow_html=True)

    # ── Distribution ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Trade Return Distribution</div>', unsafe_allow_html=True)
    wins_df  = df[df["gross_return_pct"] > 0]["gross_return_pct"]
    loss_df  = df[df["gross_return_pct"] <= 0]["gross_return_pct"]

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=loss_df, nbinsx=30, name="Losses",
        marker_color="rgba(255,69,58,0.7)", marker_line_width=0,
        hovertemplate="Range: %{x}<br>Count: %{y}<extra></extra>",
    ))
    fig_hist.add_trace(go.Histogram(
        x=wins_df, nbinsx=30, name="Wins",
        marker_color="rgba(48,209,88,0.7)", marker_line_width=0,
        hovertemplate="Range: %{x}<br>Count: %{y}<extra></extra>",
    ))
    fig_hist.add_vline(x=0, line_width=1, line_color="rgba(255,255,255,0.3)", line_dash="dash")
    hist_layout = _chart_layout(h=240, xaxis_title="Return (%)", yaxis_title="Days")
    hist_layout["legend"] = dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        font=dict(color=T3, size=11),
    )
    hist_layout["barmode"] = "overlay"
    hist_layout["bargap"]  = 0.04
    fig_hist.update_layout(**hist_layout)
    st.plotly_chart(fig_hist, width="stretch", config={"staticPlot": True})

    st.markdown("<hr class='clean-divider'>", unsafe_allow_html=True)

    # ── Trades table ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">All Trades</div>', unsafe_allow_html=True)
    display_cols = {
        "symbol": "Symbol", "direction": "Dir", "entry_time": "Entry",
        "exit_time": "Exit", "holding_seconds": "Hold (s)",
        "avg_entry_price": "Entry Price", "avg_exit_price": "Exit Price",
        "max_position_size": "Size", "deployed_notional": "Notional",
        "gross_pnl": "Gross P&L", "total_commission": "Commission",
        "commission_pct": "Comm %", "net_pnl": "Net P&L", "return_pct": "Return %",
    }
    tbl = df[list(display_cols.keys())].rename(columns=display_cols).copy()
    for col in ["Entry Price", "Exit Price", "Notional", "Gross P&L", "Commission", "Net P&L"]:
        tbl[col] = tbl[col].map(lambda x: f"${x:,.4f}" if pd.notna(x) else "")
    tbl["Comm %"]   = tbl["Comm %"].map(lambda x: f"{x:.3f}%" if pd.notna(x) else "")
    tbl["Return %"] = tbl["Return %"].map(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
    tbl["Size"]     = tbl["Size"].map(lambda x: f"{x:,.0f}" if pd.notna(x) else "")
    st.dataframe(tbl, width="stretch", hide_index=True, height=420)


# ── Calendar helpers ──────────────────────────────────────────────────────────

def _render_calendar(daily: pd.DataFrame, mode: str = "Gross %"):
    daily = daily.copy()
    daily["exit_date"] = pd.to_datetime(daily["exit_date"])
    daily["year"]  = daily["exit_date"].dt.year
    daily["month"] = daily["exit_date"].dt.month
    daily["day"]   = daily["exit_date"].dt.day

    pct_col = "gross_return_pct" if mode == "Gross %" else "return_pct"

    years = sorted(daily["year"].unique())
    year_sel = st.selectbox("Year", years, index=len(years) - 1, label_visibility="collapsed")
    yr_data = daily[daily["year"] == year_sel]

    win_days  = int((yr_data[pct_col] > 0).sum())
    loss_days = int((yr_data[pct_col] <= 0).sum())
    total_ret = yr_data[pct_col].sum()
    best_day  = yr_data.loc[yr_data[pct_col].idxmax()] if not yr_data.empty else None
    worst_day = yr_data.loc[yr_data[pct_col].idxmin()] if not yr_data.empty else None

    bd_str = f"+{best_day[pct_col]:.2f}%" if best_day is not None else "—"
    wd_str = f"{worst_day[pct_col]:.2f}%"  if worst_day is not None else "—"
    ret_color = "#30D158" if total_ret >= 0 else "#FF453A"

    st.markdown(f"""
    <div style="display:flex;gap:24px;margin-bottom:18px;padding:14px 18px;
                background:#1C1C1E;border-radius:12px;border:1px solid rgba(255,255,255,0.07);
                flex-wrap:wrap;">
        <div style="font-size:12px;color:#8E8E93;">Year Return&nbsp;
            <span style="color:{ret_color};font-weight:600;font-family:monospace;">{total_ret:+.2f}%</span>
        </div>
        <div style="font-size:12px;color:#8E8E93;">Green Days&nbsp;
            <span style="color:#30D158;font-weight:600;">{win_days}</span>
        </div>
        <div style="font-size:12px;color:#8E8E93;">Red Days&nbsp;
            <span style="color:#FF453A;font-weight:600;">{loss_days}</span>
        </div>
        <div style="font-size:12px;color:#8E8E93;">Best Day&nbsp;
            <span style="color:#30D158;font-weight:600;font-family:monospace;">{bd_str}</span>
        </div>
        <div style="font-size:12px;color:#8E8E93;">Worst Day&nbsp;
            <span style="color:#FF453A;font-weight:600;font-family:monospace;">{wd_str}</span>
        </div>
    </div>""", unsafe_allow_html=True)

    month_list = list(range(1, 13))
    for row_start in range(0, 12, 3):
        cols = st.columns(3)
        for i, m in enumerate(month_list[row_start:row_start + 3]):
            m_data = yr_data[yr_data["month"] == m]
            day_pnl = {int(r["day"]): r[pct_col] for _, r in m_data.iterrows()}
            with cols[i]:
                st.markdown(_build_month_html(m, year_sel, day_pnl), unsafe_allow_html=True)


def _build_month_html(month: int, year: int, day_pnl: dict) -> str:
    month_name = calendar.month_name[month]
    n_days = (date(year, month % 12 + 1, 1) - timedelta(days=1)).day if month < 12 else 31
    first_dow = (date(year, month, 1).weekday() + 1) % 7

    GRID    = "display:grid;grid-template-columns:repeat(7,1fr);gap:2px;"
    HDR     = "font-size:9px;font-weight:600;color:#636366;text-align:center;letter-spacing:0.05em;padding-bottom:3px;"
    BASE    = "border-radius:6px;padding:5px 4px;min-height:46px;display:flex;flex-direction:column;justify-content:space-between;"
    EMPTY   = BASE + "background:transparent;"
    NOTRADE = BASE + "background:#1C1C1E;border:1px solid rgba(255,255,255,0.05);"
    WIN     = BASE + "background:rgba(48,209,88,0.14);border:1px solid rgba(48,209,88,0.22);"
    LOSS    = BASE + "background:rgba(255,69,58,0.10);border:1px solid rgba(255,69,58,0.18);"

    DAY_NT   = "font-size:10px;font-weight:500;color:#636366;"
    DAY_WIN  = "font-size:10px;font-weight:500;color:rgba(48,209,88,0.7);"
    DAY_LOSS = "font-size:10px;font-weight:500;color:rgba(255,69,58,0.65);"
    PNL_WIN  = "font-size:9.5px;font-weight:600;color:#30D158;text-align:right;font-family:monospace;"
    PNL_LOSS = "font-size:9.5px;font-weight:600;color:#FF453A;text-align:right;font-family:monospace;"

    day_labels = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
    cells = "".join(f'<div style="{HDR}">{d}</div>' for d in day_labels)
    cells += f'<div style="{EMPTY}"></div>' * first_dow

    for d in range(1, n_days + 1):
        pnl = day_pnl.get(d)
        if pnl is None:
            cells += f'<div style="{NOTRADE}"><div style="{DAY_NT}">{d}</div></div>'
        elif pnl >= 0:
            cells += (f'<div style="{WIN}"><div style="{DAY_WIN}">{d}</div>'
                      f'<div style="{PNL_WIN}">+{pnl:.2f}%</div></div>')
        else:
            cells += (f'<div style="{LOSS}"><div style="{DAY_LOSS}">{d}</div>'
                      f'<div style="{PNL_LOSS}">{pnl:.2f}%</div></div>')

    return f"""
    <div style="margin-bottom:20px;">
        <div style="font-size:12px;font-weight:600;color:#EBEBF5;
                    margin-bottom:8px;letter-spacing:-0.01em;">{month_name}</div>
        <div style="{GRID}">{cells}</div>
    </div>"""
