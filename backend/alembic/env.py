"""Alembic environment.

The target metadata is the app's own ``Base.metadata`` (importing ``models``
registers every table on it), and the URL comes from ``DATABASE_URL`` — the same
value the app uses — so migrations always run against the real database.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from database import Base, DATABASE_URL
import models  # noqa: F401  (registers all tables on Base.metadata)

config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False: migrations run inside the app's own
    # process at startup (db_migrate.run_migrations, called from main.py), after
    # uvicorn has set up its loggers. fileConfig's default would switch every
    # one of them off — no access log, no startup line, nothing but alembic's
    # own lines in the container logs.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _get_url() -> str:
    return os.getenv("DATABASE_URL", DATABASE_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Batch mode lets future migrations ALTER columns on SQLite, which
            # otherwise has almost no native ALTER support.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
