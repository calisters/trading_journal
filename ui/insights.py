"""
Insights page: fee analysis, behavioural flags, symbol/dow analysis.
"""

import logging

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analytics.metrics import compute_insights, load_trades_df
from db.database import get_session

logger = logging.getLogger(__name__)

BG_COLOR = "#0f1923"
WIN_COLOR = "#00c896"
LOSS_COLOR = "#ff4b6e"
ACCENT = "#3b82f6"


@st.cache_data(ttl=60, show_spinner=False)
def _load_data() -> pd.DataFrame:
    session = get_session()
    try:
        return load_trades_df(session)
    finally:
        session.close()


def render_insights_page():
    st.header("Insights")

    df = _load_data()
    if df.empty:
        st.info("No trades yet - upload some IBKR files first.")
        return

    insights = compute_insights(df)

    # Fee & Commission Breakdown
    st.subheader("Fee and Commission Analysis")

    total_buy_notional = df["deployed_notional"].sum()
    total_commission = abs(df["total_commission"].sum())
    net_pnl = df["net_pnl"].sum()
    gross_pnl = df["gross_pnl"].sum()
    comm_pct_of_buy = total_commission / total_buy_notional * 100 if total_buy_notional else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Commissions Paid", f"${total_commission:,.4f}")
    c2.metric("Buy Notional (Deployed)", f"${total_buy_notional:,.2f}")
    c3.metric("Comm as % of Buy Value", f"{comm_pct_of_buy:.3f}%")
    c4.metric("Net P&L after Commissions", f"${net_pnl:,.4f}")

    pie_labels = ["Net P&L (kept)", "Commissions (paid)"]
    pie_values = [max(gross_pnl, 0), total_commission]
    fig_pie = go.Figure(go.Pie(
        labels=pie_labels,
        values=pie_values,
        hole=0.45,
        marker_colors=[WIN_COLOR, LOSS_COLOR],
        textinfo="label+percent",
    ))
    fig_pie.update_layout(
        title="Gross Profit Split: Net P&L vs Commissions",
        template="plotly_dark",
        paper_bgcolor=BG_COLOR,
        height=340,
        margin=dict(l=0, r=0, t=50, b=0),
    )
    st.plotly_chart(fig_pie, use_container_width=True)

    sym_comm = (
        df.groupby("symbol")
        .agg(
            total_commission=("total_commission", lambda x: abs(x.sum())),
            buy_notional=("deployed_notional", "sum"),
            trades=("id", "count"),
        )
        .reset_index()
    )
    sym_comm["comm_pct"] = sym_comm["total_commission"] / sym_comm["buy_notional"] * 100
    sym_comm = sym_comm.sort_values("total_commission", ascending=False)

    st.markdown("**Commission by Symbol**")
    display = sym_comm.copy()
    display.columns = ["Symbol", "Total Comm ($)", "Buy Notional ($)", "Trades", "Comm %"]
    display["Total Comm ($)"] = display["Total Comm ($)"].map(lambda x: f"${x:.4f}")
    display["Buy Notional ($)"] = display["Buy Notional ($)"].map(lambda x: f"${x:.2f}")
    display["Comm %"] = display["Comm %"].map(lambda x: f"{x:.3f}%")
    st.dataframe(display, use_container_width=True, hide_index=True)

    st.divider()

    # Symbol Performance
    st.subheader("Symbol Performance")
    col_b, col_w = st.columns(2)

    with col_b:
        st.markdown("**Best Symbols**")
        for r in insights.get("best_symbols", []):
            st.markdown(
                f"- **{r['symbol']}**: ${r['total_pnl']:+.2f} "
                f"over {r['trades']} trade(s), avg ${r['avg_pnl']:+.2f}"
            )

    with col_w:
        st.markdown("**Worst Symbols**")
        for r in insights.get("worst_symbols", []):
            st.markdown(
                f"- **{r['symbol']}**: ${r['total_pnl']:+.2f} "
                f"over {r['trades']} trade(s), avg ${r['avg_pnl']:+.2f}"
            )

    sym_pnl_all = df.groupby("symbol")["net_pnl"].sum().reset_index().sort_values("net_pnl")
    colors = [WIN_COLOR if v >= 0 else LOSS_COLOR for v in sym_pnl_all["net_pnl"]]
    fig_sym = go.Figure(go.Bar(
        x=sym_pnl_all["symbol"],
        y=sym_pnl_all["net_pnl"],
        marker_color=colors,
    ))
    fig_sym.update_layout(
        title="Net P&L by Symbol",
        template="plotly_dark",
        paper_bgcolor=BG_COLOR,
        plot_bgcolor=BG_COLOR,
        height=300,
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis_title="Symbol",
        yaxis_title="Net P&L ($)",
    )
    fig_sym.add_hline(y=0, line_dash="dot", line_color="white", opacity=0.3)
    st.plotly_chart(fig_sym, use_container_width=True)

    st.divider()

    # Day-of-Week Performance
    st.subheader("Day-of-Week Performance")
    dow_data = pd.DataFrame(insights.get("dow_performance", []))
    if not dow_data.empty:
        dow_data = dow_data.dropna(subset=["total_pnl"])
        dow_colors = [WIN_COLOR if v >= 0 else LOSS_COLOR for v in dow_data["total_pnl"]]
        fig_dow = go.Figure(go.Bar(
            x=dow_data["day"],
            y=dow_data["total_pnl"],
            marker_color=dow_colors,
            text=dow_data["trades"].map(lambda x: f"{x} trades"),
            textposition="outside",
        ))
        fig_dow.update_layout(
            title="Net P&L by Day of Week",
            template="plotly_dark",
            paper_bgcolor=BG_COLOR,
            plot_bgcolor=BG_COLOR,
            height=280,
            margin=dict(l=0, r=0, t=40, b=0),
        )
        fig_dow.add_hline(y=0, line_dash="dot", line_color="white", opacity=0.3)
        st.plotly_chart(fig_dow, use_container_width=True)

    st.divider()

    # Behavioural Flags
    st.subheader("Behavioural Flags")

    ft = insights.get("fat_tail", {})
    if ft:
        flag_icon = "RED FLAG" if ft.get("flag") else "OK"
        st.markdown(
            f"**Fat-Tail Dependence [{flag_icon}]**: "
            f"Top 1 trade = {ft['top1_pct_of_gross_profit']:.1f}% of gross profit; "
            f"Top 3 = {ft['top3_pct_of_gross_profit']:.1f}%."
        )
        if ft.get("flag"):
            st.warning("Returns are concentrated in a few outlier trades. Edge may not be systematic.")

    st_data = insights.get("streaks", {})
    if st_data:
        st.markdown(
            f"**Streaks**: Worst losing streak = {st_data['max_loss_streak']} trades. "
            f"Best winning streak = {st_data['max_win_streak']} trades."
        )

    ee = insights.get("early_exit", {})
    if ee:
        flag_icon = "RED FLAG" if ee.get("flag") else "OK"
        st.markdown(
            f"**Early-Exit Pattern [{flag_icon}]**: "
            f"Avg win = ${ee['avg_win']:.4f}, avg loss = ${ee['avg_loss']:.4f}, "
            f"reward/risk = {ee['reward_risk']:.2f}. "
            f"{ee['small_wins_fraction']*100:.0f}% of wins are below half the avg win."
        )
        if ee.get("flag"):
            st.warning(
                "Pattern detected: many small wins alongside occasional large losses. "
                "This may indicate cutting winners too early or letting losers run."
            )

    st.divider()

    # Raw stats table for analyst
    st.subheader("Full Stats Table")
    stats = {
        "Metric": [
            "Total Trades", "Win Rate", "Profit Factor", "Expectancy",
            "Avg Win", "Avg Loss", "Total Commission", "Comm % of Notional",
            "Max Loss Streak", "Max Win Streak",
        ],
        "Value": [
            len(df),
            f"{(df['net_pnl'] > 0).mean()*100:.1f}%",
            f"{df[df['net_pnl']>0]['net_pnl'].sum() / abs(df[df['net_pnl']<=0]['net_pnl'].sum()):.2f}"
            if len(df[df['net_pnl'] <= 0]) > 0 else "inf",
            f"${(df['net_pnl']).mean():.4f}",
            f"${df[df['net_pnl']>0]['net_pnl'].mean():.4f}" if len(df[df['net_pnl']>0]) else "—",
            f"${df[df['net_pnl']<=0]['net_pnl'].mean():.4f}" if len(df[df['net_pnl']<=0]) else "—",
            f"${total_commission:.4f}",
            f"{comm_pct_of_buy:.3f}%",
            str(st_data.get("max_loss_streak", "—")),
            str(st_data.get("max_win_streak", "—")),
        ],
    }
    st.dataframe(pd.DataFrame(stats), use_container_width=True, hide_index=True)
