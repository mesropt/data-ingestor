---
phase: quick-260712-fuf
plan: 01
subsystem: ui
tags: [react, fastapi, history-api, routing, swagger, vitest]

requires:
  - phase: quick-260712-fiv
    provides: hash-based tab routing (state/routing.ts, App.tsx wiring) that this task replaces
provides:
  - Clean path-based tab routing (/upload, /review, /registry, /docs) with no '#'
  - FastAPI Swagger/ReDoc/OpenAPI relocated to /api/docs, /api/redoc, /api/openapi.json
  - Backend regression test proving /docs now falls through to the SPA shell
affects: [frontend-shell, api-transport-layer]

tech-stack:
  added: []
  patterns:
    - "State collapse: one pathname state, activeTab derived (no second writer over the same URL axis)"
    - "Pure path<->tab translation lives in state/routing.ts (window-free, node-environment-testable); History API wiring is the untested seam in App.tsx"

key-files:
  created:
    - tests/api/test_docs_paths.py
  modified:
    - src/assayingest/api/app.py
    - frontend/src/state/routing.ts
    - frontend/src/state/routing.test.ts
    - frontend/src/App.tsx

key-decisions:
  - "Collapsed App.tsx's two states (path, activeTab) into one pathname state with activeTab as a derived const, per D-1 -- eliminates the de-sync bug where the two could disagree"
  - "/verify is checked against pathname before the tab shell renders (D-2), never routed through the tab allowlist -- protects the ?token= landing"
  - "Default tab is canonical at '/' (D-3): pathForTab(tabs[0], tabs) === '/', not '/define-fields' -- exactly one URL per screen"
  - "No mount-time URL rewrite for unknown paths (D-4): /nonsense renders the default tab via the allowlist but leaves the URL untouched"
  - "pushState (not replaceState) for tab navigation (D-5) so popstate only fires for real Back/Forward, never our own writes"

requirements-completed: []

coverage:
  - id: D1
    description: "FastAPI Swagger/ReDoc/OpenAPI relocated under /api/*; /docs falls through to the SPA"
    verification:
      - kind: unit
        ref: "tests/api/test_docs_paths.py -- 5 tests, all pass"
        status: pass
      - kind: manual_procedural
        ref: "curl http://localhost:8000/api/docs (Swagger), /docs (SPA shell, no swagger-ui), /api/redoc, /api/openapi.json"
        status: pass
    human_judgment: false
  - id: D2
    description: "Pure tabFromPath/pathForTab replace tabFromHash/hashForTab with root-canonical default tab"
    verification:
      - kind: unit
        ref: "frontend/src/state/routing.test.ts -- 17 tests, all pass"
        status: pass
    human_judgment: false
  - id: D3
    description: "App.tsx wired to History API: one pathname state, derived activeTab, pushState navigation, popstate Back/Forward, /verify still protected"
    verification:
      - kind: unit
        ref: "cd frontend && npm run test -- --run -- 141 passed"
        status: pass
      - kind: other
        ref: "cd frontend && npm run build (tsc -b && vite build) -- typechecks and bundles clean"
        status: pass
      - kind: manual_procedural
        ref: "curl smoke: /registry -> 200, /nonsense -> 200 (server restarted on PID 78623 after killing 64731)"
        status: pass
    human_judgment: true
    rationale: "Browser-only behaviors (URL bar updates with no '#', Back button returning to the previous tab, hard-refresh reopening the right tab, /verify?token=... CTA flow) require an actual browser session to observe -- curl/vitest/build confirm the mechanics but not the visual/interactive result."

duration: 12min
completed: 2026-07-12
status: complete
---

# Quick Task 260712-fuf: Clean path routing + relocate Swagger off /docs Summary

**Replaced hash-based tab routing with History-API clean paths (`/upload`, `/review`, `/registry`, `/docs`) and moved FastAPI's Swagger/ReDoc/OpenAPI to `/api/*` so the SPA's Docs tab can own `/docs`.**

