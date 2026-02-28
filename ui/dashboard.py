"""
Dashboard page: equity curve, drawdown, calendar heatmap, metrics cards,
trades table, distribution histogram.
"""

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
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

# ─── Colour palette ───────────────────────────────────────────────────────────
WIN_COLOR = "#00c896"
LOSS_COLOR = "#ff4b6e"
NEUTRAL_COLOR = "#7b8fa1"
BG_COLOR = "#0f1923"
CARD_BG = "#1a2535"
ACCENT = "#3b82f6"


@st.cache_data(ttl=60, show_spinner=False)
def _load_data() -> pd.DataFrame:
    session = get_session()
    try:
        return load_trades_df(session)
    finally:
        session.close()


def _metric_card(col, label: str, value: str, delta: str = "", color: str = "white"):
    col.metric(label=label, value=value, delta=delta if delta else None)


def _fmt(val, prefix="$", decimals=2):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    s = f"{val:,.{decimals}f}"
    return f"{prefix}{s}" if prefix else s


def render_dashboard_page():
    st.header("📊 Trading Dashboard")

    df_all = _load_data()
    if df_all.empty:
        st.info("No trades yet — upload some IBKR files first.")
        return

    # ── Sidebar filters ───────────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("Filters")

        min_date = df_all["exit_time"].min().date()
        max_date = df_all["exit_time"].max().date()
        date_range = st.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            d_from, d_to = date_range
        else:
            d_from, d_to = min_date, max_date

        symbols = ["All"] + sorted(df_all["symbol"].unique().tolist())
        sym_filter = st.selectbox("Symbol", symbols)

        sides = ["All", "Long", "Short"]
        side_filter = st.selectbox("Direction", sides)

        min_trades = st.slider("Min trades per symbol (filter)", 0, 20, 0)

    # ── Apply filters ─────────────────────────────────────────────────────────
    df = df_all.copy()
    df = df[
        (df["exit_time"].dt.date >= d_from) &
        (df["exit_time"].dt.date <= d_to)
    ]
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

    # ── Summary metric cards ──────────────────────────────────────────────────
    st.subheader("Performance Summary")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    _metric_card(c1, "Net P&L", _fmt(metrics.get("total_net_pnl", 0)))
    _metric_card(c2, "Win Rate", f"{metrics.get('win_rate', 0):.1f}%")
    _metric_card(c3, "Profit Factor",
                 f"{metrics.get('profit_factor', 0):.2f}"
                 if metrics.get("profit_factor") != float("inf") else "∞")
    _metric_card(c4, "Expectancy", _fmt(metrics.get("expectancy", 0)))
    _metric_card(c5, "Max Drawdown", f"{metrics.get('max_drawdown_pct', 0):.1f}%")
    _metric_card(c6, "Trades", str(metrics.get("n_trades", 0)))

    c7, c8, c9, c10 = st.columns(4)
    _metric_card(c7, "Avg Win", _fmt(metrics.get("avg_win", 0)))
    _metric_card(c8, "Avg Loss", _fmt(metrics.get("avg_loss", 0)))
    best_sym = metrics.get("best_symbol", "—")
    worst_sym = metrics.get("worst_symbol", "—")
    _metric_card(c9, "Best Symbol", best_sym or "—")
    _metric_card(c10, "Worst Symbol", worst_sym or "—")

    bd = metrics.get("best_day")
    wd = metrics.get("worst_day")
    c11, c12 = st.columns(2)
    if bd is not None:
        c11.metric("Best Day", _fmt(bd["net_pnl"]), str(bd.get("exit_date", "")))
    if wd is not None:
        c12.metric("Worst Day", _fmt(wd["net_pnl"]), str(wd.get("exit_date", "")))

    st.divider()

    # ── Equity Curve ──────────────────────────────────────────────────────────
    st.subheader("Equity Curve")
    eq = compute_equity_curve(df)
    if not eq.empty:
        tab1, tab2 = st.tabs(["Cumulative $", "Cumulative %"])
        with tab1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=eq["exit_time"], y=eq["cum_pnl_usd"],
                mode="lines", name="Cum P&L $",
                line=dict(color=ACCENT, width=2),
                fill="tozeroy",
                fillcolor="rgba(59,130,246,0.12)",
            ))
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor=BG_COLOR,
                plot_bgcolor=BG_COLOR,
                height=320,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="Date",
                yaxis_title="Cumulative P&L ($)",
            )
            st.plotly_chart(fig, use_container_width=True)
        with tab2:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=eq["exit_time"], y=eq["cum_return_pct"],
                mode="lines", name="Cum Return %",
                line=dict(color=WIN_COLOR, width=2),
                fill="tozeroy",
                fillcolor="rgba(0,200,150,0.12)",
            ))
            fig2.update_layout(
                template="plotly_dark",
                paper_bgcolor=BG_COLOR,
                plot_bgcolor=BG_COLOR,
                height=320,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="Date",
                yaxis_title="Cumulative Return (%)",
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ── Drawdown ──────────────────────────────────────────────────────────────
    st.subheader("Drawdown")
    dd = compute_drawdown(eq) if not eq.empty else pd.DataFrame()
    if not dd.empty:
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=dd["exit_time"], y=dd["drawdown_pct"],
            mode="lines", name="Drawdown %",
            line=dict(color=LOSS_COLOR, width=1.5),
            fill="tozeroy",
            fillcolor="rgba(255,75,110,0.15)",
        ))
        fig_dd.update_layout(
            template="plotly_dark",
            paper_bgcolor=BG_COLOR,
            plot_bgcolor=BG_COLOR,
            height=240,
            margin=dict(l=0, r=0, t=10, b=0),
            yaxis_title="Drawdown (%)",
        )
        st.plotly_chart(fig_dd, use_container_width=True)

    # ── Calendar Heatmaps ─────────────────────────────────────────────────────
    st.subheader("Daily P&L Calendar")
    daily = compute_daily_pnl(df)
    if not daily.empty:
        _render_calendar(daily)

    # ── Distribution Histogram ────────────────────────────────────────────────
    st.subheader("Trade P&L Distribution")
    fig_hist = px.histogram(
        df, x="net_pnl", nbins=40,
        color_discrete_sequence=[ACCENT],
        labels={"net_pnl": "Net P&L ($)"},
        template="plotly_dark",
    )
    fig_hist.update_layout(
        paper_bgcolor=BG_COLOR,
        plot_bgcolor=BG_COLOR,
        height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        bargap=0.05,
    )
    fig_hist.add_vline(x=0, line_dash="dash", line_color="white", opacity=0.5)
    st.plotly_chart(fig_hist, use_container_width=True)

    # ── Trades Table ──────────────────────────────────────────────────────────
    st.subheader("All Trades")
    display_cols = {
        "symbol": "Symbol",
        "direction": "Dir",
        "entry_time": "Entry Time",
        "exit_time": "Exit Time",
        "holding_seconds": "Hold (s)",
        "avg_entry_price": "Avg Entry",
        "avg_exit_price": "Avg Exit",
        "max_position_size": "Max Pos",
        "deployed_notional": "Notional ($)",
        "gross_pnl": "Gross P&L",
        "total_commission": "Commission",
        "commission_pct": "Comm %",
        "net_pnl": "Net P&L",
        "return_pct": "Return %",
    }
    table_df = df[list(display_cols.keys())].rename(columns=display_cols).copy()

    # Format numbers for readability
    for col in ["Avg Entry", "Avg Exit", "Notional ($)", "Gross P&L",
                "Commission", "Net P&L"]:
        table_df[col] = table_df[col].map(lambda x: f"${x:,.4f}" if pd.notna(x) else "")
    table_df["Comm %"] = table_df["Comm %"].map(lambda x: f"{x:.3f}%" if pd.notna(x) else "")
    table_df["Return %"] = table_df["Return %"].map(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
    table_df["Max Pos"] = table_df["Max Pos"].map(lambda x: f"{x:,.0f}" if pd.notna(x) else "")

    st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        height=400,
    )


