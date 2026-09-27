"""Database migration runner — replaces the old import-time ``create_all`` +
``try/except ALTER`` loop with Alembic, while safely adopting databases that
predate Alembic (yours, and every existing Docker Hub deployment).

Adoption strategy (safe for a live production DB):

* **Brand-new DB** — no tables at all: ``alembic upgrade head`` creates
  everything from the baseline revision.
* **Existing pre-Alembic DB** — has app tables but no ``alembic_version``:
  first bring it fully up to the baseline schema idempotently (create any
  missing tables, add any missing columns — exactly what the old startup loop
  did), then *stamp* it at the baseline revision WITHOUT re-running DDL, then
  apply any newer revisions.
* **Already-migrated DB** — has ``alembic_version``: just ``upgrade head``.

Set ``SKIP_MIGRATIONS=1`` to disable this entirely (used by the test suite,
which manages its schema directly via ``Base.metadata``).
"""

import logging
import os

from sqlalchemy import inspect, text

from database import engine

logger = logging.getLogger(__name__)

BASELINE_REVISION = "0001_baseline"
_HERE = os.path.dirname(os.path.abspath(__file__))

# Idempotent column additions the pre-Alembic startup applied on every boot.
# Kept so a database created by a very old build is brought fully up to the
# baseline schema before it is stamped. New schema changes must NOT be added
# here — write a proper Alembic revision instead.
LEGACY_COLUMN_MIGRATIONS = [
    "ALTER TABLE media_items ADD COLUMN thumbnail_url VARCHAR",
    "ALTER TABLE lan_events ADD COLUMN capacity INTEGER",
    "ALTER TABLE media_items ADD COLUMN event_id INTEGER REFERENCES lan_events(id)",
    "ALTER TABLE teams ADD COLUMN seed INTEGER",
    "ALTER TABLE livestreams ADD COLUMN stream_type VARCHAR DEFAULT 'channel'",
    "ALTER TABLE livestreams ADD COLUMN clip_slug VARCHAR",
    "ALTER TABLE event_rsvps ADD COLUMN arrival_date DATE",
    "ALTER TABLE event_rsvps ADD COLUMN departure_date DATE",
    "ALTER TABLE lan_events ADD COLUMN cover_image_url VARCHAR",
    "ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1",
    "ALTER TABLE tournaments ADD COLUMN event_id INTEGER REFERENCES lan_events(id)",
    "ALTER TABLE expenses ADD COLUMN event_id INTEGER REFERENCES lan_events(id)",
]


def _alembic_config():
    # Imported lazily so importing this module (and thus main.py) doesn't require
    # Alembic to be installed when SKIP_MIGRATIONS=1 (e.g. in the test suite).
    from alembic.config import Config

    cfg = Config(os.path.join(_HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_HERE, "alembic"))
    return cfg


def _bring_legacy_db_to_baseline() -> None:
    """Make a pre-Alembic DB match the baseline schema before stamping it."""
    from database import Base
    import models  # noqa: F401  (registers all tables on Base.metadata)

    Base.metadata.create_all(bind=engine)  # add any missing tables (idempotent)
    with engine.connect() as conn:
        for stmt in LEGACY_COLUMN_MIGRATIONS:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                conn.rollback()  # column already exists — expected


def run_migrations() -> None:
    if os.getenv("SKIP_MIGRATIONS") == "1":
        logger.info("SKIP_MIGRATIONS=1 — skipping Alembic migrations.")
        return

    from alembic import command

    cfg = _alembic_config()
    tables = set(inspect(engine).get_table_names())

    if "alembic_version" not in tables and "users" in tables:
        logger.info("Adopting existing pre-Alembic database at baseline %s", BASELINE_REVISION)
        _bring_legacy_db_to_baseline()
        command.stamp(cfg, BASELINE_REVISION)

    command.upgrade(cfg, "head")
    logger.info("Database is up to date (head).")
