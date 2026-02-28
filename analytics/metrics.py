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
    df["is_win"] = df["net_pnl"] > 0
    return df


def compute_equity_curve(df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative PnL ($ and %) sorted by exit_time."""
    if df.empty:
        return pd.DataFrame()
    sorted_df = df.sort_values("exit_time").copy()
    sorted_df = df[df["deployed_notional"] > 0].sort_values("exit_time").copy()
    sorted_df["cum_pnl_usd"] = sorted_df["net_pnl"].cumsum()
    sorted_df["cum_return_pct"] = sorted_df["return_pct"].cumsum()
    return sorted_df[["exit_time", "net_pnl", "cum_pnl_usd", "return_pct", "cum_return_pct"]]


def compute_drawdown(equity_curve: pd.DataFrame) -> pd.DataFrame:
    """Peak-to-trough drawdown on cumulative $ PnL."""
    if equity_curve.empty:
        return pd.DataFrame()
    ec = equity_curve.copy()
    ec["peak"] = ec["cum_pnl_usd"].cummax()
    ec["drawdown_usd"] = ec["cum_pnl_usd"] - ec["peak"]
    ec["drawdown_pct"] = ec.apply(
        lambda r: (r["drawdown_usd"] / r["peak"] * 100) if r["peak"] != 0 else 0.0,
        axis=1,
    )
    return ec


def compute_daily_pnl(df: pd.DataFrame) -> pd.DataFrame:
    """Daily aggregated net PnL and return %."""
    if df.empty:
        return pd.DataFrame()
    daily = (
        df.groupby("exit_date")
        .agg(
            net_pnl=("net_pnl", "sum"),
            trades=("id", "count"),
        )
        .reset_index()
    )
    daily["exit_date"] = pd.to_datetime(daily["exit_date"])
    return daily


def compute_summary_metrics(df: pd.DataFrame) -> dict:
    """Win rate, profit factor, expectancy, avg win/loss, etc."""
    if df.empty:
        return {}

    wins = df[df["net_pnl"] > 0]
    losses = df[df["net_pnl"] <= 0]
    n = len(df)

    win_rate = len(wins) / n * 100 if n else 0
    avg_win = wins["net_pnl"].mean() if len(wins) else 0
    avg_loss = losses["net_pnl"].mean() if len(losses) else 0

    gross_profit = wins["net_pnl"].sum()
    gross_loss = abs(losses["net_pnl"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss != 0 else float("inf")

    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

    # Equity curve for drawdown
    eq = compute_equity_curve(df)
    dd = compute_drawdown(eq)
    max_drawdown_pct = dd["drawdown_pct"].min() if not dd.empty else 0

    # Best/worst day
    daily = compute_daily_pnl(df)
    best_day = daily.loc[daily["net_pnl"].idxmax()] if not daily.empty else None
    worst_day = daily.loc[daily["net_pnl"].idxmin()] if not daily.empty else None

    # Best/worst symbol
    by_sym = df.groupby("symbol")["net_pnl"].sum()
    best_sym = by_sym.idxmax() if not by_sym.empty else ""
    worst_sym = by_sym.idxmin() if not by_sym.empty else ""

    return {
        "n_trades": n,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "total_net_pnl": df["net_pnl"].sum(),
        "total_commission": df["total_commission"].sum(),
        "max_drawdown_pct": max_drawdown_pct,
        "best_day": best_day,
        "worst_day": worst_day,
        "best_symbol": best_sym,
        "worst_symbol": worst_sym,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
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
    sym_pnl = df.groupby("symbol")["net_pnl"].agg(["sum", "count", "mean"]).reset_index()
    sym_pnl.columns = ["symbol", "total_pnl", "trades", "avg_pnl"]
    sym_pnl = sym_pnl.sort_values("total_pnl", ascending=False)
    insights["best_symbols"] = sym_pnl.head(3).to_dict("records")
    insights["worst_symbols"] = sym_pnl.tail(3).to_dict("records")

    # ── Day-of-week performance ─────────────────────────────────────────────
    df2 = df.copy()
    df2["dow"] = pd.to_datetime(df2["exit_time"]).dt.day_name()
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    dow = df2.groupby("dow")["net_pnl"].agg(["sum", "count", "mean"]).reindex(dow_order).reset_index()
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
            "flag": top1_share > 40,  # one trade driving > 40 % = dependency
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