def _render_calendar(daily: pd.DataFrame):
    """Render monthly and annual heatmaps."""
    daily = daily.copy()
    daily["exit_date"] = pd.to_datetime(daily["exit_date"])
    daily["year"] = daily["exit_date"].dt.year
    daily["month"] = daily["exit_date"].dt.month
    daily["day"] = daily["exit_date"].dt.day
    daily["dow"] = daily["exit_date"].dt.weekday  # 0=Mon

    years = sorted(daily["year"].unique())
    year_sel = st.selectbox("Year", years, index=len(years) - 1)
    yr_data = daily[daily["year"] == year_sel]

    tab_m, tab_a = st.tabs(["Monthly Heatmaps", "Annual Heatmap"])

    with tab_m:
        months = sorted(yr_data["month"].unique())
        cols = st.columns(min(len(months), 3))
        for i, m in enumerate(months):
            col = cols[i % 3]
            m_data = yr_data[yr_data["month"] == m]
            _render_month_heatmap(col, m_data, m, year_sel)

    with tab_a:
        _render_annual_heatmap(yr_data, year_sel)


def _render_month_heatmap(container, m_data: pd.DataFrame, month: int, year: int):
    import calendar
    month_name = calendar.month_name[month]
    container.markdown(f"**{month_name}**")

    # Build 6×7 grid
    first_dow = date(year, month, 1).weekday()
    n_days = (date(year, month % 12 + 1, 1) - timedelta(days=1)).day if month < 12 else 31

    day_pnl = {int(r["day"]): r["net_pnl"] for _, r in m_data.iterrows()}
    max_abs = max((abs(v) for v in day_pnl.values()), default=1) or 1

    cells = []
    for d in range(1, n_days + 1):
        pnl = day_pnl.get(d)
        cells.append((d, pnl))

    # Render as plotly heatmap
    grid_z = np.full((6, 7), np.nan)
    grid_text = [[""] * 7 for _ in range(6)]
    pos = first_dow
    for d, pnl in cells:
        row, col_idx = divmod(pos, 7)
        if row < 6:
            if pnl is not None:
                grid_z[row][col_idx] = 1 if pnl >= 0 else -1
            else:
                grid_z[row][col_idx] = np.nan
            grid_text[row][col_idx] = f"{d}<br>${pnl:+.2f}" if pnl is not None else str(d)
        pos += 1

    day_labels = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    fig = go.Figure(go.Heatmap(
        z=grid_z,
        text=grid_text,
        texttemplate="%{text}",
        colorscale=[[0, "#b32424"], [0.499, "#bb2a2a"], [0.501, "#00c896"], [1, "#00c896"]],
        zmin=-1,
        zmax=1,
        showscale=False,
        xgap=2, ygap=2,
        hovertemplate="%{text}<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG_COLOR,
        plot_bgcolor=BG_COLOR,
        height=200,
        margin=dict(l=0, r=0, t=5, b=0),
        xaxis=dict(tickvals=list(range(7)), ticktext=day_labels, showgrid=False),
        yaxis=dict(showticklabels=False, showgrid=False, autorange="reversed"),
        font=dict(size=9),
    )
    container.plotly_chart(fig, use_container_width=True)


def _render_annual_heatmap(yr_data: pd.DataFrame, year: int):
    """GitHub-style full-year heatmap."""
    day_pnl = {r["exit_date"].date(): r["net_pnl"] for _, r in yr_data.iterrows()}

    # Build 53 weeks × 7 days grid
    jan1 = date(year, 1, 1)
    dec31 = date(year, 12, 31)
    start = jan1 - timedelta(days=jan1.weekday())  # start on Monday

    weeks_z = []
    weeks_text = []
    week_dates = []
    cur = start
    while cur <= dec31 or len(weeks_z) < 53:
        week_z = []
        week_t = []
        week_d = []
        for _ in range(7):
            pnl = day_pnl.get(cur) if jan1 <= cur <= dec31 else None
            if pnl is not None:
                week_z.append(1 if pnl >= 0 else -1)
            else:
                week_z.append(np.nan)
            week_t.append(
                f"{cur.strftime('%b %d')}: ${pnl:+.2f}" if pnl is not None
                else cur.strftime('%b %d') if jan1 <= cur <= dec31 else ""
            )
            week_d.append(str(cur))
            cur += timedelta(days=1)
        weeks_z.append(week_z)
        weeks_text.append(week_t)
        week_dates.append(week_d[0])
        if cur > dec31 and len(weeks_z) >= 52:
            break

    z_arr = np.array(weeks_z).T  # shape (7, n_weeks)
    text_arr = np.array(weeks_text).T

    fig = go.Figure(go.Heatmap(
        z=z_arr,
        text=text_arr,
        colorscale=[[0, "#ffb3b3"], [0.499, "#ffb3b3"], [0.501, "#b3ffcc"], [1, "#b3ffcc"]],
        zmin=-1,
        zmax=1,
        showscale=False,
        xgap=2, ygap=2,
        hovertemplate="%{text}<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG_COLOR,
        plot_bgcolor=BG_COLOR,
        height=200,
        margin=dict(l=40, r=20, t=10, b=20),
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(
            tickvals=list(range(7)),
            ticktext=["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
            showgrid=False,
        ),
        title=dict(text=f"{year} Annual P&L Heatmap", font=dict(size=13)),
    )
    st.plotly_chart(fig, use_container_width=True)
