---
phase: quick-260712-fuf
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/assayingest/api/app.py
  - tests/api/test_docs_paths.py
  - frontend/src/state/routing.ts
  - frontend/src/state/routing.test.ts
  - frontend/src/App.tsx
autonomous: true
requirements: []
must_haves:
  truths:
    - "Clicking a tab changes the URL to a clean path (/upload, /review, /registry, /docs) with no '#'."
    - "Browser Back after switching tabs returns to the previous tab instead of leaving the app."
    - "A hard reload (F5) on /registry re-opens the Registry tab; a hard reload on /docs opens the app's Docs tab, NOT Swagger."
    - "Swagger UI is still reachable, at /api/docs; ReDoc at /api/redoc; the OpenAPI schema at /api/openapi.json."
    - "An unknown path (/nonsense) renders the default tab, never a blank screen."
    - "The default tab is canonical at '/' -- there is exactly one URL per screen."
    - "/verify?token=... still renders VerifyLanding, and its CTA still returns to the app shell."
    - "No new frontend dependency: git diff --stat frontend/package.json is empty."
  artifacts:
    - frontend/src/state/routing.ts
    - frontend/src/state/routing.test.ts
    - tests/api/test_docs_paths.py
  key_links:
    - "FastAPI(docs_url='/api/docs', ...) vacates /docs -> app.frontend() catch-all serves the SPA there -> the Docs tab can own /docs"
    - "App.tsx TABS (the only slug source) -> TAB_VALUES -> tabFromPath allowlist"
    - "window 'popstate' listener -> setPathname (this is what makes Back/Forward work)"
    - "ONE pathname state is the single source of truth; activeTab is derived from it, so the two can never disagree"
---

<objective>
Replace the hash routing shipped in quick task 260712-fiv with clean History-API path routing (`/upload`, `/review`, `/registry`, `/docs`), and move FastAPI's Swagger/ReDoc/OpenAPI off the SPA's `/docs` namespace so the Docs tab can own that path.

Purpose: the user saw the `#` and wants real URLs. `/docs` is the single collision that made hash routing the safe first move; relocating Swagger removes it.
Output: a pure, node-testable `state/routing.ts` (path <-> tab), its vitest spec, thin History-API wiring in `App.tsx`, and a backend regression test proving Swagger moved and `/docs` now belongs to the SPA.
</objective>

<context>
@.planning/STATE.md
@frontend/src/App.tsx
@frontend/src/state/routing.ts
@frontend/src/state/routing.test.ts
@frontend/src/components/VerifyLanding.tsx
@src/assayingest/api/app.py
</context>

<facts>
Verified live during planning against the running server and the working tree. Re-check anything you are about to depend on, but do not re-derive from scratch:

- The SPA catch-all already exists: `app.frontend("/", directory="frontend/dist", check_dir=False)` at `src/assayingest/api/app.py:145`. `GET /registry` returns **200 + the SPA shell** today. Path routing therefore needs **no new server-side fallback** -- this is the enabler.
- `GET /docs` returns **Swagger**, not the app (body contains `swagger-ui`). It is FastAPI's built-in, because `FastAPI(title="Data Ingestor", lifespan=_lifespan)` at `app.py:101` passes no `docs_url`. This is the one collision.
- `grep -rn "docs_url\|redoc\|openapi\|/docs" src/ tests/ frontend/src/ README.md` finds **nothing** (the only hit is an unrelated `docs.astral.sh` link in README). Relocating the docs endpoints breaks no dependent.
- FastAPI is **0.139.0** and `hasattr(FastAPI, "frontend")` is `True` -- `app.frontend()` is a real framework method, not a local helper.
- **`frontend/dist` is gitignored** (`git ls-files frontend/dist` -> 0 files). Any backend test that asserts on the SPA shell's *content* must be `skipif`-guarded on `frontend/dist/index.html` existing, or it fails in a fresh checkout that has not run `npm run build`.
- `frontend/dist/index.html` references its assets **root-absolutely** (`/assets/index-*.js`, `/favicon.svg`), and `frontend/src/lib/api.ts` calls **root-absolute** `/api/...` URLs. So a nested route like `/docs` hard-refreshes correctly with no Vite `base` change and no relative-URL breakage. Do not touch `vite.config.ts`.
- `frontend/vite.config.ts` sets vitest `environment: 'node'` -- there is **NO DOM**. Pure functions must take the path as a plain `string` argument and never touch `window`. Do not add jsdom; do not change the environment. (This is also the proof mechanism: if `routing.ts` touched `window`, its tests would throw under node.)
- `package.json`'s `test` script is bare `vitest` (watch mode) -- `-- --run` is MANDATORY or the run hangs.
- `tsconfig.app.json` enables `noUnusedLocals`/`noUnusedParameters` -- an orphaned import fails `npm run build`.
- Baselines today: `uv run pytest` = **615 passed, 4 skipped** (the 4 skipped are live-Claude tests gated behind `ASSAYINGEST_LIVE_TESTS=1`; they cost real money and MUST stay skipped). `cd frontend && npm run test -- --run` = **136 passed** (12 of them in `routing.test.ts`, which this task rewrites).
- A uvicorn dev server runs on **:8000 (PID 64731)**, launched flagless: `uv run uvicorn assayingest.api.app:app --host 0.0.0.0 --port 8000`. It serves `frontend/dist` **from disk**, so `npm run build` publishes itself with no restart -- but the `app.py` change **requires a restart**. You may kill that PID and relaunch with the identical command. Do NOT start a second server on :8000.
</facts>

