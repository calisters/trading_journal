"""Database engine, session factory, and initialisation."""
import logging
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from db.models import Base

logger = logging.getLogger(__name__)

DB_PATH = Path("trading_journal.db")
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = f"sqlite:///{DB_PATH}"
        _engine = create_engine(db_url, connect_args={"check_same_thread": False})

        # Enable WAL mode for better concurrency
        @event.listens_for(_engine, "connect")
        def set_wal(dbapi_con, _):
            dbapi_con.execute("PRAGMA journal_mode=WAL")
            dbapi_con.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(_engine)
        logger.info("Database initialised at %s", DB_PATH.absolute())
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal()


def reset_database():
    """Drop all tables and recreate. Use when schema changes."""
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    logger.warning("Database reset: all data cleared.")
