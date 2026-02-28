"""SQLAlchemy ORM models for the trading journal."""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, Boolean,
    ForeignKey, UniqueConstraint, create_engine
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class RawSourceFile(Base):
    """Tracks every uploaded file."""
    __tablename__ = "raw_source_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(512), nullable=False)
    file_hash = Column(String(64), unique=True, nullable=False)  # SHA-256
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    account_id = Column(String(64))
    row_count = Column(Integer, default=0)

    fills = relationship("Fill", back_populates="source_file")


class Fill(Base):
    """Canonical normalised fill (one execution / partial fill)."""
    __tablename__ = "fills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_source_file_id = Column(Integer, ForeignKey("raw_source_files.id"), nullable=False)

    # Canonical fields
    execution_id = Column(String(64))
    order_id = Column(String(64))
    account_id = Column(String(64))
    timestamp = Column(DateTime, nullable=False)
    symbol = Column(String(32), nullable=False)
    company_name = Column(String(256))
    side = Column(String(8), nullable=False)   # BUY / SELL
    qty = Column(Float, nullable=False)         # always positive
    price = Column(Float, nullable=False)
    commission = Column(Float, default=0.0)     # always negative or zero
    fees = Column(Float, default=0.0)
    currency = Column(String(8))
    exchange = Column(String(32))
    action = Column(String(32))                 # BUYTOOPEN, SELLTOCLOSE, …
    open_close = Column(String(4))              # O / C

    raw_row_json = Column(Text)                 # original row for traceability

    source_file = relationship("RawSourceFile", back_populates="fills")
    trade_legs = relationship("TradeLeg", back_populates="fill")

    __table_args__ = (
        UniqueConstraint("execution_id", "raw_source_file_id", name="uq_fill_exec"),
    )


class Trade(Base):
    """A completed round-trip trade (entry → exit)."""
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False)
    direction = Column(String(8), nullable=False)   # Long / Short
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime, nullable=False)
    holding_seconds = Column(Integer)

    avg_entry_price = Column(Float)
    avg_exit_price = Column(Float)
    max_position_size = Column(Float)
    total_commission = Column(Float, default=0.0)

    gross_pnl = Column(Float)        # before commissions
    net_pnl = Column(Float)          # after commissions
    return_pct = Column(Float)       # net_pnl / deployed_notional * 100
    deployed_notional = Column(Float)

    currency = Column(String(8))
    account_id = Column(String(64))

    legs = relationship("TradeLeg", back_populates="trade")


class TradeLeg(Base):
    """Links fills to trades."""
    __tablename__ = "trade_legs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=False)
    fill_id = Column(Integer, ForeignKey("fills.id"), nullable=False)
    leg_type = Column(String(8))  # ENTRY / EXIT

    trade = relationship("Trade", back_populates="legs")
    fill = relationship("Fill", back_populates="trade_legs")