<design_decisions>
Decided during planning. Implement these; do not re-litigate them mid-task.

**D-1 -- Collapse `path` and `activeTab` into ONE state.** Today `App.tsx` holds two independent states: `path` (line 58, drives the `/verify` landing) and `activeTab` (line 46, drives the tab shell). While tabs lived on the hash these occupied different URL axes and could not collide. Once tabs are paths they share one axis, and two states over one axis is exactly the bug to avoid -- they can disagree (e.g. `path === "/review"` while `activeTab === "upload"`).

So: keep **one** `pathname` state, and **derive** the tab from it:
```
const [pathname, setPathname] = useState(...window.location.pathname)
const activeTab = tabFromPath(pathname, TAB_VALUES)   // derived, not state
```
`activeTab` then has no writer at all and cannot drift. `pathname` has exactly three writers: `navigateTo`, `goToApp`, and the `popstate` handler -- all funnelled through one private URL writer.

**D-2 -- `/verify` wins by checking `pathname`, not `activeTab`.** The existing early return stays as-is, just reading the new state name:
```
if (pathname.startsWith("/verify")) return <VerifyLanding ... />
```
It runs BEFORE the tab shell renders, so `/verify` is never routed through the tab allowlist. `tabFromPath("/verify", ...)` does return the default tab (it is not a slug), but that value is never used on the `/verify` branch -- the early return already fired. This is precisely why collapsing to a single `pathname` is correct: the landing and the tabs read the same one truth, in a defined order.

**D-3 -- `/` is the canonical URL for the default tab.** `pathForTab(tabs[0], tabs) === "/"`, so the default tab is NOT also reachable at `/define-fields` from any in-app navigation. Exactly one URL per screen; the root URL keeps working as the app's front door; and the round-trip property still holds because `tabFromPath("/", tabs) === tabs[0]`. (`/define-fields` typed by hand still resolves to the same screen via the allowlist -- it is tolerated, just never minted.)

**D-4 -- Do NOT rewrite an unknown path.** `/nonsense` renders the default tab (allowlist) and leaves the URL alone. Re-examined now that tabs are paths, and the answer is still no, for a stronger reason than before: a mount-time `history.replaceState("/")` would have to carve out an exception for `/verify?token=...` (whose hooks run before the early return) or it would destroy the token in the URL before `VerifyLanding` reads it. Adding a rewrite means adding that exception, i.e. more branching for zero user benefit -- the allowlist already guarantees a correct screen, and the URL self-corrects on the first tab click. No rewrite, no exception, no bug.

