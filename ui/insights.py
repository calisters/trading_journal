"""
Insights page — Apple-style, Tradervue-quality.
Fee analysis · Symbol performance · Day-of-week · Behavioural flags
All HTML uses 100% inline styles — no CSS class dependencies.
"""

import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics.metrics import compute_insights, load_trades_df
from db.database import get_session

logger = logging.getLogger(__name__)

# ── Design tokens ─────────────────────────────────────────────────────────────
G   = "#30D158"
R   = "#FF453A"
B   = "#0A84FF"
BG  = "#0A0A0F"
S1  = "#1C1C1E"
T1  = "#FFFFFF"
T2  = "#EBEBF5"
T3  = "#8E8E93"
SEP = "rgba(255,255,255,0.07)"

# Only global font + background in CSS — nothing layout-specific
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


# ── Inline HTML helpers ───────────────────────────────────────────────────────

def _section_title(text: str) -> str:
    return (f'<div style="font-size:11px;font-weight:600;letter-spacing:0.12em;'
            f'text-transform:uppercase;color:{T3};margin:0 0 12px 0;">{text}</div>')


def _divider() -> str:
    return f'<hr style="border:none;border-top:1px solid {SEP};margin:28px 0;">'


def _card(label: str, value: str, sub: str = "", value_color: str = T1) -> str:
    sub_html = (f'<div style="font-size:12px;color:{T3};margin-top:4px;'
                f'font-family:monospace;">{sub}</div>') if sub else ""
    return f"""
    <div style="background:{S1};border:1px solid {SEP};border-radius:14px;
                padding:18px 20px 16px;height:100%;">
        <div style="font-size:11px;font-weight:500;letter-spacing:0.06em;
                    text-transform:uppercase;color:{T3};margin-bottom:8px;">{label}</div>
        <div style="font-size:24px;font-weight:600;letter-spacing:-0.03em;
                    color:{value_color};font-family:monospace;">{value}</div>
        {sub_html}
    </div>"""