## Performance

- **Duration:** ~12 min (11:31:45 to ~11:44 local time)
- **Started:** 2026-07-12T07:31:45Z
- **Completed:** 2026-07-12T07:44:00Z (approx)
- **Tasks:** 3
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

- FastAPI's Swagger UI, ReDoc, and OpenAPI schema relocated to `/api/docs`, `/api/redoc`, `/api/openapi.json` — `/docs` now falls through to `app.frontend()`'s existing SPA catch-all instead of colliding with the app's own Docs tab.
- `frontend/src/state/routing.ts` rewritten from hash-based (`tabFromHash`/`hashForTab`) to path-based (`tabFromPath`/`pathForTab`) translation — pure, `window`-free, unit-tested under `environment: 'node'`.
- `App.tsx` rewired onto the History API: a single `pathname` state (with `activeTab` derived, never a second state), `pushState`-based navigation via one private `_navigate` helper, and a `popstate` listener for Back/Forward — replacing the prior two-state (`path` + `activeTab`) design and the `hashchange` listener.
- `/verify?token=...` landing preserved exactly: the early return still checks the pathname before the tab shell renders, and `goToApp()` still doesn't touch `authView` so `VerifyLanding`'s Sign In CTA ordering survives unchanged.

## Task Commits

Each task was committed atomically:

1. **Task 1: Move Swagger/ReDoc/OpenAPI under /api so the SPA can own /docs** - `1b72334` (feat, TDD RED→GREEN)
2. **Task 2: Convert state/routing.ts from hash to path** - `416bcd8` (test+refactor combined, TDD RED→GREEN)
3. **Task 3: Wire the History API into App.tsx and collapse path + activeTab into one state** - `216919d` (refactor)

_Note: Tasks 1 and 2 were each single commits containing both the RED test and the GREEN implementation, per this plan's own commit-per-task cadence (the plan did not request separate test/feat commits for these tasks)._

## Files Created/Modified

- `tests/api/test_docs_paths.py` - New backend regression test: Swagger/ReDoc/OpenAPI reachable under `/api/*`; `/docs` is no longer Swagger and (when `frontend/dist` exists) serves the SPA shell
- `src/assayingest/api/app.py` - `FastAPI(docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json")`
- `frontend/src/state/routing.ts` - Replaced `tabFromHash`/`hashForTab` with `tabFromPath`/`pathForTab`; default tab canonical at `/`
- `frontend/src/state/routing.test.ts` - Rewritten spec: 17 tests covering normalization, allowlist fallback, the freed `/docs` path, `/verify` non-tab behavior, and the round-trip property
- `frontend/src/App.tsx` - Collapsed `path`/`activeTab` into one `pathname` state with `activeTab` derived; added `_navigate` helper (`pushState` + `setPathname`); replaced the `hashchange` effect with a `popstate` effect

## Decisions Made

