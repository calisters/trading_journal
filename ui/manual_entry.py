"""
Manual Entry page: log daily net return percentage.
"""

import logging
from datetime import datetime, time

import streamlit as st

from db.database import get_session
from db.models import Trade

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _save_trade(trade_id, trade_date, return_pct: float) -> str:
    session = get_session()
    try:
        dt = datetime.combine(trade_date, time.min)
        if trade_id:
            trade = session.query(Trade).filter(
                Trade.id == trade_id, Trade.is_manual == True
            ).first()
            if not trade:
                return "❌ Trade not found."
        else:
            trade = Trade(symbol="-", direction="-", is_manual=True)
            session.add(trade)

        trade.entry_time = dt
        trade.exit_time = dt
        trade.holding_seconds = 0
        trade.return_pct = round(return_pct, 4)

        session.commit()
        logger.info("Manual trade saved: %s %s%%", trade_date, return_pct)
        return "✅ Saved."
    except Exception as exc:
        session.rollback()
        logger.exception("Failed to save manual trade")
        return f"❌ Error: {exc}"
    finally:
        session.close()


def _delete_trade(trade_id: int) -> str:
    session = get_session()
    try:
        trade = session.query(Trade).filter(
            Trade.id == trade_id, Trade.is_manual == True
        ).first()
        if not trade:
            return "❌ Not found."
        session.delete(trade)
        session.commit()
        return "✅ Deleted."
    except Exception as exc:
        session.rollback()
        return f"❌ Error: {exc}"
    finally:
        session.close()


def _load_manual_trades() -> list:
    session = get_session()
    try:
        return (
            session.query(Trade)
            .filter(Trade.is_manual == True)
            .order_by(Trade.entry_time.desc())
            .all()
        )
    finally:
        session.close()


# ── form ──────────────────────────────────────────────────────────────────────

def _render_form(prefill=None):
    is_edit = prefill is not None
    key_pfx = f"edit_{prefill.id}" if is_edit else "new"

    with st.form(key=f"form_{key_pfx}", clear_on_submit=not is_edit):
        c1, c2 = st.columns(2)
        with c1:
            default_date = prefill.entry_time.date() if is_edit else datetime.utcnow().date()
            trade_date = st.date_input("Date", value=default_date, key=f"{key_pfx}_d")
        with c2:
            return_pct = st.number_input(
                "Net Return %", step=0.01, format="%.2f",
                value=float(prefill.return_pct or 0) if is_edit else 0.0,
                key=f"{key_pfx}_pct",
            )

        submitted = st.form_submit_button("💾 Save", type="primary")
        if submitted:
            msg = _save_trade(prefill.id if is_edit else None, trade_date, return_pct)
            if msg.startswith("✅"):
                st.success(msg)
                st.session_state.pop("editing_trade_id", None)
                st.rerun()
            else:
                st.error(msg)


# ── main page ─────────────────────────────────────────────────────────────────

def render_manual_entry_page():
    st.header("✍️ Manual Entry")

    editing_id = st.session_state.get("editing_trade_id")

    if editing_id:
        session = get_session()
        try:
            prefill = session.query(Trade).filter(Trade.id == editing_id).first()
        finally:
            session.close()
        _render_form(prefill=prefill)
        if st.button("← Cancel"):
            st.session_state.pop("editing_trade_id", None)
            st.rerun()
    else:
        _render_form()

    # ── Trade list ────────────────────────────────────────────────────────────
    st.divider()

    trades = _load_manual_trades()

    if not trades:
        st.info("No entries yet.")
        return

    for t in trades:
        date_str = t.entry_time.strftime("%Y-%m-%d") if t.entry_time else "—"
        pct = t.return_pct or 0
        color = "green" if pct >= 0 else "red"

        with st.container(border=True):
            left, right = st.columns([5, 2])
            with left:
                st.markdown(f"`{date_str}` &nbsp;|&nbsp; :{color}[**{pct:+.2f}%**]")
            with right:
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✏️", key=f"edit_{t.id}", help="Edit"):
                        st.session_state["editing_trade_id"] = t.id
                        st.rerun()
                with c2:
                    if st.button("🗑️", key=f"del_{t.id}", help="Delete"):
                        st.session_state[f"confirm_del_{t.id}"] = True

            if st.session_state.get(f"confirm_del_{t.id}"):
                st.warning("Delete this entry? Cannot be undone.")
                yc, nc = st.columns(2)
                with yc:
                    if st.button("Yes", key=f"yes_{t.id}", type="primary"):
                        msg = _delete_trade(t.id)
                        st.session_state.pop(f"confirm_del_{t.id}", None)
                        st.success(msg) if msg.startswith("✅") else st.error(msg)
                        st.rerun()
                with nc:
                    if st.button("No", key=f"no_{t.id}"):
                        st.session_state.pop(f"confirm_del_{t.id}", None)
                        st.rerun()
