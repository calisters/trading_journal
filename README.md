# Trading Journal

https://journal22.streamlit.app

A production-grade local trading journal for IBKR Trade Log (.tlg) files.
Built with Streamlit · Pandas · SQLite/SQLAlchemy · Plotly.

---

## Quick Start

### 1. Clone / copy this folder

```
trading_journal/
├── app.py
├── requirements.txt
├── parsers/
├── db/
├── analytics/
├── ui/
└── logs/
```

### 2. Create a virtual environment

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the app

```bash
streamlit run app.py
```

The app opens at **http://localhost:8501** in your browser.

---

## Usage

1. **Upload page** — drag-and-drop one or more `.tlg` files.  
   Duplicate files and duplicate fills are silently skipped.

2. **Dashboard** — equity curve, drawdown, calendar heatmap, metrics cards,
   distribution histogram, full trades table with commissions.

3. **Insights** — commission pie chart, symbol/day-of-week breakdown,
   fat-tail dependency flag, streak analysis, early-exit pattern detection.

---

## Supported IBKR File Formats

| Section marker | Description |
|---|---|
| `ACT_INF` | Account info (extracts account ID) |
| `STK_TRD` | Stock execution fills (parsed) |
| `CASH_TRD` | Currency transactions (skipped in MVP) |

The parser is row-type driven — unknown sections are silently skipped, so
future IBKR format changes are handled gracefully.

---

## Database

- SQLite file: `trading_journal.db` (auto-created on first run)
- Tables: `raw_source_files`, `fills`, `trades`, `trade_legs`
- To reset: use the **Reset Database** button in the Upload page danger zone,
  or delete `trading_journal.db` and re-import your files.

---

## Logging

All events are written to `logs/app.log` and also printed to the console.

---

## File Layout

```
app.py                   Entry point
parsers/ibkr_tlg.py      IBKR .tlg file parser
db/models.py             SQLAlchemy ORM models
db/database.py           Engine, session factory, reset
analytics/trade_builder.py  Round-trip trade construction
analytics/metrics.py     Equity curve, drawdown, summary stats, insights
ui/upload.py             Upload & import page
ui/dashboard.py          Charts & metrics dashboard
ui/insights.py           Insights & fee analysis page
requirements.txt
README.md
logs/app.log             Runtime log (auto-created)
trading_journal.db       SQLite database (auto-created)
```

---

## Windows Helper Script

Create `run.bat` in the project folder:

```bat
@echo off
call .venv\Scripts\activate.bat
streamlit run app.py
```

Double-click to launch.
