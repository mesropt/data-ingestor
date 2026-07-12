"""The test harness for a PostgreSQL-backed suite (quick 260712-ghn).

THE ISOLATION KEYSTONE. Read this before changing anything in it.

Every test runs inside an outer transaction that is ALWAYS rolled back, so the
suite leaves the database exactly as it found it. That only works if EVERY
`Session` the code under test can reach is bound to the ONE connection this
harness holds. There are FOUR ways to get a `Session` in this codebase, and
`app.dependency_overrides` reaches only the first:

  1. `Depends(get_session)`                 -- FastAPI routes.
  2. `api/app.py::_lifespan`                -- preset seeding, OUTSIDE the request cycle.
  3. `api/app.py::_require_schema_at_head`  -- startup check, outside the request cycle.
  4. `cli.py`                               -- no FastAPI at all.

So `_bind_sessions_to_the_test_connection` below closes BOTH doors:

  * Half 1 -- the DI door: `dependency_overrides[get_session]`.
  * Half 2 -- the composition-root door: rebind `persistence.engine`'s session
    factory to a sessionmaker bound to the SAME CONNECTION `db_session` holds.

Half 2 must bind to the same CONNECTION, not merely the same database. Same
database but a different connection means lifespan's `commit()` lands OUTSIDE the
outer transaction: the rows are never rolled back, they leak across tests, and the
exact-count assertions in `tests/api/test_preset_seeding.py` become order-dependent.
Same connection means lifespan's writes join the outer transaction -- visible to
`db_session`, and rolled back with it.

Without Half 2, `_lifespan` would seed preset rows into the DEVELOPER'S REAL
DATABASE on every `with TestClient(app)` test, forever, while the suite stayed green.
"""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from assayingest.api.app import app
from assayingest.auth.postgres_store import PostgresUserStore
from assayingest.learning.postgres_field_set_store import PostgresFieldSetStore
from assayingest.learning.postgres_schema_store import PostgresSchemaStore
from assayingest.learning.postgres_store import PostgresProfileStore
from assayingest.persistence import engine as engine_module
from assayingest.persistence.engine import get_session

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The suite runs against a SEPARATE database, never the dev one. `.env` supplies
#: this in a normal checkout; the literal is the docker-compose default.
TEST_DATABASE_URL = os.environ.get("DATABASE_URL_TEST") or (
    "postgresql+psycopg://assayingest:assayingest@localhost:5432/assayingest_test"
)


@pytest.fixture(scope="session")
def engine():
    """A session-scoped engine on the TEST database, with the schema migrated.

    Fails LOUDLY when Postgres is down -- never `pytest.skip`. A green suite that
    tested nothing is the worst possible outcome. `connect_timeout=3` is what makes
    that failure take seconds instead of the OS TCP timeout's two minutes.
    """
    eng = create_engine(TEST_DATABASE_URL, connect_args={"connect_timeout": 3})
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise pytest.UsageError(
            f"PostgreSQL is not reachable at {TEST_DATABASE_URL!r}, so the test "
            f"suite cannot run against a database.\n"
            f"Start it with:  sg docker -c 'docker compose up -d db'\n"
            f"Create the test database once with:  sg docker -c "
            f"'docker compose exec -T db createdb -U assayingest assayingest_test'\n"
            f"Underlying error: {exc}"
        ) from exc

    _migrate_to_head()
    yield eng
    eng.dispose()


def _migrate_to_head() -> None:
    """Run the REAL migration against the test database, once per session.

    Not `Base.metadata.create_all`: running the actual migration proves it on every
    suite run and eliminates model-vs-migration drift (a `create_all` suite is green
    against models the migration may not actually produce). Costs ~1s, once.

    The URL goes through `config.attributes`, a plain dict -- NOT `set_main_option`,
    which routes it through ConfigParser and would treat a `%` in a password as
    interpolation. It is deliberately NOT written into `os.environ` either: leaving
    `DATABASE_URL` pointing at the DEV database is what keeps the "did the suite leak
    into dev?" gate a real proof rather than a tautology.
    """
    cfg = Config(os.path.join(_PROJECT_ROOT, "alembic.ini"))
    cfg.attributes["db_url"] = TEST_DATABASE_URL
    command.upgrade(cfg, "head")


@pytest.fixture
def connection(engine):
    """One connection per test, holding an outer transaction that is always rolled
    back -- the thing that makes the suite leave no trace."""
    conn = engine.connect()
    trans = conn.begin()
    yield conn
    trans.rollback()
    conn.close()


@pytest.fixture
def db_session(connection):
    """The test's own `Session`, joined into the outer transaction.

    `join_transaction_mode="create_savepoint"` is what lets a store call
    `session.commit()` -- which it must, to preserve today's write-then-read
    semantics -- while the outer transaction stays open, so `trans.rollback()` still
    wipes everything. (SQLAlchemy 2.0's official recipe; the old event-listener
    "restart savepoint" dance is no longer required.)
    """
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _bind_sessions_to_the_test_connection(connection, db_session):
    """AUTOUSE. Route every one of the four Session paths at the test connection.

    Both halves are required; neither alone is sufficient. See the module docstring.
    """
    # Half 2 -- the composition-root door (lifespan, the startup schema check, the
    # CLI). Bound to the SAME CONNECTION `db_session` holds, so their committed rows
    # are visible to `db_session` and roll back with it.
    engine_module.set_session_factory(
        sessionmaker(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
    )
    # Half 1 -- the DI door. Every store the app resolves through `Depends` --
    # overridden or not -- now shares the test's Session.
    app.dependency_overrides[get_session] = lambda: db_session
    yield
    app.dependency_overrides.pop(get_session, None)
    engine_module.set_session_factory(None)


@pytest.fixture
def profile_store(db_session) -> PostgresProfileStore:
    return PostgresProfileStore(db_session)


@pytest.fixture
def user_store(db_session) -> PostgresUserStore:
    return PostgresUserStore(db_session)


@pytest.fixture
def field_set_store(db_session) -> PostgresFieldSetStore:
    return PostgresFieldSetStore(db_session)


@pytest.fixture
def schema_store(db_session) -> PostgresSchemaStore:
    return PostgresSchemaStore(db_session)
