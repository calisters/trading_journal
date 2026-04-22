"""
Manual Entry page: add, edit, and delete trades without importing .tlg files.
All values are entered directly and written straight to the trades table.
"""

import logging
from datetime import datetime, date, time

import streamlit as st
import pandas as pd

from db.database import get_session
from db.models import Trade

logger = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────────────

def _calc_fields(
    direction: str,
    entry_price: float,
    exit_price: float,
    shares: float,
    commission: float,
    entry_dt: datetime,
    exit_dt: datetime,
) -> dict:
    """Derive all computed trade fields from raw inputs."""
    sign = 1 if direction == "Long" else -1
    deployed_notional = entry_price * shares
    gross_pnl = sign * (exit_price - entry_price) * shares
    net_pnl = gross_pnl + commission          # commission is negative or 0
    return_pct = (net_pnl / deployed_notional * 100) if deployed_notional else 0.0
    holding_seconds = int((exit_dt - entry_dt).total_seconds())
    return dict(
        gross_pnl=round(gross_pnl, 4),
        net_pnl=round(net_pnl, 4),
        return_pct=round(return_pct, 4),
        deployed_notional=round(deployed_notional, 4),
        holding_seconds=holding_seconds,
    )


def _save_trade(trade_id: int | None, fields: dict) -> str:
    """Insert a new trade or update an existing one. Returns status message."""
    session = get_session()
    try:
        if trade_id:
            trade = session.query(Trade).filter_by(id=trade_id, is_manual=True).first()
            if not trade:
                return "❌ Trade not found or not editable."
            for k, v in fields.items():
                setattr(trade, k, v)
            msg = f"✅ Trade #{trade_id} updated."
        else:
            trade = Trade(**fields, is_manual=True)
            session.add(trade)
            msg = "✅ Trade saved."
        session.commit()
        logger.info("Manual trade saved: %s", fields.get("symbol"))
        return msg
    except Exception as exc:
        session.rollback()
        logger.exception("Failed to save manual trade")
        return f"❌ Error: {exc}"
    finally:
        session.close()


def _delete_trade(trade_id: int) -> str:
    session = get_session()
    try:
        trade = session.query(Trade).filter_by(id=trade_id, is_manual=True).first()
        if not trade:
            return "❌ Trade not found or not deletable."
        session.delete(trade)
        session.commit()
        return f"✅ Trade #{trade_id} deleted."
    except Exception as exc:
        session.rollback()
        return f"❌ Error: {exc}"
    finally:
        session.close()


def _load_manual_trades() -> list[Trade]:
    session = get_session()
    try:
        return (
            session.query(Trade)
            .filter_by(is_manual=True)
            .order_by(Trade.entry_time.desc())
            .all()
        )
    finally:
        session.close()


# ── form ─────────────────────────────────────────────────────────────────────

def _render_form(prefill: Trade | None = None):
    """Render the add/edit form. prefill=None means new trade."""
    is_edit = prefill is not None
    label = "✏️ Edit Trade" if is_edit else "➕ Add Trade"
    key_pfx = f"edit_{prefill.id}" if is_edit else "new"

    with st.form(key=f"form_{key_pfx}", clear_on_submit=not is_edit):
        st.subheader(label)

        col1, col2 = st.columns(2)
        with col1:
            symbol = st.text_input(
                "Symbol", value=prefill.symbol if is_edit else "",
                placeholder="e.g. AAPL", key=f"{key_pfx}_sym"
            ).upper().strip()
            direction = st.selectbox(
                "Direction", ["Long", "Short"],
                index=0 if (not is_edit or prefill.direction == "Long") else 1,
                key=f"{key_pfx}_dir"
            )
            shares = st.number_input(
                "Shares / Size", min_value=0.0, step=1.0,
                value=float(prefill.max_position_size or 0) if is_edit else 0.0,
                key=f"{key_pfx}_shares"
            )
            currency = st.text_input(
                "Currency", value=prefill.currency if (is_edit and prefill.currency) else "USD",
                key=f"{key_pfx}_cur"
            ).upper().strip()
            account_id = st.text_input(
                "Account ID (optional)",
                value=prefill.account_id if (is_edit and prefill.account_id) else "",
                key=f"{key_pfx}_acct"
            ).strip()

        with col2:
            entry_price = st.number_input(
                "Avg Entry Price ($)", min_value=0.0, step=0.01, format="%.4f",
                value=float(prefill.avg_entry_price or 0) if is_edit else 0.0,
                key=f"{key_pfx}_ep"
            )
            exit_price = st.number_input(
                "Avg Exit Price ($)", min_value=0.0, step=0.01, format="%.4f",
                value=float(prefill.avg_exit_price or 0) if is_edit else 0.0,
                key=f"{key_pfx}_xp"
            )
            commission = st.number_input(
                "Total Commission ($, enter as negative)",
                max_value=0.0, step=0.01, format="%.2f",
                value=float(prefill.total_commission or 0) if is_edit else 0.0,
                key=f"{key_pfx}_comm"
            )

        st.markdown("**Entry Date & Time**")
        ec1, ec2 = st.columns(2)
        default_entry_dt = prefill.entry_time if is_edit else datetime.utcnow()
        with ec1:
            entry_date = st.date_input("Entry Date", value=default_entry_dt.date(), key=f"{key_pfx}_ed")
        with ec2:
            entry_time_val = st.time_input("Entry Time (UTC)", value=default_entry_dt.time(), key=f"{key_pfx}_et")

        st.markdown("**Exit Date & Time**")
        xc1, xc2 = st.columns(2)
        default_exit_dt = prefill.exit_time if is_edit else datetime.utcnow()
        with xc1:
            exit_date = st.date_input("Exit Date", value=default_exit_dt.date(), key=f"{key_pfx}_xd")
        with xc2:
            exit_time_val = st.time_input("Exit Time (UTC)", value=default_exit_dt.time(), key=f"{key_pfx}_xt")

        # Live P&L preview
        entry_dt = datetime.combine(entry_date, entry_time_val)
        exit_dt = datetime.combine(exit_date, exit_time_val)

        if symbol and shares > 0 and entry_price > 0 and exit_price > 0:
            calc = _calc_fields(direction, entry_price, exit_price, shares, commission, entry_dt, exit_dt)
            pnl_color = "green" if calc["net_pnl"] >= 0 else "red"
            st.markdown(
                f"**Preview →** Gross P&L: `${calc['gross_pnl']:+.2f}` &nbsp;|&nbsp; "
                f"Net P&L: :{pnl_color}[`${calc['net_pnl']:+.2f}`] &nbsp;|&nbsp; "
                f"Return: `{calc['return_pct']:+.2f}%` &nbsp;|&nbsp; "
                f"Notional: `${calc['deployed_notional']:,.2f}`"
            )

        submitted = st.form_submit_button("💾 Save Trade", type="primary")

        if submitted:
            errors = []
            if not symbol:
                errors.append("Symbol is required.")
            if shares <= 0:
                errors.append("Shares must be > 0.")
            if entry_price <= 0:
                errors.append("Entry price must be > 0.")
            if exit_price <= 0:
                errors.append("Exit price must be > 0.")
            if exit_dt <= entry_dt:
                errors.append("Exit time must be after entry time.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                calc = _calc_fields(direction, entry_price, exit_price, shares, commission, entry_dt, exit_dt)
                fields = dict(
                    symbol=symbol,
                    direction=direction,
                    entry_time=entry_dt,
                    exit_time=exit_dt,
                    avg_entry_price=entry_price,
                    avg_exit_price=exit_price,
                    max_position_size=shares,
                    total_commission=commission,
                    currency=currency or "USD",
                    account_id=account_id or None,
                    **calc,
                )
                msg = _save_trade(prefill.id if is_edit else None, fields)
                if msg.startswith("✅"):
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)


