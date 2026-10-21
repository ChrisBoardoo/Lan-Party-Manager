from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/lanparty.db")
# `timeout` is SQLite's busy timeout: a writer that finds the file locked (a
# WAL checkpoint, a restore, a burst of presence heartbeats) waits up to 30 s
# instead of the default 5 before failing with "database is locked" (Q-11 of
# the 2026-10-20 review).
connect_args = {"check_same_thread": False, "timeout": 30} if "sqlite" in DATABASE_URL else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

if "sqlite" in DATABASE_URL:
    @event.listens_for(engine, "connect")
    def _set_sqlite_wal(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        # In WAL mode NORMAL is durable against application crashes and only
        # risks the very last transactions on a power cut — never corruption —
        # and it spares the Pi's SD card an fsync per commit.
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
