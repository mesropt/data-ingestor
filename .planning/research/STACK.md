# Technology Stack

**Project:** Data Ingestor — Day 2-4 additions (validator, learning store, review UI, API surface)
**Researched:** 2026-07-09
**Confidence:** MEDIUM-HIGH (versions cross-verified against pypi.org / npm registry directly; patterns from multiple 2026 web sources, not from a single vendor doc)

**Scope note:** Day 1's stack (Python 3.13, pandas/openpyxl, Anthropic SDK, Pydantic, pytest, uv) is already decided and is NOT re-researched here. This file covers only what Day 2-4 adds: exposing the mapper over HTTP, a SQLite learning store, and a Vite+React review UI. All recommendations assume and preserve the existing Clean Architecture (parsing / mapping / domain layers; wire-to-domain boundary mapping) documented in `.planning/codebase/ARCHITECTURE.md`.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| FastAPI | 0.139.0 | HTTP API wrapping the existing mapper (`/upload`, `/propose`, `/confirm`) | Current stable as of 2026-07-01 (verified on pypi.org). Already named in `CLAUDE.md`/`PROJECT.md` as the backend framework; type-hint-driven request/response models compose naturally with the existing Pydantic wire models. |
| uvicorn | 0.51.0 | ASGI server to run FastAPI locally for the demo | Current stable as of 2026-07-08 (verified on pypi.org). Standard pairing with FastAPI; `uvicorn app.main:app --reload` is the whole "run the backend" step for a 4-day build. |
| python-multipart | 0.0.32 | Required by FastAPI/Starlette to parse `multipart/form-data` (file uploads) | Current stable as of 2026-06-04 (verified on pypi.org). Starlette stopped bundling this; **omitting it causes `UploadFile`/`File()` endpoints to fail at runtime**, not at import time — an easy Day 2 trap. |
| Vite | 8.1.3 (via `create-vite@9.1.1`) | Frontend build tool + dev server | Current as of 2026-07-09 (verified on npm registry). Instant HMR dev server, near-zero config, `npm create vite@latest <name> -- --template react-ts` scaffolds a working React+TS app in seconds — the fastest path to a running UI for a hackathon. |
| React | 19.2.7 | Review-table UI (source vs. recognized, yellow uncertain cells, confirm button) | Current as of 2026-07-09 (verified on npm registry). Already named in `CLAUDE.md` as the frontend framework; no reason to deviate. |
| TypeScript | 7.0.2 | Type safety for the frontend, mirrors the Pydantic wire schema | Use the `react-ts` Vite template. The mapper's wire schema (`WireFieldMapping`, `WireMappingProposal`) has a fixed shape (7 fields, confidence, flags, alternatives) — typing it once in the frontend prevents silent shape-drift bugs during a fast build, which is exactly the kind of bug that eats hackathon hours. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python stdlib `sqlite3` | bundled with Python 3.13 | SQLite access for the `lab_profile` learning store | Default choice — see "Alternatives Considered" below. Use directly behind a small repository class (e.g. `LabProfileRepository`) exposing `find_by_signature()` / `save()`, so the domain/mapping layers never import `sqlite3` directly (keeps dependencies pointing inward per the existing Clean Architecture). |
| `httpx` | 0.28+ (pulled in transitively by `starlette.testclient.TestClient`, but pin explicitly as a dev dependency) | FastAPI endpoint testing via `TestClient` | Add to `[dependency-groups].dev` alongside `pytest`. Lets the existing pytest suite grow to cover `/upload`, `/propose`, `/confirm` without a running server. |
| `@tailwindcss/vite` + `tailwindcss` | 4.3.2 | Fast utility-class styling for the yellow/green confidence highlighting in the review table | Optional but recommended — see rationale below. Skip if you'd rather write ~40 lines of plain CSS; either is fine for a 4-day build. |
| Zustand | 5.0.14 | Shared state across review-table components, only if `useState`/prop-drilling gets painful | Not needed at MVP scope (single review screen, one proposal in flight). Reach for it only if the confirm flow grows a second screen (e.g. an upload history / lab-profile list) that needs to share state without prop-drilling. Do not install it up front — see "What NOT to Use". |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` | Backend dependency management, already in use | Add `fastapi`, `uvicorn[standard]`, `python-multipart` to `[project.dependencies]`; add `httpx` to the dev group. Keep using `uv run pytest` / `uv run uvicorn ...`. |
| `npm` (bundled with Node 20.19+/22.12+) | Frontend dependency management | Vite 8 requires Node 20.19+ or 22.12+ — confirm the WSL Node version before scaffolding (`node -v`). |
| Vite dev proxy (`server.proxy` in `vite.config.ts`) | Avoid CORS entirely during local dev | See "Installation" below — simpler than maintaining a CORS allow-list for a local-only demo. |

## Installation

```bash
# Backend — from repo root, using existing uv-managed project
uv add fastapi "uvicorn[standard]" python-multipart
uv add --dev httpx

