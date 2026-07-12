"""The composition root for database sessions -- the ONE place a `Session` can
come from, and the one place a test can rebind.

WHY THIS MODULE IS SHAPED THE WAY IT IS
---------------------------------------
Four call sites in this codebase need a `Session`, and only ONE of them goes
through FastAPI's dependency injection:

  1. `Depends(get_session)`                    -- every route, via `api/deps.py`.
  2. `api/app.py::_lifespan`                   -- preset seeding, OUTSIDE the request cycle.
  3. `api/app.py::_require_schema_at_head`     -- startup check, outside the request cycle.
  4. `cli.py::_resolve_store`                  -- no FastAPI at all.

`app.dependency_overrides` reaches only (1). If (2), (3), or (4) hard-bind
themselves to `DATABASE_URL`, they write to the DEVELOPER'S REAL DATABASE even
under test -- silently, forever, while the suite stays green. So all four route
through `session_factory()` below, and the test suite rebinds that one seam.

THE SEAM MUST BE DEREFERENCED AT CALL TIME.
Never write `from .engine import SessionFactory` and hold the result. A name
captured at import time cannot be rebound afterwards: a test's patch would
silently not take, and the suite would go green while writing to dev. Always call
`session_factory()` (or `new_session()`) at the moment you need a session.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..env import load_project_env

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _database_url() -> str:
    """The configured Postgres URL, or a consequence-shaped failure.

    There is deliberately NO default: a silent fallback would let the app connect
    somewhere the operator never chose.
    """
    # override=False -- a real environment variable always wins over `.env`
    # (quick 260712-ekj).
    load_project_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Cannot reach the database: DATABASE_URL is not set, so no store can "
            "be opened. Copy .env.example to .env, then start PostgreSQL with: "
            "sg docker -c 'docker compose up -d db'"
        )
    return url


def get_engine() -> Engine:
    """The lazily-built module-level engine (one connection pool per process)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            _database_url(),
            # A container restart kills every pooled connection; without this the
            # next request fails on a corpse instead of reconnecting.
            pool_pre_ping=True,
            # Load-bearing: psycopg's default connect timeout is the OS TCP
            # timeout (~2 minutes). Without this, a run against a stopped
            # Postgres HANGS instead of failing.
            connect_args={"connect_timeout": 3},
        )
    return _engine


def session_factory() -> sessionmaker[Session]:
    """The rebindable seam. Call it; never capture its result at import time.

    Lazily builds the real factory on first use, so importing this module never
    connects to anything -- and a test that rebinds the seam first never builds
    the dev engine at all.
    """
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


def set_session_factory(factory: sessionmaker[Session] | None) -> None:
    """Rebind the seam (the test suite's only door into paths 2-4).

    `None` restores the lazy default, so a fixture can always put the module back
    the way it found it.
    """
    global _SessionFactory
    _SessionFactory = factory


def new_session() -> Session:
    """A fresh `Session` from the current seam -- for the callers that live
    outside FastAPI's request cycle (lifespan, the startup schema check, the CLI).

    The CALLER owns its lifetime: `with new_session() as session: ...`.
    """
    return session_factory()()


def get_session() -> Iterator[Session]:
    """The FastAPI dependency: one `Session` per request, closed when it ends.

    This is a GENERATOR and exists for FastAPI's `Depends` protocol only. A
    non-FastAPI caller must use `new_session()` -- calling `get_session()`
    directly hands back a generator object, and every `session.execute(...)` on it
    would fail.
    """
    with new_session() as session:
        yield session