**D-5 -- `pushState`, not `replaceState`, for tab navigation.** Pushing a history entry is the whole mechanism behind a working Back button. `popstate` (unlike `hashchange`) does NOT fire for our own `pushState` calls, so -- unlike the previous implementation -- there is no self-fire to reason about at all; the listener is woken only by real Back/Forward.
</design_decisions>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Move Swagger/ReDoc/OpenAPI under /api so the SPA can own /docs (RED then GREEN)</name>
  <files>tests/api/test_docs_paths.py, src/assayingest/api/app.py</files>
  <behavior>
    Write `tests/api/test_docs_paths.py` FIRST and watch it fail against today's `app.py`, then make it pass. Use `fastapi.testclient.TestClient(app)` WITHOUT a `with` block (a bare client does not trigger the lifespan, so no preset seeding runs -- matching the lighter idiom already used in `tests/api/`).

    Cases:
    - `GET /api/docs` -> 200, body contains `swagger-ui` (Swagger UI relocated and still reachable).
    - `GET /api/redoc` -> 200 (ReDoc relocated).
    - `GET /api/openapi.json` -> 200, and the parsed JSON has an `openapi` key (the schema the two UIs above load).
    - `GET /docs` is NO LONGER Swagger: the response body does NOT contain `swagger-ui`. Assert this unconditionally -- it holds whether or not a built SPA exists on disk, and it is the regression that motivated this whole task.
    - `GET /docs` falls through to the SPA shell: 200, and the body is the built `frontend/dist/index.html` (assert on a stable marker such as the root mount div). This one MUST carry
      `@pytest.mark.skipif(not (Path(...) / "frontend/dist/index.html").exists(), reason=...)` -- `frontend/dist` is a gitignored build artifact, so a fresh checkout that has not run `npm run build` has no shell to serve and the assertion would be meaningless there. Resolve the repo root from `__file__`, not from the process CWD.
  </behavior>
  <action>
    In `src/assayingest/api/app.py`, change the app construction at line 101 to pass the three relocated endpoints:
    `app = FastAPI(title="Data Ingestor", lifespan=_lifespan, docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json")`.

    Nothing else in `app.py` changes. In particular do NOT touch the `app.frontend(...)` mount -- it already provides the SPA fallback, and once FastAPI stops registering `/docs` as an explicit path operation, `/docs` simply falls through to it. That fall-through IS the fix; there is no second mechanism to add.

    Add a comment on the FastAPI(...) call explaining WHY (per CLAUDE.md: why, not what): the SPA owns the site's top-level path namespace now that the frontend routes on paths instead of a hash, so the API's own documentation endpoints move under the `/api` prefix that every other backend route already uses -- otherwise FastAPI's built-in Swagger shadows the app's own Docs tab. Note that `/api/*` is already the prefix the Vite dev proxy forwards (`vite.config.ts`), so the relocated docs stay reachable in dev with no proxy change.

    Do NOT rename or move any existing route. Do NOT add an `openapi_prefix`/`root_path`.
  </action>
  <verify>
    <automated>uv run pytest tests/api/test_docs_paths.py -v</automated>
  </verify>
  <done>The new test file failed against the unmodified `app.py` (RED observed and REPORTED in the summary with real output), and passes after the one-line FastAPI(...) change. `GET /api/docs` serves Swagger; `GET /docs` does not.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Convert state/routing.ts from hash to path (RED then GREEN)</name>
  <files>frontend/src/state/routing.ts, frontend/src/state/routing.test.ts</files>
  <behavior>
    Rewrite `routing.test.ts` FIRST against the new API and watch it fail (the old exports are gone), then rewrite `routing.ts` to satisfy it. The two new exports replace the two old ones outright -- this is a rename-and-reshape, not an addition.

    `tabFromPath(pathname: string, tabs: readonly string[]): string`
    - "/" -> tabs[0]                      (the canonical default, D-3)
    - "" -> tabs[0]
    - "/upload" -> "upload"
    - "upload" -> "upload"                (a caller may pass either form)
    - "/upload/" -> "upload"              (a trailing slash is cosmetic, not a 404)
    - "/define-fields" -> "define-fields" (hyphenated slug survives)
    - "/UPLOAD" -> "upload"               (hand-typed paths vary in case; real slugs are lowercase)
    - "/docs" -> "docs"                   (the path Task 1 just freed -- this is the point of the whole task)
    - "/nonsense" -> tabs[0]              (unknown -> default, never a blank screen)
    - "/upload/extra" -> tabs[0]          (a nested path is not a slug; the allowlist matches the whole normalized string)
    - "/%20upload" -> tabs[0]             (percent-encoded junk fails the allowlist and degrades to default rather than throwing)
    - "/verify" -> tabs[0]                (documented, deliberate: `/verify` is not a tab. App.tsx checks the pathname for the verify landing BEFORE it renders the tab shell, so this default value is never used on that branch -- see D-2. Assert it anyway so the behaviour is pinned.)
    - Guard property: the return value is ALWAYS a member of the `tabs` argument, for every input above. This is the property that makes a blank screen impossible.

    `pathForTab(tab: string, tabs: readonly string[]): string`
    - pathForTab(tabs[0], tabs) -> "/"    (D-3: the default tab's canonical URL is the root, NOT "/define-fields")
    - pathForTab("review", tabs) -> "/review"
    - pathForTab("docs", tabs) -> "/docs"

    Round-trip property: for EVERY slug in the list, `tabFromPath(pathForTab(slug, slugs), slugs) === slug` -- including the default slug, whose round trip goes through "/".

    Test fixture: keep the existing local `const TAB_SLUGS = [...]` test DATA. It is not a second source of truth -- production code always receives the live list as an argument from App.tsx's `TABS`.
  </behavior>
  <action>
    Rewrite `frontend/src/state/routing.ts` to export exactly `tabFromPath` and `pathForTab`. Delete the two old hash exports entirely -- do not keep them as aliases; nothing else may import them after Task 3.

    `tabFromPath` normalizes then allowlists, in that order, as two levels of abstraction: a small private normalizer (trim, strip a leading "/", strip a trailing "/", lowercase) and the public function that returns the slug only if `tabs.includes(...)`, else `tabs[0]`. The allowlist is the whole safety story: an unrecognized path can only ever produce the default tab, so no user- or attacker-controlled path can select a screen that does not exist.

    `pathForTab` takes the `tabs` list too (symmetric with `tabFromPath`) precisely so the canonical-root rule (D-3) lives HERE, inside the pure, unit-tested module, rather than as an `if` in App.tsx: the default tab maps to "/", every other tab to `/${tab}`.

    Per CLAUDE.md, document WHY not WHAT. The module docstring must state: (a) these are pure and window-free because vitest runs in `environment: 'node'` with no DOM, so the History-API wiring stays in App.tsx as the untested seam; (b) `tabs[0]` is the default by convention, matching App.tsx's own ordering; (c) the default tab is canonical at "/" so there is exactly one URL per screen.

    Do NOT add any dependency. Do NOT export a hardcoded slug list -- the caller supplies it. Do NOT reference `window` anywhere in this file, including in the docstring's examples: the node-environment test run is the enforcement, and any `window` access on an executed path would throw.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/state/routing.test.ts</automated>
  </verify>
  <done>The rewritten spec failed against the old hash-based module (RED observed and REPORTED), and every case above now passes under `environment: 'node'`. `routing.ts` exports only `tabFromPath` and `pathForTab`.</done>
</task>

<task type="auto">
  <name>Task 3: Wire the History API into App.tsx and collapse path + activeTab into one state</name>
  <files>frontend/src/App.tsx</files>
  <action>
    Implement D-1 through D-5. Import `pathForTab` / `tabFromPath` from `@/state/routing`; keep the existing `TAB_VALUES = TABS.map(...)` derivation (TABS stays the single source of truth for slugs, and `state/` must not import from `components/`).

    1. **One state.** Delete BOTH the `activeTab` state (line 46) and the `path` state (line 58). Replace them with a single `pathname` state, lazily seeded from `window.location.pathname` behind the same `typeof window === "undefined"` guard the two old initializers already used (seed `"/"` when there is no window). Then derive, as a plain const (NOT state, NOT a memo):
       `const activeTab = tabFromPath(pathname, TAB_VALUES);`
       Everything downstream (`<AppShell activeTab={activeTab}>` and the five `activeTab === "..."` render branches) keeps working untouched. Because `activeTab` is now derived, it has no writer and cannot drift out of sync with the URL -- that de-sync was the specific bug this design exists to prevent.

    2. **One URL writer.** Add a private helper that is the ONLY code that touches `history` and `pathname` together: it pushes a history entry via `window.history.pushState({}, "", next)` when `window.location.pathname !== next`, then calls `setPathname(next)`. Build the two public navigators on top of it:
       - `navigateTo(tab)`: clears `authView` (leaving a tab also dismisses an open auth overlay -- today's `handleTabChange` behaviour), then routes through the helper with `pathForTab(tab, TAB_VALUES)`. Keep it as the single tab-navigation entry point: `handleMapped`, `handleTabChange`, and `handleSignedIn` all continue to call it.
       - `goToApp()`: routes through the helper with `"/"` and does NOT touch `authView`. This preserves today's exact semantics -- `VerifyLanding`'s CTA calls `goToApp()` and THEN `setAuthView("signin")`, so `goToApp` must not clear the overlay the caller is about to open. Do not "simplify" it into `navigateTo(TABS[0].value)`; that would make the CTA depend on setState ordering to survive.

    3. **Back/Forward.** Replace the `hashchange` `useEffect` with a `popstate` one (empty dep array, returns a cleanup that removes the listener). On each event: clear `authView` and `setPathname(window.location.pathname)`. This effect is what makes Back/Forward move between screens; without it the URL would change and the render would not. Clearing `authView` matters for the same reason as before: pressing Back with the sign-in overlay open must not swap the screen underneath a still-covering overlay.
       Unlike the old listener, `popstate` does NOT fire for our own `pushState` calls -- so there is no idempotent self-fire to explain away. Say that in the comment, because the previous comment said the opposite and a reader will remember it.

    4. **The verify landing.** The early return keeps its exact shape and position (after all hooks), now reading the new state: `if (pathname.startsWith("/verify"))`. `VerifyLanding` itself does not change -- it still reads `?token=` off `window.location.search`, which `pushState` never disturbs.

    Deliberate non-goals, so the diff stays honest:
    - Do NOT rewrite an unknown or non-canonical path on mount (D-4).
    - Do NOT add a redirect for a cold `/review` -- `Review` already renders its own "No file uploaded yet." empty state.
    - Do NOT touch `vite.config.ts` (assets and API calls are already root-absolute), `Review`'s `key={lastMapping?.upload_token ?? "empty"}`, or any other component.

    Finally, no source comment anywhere in `frontend/src/` may name the old hash helpers or the old DOM event -- the migration is complete, not annotated. A stale mention would also trip this task's own grep gate below.
  </action>
  <verify>
    <automated>cd frontend && npm run test -- --run && npm run build && grep -rn "tabFromHash\|hashForTab\|hashchange" src/ ; test $? -eq 1 && git diff --stat package.json</automated>
  </verify>
  <done>
    Full vitest suite green -- the 124 non-routing tests still pass alongside Task 2's rewritten ones (report the REAL total, do not assume it stayed 136). `npm run build` (tsc -b && vite build) typechecks and bundles clean. The grep for the old hash helpers and the `hashchange` event over `frontend/src/` returns ZERO matches. `git diff --stat frontend/package.json` is empty, proving no dependency was added. `activeTab` appears in `App.tsx` as a derived const with no setter.
  </done>
</task>

</tasks>

<!-- planner-discipline-allow: tabFromHash -->
<!-- planner-discipline-allow: hashForTab -->
<!-- planner-discipline-allow: hashchange -->

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| URL bar -> client state | `location.pathname` is fully user/attacker-controlled text entering the SPA |
| Public network -> FastAPI | The relocated `/api/docs`, `/api/redoc`, `/api/openapi.json` endpoints |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-fuf-01 | Tampering | `tabFromPath` | low | mitigate | The pathname is matched against the `TAB_VALUES` allowlist and is never rendered as markup, never used to build a request URL, and never `eval`'d. A non-member returns `tabs[0]`, so a hostile path can only ever select an existing screen. Pinned by the guard property test in Task 2. |
| T-fuf-02 | Elevation of privilege | `/verify` early return | medium | mitigate | Tabs and `/verify` now share one path axis, so a crafted path must not be able to make the app render the tab shell while it believes it is on the landing, or vice-versa. Mitigated structurally by D-1/D-2: ONE `pathname` state, checked for `/verify` BEFORE the tab shell renders. There is no second state that can disagree with it. |
| T-fuf-03 | Information disclosure | Swagger at `/api/docs` | low | accept | The API's interactive docs remain publicly reachable, exactly as they are today at `/docs` -- this task RELOCATES that exposure, it does not widen or narrow it. Locking the docs behind auth is a separate, out-of-scope decision (note it, do not act on it). |
| T-fuf-04 | Information disclosure | path in history/referrer | low | accept | Only opaque tab slugs are written to the path -- no upload token, no mapping, no email. `pushState` never rewrites `?token=` on the `/verify` landing (nothing calls it there). |

No package installs in this task (`frontend/package.json` diff must be empty; `pyproject.toml` untouched), so there is no supply-chain (`T-*-SC`) surface.
</threat_model>

<verification>
Run from the repo root and report REAL output (not a summary) for every gate:

1. `uv run pytest` -- baseline is **615 passed, 4 skipped**. Must stay green, the count must only go UP (Task 1 adds tests), and the **4 live-Claude tests MUST remain SKIPPED** (they are gated behind `ASSAYINGEST_LIVE_TESTS=1` and cost real money -- do not set that variable).
2. `cd frontend && npm run test -- --run` -- `--run` is mandatory (the `test` script is bare `vitest`, which otherwise hangs in watch mode). Baseline 136 passed; report the real new total.
3. `cd frontend && npm run build` -- `tsc -b && vite build`; must typecheck clean.
4. `git diff --stat frontend/package.json` -- must be EMPTY (no new dependency; no react-router, no wouter).
5. `grep -rn "tabFromHash\|hashForTab\|hashchange" frontend/src/` -- must return zero matches.

Then restart the backend so the `app.py` change is live (the `npm run build` above already published the frontend, since the server reads `frontend/dist` from disk):
- `kill 64731`, then relaunch with the IDENTICAL flagless command in the background: `uv run uvicorn assayingest.api.app:app --host 0.0.0.0 --port 8000`. Do NOT add `--reload`. Do NOT start a second server on :8000 -- if the port is busy, the old process did not die.

Live smoke (curl, then report the actual status codes / body snippets):
- `curl -s http://localhost:8000/api/docs | head -c 200` -> Swagger HTML.
- `curl -s http://localhost:8000/docs | head -c 200` -> the SPA shell (a root div, NOT `swagger-ui`).
- `curl -so /dev/null -w "%{http_code}" http://localhost:8000/registry` -> 200.
- `curl -so /dev/null -w "%{http_code}" http://localhost:8000/nonsense` -> 200 (SPA shell; the client then renders the default tab).

Browser smoke (state what you actually observed):
- Click Upload -> URL is `/upload` with no `#`. Click Review -> `/review`. Press Back -> returns to Upload, not out of the app.
- Load `http://localhost:8000/registry` fresh -> Registry tab opens.
- Load `http://localhost:8000/docs` fresh -> the app's **Docs tab**, not Swagger.
- Load `http://localhost:8000/nonsense` -> Define Fields renders (no blank screen), URL left as-is.
- Click the default tab -> URL is `/`, not `/define-fields`.
- `/verify?token=...` still renders the verification landing, and its Sign In CTA returns to the app shell.
</verification>

<success_criteria>
- Tabs live on clean paths; Back/Forward and hard refresh work; no `#` anywhere in the URL.
- Swagger/ReDoc/OpenAPI are reachable under `/api/*`, and `/docs` belongs to the SPA -- pinned by a backend regression test, not just a manual curl.
- `App.tsx` holds ONE `pathname` state; `activeTab` is derived from it and has no setter.
- Path <-> tab logic is pure and unit-tested in `state/routing.ts`; only the History-API seam lives in `App.tsx`.
- Zero new dependencies; vitest still runs in `environment: 'node'`; `vite.config.ts` untouched.
- Commit messages: English, capitalized, one short imperative line (<=150 chars). Suggested split -- `Move Swagger and ReDoc under /api so the SPA can own the /docs path`, then `Switch tab routing from the URL hash to clean History-API paths`.
</success_criteria>

<output>
Create `.planning/quick/260712-fuf-switch-to-clean-path-routing-and-move-sw/260712-fuf-SUMMARY.md` when done.
</output>
