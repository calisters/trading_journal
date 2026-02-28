"""
Parser for IBKR Trade Log (.tlg) files.

Format observed:
  Pipe-delimited sections. Stock trades are STK_TRD rows.

STK_TRD columns (0-indexed):
  0  record_type  = STK_TRD
  1  execution_id
  2  symbol
  3  company_name
  4  exchange
  5  action       (BUYTOOPEN / SELLTOOPEN / BUYTOCLOSE / SELLTOCLOSE)
  6  open_close   (O / C)
  7  date         (YYYYMMDD)
  8  time         (HH:MM:SS)
  9  currency
  10 qty          (signed: positive=buy, negative=sell)
  11 multiplier
  12 price
  13 value        (signed cost/proceeds)
  14 commission   (negative)
  15 fee_mult     (usually 1.00)
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import IO, List, Tuple, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ─── canonical column names in output DataFrame ───────────────────────────────
CANONICAL_COLS = [
    "execution_id", "symbol", "company_name", "exchange",
    "action", "open_close", "timestamp", "currency",
    "qty", "price", "commission", "fees",
    "side", "account_id", "raw_row_json",
]


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _parse_stk_trd_row(parts: List[str], account_id: str) -> Optional[dict]:
    """Parse a single STK_TRD pipe-split row into a canonical dict."""
    if len(parts) < 15:
        logger.debug("STK_TRD row too short (%d cols): %s", len(parts), parts)
        return None

    action = parts[5].strip().upper()
    side = "BUY" if "BUY" in action else "SELL"
    qty_raw = _safe_float(parts[10])
    qty = abs(qty_raw)  # store magnitude; side carries direction

    try:
        ts = datetime.strptime(f"{parts[7].strip()} {parts[8].strip()}", "%Y%m%d %H:%M:%S")
    except ValueError:
        logger.warning("Bad timestamp in row: %s", parts)
        return None

    return {
        "execution_id": parts[1].strip(),
        "order_id": None,
        "symbol": parts[2].strip(),
        "company_name": parts[3].strip(),
        "exchange": parts[4].strip(),
        "action": action,
        "open_close": parts[6].strip(),
        "timestamp": ts,
        "currency": parts[9].strip(),
        "qty": qty,
        "price": _safe_float(parts[12]),
        "commission": _safe_float(parts[14]),   # already negative in file
        "fees": 0.0,
        "side": side,
        "account_id": account_id,
        "raw_row_json": json.dumps(parts),
    }


def parse_tlg(file_obj: IO[bytes]) -> Tuple[str, str, pd.DataFrame]:
    """
    Parse an IBKR .tlg file.

    Returns
    -------
    file_hash : str
        SHA-256 hex digest of the raw file bytes.
    account_id : str
    fills_df : pd.DataFrame
        One row per fill with canonical columns.
    """
    raw_bytes = file_obj.read()
    file_hash = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode("utf-8", errors="replace")

    lines = text.splitlines()
    account_id = "UNKNOWN"
    rows: List[dict] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        parts = line.split("|")
        record = parts[0].strip().upper()

        if record == "ACT_INF":
            # ACT_INF|<account_id>|<name>|...
            if len(parts) >= 2:
                account_id = parts[1].strip()
            logger.info("Account ID: %s", account_id)

        elif record == "STK_TRD":
            row = _parse_stk_trd_row(parts, account_id)
            if row:
                rows.append(row)

        else:
            # CASH_TRD, section headers – skip silently
            pass

    if not rows:
        logger.warning("No STK_TRD rows found in file (hash=%s)", file_hash[:8])
        return file_hash, account_id, pd.DataFrame(columns=CANONICAL_COLS)

    df = pd.DataFrame(rows)
    logger.info("Parsed %d fills from account %s", len(df), account_id)
    return file_hash, account_id, df


def hash_file(file_obj: IO[bytes]) -> str:
    """Compute SHA-256 of an already-open file without consuming it."""
    pos = file_obj.tell()
    h = hashlib.sha256(file_obj.read()).hexdigest()
    file_obj.seek(pos)
    return h
