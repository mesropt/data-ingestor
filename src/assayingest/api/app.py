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

from ..env import load_project_env
from ..learning.seed import seed_presets
from .deps import get_field_set_store
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


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Seed the shipped starter presets into the field-set store on
    startup (FIELD-05). Resolved through `app.dependency_overrides` --
    not called directly as `get_field_set_store()` -- because lifespan runs
    outside the request cycle, so FastAPI never applies dependency
    overrides for us here. Without this, a test that overrides
    `get_field_set_store` with a tmp-path store would still seed the real
    `.assayingest/profiles.db` on lifespan startup.

    Seeding failures must not brick the server (T-e0e-03): log a
    consequence-shaped warning and let the app start regardless. Log-or-
    raise -- this is the log branch, so nothing is re-raised.
    """
    try:
        factory = _app.dependency_overrides.get(get_field_set_store, get_field_set_store)
        seed_presets(factory())
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
