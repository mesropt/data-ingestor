"""The FastAPI transport adapter -- app object, router includes, and the
one-command demo's frontend mount (RESEARCH.md Pattern 3).

Run `uvicorn assayingest.api.app:app` once `frontend/dist` exists (built via
`npm run build`) to serve both the API and the built React bundle from one
process, one port -- the one-command demo. In dev, run the Vite dev server
separately (`npm run dev`) with its own proxy to this app's `/api/*` routes
(Claude's Discretion, CONTEXT.md D-04 area); `app.frontend()` is only needed
for the recorded demo/submission build.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from ..env import load_project_env
from ..learning.postgres_field_set_store import PostgresFieldSetStore
from ..learning.seed import seed_presets
from ..persistence.engine import new_session
from .routes import (
    auth,
    confirm,
    export,
    field_sets,
    reconcile,
    schemas,
    structural_hint,
    upload,
)

_logger = logging.getLogger("assayingest")

# Load .env BEFORE anything below reads os.environ. uvicorn imports this
# module directly (`uvicorn assayingest.api.app:app`) and never calls a
# main(), so module-import time IS this app's composition root -- there is
# no earlier point to hook in. Ordering matters concretely: the
# ASSAYINGEST_DEV_CORS and DATA_INGESTOR_GOOGLE_OAUTH reads below, and the
# FastAPI() construction itself, must see a .env-supplied value if one
# exists, or those conditional-middleware blocks silently stay off. A real
# environment variable (CI, deployment, operator shell) always wins --
# override=False, enforced inside load_project_env().
load_project_env()


def _require_schema_at_head() -> None:
    """Refuse to start unless the database schema has actually been migrated.

    Under Alembic the stores no longer run `CREATE TABLE IF NOT EXISTS`, so nothing
    else creates the tables. Without this check, an unmigrated database lets
    `seed_presets` raise `UndefinedTable`, which `_lifespan`'s deliberate
    `except Exception` would log as a mere warning -- and the app would boot with an
    EMPTY field-set picker and an "Upload and Map" button that silently does nothing.
    That is exactly the regression quick task 260712-e0e fixed.

    Log-or-raise: this RAISES and does not log.

    The Session comes from the composition-root seam, NOT a private `create_engine`.
    A private engine would read `DATABASE_URL` (the DEV database) even under test and
    so validate a database the tests never touch -- passing by accident while proving
    nothing about the one actually in use.
    """
    try:
        with new_session() as session:
            revision = session.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
    except Exception as exc:
        raise RuntimeError(
            "Cannot start: the database schema is missing or unreachable, so no "
            "field set, profile, or user could be read. Start PostgreSQL with "
            "\"sg docker -c 'docker compose up -d db'\" and create the schema with "
            "'uv run alembic upgrade head'."
        ) from exc
    if not revision:
        raise RuntimeError(
            "Cannot start: the database has no Alembic revision, so its tables are "
            "absent and the field-set picker would be empty. Create the schema with "
            "'uv run alembic upgrade head'."
        )


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Refuse to start on a missing schema, then seed the shipped starter presets
    into the field-set store (FIELD-05).

    THE TWO FAILURES ARE DIFFERENT AND MUST BEHAVE DIFFERENTLY. A missing SCHEMA is a
    deployment error: LOUD, refuse to start. A malformed preset YAML is a data hiccup:
    warn and start anyway (T-e0e-03) -- a bad preset must never brick the server. So
    `_require_schema_at_head()` is called BEFORE the seeding block and OUTSIDE its
    `except`. Do not widen that `except` to cover it.

    Seeding builds its OWN session and store directly, through the composition-root
    seam -- NEVER through a DI factory. `get_field_set_store` is `Depends`-typed, and
    lifespan runs outside the request cycle where FastAPI never resolves `Depends` for
    us: calling it as a plain function would bind `session` to the `Depends` OBJECT,
    and the first `session.execute(...)` would raise `AttributeError`. The `except`
    below would swallow that, log a warning, and boot with a blank picker -- green
    suite, broken product. Lifespan takes NO dependency override; a test reaches it by
    rebinding the seam (`tests/conftest.py`), not by substituting a store.
    """
    _require_schema_at_head()
    try:
        with new_session() as session:
            seed_presets(PostgresFieldSetStore(session))
    except Exception as exc:  # noqa: BLE001 -- seeding must never block startup
        _logger.warning("Starter field sets are unavailable: %s", exc)
    yield


