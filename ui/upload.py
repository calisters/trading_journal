"""
Upload page: accept IBKR .tlg files, parse, deduplicate, store.
"""

import io
import logging
import json

import streamlit as st
import pandas as pd

from parsers.ibkr_tlg import parse_tlg, hash_file
from db.database import get_session
from db.models import RawSourceFile, Fill, Trade, TradeLeg
from analytics.trade_builder import build_trades

logger = logging.getLogger(__name__)


def _ingest_file(file_bytes: bytes, filename: str) -> dict:
    """
    Parse one file, persist raw fills, build trades, return a status dict.
    """
    session = get_session()
    try:
        buf = io.BytesIO(file_bytes)
        file_hash, account_id, fills_df = parse_tlg(buf)

        # ── Duplicate file check ─────────────────────────────────────────
        existing = session.query(RawSourceFile).filter_by(file_hash=file_hash).first()
        if existing:
            return {
                "status": "duplicate",
                "filename": filename,
                "msg": f"Already imported (imported at {existing.uploaded_at})",
                "fills_added": 0,
                "trades_added": 0,
            }

        # ── Persist source file record ───────────────────────────────────
        src = RawSourceFile(
            filename=filename,
            file_hash=file_hash,
            account_id=account_id,
            row_count=len(fills_df),
        )
        session.add(src)
        session.flush()  # get src.id

        if fills_df.empty:
            session.commit()
            return {
                "status": "empty",
                "filename": filename,
                "msg": "No stock fills found in file.",
                "fills_added": 0,
                "trades_added": 0,
            }

        # ── Persist fills, skip exec_id duplicates across files ──────────
        existing_exec_ids = {
            r[0]
            for r in session.query(Fill.execution_id).all()
            if r[0]
        }

        fill_objs = []
        skipped = 0
        for _, row in fills_df.iterrows():
            if row["execution_id"] in existing_exec_ids:
                skipped += 1
                continue
            f = Fill(
                raw_source_file_id=src.id,
                execution_id=row.get("execution_id"),
                order_id=row.get("order_id"),
                account_id=row.get("account_id"),
                timestamp=row["timestamp"],
                symbol=row["symbol"],
                company_name=row.get("company_name"),
                side=row["side"],
                qty=float(row["qty"]),
                price=float(row["price"]),
                commission=float(row.get("commission", 0)),
                fees=float(row.get("fees", 0)),
                currency=row.get("currency"),
                exchange=row.get("exchange"),
                action=row.get("action"),
                open_close=row.get("open_close"),
                raw_row_json=row.get("raw_row_json"),
            )
            session.add(f)
            fill_objs.append(f)
            existing_exec_ids.add(row["execution_id"])

        session.flush()

        # ── Build and persist trades ─────────────────────────────────────
        # Use ALL fills for this account (not just new ones) so that
        # partial trades from prior imports are completed properly.
        all_fills = (
            session.query(Fill)
            .filter(Fill.account_id == account_id)
            .order_by(Fill.timestamp)
            .all()
        )

        # Remove existing trades for this account to rebuild cleanly
        existing_trade_ids = [
            r[0]
            for r in session.query(Trade.id)
            .filter(Trade.account_id == account_id)
            .all()
        ]
        if existing_trade_ids:
            session.query(TradeLeg).filter(
                TradeLeg.trade_id.in_(existing_trade_ids)
            ).delete(synchronize_session=False)
            session.query(Trade).filter(
                Trade.id.in_(existing_trade_ids)
            ).delete(synchronize_session=False)

        trade_tuples = build_trades(all_fills)
        trades_added = len(trade_tuples)
        for trade, legs in trade_tuples:
            trade.account_id = account_id
            session.add(trade)
            session.flush()
            for leg in legs:
                leg.trade_id = trade.id
                session.add(leg)

        session.commit()
        logger.info(
            "Ingested %s: %d fills (+%d skipped), %d trades",
            filename, len(fill_objs), skipped, trades_added,
        )
        return {
            "status": "ok",
            "filename": filename,
            "fills_added": len(fill_objs),
            "fills_skipped": skipped,
            "trades_added": trades_added,
            "msg": f"✅ {len(fill_objs)} fills, {trades_added} trades imported.",
        }

    except Exception as exc:
        session.rollback()
        logger.exception("Failed to ingest %s", filename)
        return {
            "status": "error",
            "filename": filename,
            "msg": f"Error: {exc}",
            "fills_added": 0,
            "trades_added": 0,
        }
    finally:
        session.close()


def render_upload_page():
    st.header("📂 Upload IBKR Trade Log Files")
    st.markdown(
        "Upload one or more IBKR **Trade Log (.tlg)** files. "
        "Duplicate files and fills are automatically skipped."
    )

    uploaded_files = st.file_uploader(
        "Choose .tlg file(s)",
        type=["tlg", "txt"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        if st.button("🚀 Import Files", type="primary"):
            results = []
            bar = st.progress(0)
            for i, uf in enumerate(uploaded_files):
                with st.spinner(f"Importing {uf.name}…"):
                    res = _ingest_file(uf.read(), uf.name)
                results.append(res)
                bar.progress((i + 1) / len(uploaded_files))

            # Summary table
            st.subheader("Import Results")
            for r in results:
                if r["status"] == "ok":
                    st.success(f"**{r['filename']}** — {r['msg']}")
                elif r["status"] == "duplicate":
                    st.warning(f"**{r['filename']}** — {r['msg']}")
                elif r["status"] == "empty":
                    st.info(f"**{r['filename']}** — {r['msg']}")
                else:
                    st.error(f"**{r['filename']}** — {r['msg']}")

    # ── Existing imports table ──────────────────────────────────────────────
    st.divider()
    st.subheader("Previously Imported Files")
    session = get_session()
    try:
        files = session.query(RawSourceFile).order_by(RawSourceFile.uploaded_at.desc()).all()
        if files:
            rows = [
                {
                    "File": f.filename,
                    "Account": f.account_id,
                    "Rows": f.row_count,
                    "Imported At": str(f.uploaded_at)[:19],
                }
                for f in files
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No files imported yet.")
    finally:
        session.close()

    # ── Danger zone ─────────────────────────────────────────────────────────
    with st.expander("⚠️ Danger Zone"):
        st.warning("This will delete ALL imported data and rebuild from scratch.")
        if st.button("🗑️ Reset Database", type="secondary"):
            from db.database import reset_database
            reset_database()
            st.success("Database reset. Re-import your files.")
            st.rerun()
