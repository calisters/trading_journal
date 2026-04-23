"""
Analytics: compute all dashboard metrics from a trades DataFrame.
"""

import logging
from typing import Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def load_trades_df(session) -> pd.DataFrame:
    """Load all trades from DB into a DataFrame."""
    from db.models import Trade
    trades = session.query(Trade).order_by(Trade.exit_time).all()
    if not trades:
        return pd.DataFrame()

    records = []
    for t in trades:
        records.append({
            "id": t.id,
            "symbol": t.symbol,
            "direction": t.direction,
            "entry_time": t.entry_time,
            "exit_time": t.exit_time,
            "holding_seconds": t.holding_seconds,
            "avg_entry_price": t.avg_entry_price,
            "avg_exit_price": t.avg_exit_price,
            "max_position_size": t.max_position_size,
            "total_commission": t.total_commission,
            "gross_pnl": t.gross_pnl,
            "net_pnl": t.net_pnl,
            "return_pct": t.return_pct,
            "deployed_notional": t.deployed_notional,
            "currency": t.currency,
            "account_id": t.account_id,
        })

    df = pd.DataFrame(records)
    df["exit_date"] = pd.to_datetime(df["exit_time"]).dt.date
    df["entry_date"] = pd.to_datetime(df["entry_time"]).dt.date
    df["commission_pct"] = df.apply(
        lambda r: abs(r["total_commission"]) / r["deployed_notional"] * 100
        if r["deployed_notional"] and r["deployed_notional"] != 0 else 0.0,
        axis=1,
    )

    # For manual trades deployed_notional is None/0 — fall back to return_pct directly
    df["gross_return_pct"] = df.apply(
        lambda r: r["gross_pnl"] / r["deployed_notional"] * 100
        if r["deployed_notional"] and r["deployed_notional"] != 0
        else (r["return_pct"] if pd.notna(r["return_pct"]) else 0.0),
        axis=1,
    )

    # Win classification: use return_pct when net_pnl is absent (manual trades)
    df["is_win"] = df.apply(
        lambda r: r["return_pct"] > 0
        if (r["net_pnl"] is None or pd.isna(r["net_pnl"]))
        else r["net_pnl"] > 0,
        axis=1,
    )
    return df


