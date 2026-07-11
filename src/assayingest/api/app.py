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

import os

from fastapi import FastAPI

from .routes import confirm, field_sets, upload

app = FastAPI(title="AssayIngest")
app.include_router(upload.router)
app.include_router(field_sets.router)
app.include_router(confirm.router)

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

# API routes always win: FastAPI checks explicit path operations (registered
# above via app.include_router) before app.frontend()'s catch-all fallback,
# regardless of registration order (RESEARCH.md Pattern 3/Pitfall 5). This
# mount is registered LAST anyway, as the clearest possible signal of that
# invariant to a future reader. check_dir=False: frontend/dist may not exist
# yet in a dev checkout before `npm run build` has been run once -- the app
# must still start and serve /api/* correctly in that case.
app.frontend("/", directory="frontend/dist", check_dir=False)