def _sym_section(title: str, sym_list: list, pnl_color: str) -> str:
    rows = ""
    for r in sym_list:
        pnl_str = f"${r['total_pnl']:+,.2f}"
        rows += f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
                    padding:12px 16px;border-bottom:1px solid {SEP};">
            <div>
                <div style="font-size:14px;font-weight:600;color:{T2};">{r['symbol']}</div>
                <div style="font-size:12px;color:{T3};margin-top:2px;">
                    {r['trades']} trades &middot; avg ${r['avg_pnl']:+.2f}
                </div>
            </div>
            <div style="font-size:15px;font-weight:600;color:{pnl_color};
                        font-family:monospace;">{pnl_str}</div>
        </div>"""
    return f"""
    <div style="background:{S1};border:1px solid {SEP};border-radius:14px;overflow:hidden;">
        <div style="font-size:11px;font-weight:600;letter-spacing:0.08em;
                    text-transform:uppercase;color:{T3};
                    padding:12px 16px;border-bottom:1px solid {SEP};">{title}</div>
        {rows}
    </div>"""


def _flag_card(title: str, body: str, is_warn: bool) -> str:
    if is_warn:
        bg     = "rgba(255,69,58,0.06)"
        border = "rgba(255,69,58,0.4)"
        badge  = (f'<span style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
                  f'padding:2px 8px;border-radius:20px;text-transform:uppercase;'
                  f'background:rgba(255,69,58,0.2);color:{R};">&#9888; Flag</span>')
    else:
        bg     = "rgba(48,209,88,0.04)"
        border = "rgba(48,209,88,0.3)"
        badge  = (f'<span style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
                  f'padding:2px 8px;border-radius:20px;text-transform:uppercase;'
                  f'background:rgba(48,209,88,0.15);color:{G};">&#10003; OK</span>')
    return f"""
    <div style="background:{bg};border:1px solid {border};border-radius:14px;
                padding:18px 20px;margin-bottom:12px;">
        <div style="font-size:13px;font-weight:600;color:{T2};margin-bottom:6px;
                    display:flex;align-items:center;gap:8px;">{title}&nbsp;{badge}</div>
        <div style="font-size:13px;color:{T3};line-height:1.6;">{body}</div>
    </div>"""


def _chart_layout(h=280, yaxis_title="", xaxis_title=""):
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=h,
        margin=dict(l=4, r=4, t=4, b=4),
        font=dict(family="DM Sans, sans-serif", color=T3, size=11),
        xaxis=dict(
            title=xaxis_title, showgrid=False, zeroline=False, showline=False,
            tickfont=dict(color=T3, size=10), title_font=dict(color=T3),
        ),
        yaxis=dict(
            title=yaxis_title, showgrid=True, gridcolor=SEP,
            zeroline=True, zerolinecolor="rgba(255,255,255,0.1)", zerolinewidth=1,
            showline=False, tickfont=dict(color=T3, size=10), title_font=dict(color=T3),
        ),
        hovermode="x unified",
        showlegend=False,
    )


# ── Main page ─────────────────────────────────────────────────────────────────

def render_insights_page():
    st.markdown(CSS, unsafe_allow_html=True)

    df = _load_data()
    if df.empty:
        st.info("No trades yet — upload IBKR files to get started.")
        return

    insights = compute_insights(df)

    # Page title
    st.markdown(f"""
        <div style="font-size:26px;font-weight:600;color:{T1};
                    letter-spacing:-0.03em;margin:0 0 4px 0;">Insights</div>
        <div style="font-size:13px;color:{T3};margin-bottom:28px;font-weight:400;">
            Behavioural analysis &middot; Fee breakdown &middot; Symbol edge
        </div>
    """, unsafe_allow_html=True)

    # ── Fee breakdown ─────────────────────────────────────────────────────────
    st.markdown(_section_title("Commission &amp; Fees"), unsafe_allow_html=True)

    total_notional = df["deployed_notional"].sum()
    total_comm     = abs(df["total_commission"].sum())
    net_pnl        = df["net_pnl"].sum()
    gross_pnl      = df["gross_pnl"].sum()
    comm_pct       = total_comm / total_notional * 100 if total_notional else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(_card("Total Commissions", f"${total_comm:,.4f}", "all-in fees paid", R),
                    unsafe_allow_html=True)
    with c2:
        st.markdown(_card("Deployed Notional", f"${total_notional:,.0f}", "buy-side only"),
                    unsafe_allow_html=True)
    with c3:
        st.markdown(_card("Comm % of Notional", f"{comm_pct:.3f}%", "cost per dollar traded"),
                    unsafe_allow_html=True)
    with c4:
        vc = G if net_pnl >= 0 else R
        st.markdown(_card("Net P&L (after fees)", f"${net_pnl:+,.4f}", "", vc),
                    unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Donut + commission table
    left, right = st.columns([1, 2])
    with left:
        fig_pie = go.Figure(go.Pie(
            labels=["Net P&L", "Commissions"],
            values=[max(gross_pnl, 0), total_comm],
            hole=0.60,
            marker_colors=[G, R],
            textinfo="percent",
            hoverinfo="label+value+percent",
            textfont=dict(size=12, color=T1),
        ))
        fig_pie.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            height=240,
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=True,
            legend=dict(font=dict(color=T3, size=11),
                        orientation="h", yanchor="bottom", y=-0.15,
                        x=0.5, xanchor="center"),
            annotations=[dict(
                text=f"<b>${gross_pnl:,.0f}</b>",
                x=0.5, y=0.5, font_size=14, font_color=T1, showarrow=False,
            )],
        )
        st.plotly_chart(fig_pie, width="stretch", config={"displayModeBar": False})

    with right:
        sym_comm = (
            df.groupby("symbol")
            .agg(total_commission=("total_commission", lambda x: abs(x.sum())),
                 buy_notional=("deployed_notional", "sum"),
                 trades=("id", "count"))
            .reset_index()
        )
        sym_comm["comm_pct"] = sym_comm["total_commission"] / sym_comm["buy_notional"] * 100
        sym_comm = sym_comm.sort_values("total_commission", ascending=False)
        tbl = sym_comm.copy()
        tbl.columns = ["Symbol", "Commission ($)", "Notional ($)", "Trades", "Comm %"]
        tbl["Commission ($)"] = tbl["Commission ($)"].map(lambda x: f"${x:.4f}")
        tbl["Notional ($)"]   = tbl["Notional ($)"].map(lambda x: f"${x:,.2f}")
        tbl["Comm %"]         = tbl["Comm %"].map(lambda x: f"{x:.3f}%")
        st.dataframe(tbl, width="stretch", hide_index=True, height=220)

    st.markdown(_divider(), unsafe_allow_html=True)

    # ── Symbol performance ────────────────────────────────────────────────────
    st.markdown(_section_title("Symbol Performance"), unsafe_allow_html=True)

    sym_pnl = df.groupby("symbol")["gross_return_pct"].sum().reset_index().sort_values("gross_return_pct")
    bar_colors = ["rgba(48,209,88,0.75)" if v >= 0 else "rgba(255,69,58,0.75)"
                  for v in sym_pnl["gross_return_pct"]]

    fig_sym = go.Figure(go.Bar(
        x=sym_pnl["symbol"], y=sym_pnl["gross_return_pct"],
        marker_color=bar_colors, marker_line_width=0,
        hovertemplate="<b>%{x}</b><br>Gross Return: %{y:.2f}%<extra></extra>",
    ))
    fig_sym.add_hline(y=0, line_width=1, line_color="rgba(255,255,255,0.15)")
    fig_sym.update_layout(**_chart_layout(h=260, xaxis_title="Symbol", yaxis_title="Gross Return (%)"))
    st.plotly_chart(fig_sym, width="stretch", config={"staticPlot": True})

    best_syms  = insights.get("best_symbols", [])
    worst_syms = insights.get("worst_symbols", [])
    col_b, col_w = st.columns(2)
    # with col_b:
    #     st.markdown(_sym_section("Best Symbols", best_syms, G), unsafe_allow_html=True)
    # with col_w:
    #     st.markdown(_sym_section("Worst Symbols", worst_syms, R), unsafe_allow_html=True)

    st.markdown(_divider(), unsafe_allow_html=True)

    # ── Day-of-week ───────────────────────────────────────────────────────────
    st.markdown(_section_title("Day-of-Week Performance"), unsafe_allow_html=True)

    dow_data = pd.DataFrame(insights.get("dow_performance", [])).dropna(subset=["total_pnl"])
    if not dow_data.empty:
        bar_c = ["rgba(48,209,88,0.75)" if v >= 0 else "rgba(255,69,58,0.75)"
                 for v in dow_data["total_pnl"]]
        fig_dow = go.Figure(go.Bar(
            x=dow_data["day"], y=dow_data["total_pnl"],
            marker_color=bar_c, marker_line_width=0,
            text=dow_data["trades"].map(str),
            textposition="outside",
            textfont=dict(color=T3, size=10),
            hovertemplate="<b>%{x}</b><br>Gross Return: %{y:.2f}%<br>Trades: %{text}<extra></extra>",
        ))
        fig_dow.add_hline(y=0, line_width=1, line_color="rgba(255,255,255,0.15)")
        fig_dow.update_layout(**_chart_layout(h=240, yaxis_title="Gross Return (%)"))
        st.plotly_chart(fig_dow, width="stretch", config={"staticPlot": True})

        # Win rate by day
        df2 = df.copy()
        df2["dow"] = pd.to_datetime(df2["exit_time"]).dt.day_name()
        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        dow_wr = (
            df2.groupby("dow")["net_pnl"]
            .apply(lambda x: (x > 0).mean() * 100)
            .reindex(dow_order)
            .reset_index()
        )
        dow_wr.columns = ["day", "win_rate"]
        fig_wr = go.Figure(go.Bar(
            x=dow_wr["day"], y=dow_wr["win_rate"],
            marker_color="rgba(10,132,255,0.65)", marker_line_width=0,
            text=dow_wr["win_rate"].map(lambda x: f"{x:.0f}%"),
            textposition="outside",
            textfont=dict(color=T3, size=10),
            hovertemplate="<b>%{x}</b><br>Win Rate: %{y:.1f}%<extra></extra>",
        ))
        fig_wr.add_hline(y=50, line_width=1, line_dash="dash",
                         line_color="rgba(255,255,255,0.2)")
        fig_wr.update_layout(**_chart_layout(h=180, yaxis_title="Win Rate (%)"))
        st.plotly_chart(fig_wr, width="stretch", config={"displayModeBar": False})

    st.markdown(_divider(), unsafe_allow_html=True)

    # ── Behavioural flags ─────────────────────────────────────────────────────
    st.markdown(_section_title("Behavioural Analysis"), unsafe_allow_html=True)

    ft = insights.get("fat_tail", {})
    if ft:
        warn_line = ("<br>Returns are concentrated in a few outlier trades — "
                     "edge may not be systematic.") if ft.get("flag") else ""
        body = (f"Top trade = <b style='color:{T2}'>{ft['top1_pct_of_gross_profit']:.1f}%</b> of gross profit &middot; "
                f"Top 3 trades = <b style='color:{T2}'>{ft['top3_pct_of_gross_profit']:.1f}%</b> of gross profit"
                f"{warn_line}")
        st.markdown(_flag_card("Fat-Tail Dependence", body, ft.get("flag", False)),
                    unsafe_allow_html=True)

    st_data = insights.get("streaks", {})
    if st_data:
        max_loss = st_data["max_loss_streak"]
        max_win  = st_data["max_win_streak"]
        body = (f"Longest winning streak: <b style='color:{G}'>{max_win} trades</b> &middot; "
                f"Longest losing streak: <b style='color:{R}'>{max_loss} trades</b>")
        st.markdown(_flag_card("Streak Analysis", body, max_loss >= 5),
                    unsafe_allow_html=True)

    ee = insights.get("early_exit", {})
    if ee:
        warn_line = ("<br>Many small wins + occasional large losses — "
                     "possible premature exit on winners.") if ee.get("flag") else ""
        body = (f"Avg win: <b style='color:{G}'>${ee['avg_win']:.4f}</b> &middot; "
                f"Avg loss: <b style='color:{R}'>${ee['avg_loss']:.4f}</b> &middot; "
                f"Reward/Risk: <b style='color:{T2}'>{ee['reward_risk']:.2f}</b> &middot; "
                f"Small wins (&lt;50% avg): <b style='color:{T2}'>{ee['small_wins_fraction']*100:.0f}%</b>"
                f"{warn_line}")
        st.markdown(_flag_card("Early-Exit Pattern", body, ee.get("flag", False)),
                    unsafe_allow_html=True)

    st.markdown(_divider(), unsafe_allow_html=True)

    # ── Full stats table ──────────────────────────────────────────────────────
    st.markdown(_section_title("Full Stats"), unsafe_allow_html=True)

    wins_df = df[df["net_pnl"] > 0]
    loss_df = df[df["net_pnl"] <= 0]
    pf = wins_df["net_pnl"].sum() / abs(loss_df["net_pnl"].sum()) if len(loss_df) > 0 else float("inf")

    stats_rows = [
        ("Total Trades",       str(len(df))),
        ("Winning Trades",     str(len(wins_df))),
        ("Losing Trades",      str(len(loss_df))),
        ("Win Rate",           f"{len(wins_df)/len(df)*100:.1f}%" if len(df) > 0 else "—"),
        ("Profit Factor",      f"{pf:.2f}" if pf != float("inf") else "inf"),
        ("Expectancy",         f"${df['net_pnl'].mean():.4f}"),
        ("Avg Win",            f"${wins_df['net_pnl'].mean():.4f}" if len(wins_df) > 0 else "—"),
        ("Avg Loss",           f"${loss_df['net_pnl'].mean():.4f}" if len(loss_df) > 0 else "—"),
        ("Gross Profit",       f"${wins_df['net_pnl'].sum():,.4f}"),
        ("Gross Loss",         f"${loss_df['net_pnl'].sum():,.4f}"),
        ("Total Commission",   f"${total_comm:.4f}"),
        ("Comm % of Notional", f"{comm_pct:.3f}%"),
        ("Max Loss Streak",    str(st_data.get("max_loss_streak", "—"))),
        ("Max Win Streak",     str(st_data.get("max_win_streak", "—"))),
    ]
    stats_df = pd.DataFrame(stats_rows, columns=["Metric", "Value"])
    st.dataframe(stats_df, width="stretch", hide_index=True)