def compute_equity_curve(df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative PnL ($ and %) sorted by exit_time."""
    if df.empty:
        return pd.DataFrame()
    sorted_df = df[df["deployed_notional"] > 0].sort_values("exit_time").copy()
    sorted_df["cum_pnl_usd"] = sorted_df["net_pnl"].cumsum()
    sorted_df["cum_return_pct"] = sorted_df["return_pct"].cumsum()
    sorted_df["cum_gross_return_pct"] = sorted_df["gross_return_pct"].cumsum()
    return sorted_df[["exit_time", "net_pnl", "cum_pnl_usd", "return_pct",
                       "cum_return_pct", "gross_return_pct", "cum_gross_return_pct"]]


def compute_daily_pnl(df: pd.DataFrame) -> pd.DataFrame:
    """Daily aggregated net PnL and return %."""
    if df.empty:
        return pd.DataFrame()
    daily = (
        df.groupby("exit_date")
        .agg(
            net_pnl=("net_pnl", "sum"),
            return_pct=("return_pct", "sum"),
            gross_return_pct=("gross_return_pct", "sum"),
            trades=("id", "count"),
        )
        .reset_index()
    )
    daily["exit_date"] = pd.to_datetime(daily["exit_date"])
    return daily


def compute_summary_metrics(df: pd.DataFrame) -> dict:
    """Win rate, expectancy, avg win/loss — all gross % based."""
    if df.empty:
        return {}

    n = len(df)

    wins_gross   = df[df["gross_return_pct"] > 0]["gross_return_pct"]
    losses_gross = df[df["gross_return_pct"] <= 0]["gross_return_pct"]

    win_rate     = len(wins_gross) / n * 100 if n else 0
    avg_win_pct  = wins_gross.mean()  if len(wins_gross)   else 0.0
    avg_loss_pct = losses_gross.mean() if len(losses_gross) else 0.0

    expectancy_pct = (win_rate / 100 * avg_win_pct) + ((1 - win_rate / 100) * avg_loss_pct)

    total_gross_return_pct = df["gross_return_pct"].sum()

    daily = compute_daily_pnl(df)
    best_day  = daily.loc[daily["gross_return_pct"].idxmax()] if not daily.empty else None
    worst_day = daily.loc[daily["gross_return_pct"].idxmin()] if not daily.empty else None

    by_sym = df.groupby("symbol")["gross_return_pct"].sum()
    best_sym  = by_sym.idxmax() if not by_sym.empty else ""
    worst_sym = by_sym.idxmin() if not by_sym.empty else ""

    return {
        "n_trades": n,
        "win_rate": win_rate,
        "expectancy_pct": expectancy_pct,
        "avg_win_pct": avg_win_pct,
        "avg_loss_pct": avg_loss_pct,
        "total_gross_return_pct": total_gross_return_pct,
        "total_net_pnl": df["net_pnl"].sum(),
        "total_commission": df["total_commission"].sum(),
        "best_day": best_day,
        "worst_day": worst_day,
        "best_symbol": best_sym,
        "worst_symbol": worst_sym,
    }


def compute_insights(df: pd.DataFrame) -> dict:
    """
    Deeper behavioural insights with no ML.
    Returns a dict of categorised finding strings.
    """
    if df.empty:
        return {}

    insights = {}

    # ── Symbol performance ──────────────────────────────────────────────────
    sym_pnl = df.groupby("symbol")["gross_return_pct"].agg(["sum", "count", "mean"]).reset_index()
    sym_pnl.columns = ["symbol", "total_pnl", "trades", "avg_pnl"]
    sym_pnl = sym_pnl.sort_values("total_pnl", ascending=False)
    insights["best_symbols"]  = sym_pnl.head(3).to_dict("records")
    insights["worst_symbols"] = sym_pnl.tail(3).to_dict("records")

    # ── Day-of-week performance ─────────────────────────────────────────────
    df2 = df.copy()
    df2["dow"] = pd.to_datetime(df2["exit_time"]).dt.day_name()
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    dow = df2.groupby("dow")["gross_return_pct"].agg(["sum", "count", "mean"]).reindex(dow_order).reset_index()
    dow.columns = ["day", "total_pnl", "trades", "avg_pnl"]
    insights["dow_performance"] = dow.to_dict("records")

    # ── Fat-tail dependence ─────────────────────────────────────────────────
    sorted_wins = df[df["net_pnl"] > 0]["net_pnl"].sort_values(ascending=False)
    if len(sorted_wins) > 0:
        top1_share = sorted_wins.iloc[0] / sorted_wins.sum() * 100
        top3_share = sorted_wins.iloc[:3].sum() / sorted_wins.sum() * 100 if len(sorted_wins) >= 3 else top1_share
        insights["fat_tail"] = {
            "top1_pct_of_gross_profit": round(top1_share, 1),
            "top3_pct_of_gross_profit": round(top3_share, 1),
            "flag": top1_share > 40,
        }

    # ── Streak analysis ─────────────────────────────────────────────────────
    outcomes = df.sort_values("exit_time")["net_pnl"].apply(lambda x: 1 if x > 0 else -1).tolist()
    max_loss_streak = 0
    cur_loss = 0
    max_win_streak = 0
    cur_win = 0
    for o in outcomes:
        if o < 0:
            cur_loss += 1
            cur_win = 0
            max_loss_streak = max(max_loss_streak, cur_loss)
        else:
            cur_win += 1
            cur_loss = 0
            max_win_streak = max(max_win_streak, cur_win)
    insights["streaks"] = {
        "max_loss_streak": max_loss_streak,
        "max_win_streak": max_win_streak,
    }

    # ── Early-exit fingerprint ──────────────────────────────────────────────
    wins = df[df["net_pnl"] > 0]["net_pnl"]
    losses = df[df["net_pnl"] < 0]["net_pnl"]
    if len(wins) > 0 and len(losses) > 0:
        avg_win = wins.mean()
        avg_loss = abs(losses.mean())
        small_wins_ratio = (wins < avg_win * 0.5).mean()
        large_losses_flag = (abs(losses) > avg_loss * 2).any()
        insights["early_exit"] = {
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "reward_risk": round(avg_win / avg_loss, 2) if avg_loss else 0,
            "small_wins_fraction": round(float(small_wins_ratio), 2),
            "has_large_losses": bool(large_losses_flag),
            "flag": float(small_wins_ratio) > 0.5 and bool(large_losses_flag),
        }

    return insights