- D-1: One `pathname` state, `activeTab` derived as a plain const with no setter — the specific fix for the two-states-over-one-axis de-sync bug this task's design docs called out.
- D-2: `/verify` checked against `pathname` before the tab shell renders, so it's never routed through the tab allowlist — no mount-time rewrite risks the `?token=` query string.
- D-3: `pathForTab(tabs[0], tabs) === "/"` — the default tab is canonical at the root, never also reachable at its own slug from in-app navigation.
- D-4: No mount-time URL rewrite for unknown paths — `/nonsense` renders the default tab via the allowlist and leaves the URL as-is.
- D-5: `pushState`, not `replaceState`, for tab navigation — gives `popstate` a clean signal (fires only for real Back/Forward, never our own writes).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stale reference to the old `hashchange` event left in a comment**
- **Found during:** Task 3 verification (the plan's own grep gate: `grep -rn "tabFromHash\|hashForTab\|hashchange" frontend/src/` must return zero matches)
- **Issue:** The new `popstate` effect's comment explained the difference "unlike the hashchange event this replaces," which literally names the banned string and tripped the plan's own grep gate — the plan explicitly requires the migration to be complete, not annotated with the old term.
- **Fix:** Reworded the comment to describe the behavior (fires only for real Back/Forward, never our own `pushState` calls) without naming the old event.
- **Files modified:** `frontend/src/App.tsx`
- **Verification:** `grep -rn "tabFromHash\|hashForTab\|hashchange" frontend/src/` returned zero matches (exit 1); vitest (141 passed) and `npm run build` re-run clean after the edit.
- **Committed in:** `216919d` (part of Task 3 commit — caught before commit, not a follow-up fix)

---

**Total deviations:** 1 auto-fixed (1 bug, self-caught during verification before commit)
**Impact on plan:** No scope creep — the plan itself anticipated this exact comment-text trap by naming the grep gate; this deviation is the executor honoring that gate.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None - no external service configuration required.

## Verification Gates (actual output)

**Backend tests:**
```
uv run pytest
================== 620 passed, 4 skipped, 1 warning in 24.10s ==================
```
(Baseline was 615 passed / 4 skipped; +5 from `test_docs_paths.py`. The 4 skipped are the live-Claude tests gated behind `ASSAYINGEST_LIVE_TESTS=1` — confirmed still SKIPPED, not set.)

**Frontend tests:**
```
cd frontend && npm run test -- --run
 Test Files  9 passed (9)
      Tests  141 passed (141)
```
(Baseline was 136 passed; +5 net from the rewritten `routing.test.ts`, 17 tests vs. the old 12.)

**Frontend build:**
```
cd frontend && npm run build
> tsc -b && vite build
✓ 2089 modules transformed.
✓ built in ~400ms
```
Typechecks and bundles clean (one pre-existing chunk-size warning, unrelated to this task).

**package.json diff:**
```
git diff --stat frontend/package.json
```
Empty — confirmed no new dependency (no react-router, no wouter).

**Hash-remnant grep:**
```
grep -rn "tabFromHash\|hashForTab\|hashchange" frontend/src/
```
Zero matches (exit code 1) — confirmed after fixing the deviation above.

**Server restart:** Killed PID 64731 (old server, pre-`app.py` change), relaunched flagless:
`uv run uvicorn assayingest.api.app:app --host 0.0.0.0 --port 8000` → new PID 78623, listening on `:8000`, startup log clean ("Application startup complete").

**Live curl smoke:**
```
GET /api/docs      -> 200, Swagger UI HTML (swagger-ui-dist, "Data Ingestor" title)
GET /docs          -> 200, SPA shell (<div id="root">...), 0 occurrences of "swagger-ui"
GET /api/redoc     -> 200
GET /api/openapi.json -> 200, {"openapi":"3.1.0", ...}
GET /registry      -> 200
GET /nonsense      -> 200
```

**Browser smoke:** Not performed interactively in this session (no browser driver available in this execution context) — the mechanics (History API pushState/popstate wiring, pure routing-module unit tests, the live curl responses above, and the successful production build) collectively cover the same code paths a manual click-through would exercise. Flagged under coverage item D3 as requiring human judgment for final sign-off (URL-bar/Back-button/hard-refresh visual confirmation).

## Next Phase Readiness

- Clean path routing and the `/docs` relocation are both shipped and covered by unit tests + a live server smoke test.
- Recommended before demo recording: a quick manual browser pass — click each tab and confirm the URL bar shows no `#`, press Back and confirm it returns to the previous tab, hard-refresh on `/registry` and `/docs`, and click through the `/verify?token=...` console link once to confirm the Sign In CTA still returns to the app shell.
- No blockers for downstream work.

---
*Phase: quick-260712-fuf*
*Completed: 2026-07-12*

## Self-Check: PASSED

All 5 created/modified source files verified present on disk; all 3 task commits (`1b72334`, `416bcd8`, `216919d`) verified present in `git log --oneline --all`.
