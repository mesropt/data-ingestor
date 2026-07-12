"""Alembic's runtime environment.

TWO deliberate deviations from the scaffolded `env.py`, each a bug fix:

  1. The engine is built DIRECTLY from a plain string, not via
     `config.set_main_option("sqlalchemy.url", ...)` + `engine_from_config`. That
     scaffolded path routes the URL through ConfigParser, which treats `%` as an
     interpolation sigil -- a password containing `%` raises
     `InterpolationSyntaxError`. Building the engine directly sidesteps it entirely.

  2. `assayingest.persistence.models` is imported for its SIDE EFFECT: it registers
     all six tables on `Base.metadata`. Without that import the metadata is EMPTY
     and `--autogenerate` cheerfully emits an empty migration.

URL resolution order (`config.attributes` FIRST) is what lets the test suite point
`alembic upgrade head` at the TEST database without mutating `os.environ` -- which
matters, because mutating `os.environ["DATABASE_URL"]` would make the dev database
unreachable from the test process and so render the "did the suite leak into dev?"
gate vacuous. `config.attributes` is a plain dict, so deviation (1) still holds:
no ConfigParser, no `%` interpolation.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from assayingest.env import load_project_env
from assayingest.persistence import models  # noqa: F401 -- registers the six tables
from assayingest.persistence.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """The suite's injected URL if there is one, else the environment's."""
    injected = config.attributes.get("db_url")
    if injected:
        return str(injected)
    # override=False -- a real environment variable always wins (quick 260712-ekj).
    load_project_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Cannot run migrations: DATABASE_URL is not set, so there is no "
            "database to migrate. Copy .env.example to .env, then start PostgreSQL "
            "with: sg docker -c 'docker compose up -d db'"
        )
    return url


def run_migrations_offline() -> None:
    """Emit SQL without connecting (`alembic upgrade head --sql`)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Migrate a live database. NullPool: a migration is a one-shot connection."""
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