# ── main page ────────────────────────────────────────────────────────────────

def render_manual_entry_page():
    st.header("✍️ Manual Trade Entry")
    st.markdown(
        "Add, edit, or delete trades directly — no .tlg file needed. "
        "All computed fields (P&L, return %, notional) are calculated automatically."
    )

    # Edit mode: triggered by clicking Edit on a row
    editing_id = st.session_state.get("editing_trade_id")

    if editing_id:
        session = get_session()
        try:
            prefill = session.query(Trade).filter_by(id=editing_id, is_manual=True).first()
        finally:
            session.close()

        if prefill:
            _render_form(prefill=prefill)
        else:
            st.error("Trade not found.")
        if st.button("← Cancel Edit"):
            st.session_state.pop("editing_trade_id", None)
            st.rerun()
    else:
        _render_form()

    # ── Existing manual trades ────────────────────────────────────────────────
    st.divider()
    st.subheader("Manually Entered Trades")

    trades = _load_manual_trades()

    if not trades:
        st.info("No manual trades yet. Use the form above to add one.")
        return

    for t in trades:
        pnl_str = f"${t.net_pnl:+.2f}" if t.net_pnl is not None else "—"
        pct_str = f"{t.return_pct:+.2f}%" if t.return_pct is not None else "—"
        entry_str = t.entry_time.strftime("%Y-%m-%d %H:%M") if t.entry_time else "—"
        exit_str = t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else "—"

        with st.container(border=True):
            row1, row2 = st.columns([5, 2])
            with row1:
                st.markdown(
                    f"**{t.symbol}** &nbsp; `{t.direction}` &nbsp; "
                    f"| Entry: `{entry_str}` → Exit: `{exit_str}` &nbsp; "
                    f"| Shares: `{t.max_position_size}` &nbsp; "
                    f"| Avg In: `${t.avg_entry_price:.4f}` &nbsp; "
                    f"| Avg Out: `${t.avg_exit_price:.4f}`"
                )
                color = "green" if (t.net_pnl or 0) >= 0 else "red"
                st.markdown(
                    f"Net P&L: :{color}[**{pnl_str}**] &nbsp;|&nbsp; "
                    f"Return: `{pct_str}` &nbsp;|&nbsp; "
                    f"Notional: `${t.deployed_notional:,.2f}`"
                )
            with row2:
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✏️ Edit", key=f"edit_{t.id}"):
                        st.session_state["editing_trade_id"] = t.id
                        st.rerun()
                with c2:
                    if st.button("🗑️ Delete", key=f"del_{t.id}"):
                        st.session_state[f"confirm_del_{t.id}"] = True

            # Confirm delete
            if st.session_state.get(f"confirm_del_{t.id}"):
                st.warning(f"Delete trade #{t.id} ({t.symbol})? This cannot be undone.")
                yc, nc = st.columns(2)
                with yc:
                    if st.button("Yes, delete", key=f"yes_del_{t.id}", type="primary"):
                        msg = _delete_trade(t.id)
                        st.session_state.pop(f"confirm_del_{t.id}", None)
                        if msg.startswith("✅"):
                            st.success(msg)
                        else:
                            st.error(msg)
                        st.rerun()
                with nc:
                    if st.button("Cancel", key=f"no_del_{t.id}"):
                        st.session_state.pop(f"confirm_del_{t.id}", None)
                        st.rerun()
