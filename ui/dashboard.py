"""
Dashboard page — Apple-style, Tradervue-quality.
Equity curve · Drawdown · Calendar · Distribution · Trades table
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
    compute_drawdown,
    compute_equity_curve,
    compute_summary_metrics,
    load_trades_df,
)
from db.database import get_session

logger = logging.getLogger(__name__)

# ── Design tokens ──────────────────────────────────────────────────────────────
G  = "#30D158"   # Apple green
R  = "#FF453A"   # Apple red
B  = "#0A84FF"   # Apple blue
BG = "#0A0A0F"
S1 = "#1C1C1E"   # card surface
S2 = "#2C2C2E"   # elevated surface
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

/* Remove default Streamlit top padding */
.block-container {{ padding-top: 1.5rem !important; padding-bottom: 2rem !important; max-width: 1400px !important; }}

/* Hide Streamlit branding */
#MainMenu, footer {{ visibility: hidden; }}

/* Section titles */
.section-title {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: {T3};
    margin: 0 0 12px 0;
    padding: 0;
}}

.page-title {{
    font-size: 26px;
    font-weight: 600;
    color: {T1};
    letter-spacing: -0.03em;
    margin: 0 0 4px 0;
}}

.page-sub {{
    font-size: 13px;
    color: {T3};
    margin-bottom: 28px;
    font-weight: 400;
}}

/* Metric card */
.metric-card {{
    background: {S1};
    border: 1px solid {SEP};
    border-radius: 14px;
    padding: 18px 20px 16px;
    height: 100%;
    transition: border-color 0.15s ease;
}}
.metric-card:hover {{ border-color: rgba(255,255,255,0.14); }}

.metric-label {{
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: {T3};
    margin-bottom: 8px;
}}
.metric-value {{
    font-size: 24px;
    font-weight: 600;
    letter-spacing: -0.03em;
    color: {T1};
    font-feature-settings: "tnum";
    font-family: 'DM Mono', monospace;
}}
.metric-value.green {{ color: {G}; }}
.metric-value.red   {{ color: {R}; }}

.metric-sub {{
    font-size: 12px;
    color: {T3};
    margin-top: 4px;
    font-family: 'DM Mono', monospace;
}}

/* Divider */
.clean-divider {{
    border: none;
    border-top: 1px solid {SEP};
    margin: 28px 0;
}}

/* Calendar */
.cal-grid {{
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 3px;
}}
.cal-header-cell {{
    text-align: center;
    font-size: 10px;
    font-weight: 600;
    color: {T3};
    letter-spacing: 0.05em;
    padding-bottom: 4px;
}}
.cal-cell {{
    border-radius: 8px;
    padding: 8px 6px;
    min-height: 56px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    position: relative;
}}
.cal-cell.empty {{
    background: transparent;
}}
.cal-cell.no-trade {{
    background: {S1};
    border: 1px solid {SEP};
}}
.cal-cell.win {{
    background: rgba(48,209,88,0.15);
    border: 1px solid rgba(48,209,88,0.25);
}}
.cal-cell.loss {{
    background: rgba(255,69,58,0.12);
    border: 1px solid rgba(255,69,58,0.22);
}}
.cal-day-num {{
    font-size: 11px;
    font-weight: 500;
    color: {T3};
}}
.cal-cell.win .cal-day-num  {{ color: rgba(48,209,88,0.8); }}
.cal-cell.loss .cal-day-num {{ color: rgba(255,69,58,0.7); }}
.cal-pnl {{
    font-size: 10.5px;
    font-weight: 600;
    font-family: 'DM Mono', monospace;
    text-align: right;
}}
.cal-cell.win  .cal-pnl {{ color: {G}; }}
.cal-cell.loss .cal-pnl {{ color: {R}; }}

.cal-month-label {{
    font-size: 13px;
    font-weight: 600;
    color: {T2};
    margin-bottom: 10px;
    letter-spacing: -0.01em;
}}

/* Month row */
.month-block {{ margin-bottom: 24px; }}

/* Summary row for calendar */
.day-summary-bar {{
    display: flex;
    gap: 20px;
    margin-bottom: 20px;
    padding: 14px 18px;
    background: {S1};
    border-radius: 12px;
    border: 1px solid {SEP};
}}
.day-summary-item {{ font-size: 12px; color: {T3}; }}
.day-summary-item span {{ color: {T1}; font-weight: 600; font-family: 'DM Mono', monospace; }}

/* Streamlit element cleanup */
div[data-testid="stMetric"] {{ display: none; }}
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


def _col(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    return "green" if val >= 0 else "red"


def _fmt(val, prefix="$", decimals=2, signed=False):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    sign = "+" if signed and val > 0 else ""
    s = f"{abs(val):,.{decimals}f}"
    if val < 0:
        return f"-{prefix}{s}"
    return f"{sign}{prefix}{s}"


def _card(label: str, value: str, sub: str = "", color_class: str = ""):
    sub_html = f'<div class="metric-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value {color_class}">{value}</div>
        {sub_html}
    </div>"""


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
        st.info("No trades yet — upload IBKR files to get started.")
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

        symbols = ["All"] + sorted(df_all["symbol"].unique().tolist())
        sym_filter = st.selectbox("Symbol", symbols)
        side_filter = st.selectbox("Direction", ["All", "Long", "Short"])
        min_trades = st.slider("Min trades per symbol", 0, 20, 0)

    # ── Apply filters ─────────────────────────────────────────────────────────
    df = df_all.copy()
    df = df[(df["exit_time"].dt.date >= d_from) & (df["exit_time"].dt.date <= d_to)]
    if sym_filter != "All":
        df = df[df["symbol"] == sym_filter]
    if side_filter != "All":
        df = df[df["direction"] == side_filter]
    if min_trades > 0:
        sym_counts = df.groupby("symbol")["id"].count()
        valid_syms = sym_counts[sym_counts >= min_trades].index
        df = df[df["symbol"].isin(valid_syms)]

    if df.empty:
        st.warning("No trades match current filters.")
        return

    metrics = compute_summary_metrics(df)
    net_pnl = metrics.get("total_net_pnl", 0)

    # ── Page title ────────────────────────────────────────────────────────────
    st.markdown(f"""
        <div class="page-title">Dashboard</div>
        <div class="page-sub">{d_from.strftime('%b %d, %Y')} — {d_to.strftime('%b %d, %Y')}</div>
    """, unsafe_allow_html=True)

    # ── Row 1: Core metrics ───────────────────────────────────────────────────
    st.markdown('<div class="section-title">Performance</div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    pf = metrics.get("profit_factor", 0)
    pf_str = "∞" if pf == float("inf") else f"{pf:.2f}"
    cards = [
        (c1, "Net P&L",        _fmt(net_pnl, signed=True),                  "",                                   _col(net_pnl)),
        (c2, "Win Rate",       f"{metrics.get('win_rate', 0):.1f}%",         f"{metrics.get('n_trades',0)} trades", ""),
        (c3, "Profit Factor",  pf_str,                                       "",                                   "green" if pf > 1 else "red"),
        (c4, "Expectancy",     _fmt(metrics.get("expectancy", 0), signed=True), "per trade",                       _col(metrics.get("expectancy", 0))),
        (c5, "Max Drawdown",   f"{abs(metrics.get('max_drawdown_pct', 0)):.1f}%", "",                              "red"),
        (c6, "Trades",         str(metrics.get("n_trades", 0)),              "",                                   ""),
    ]
    for col, label, value, sub, cls in cards:
        with col:
            st.markdown(_card(label, value, sub, cls), unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Row 2: Secondary metrics ──────────────────────────────────────────────
    c7, c8, c9, c10, c11, c12 = st.columns(6)
    bd = metrics.get("best_day")
    wd = metrics.get("worst_day")
    cards2 = [
        (c7,  "Avg Win",      _fmt(metrics.get("avg_win", 0)),                "",                                          "green"),
        (c8,  "Avg Loss",     _fmt(metrics.get("avg_loss", 0)),               "",                                          "red"),
        (c9,  "Best Symbol",  metrics.get("best_symbol", "—") or "—",         "",                                          "green"),
        (c10, "Worst Symbol", metrics.get("worst_symbol", "—") or "—",        "",                                          "red"),
        (c11, "Best Day",     _fmt(bd["net_pnl"], signed=True) if bd is not None else "—",
              str(bd.get("exit_date", "")) if bd is not None else "",          "green"),
        (c12, "Worst Day",    _fmt(wd["net_pnl"], signed=True) if wd is not None else "—",
              str(wd.get("exit_date", "")) if wd is not None else "",          "red"),
    ]
    for col, label, value, sub, cls in cards2:
        with col:
            st.markdown(_card(label, value, sub, cls), unsafe_allow_html=True)

    st.markdown("<hr class='clean-divider'>", unsafe_allow_html=True)

    # ── Equity Curve + Drawdown ───────────────────────────────────────────────
    eq = compute_equity_curve(df)
    if not eq.empty:
        st.markdown('<div class="section-title">Equity Curve</div>', unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["Cumulative P&L ($)", "Cumulative Return (%)"])

        with tab1:
            fig = go.Figure()
            # Gradient fill: positive vs negative
            fig.add_trace(go.Scatter(
                x=eq["exit_time"], y=eq["cum_pnl_usd"],
                mode="lines", name="Cum P&L",
                line=dict(color=G if net_pnl >= 0 else R, width=2),
                fill="tozeroy",
                fillcolor=f"rgba(48,209,88,0.08)" if net_pnl >= 0 else "rgba(255,69,58,0.08)",
                hovertemplate="<b>%{x|%b %d}</b><br>$%{y:,.2f}<extra></extra>",
            ))
            fig.add_hline(y=0, line_width=1, line_color="rgba(255,255,255,0.12)")
            fig.update_layout(**_chart_layout(h=280, yaxis_title="Cumulative P&L ($)"))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        with tab2:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=eq["exit_time"], y=eq["cum_return_pct"],
                mode="lines", name="Return %",
                line=dict(color=B, width=2),
                fill="tozeroy",
                fillcolor="rgba(10,132,255,0.08)",
                hovertemplate="<b>%{x|%b %d}</b><br>%{y:.2f}%<extra></extra>",
            ))
            fig2.add_hline(y=0, line_width=1, line_color="rgba(255,255,255,0.12)")
            fig2.update_layout(**_chart_layout(h=280, yaxis_title="Cumulative Return (%)"))
            st.plotly_chart(fig2, width="stretch", config={"displayModeBar": False})

        # Drawdown
        dd = compute_drawdown(eq)
        if not dd.empty:
            st.markdown('<div class="section-title" style="margin-top:8px">Drawdown</div>',
                        unsafe_allow_html=True)
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(
                x=dd["exit_time"], y=dd["drawdown_pct"],
                mode="lines", name="Drawdown",
                line=dict(color=R, width=1.5),
                fill="tozeroy",
                fillcolor="rgba(255,69,58,0.10)",
                hovertemplate="<b>%{x|%b %d}</b><br>%{y:.2f}%<extra></extra>",
            ))
            fig_dd.update_layout(**_chart_layout(h=160, yaxis_title="Drawdown (%)"))
            st.plotly_chart(fig_dd, width="stretch", config={"displayModeBar": False})

    st.markdown("<hr class='clean-divider'>", unsafe_allow_html=True)

    # ── Calendar ──────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Daily P&L Calendar</div>', unsafe_allow_html=True)
    daily = compute_daily_pnl(df)
    if not daily.empty:
        _render_calendar(daily)

    st.markdown("<hr class='clean-divider'>", unsafe_allow_html=True)

    # ── Distribution ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Trade P&L Distribution</div>', unsafe_allow_html=True)
    wins_df  = df[df["net_pnl"] > 0]["net_pnl"]
    loss_df  = df[df["net_pnl"] <= 0]["net_pnl"]

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
    hist_layout = _chart_layout(h=240, xaxis_title="Net P&L ($)", yaxis_title="Trades")
    hist_layout["legend"] = dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        font=dict(color=T3, size=11),
    )
    hist_layout["barmode"] = "overlay"
    hist_layout["bargap"] = 0.04
    fig_hist.update_layout(**hist_layout)
    st.plotly_chart(fig_hist, width="stretch", config={"displayModeBar": False})

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
    tbl["Comm %"]    = tbl["Comm %"].map(lambda x: f"{x:.3f}%" if pd.notna(x) else "")
    tbl["Return %"]  = tbl["Return %"].map(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
    tbl["Size"]      = tbl["Size"].map(lambda x: f"{x:,.0f}" if pd.notna(x) else "")

    st.dataframe(tbl, width="stretch", hide_index=True, height=420)


# ── Calendar helpers ──────────────────────────────────────────────────────────

def _render_calendar(daily: pd.DataFrame):
    daily = daily.copy()
    daily["exit_date"] = pd.to_datetime(daily["exit_date"])
    daily["year"]  = daily["exit_date"].dt.year
    daily["month"] = daily["exit_date"].dt.month
    daily["day"]   = daily["exit_date"].dt.day

    years = sorted(daily["year"].unique())
    year_sel = st.selectbox("Year", years, index=len(years) - 1, label_visibility="collapsed")
    yr_data = daily[daily["year"] == year_sel]

    # Summary bar
    win_days  = int((yr_data["net_pnl"] > 0).sum())
    loss_days = int((yr_data["net_pnl"] <= 0).sum())
    total_pnl = yr_data["net_pnl"].sum()
    best_day  = yr_data.loc[yr_data["net_pnl"].idxmax()] if not yr_data.empty else None
    worst_day = yr_data.loc[yr_data["net_pnl"].idxmin()] if not yr_data.empty else None

    bd_str = f"+${best_day['net_pnl']:,.2f}" if best_day is not None else "—"
    wd_str  = f"-${abs(worst_day['net_pnl']):,.2f}" if worst_day is not None else "—"
    pnl_color = "#30D158" if total_pnl >= 0 else "#FF453A"

    summary_html = f"""
    <div style="display:flex;gap:24px;margin-bottom:18px;padding:14px 18px;
                background:#1C1C1E;border-radius:12px;border:1px solid rgba(255,255,255,0.07);
                flex-wrap:wrap;">
        <div style="font-size:12px;color:#8E8E93;">Year P&L&nbsp;
            <span style="color:{pnl_color};font-weight:600;font-family:monospace;">${total_pnl:+,.2f}</span>
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
    </div>"""
    st.markdown(summary_html, unsafe_allow_html=True)

    month_list = list(range(1, 13))
    for row_start in range(0, 12, 3):
        cols = st.columns(3)
        for i, m in enumerate(month_list[row_start:row_start + 3]):
            m_data = yr_data[yr_data["month"] == m]
            day_pnl = {int(r["day"]): r["net_pnl"] for _, r in m_data.iterrows()}
            with cols[i]:
                st.markdown(
                    _build_month_html(m, year_sel, day_pnl),
                    unsafe_allow_html=True,
                )


def _build_month_html(month: int, year: int, day_pnl: dict) -> str:
    """Build a fully inline-styled month calendar block."""
    month_name = calendar.month_name[month]
    n_days = (date(year, month % 12 + 1, 1) - timedelta(days=1)).day if month < 12 else 31
    first_dow = (date(year, month, 1).weekday() + 1) % 7  # 0=Sun, 1=Mon, ..., 6=Sat

    # ── Styles (all inline, no class dependency) ──────────────────────────────
    GRID  = "display:grid;grid-template-columns:repeat(7,1fr);gap:2px;"
    HDR   = ("font-size:9px;font-weight:600;color:#636366;text-align:center;"
             "letter-spacing:0.05em;padding-bottom:3px;")
    BASE  = ("border-radius:6px;padding:5px 4px;min-height:46px;"
             "display:flex;flex-direction:column;justify-content:space-between;")
    EMPTY = BASE + "background:transparent;"
    NOTRADE = BASE + "background:#1C1C1E;border:1px solid rgba(255,255,255,0.05);"
    WIN   = BASE + "background:rgba(48,209,88,0.14);border:1px solid rgba(48,209,88,0.22);"
    LOSS  = BASE + "background:rgba(255,69,58,0.10);border:1px solid rgba(255,69,58,0.18);"

    DAY_BASE = "font-size:10px;font-weight:500;"
    DAY_NT   = DAY_BASE + "color:#636366;"
    DAY_WIN  = DAY_BASE + "color:rgba(48,209,88,0.7);"
    DAY_LOSS = DAY_BASE + "color:rgba(255,69,58,0.65);"
    PNL_WIN  = "font-size:9.5px;font-weight:600;color:#30D158;text-align:right;font-family:monospace;"
    PNL_LOSS = "font-size:9.5px;font-weight:600;color:#FF453A;text-align:right;font-family:monospace;"

    # Header row
    day_labels = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
    cells = "".join(f'<div style="{HDR}">{d}</div>' for d in day_labels)

    # Empty offset cells
    cells += f'<div style="{EMPTY}"></div>' * first_dow

    # Day cells
    for d in range(1, n_days + 1):
        pnl = day_pnl.get(d)
        if pnl is None:
            cells += f'<div style="{NOTRADE}"><div style="{DAY_NT}">{d}</div></div>'
        elif pnl >= 0:
            pnl_str = f"+${pnl:,.2f}" if pnl >= 1 else f"+${pnl:.2f}"
            cells += (f'<div style="{WIN}">'
                      f'<div style="{DAY_WIN}">{d}</div>'
                      f'<div style="{PNL_WIN}">{pnl_str}</div>'
                      f'</div>')
        else:
            pnl_str = f"-${abs(pnl):,.2f}" if abs(pnl) >= 1 else f"-${abs(pnl):.2f}"
            cells += (f'<div style="{LOSS}">'
                      f'<div style="{DAY_LOSS}">{d}</div>'
                      f'<div style="{PNL_LOSS}">{pnl_str}</div>'
                      f'</div>')

    return f"""
    <div style="margin-bottom:20px;">
        <div style="font-size:12px;font-weight:600;color:#EBEBF5;
                    margin-bottom:8px;letter-spacing:-0.01em;">{month_name}</div>
        <div style="{GRID}">{cells}</div>
    </div>"""