# Frontend — scaffold in a new frontend/ directory
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install tailwindcss @tailwindcss/vite   # optional but recommended for fast styling
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| SQLite access | stdlib `sqlite3` behind a hand-written repository | SQLAlchemy (Core or ORM) | SQLAlchemy earns its weight at multi-table/relational scale with migrations across engines. The learning store is one table (`lab_profile`) with a signature lookup and an upsert — stdlib `sqlite3` keeps the SQL explicit and adds zero new dependencies, which matters more than ORM convenience with 4 days on the clock. |
| SQLite access | stdlib `sqlite3` | `sqlite-utils` (Simon Willison) | Nice productivity layer (schema-on-insert, `.upsert()` helpers) but it's another abstraction between the repository and the SQL, and it obscures exactly the kind of explicit, inspectable code a Clean-Architecture repository should expose. Skip it. |
| API doc pattern | FastAPI's built-in OpenAPI/Swagger UI (free at `/docs`) | Hand-rolled API docs | Not worth building — FastAPI generates this from the Pydantic response models for free. Useful for demoing the API surface if judges ask to see it. |
| CORS | Vite dev-server proxy (`server.proxy`) | `CORSMiddleware` with an origin allow-list | Both work; proxy is simpler for a same-machine local demo (browser sees same-origin requests, zero CORS config). Use `CORSMiddleware` only if you end up deploying the frontend and backend on different hosts before the deadline. |
| Frontend state | Component-local `useState`/`useReducer` | Zustand | Zustand is genuinely tiny (<1kB) and would not be wrong, but for a single review screen with one proposal in flight, introducing any state library is unneeded ceremony. Add it only if a second screen needs cross-component sharing. |
| Frontend state | (above) | Redux / Redux Toolkit | Actively wrong for this scope — boilerplate cost has no payoff for a 4-day, single-screen demo app. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| Flask / Django for the API layer | Contradicts the already-decided stack (`CLAUDE.md`, `.planning/codebase/STACK.md` name FastAPI); Django in particular is far too heavy (ORM, admin, migrations) for a 3-endpoint hackathon API. | FastAPI |
| An ORM (SQLAlchemy, Tortoise, etc.) for the learning store | One table, no relations, no migrations across environments needed for a hackathon demo; ORM setup/session-management overhead costs more time than it saves at this scale. | stdlib `sqlite3` behind a small repository |
| `axios` on the frontend | Native `fetch()` in modern browsers already does everything needed here (JSON + multipart POST); axios is one more dependency and one more thing to configure (base URL, interceptors) that buys nothing at this scope. | Native `fetch()` |
| Redux / MobX / Recoil | Heavy state-management ceremony for a single-screen review UI with one round trip (upload → propose → confirm). | `useState`/`useReducer`, escalate to Zustand only if needed |
| Manually setting the `Content-Type` header on the file-upload `fetch()` call | Breaks the multipart boundary the browser generates automatically; this is the #1 cause of mysterious 422s when wiring React file upload to FastAPI. | Let the browser set `Content-Type` automatically — pass a `FormData` body and no header |
| SQLite on a network-mounted volume (NFS, some Docker volume drivers) with WAL mode | WAL requires shared-memory primitives that don't work reliably over NFS and can corrupt the database. | Local filesystem path for the SQLite file — a non-issue for a local hackathon demo but worth knowing if you containerize |
| `async def` FastAPI endpoints that call the existing (synchronous, blocking) Anthropic mapper directly | The existing `mapper.py` makes a blocking network call; calling it from an `async def` path operation blocks the whole event loop, stalling every other request during the ~seconds-long Claude call — bad for a demo where you might upload two files back to back. | Declare the mapper-calling endpoints as plain `def` (not `async def`) — FastAPI automatically runs synchronous path operations in a threadpool, matching the existing single-threaded-per-call design without any code changes to `mapper.py` |