def _configure_console_logging() -> None:
    """Make the app's own loggers actually reach the server console.

    AUTH-03's dev fallback prints the email-verification link via the
    `assayingest.auth` logger (`routes/auth.py`). Uvicorn configures only its
    OWN loggers, and Python's root logger defaults to WARNING with no INFO
    handler, so a bare `logger.info(...)` from an `assayingest.*` logger is
    silently dropped in a real `uvicorn assayingest.api.app:app` run -- the
    verification link never appears on the console the dev fallback promises.
    (pytest's `caplog` captures records regardless of handlers, which masked
    this in the unit tests.) Attach a stdout INFO handler to the top-level
    `assayingest` logger exactly once so the link is visible when the app runs.
    """
    app_logger = logging.getLogger("assayingest")
    already = any(getattr(h, "_assayingest_console", False) for h in app_logger.handlers)
    if not already:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
        handler._assayingest_console = True  # type: ignore[attr-defined]
        app_logger.addHandler(handler)
    if app_logger.level == logging.NOTSET or app_logger.level > logging.INFO:
        app_logger.setLevel(logging.INFO)
    # Propagation is intentionally left ON: under uvicorn the root logger has no
    # INFO handler so no duplicate line results, while pytest's `caplog` (which
    # attaches its handler at the root) still captures `assayingest.*` records
    # via propagation -- turning it off would silently break those tests.


_configure_console_logging()

# The SPA now owns the site's top-level path namespace (tabs route on clean
# paths, not a hash), so the API's own documentation endpoints move under
# the `/api` prefix every other backend route already uses -- otherwise
# FastAPI's built-in Swagger at `/docs` shadows the app's own Docs tab.
# `/api/*` is already the prefix the Vite dev proxy forwards
# (`vite.config.ts`), so the relocated docs stay reachable in dev with no
# proxy change.
app = FastAPI(
    title="Data Ingestor",
    lifespan=_lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.include_router(upload.router)
app.include_router(field_sets.router)
app.include_router(confirm.router)
app.include_router(structural_hint.router)
app.include_router(reconcile.router)
app.include_router(export.router)
app.include_router(auth.router)
app.include_router(schemas.router)

# Dev-only CORS for the Vite dev server (default port 5173) -- gated behind
# an env flag so it is never active in the demo build (smaller attack
# surface, RESEARCH.md CORS note). Once app.frontend() serves the built
# bundle from this same process/port, requests are same-origin and CORS is
# not needed at all.
if os.environ.get("ASSAYINGEST_DEV_CORS") == "1":
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Starlette's SessionMiddleware backs Authlib's OAuth state/nonce ONLY -- it is
# never the app's own login session (that is the itsdangerous-signed di_session
# cookie in auth/session.py). Registered ONLY when the Google OAuth flag is on,
# mirroring the ASSAYINGEST_DEV_CORS conditional-middleware block above, so the
# overnight (flag-off) app starts with zero extra middleware and no
# SESSION_SECRET requirement beyond what the cookie seam already needs.
if os.environ.get("DATA_INGESTOR_GOOGLE_OAUTH") == "1":
    from starlette.middleware.sessions import SessionMiddleware

    app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET"])

# API routes always win: FastAPI checks explicit path operations (registered
# above via app.include_router) before app.frontend()'s catch-all fallback,
# regardless of registration order (RESEARCH.md Pattern 3/Pitfall 5). This
# mount is registered LAST anyway, as the clearest possible signal of that
# invariant to a future reader. check_dir=False: frontend/dist may not exist
# yet in a dev checkout before `npm run build` has been run once -- the app
# must still start and serve /api/* correctly in that case.
app.frontend("/", directory="frontend/dist", check_dir=False)
