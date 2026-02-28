"""
Trade Builder
=============
Converts a list of Fill ORM objects into completed round-trip Trade records.

Algorithm
---------
For each symbol, sort fills by timestamp.
Maintain a running position (signed: + for long, - for short).
When position crosses zero, close the current trade and open a new one if
the crossing fill had residual qty.

Handles:
 - scaling in/out
 - partial exits
 - multiple entries before first exit
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import List, Tuple

from db.models import Fill, Trade, TradeLeg

logger = logging.getLogger(__name__)


def _weighted_avg(prices: List[float], qtys: List[float]) -> float:
    total_qty = sum(qtys)
    if total_qty == 0:
        return 0.0
    return sum(p * q for p, q in zip(prices, qtys)) / total_qty


def build_trades(fills: List[Fill]) -> List[Tuple[Trade, List[TradeLeg]]]:
    """
    Given a list of Fill ORM objects (already saved in DB),
    return a list of (Trade, [TradeLeg, ...]) tuples ready to be saved.
    """
    # Group by symbol
    by_symbol: dict[str, List[Fill]] = defaultdict(list)
    for f in fills:
        by_symbol[f.symbol].append(f)

    results: List[Tuple[Trade, List[TradeLeg]]] = []

    for symbol, sym_fills in by_symbol.items():
        sym_fills.sort(key=lambda f: f.timestamp)
        results.extend(_build_symbol_trades(symbol, sym_fills))

    logger.info("Built %d round-trip trades from %d fills", len(results), len(fills))
    return results


def _build_symbol_trades(symbol: str, fills: List[Fill]) -> List[Tuple[Trade, List[TradeLeg]]]:
    """Process one symbol's fills into zero or more completed trades."""
    results = []

    # State for the open trade being accumulated
    position = 0.0         # signed running position
    entry_fills: List[Fill] = []
    exit_fills: List[Fill] = []
    entry_qtys: List[float] = []
    exit_qtys: List[float] = []
    total_commission = 0.0
    max_position = 0.0
    currency = fills[0].currency if fills else "USD"
    account_id = fills[0].account_id if fills else None

    def _flush_trade() -> None:
        nonlocal position, entry_fills, exit_fills, entry_qtys, exit_qtys
        nonlocal total_commission, max_position

        if not entry_fills:
            return

        entry_time = entry_fills[0].timestamp
        exit_time = exit_fills[-1].timestamp if exit_fills else entry_fills[-1].timestamp
        holding_seconds = int((exit_time - entry_time).total_seconds())

        avg_entry = _weighted_avg([f.price for f in entry_fills], entry_qtys)
        avg_exit = _weighted_avg([f.price for f in exit_fills], exit_qtys) if exit_fills else 0.0

        total_entry_qty = sum(entry_qtys)
        total_exit_qty = sum(exit_qtys)
        matched_qty = min(total_entry_qty, total_exit_qty)

        direction = "Long" if entry_fills[0].side == "BUY" else "Short"

        # Gross PnL (before commission)
        if direction == "Long":
            gross_pnl = (avg_exit - avg_entry) * matched_qty
        else:
            gross_pnl = (avg_entry - avg_exit) * matched_qty

        deployed_notional = avg_entry * matched_qty
        net_pnl = gross_pnl + total_commission  # commission is negative
        return_pct = (net_pnl / deployed_notional * 100) if deployed_notional else 0.0

        trade = Trade(
            symbol=symbol,
            direction=direction,
            entry_time=entry_time,
            exit_time=exit_time,
            holding_seconds=holding_seconds,
            avg_entry_price=avg_entry,
            avg_exit_price=avg_exit,
            max_position_size=max_position,
            total_commission=total_commission,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            return_pct=return_pct,
            deployed_notional=deployed_notional,
            currency=currency,
            account_id=account_id,
        )

        legs = []
        for f in entry_fills:
            legs.append(TradeLeg(fill=f, leg_type="ENTRY"))
        for f in exit_fills:
            legs.append(TradeLeg(fill=f, leg_type="EXIT"))

        results.append((trade, legs))

        # Reset state
        entry_fills.clear()
        exit_fills.clear()
        entry_qtys.clear()
        exit_qtys.clear()

    for fill in fills:
        signed_qty = fill.qty if fill.side == "BUY" else -fill.qty
        total_commission += fill.commission

        if position == 0.0:
            # Starting a new trade
            entry_fills.append(fill)
            entry_qtys.append(fill.qty)
            position += signed_qty
            max_position = abs(position)
        else:
            prev_sign = 1 if position > 0 else -1
            new_position = position + signed_qty

            if new_position == 0.0:
                # Exactly closed
                exit_fills.append(fill)
                exit_qtys.append(fill.qty)
                position = 0.0
                _flush_trade()

            elif (new_position > 0) == (position > 0):
                # Same direction: scaling in or partially exiting
                if fill.side == ("BUY" if prev_sign > 0 else "SELL"):
                    # Adding to position (scale in)
                    entry_fills.append(fill)
                    entry_qtys.append(fill.qty)
                else:
                    # Partial exit
                    exit_fills.append(fill)
                    exit_qtys.append(fill.qty)
                position = new_position
                max_position = max(max_position, abs(position))

            else:
                # Position flipped — close current and open new
                # The fill partially closes and then opens opposite
                close_qty = abs(position)
                leftover_qty = fill.qty - close_qty

                # Synthetic exit fill with close_qty
                exit_fills.append(fill)
                exit_qtys.append(close_qty)
                position = 0.0
                _flush_trade()

                if leftover_qty > 0:
                    # Start new trade with residual
                    entry_fills.append(fill)
                    entry_qtys.append(leftover_qty)
                    position = signed_qty - (-close_qty if signed_qty < 0 else close_qty)
                    max_position = abs(position)
                    total_commission = 0.0  # already counted in closed trade
                    total_commission += fill.commission  # re-attribute to new trade

    # If position still open at end of data, flush partial trade anyway
    if entry_fills and abs(position) > 0:
        logger.warning("Symbol %s has unclosed position %.2f — recording partial trade", symbol, position)
        _flush_trade()

    return results