## Stack Patterns by Variant

**If the review UI needs to demo the "second file, zero yellow" learning-loop moment (the differentiator, per `CLAUDE.md`):**
- Add a `POST /confirm` endpoint that persists the curator-approved mapping (`lab_name`, `source_columns_signature`, `mapping_json`) via the `LabProfileRepository`.
- On `POST /propose`, compute the same column-signature (e.g. sorted, normalized tuple of header strings, hashed) and check the repository *before* calling Claude. On a hit, return the stored mapping directly with `confidence=1.0`, `needs_confirmation=false` for every field, skipping the Claude call entirely — this is both the fastest and the most honest way to demo the loop (visibly zero LLM calls on repeat).
- Because this check happens in the mapping layer (which already depends on the domain and is used by the API layer), keep the repository interface defined in the domain layer (a `Protocol`) and the `sqlite3` implementation in a new `infrastructure/` (or `persistence/`) package — mirrors the existing wire/domain boundary-mapping pattern already used for Claude's response.

**If time runs short on frontend styling:**
- Skip Tailwind; ship with ~40-60 lines of plain CSS (`.confidence-high { background: #d1fae5 }`, `.confidence-low { background: #fef08a }`). Fewer moving parts, same visual result for a 3-minute demo video. Only add Tailwind if you want faster iteration on layout (side-by-side columns, responsive table) across multiple styling passes.

**If you want the API testable without a live Anthropic key in CI:**
- FastAPI's `Depends()` can inject the mapper function; override it in tests with `app.dependency_overrides[get_mapper] = lambda: fake_mapper`. This is the standard FastAPI DI-for-testing pattern and keeps `TestClient`-based endpoint tests fast and hermetic, separate from the existing "1 live integration test" that hits the real API.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| fastapi 0.139.0 | pydantic 2.13.4 (already pinned per `.planning/codebase/STACK.md`, 2.9+) | FastAPI 0.11x+ targets Pydantic v2; no action needed, existing wire models (`WireFieldMapping`, `WireMappingProposal`) can be reused as FastAPI response models directly. |
| fastapi 0.139.0 | python-multipart 0.0.32 | Required for any endpoint using `UploadFile`/`File()`/`Form()`; install explicitly — not a transitive dependency in current FastAPI/Starlette. |
| vite 8.1.3 | Node 20.19+ / 22.12+ | Verify with `node -v` in WSL before scaffolding; older Node silently produces confusing Vite startup errors. |
| react 19.2.7 | typescript 7.0.2 (via `react-ts` template) | Handled automatically by `create-vite`'s `react-ts` template; no manual type-package wrangling needed. |
| tailwindcss 4.3.2 | vite 8.1.3 | Use the `@tailwindcss/vite` plugin (Tailwind v4's official Vite integration) — no PostCSS/autoprefixer config file needed, unlike Tailwind v3. |

## Sources

- pypi.org/project/fastapi — version 0.139.0, released 2026-07-01 (direct registry fetch, HIGH-confidence source but classified LOW/MEDIUM by this session's provider-tier rules since fetched via generic webfetch rather than a curated docs provider — cross-checked against web search results referencing FastAPI 0.115+ era features, consistent)
- pypi.org/project/pydantic — version 2.13.4, released 2026-05-06 (direct registry fetch)
- pypi.org/project/uvicorn — version 0.51.0, released 2026-07-08 (direct registry fetch)
- pypi.org/project/python-multipart — version 0.0.32, released 2026-06-04 (direct registry fetch)
- registry.npmjs.org/vite, /react, /zustand, /create-vite, /tailwindcss, /typescript — latest dist-tags (direct registry JSON fetch, 2026-07-09)
- Web search, multiple 2026 sources (FastAPI Clean Architecture layering, sqlite3/SQLAlchemy tradeoffs, SQLite WAL + FastAPI threading, React file-upload FormData pattern, FastAPI CORS + Vite proxy, Zustand vs useState for small apps) — MEDIUM confidence, cross-checked across 3+ independent articles per topic; full digests cached via `gsd-tools query research-store` under this session's research-plan keys

---
*Stack research for: Data Ingestor Day 2-4 (validator/learning-store/review-UI/API additions)*
*Researched: 2026-07-09*
