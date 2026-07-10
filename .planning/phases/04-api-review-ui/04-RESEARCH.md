# Phase 4: API & Review UI (BACKEND) - Research

**Researched:** 2026-07-10
**Domain:** FastAPI transport layer over an existing Python library (Anthropic SDK, SQLite, pandas/openpyxl); frontend↔backend integration seam only. UI/visual design is out of scope (covered separately by UI-SPEC).
**Confidence:** HIGH

## Summary

Phase 4's backend job is narrow and disciplined: **add zero new business logic**. Every capability the API exposes — parse, propose, validate, auto-apply, save profile, export — already exists as a tested Python function in `src/assayingest/`. The only new code is (1) a thin FastAPI transport layer that translates HTTP↔domain at the existing wire/domain boundary, (2) one new SQLite table (`field_set_templates`) behind the same `ProfileStore`-style repository seam, and (3) a small set of Pydantic *HTTP* wire models that are siblings of — not replacements for — the existing `mapping/schema.py` Claude-facing wire models.

The single most important structural decision is extracting `cli.py`'s private, underscore-prefixed orchestration (`_map_one`, `_resolve_proposal`, `_save_profile_if_ready`, `_export_if_ready`) into a new **public** service module. `.claude/CLAUDE.md`'s own convention ("Public API is everything not prefixed with `_`") makes it a boundary violation for a new `api/` package to import `cli._map_one` directly — and several of these functions currently `print()` as a side effect, which is fine for a CLI but wrong for a service a JSON endpoint calls. The service layer must return data, not print it; `cli.py` and the new FastAPI routes become two adapters that both call the same service functions and each do their own rendering (print vs JSON response).

The blocking Anthropic SDK call is the other load-bearing finding: `anthropic.Anthropic().messages.parse()` is synchronous. FastAPI's own recommended pattern for this exact situation is a **sync `def` endpoint** (not `async def`) — FastAPI already runs `def` path operations in its external threadpool automatically, so the event loop is never blocked and no `run_in_executor`/`run_in_threadpool` glue code is needed. This matches the existing codebase's synchronous style throughout (no `asyncio` anywhere in `src/`) and is the simplest correct answer for a 4-day hackathon.

**Primary recommendation:** New `src/assayingest/service.py` (public functions, no printing) wraps the Phase 1–3 pipeline; `src/assayingest/api/` (FastAPI, `def` endpoints, Pydantic HTTP wire models) and `cli.py` both call it. Add `fastapi`, `uvicorn[standard]`, `python-multipart` to `pyproject.toml` — no other new runtime dependencies. `fastapi.testclient.TestClient` + monkeypatching the *same* `propose_mapping`/`anthropic.Anthropic` seams the existing CLI tests already monkeypatch proves every endpoint offline, including the SC4 money-shot (zero Claude calls on second same-signature upload). FastAPI 0.138+'s new `app.frontend()` API is the simplest way to serve the built Vite bundle for the one-command demo.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Visual design (D-01)** — Clean clinical/lab aesthetic, light theme, restrained blue-green accent, monospaced/tabular numerics. Uncertain (yellow) fields render as an amber-highlighted cell with Claude's reason shown beside it (not hidden behind a hover). Professional and calm. A proper `artifact-design`-grade design pass. *(Frontend — covered by the UI-SPEC, not this document; the API's response shape must carry every datum the UI needs to render this.)*

**Yellow-field resolution interaction (D-02)** — Three complementary controls on a yellow field: (a) click a ranked-alternative chip, (b) an "accept" action for Claude's top proposal, (c) a manual full-column dropdown fallback. Resolving a field clears its yellow state locally; the server still re-validates on confirm.

**Field-set template storage (D-03)** — Field-set templates (UI-01) are stored server-side in the same SQLite as the learning profiles, behind the same repository-style seam. Not localStorage.

**Inline structural-hint UX (D-04)** — When the parser is unsure of a file's structure (UI-02/PARSE-06), the browser shows an inline form within the upload flow (not a separate wizard step, not a blocking modal) — the tool's question with a small preview of the first rows, answer, and re-submit in one flow. Under `--headers-only`, the preview shows no cell values.

### Claude's Discretion

- Exact FastAPI route shape and request/response schemas (wire↔domain boundary applies — reuse existing wire models where possible).
- How React is served (Vite dev server proxying FastAPI in dev; FastAPI serving the built static bundle for the demo — planner's call).
- React state/data-fetching approach, component library vs hand-rolled, and the design-token implementation (subject to D-01 and a UI-SPEC).
- Endpoint that lists/saves field-set templates and profiles.

### Deferred Ideas (OUT OF SCOPE)

- Multi-user / auth / accounts — v1 is local single-user; Postgres store deferred post-hackathon.
- Formal medical certification / regulatory path (CLIA/IEC 62304/ISO 13485/FDA SaMD), data-confidentiality legal/contractual angle, fully-local model option — deferred, must be raised at project close.
- Parser-hardening todos (`parser-encoding-detection.md` etc.) — explicitly not Phase 4 scope.

### Binding Principles (carry forward — still govern)

**P1 — Accuracy over convenience, fail-closed.** The confirm/export gate is enforced **server-side** (API-02): the server re-runs the validator + `is_ready` before persisting a profile, regardless of what the client sent. UI-05's disabled button is a UX mirror, never a replacement. A yellow field can never be cleared by the client alone.

**P2 — Confidentiality.** `--headers-only` MUST be reachable from the web upload as a per-upload toggle, on ALL paths that can reach Claude (mapping AND the inline structural-hint evidence). The learning loop is itself a privacy control. Profile + field-set stores stay local SQLite, never a network DB in v1.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-01 | Upload CSV/Excel with a chosen field set, receive proposed-and-validated mapping as JSON | §Endpoints "upload"; reuses `service.map_or_ask()` → `cli.proposal_to_dict()` shape |
| API-02 | Confirm endpoint; server re-checks the all-clear gate before persisting, never trusts client | §Server-Side Gate; `service.confirm()` re-runs `validate()` + `MappingProposal.is_ready` |
| API-03 | On upload, auto-apply a matching profile when (field set + signature) is already known | §Endpoints "upload"; reuses `_resolve_proposal`'s exact auto-apply branch verbatim via `service.map_or_ask()` |
| UI-01 | Define/edit target fields + constraints in browser; save/load field-set templates | §Field-Set Template Storage (D-03); `FieldSetTemplateStore` seam mirroring `ProfileStore` |
| UI-02 | Upload a file; give a structural hint inline instead of failing | §Endpoints "upload" + "resolve-structural-hint"; reuses `StructureQuestion`/`StructuralHint.to_dict()` verbatim |
| UI-03 | Side-by-side source columns / target fields view | §Endpoints "upload" response shape (`source_columns` + `field_mappings`) — UI concern, API supplies the data |
| UI-04 | Yellow fields highlighted with reason + ranked alternatives; resolve to clear | §Endpoints "upload" response shape (`alternatives`, `reasoning`, `validator_note`) — UI concern, API supplies the data |
| UI-05 | Confirm/export button disabled while any field yellow, mirroring server gate | §Server-Side Gate — UI mirrors what API-02 already enforces |
| UI-06 | Save confirmed mapping as profile; next same-signature upload shows zero yellow | §Testing the API "money shot"; §Endpoints "confirm" (LEARN-02 save) + "upload" (LEARN-03 auto-apply) |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| File parsing (CSV/Excel structural detection) | API / Backend | — | Already pure Python in `parsing/`; must never run in the browser (security, and the library only exists server-side) |
| Claude structured-output mapping | API / Backend | — | Anthropic API key lives server-side only; a browser-side call would leak the key |
| No-LLM validation (VAL-01/02/03) | API / Backend | — | Server-side gate (P1) — the browser's mirrored gate (UI-05) is UX only, never authoritative |
| Learning-loop profile store (SQLite) | API / Backend | — | Local file on the server host (P2); never queried directly by the browser |
| Field-set template store (SQLite) | API / Backend | — | Same store, same seam as profiles (D-03) |
| Field-set authoring form | Browser / Client | — | Pure UI state until submitted; POSTed as JSON on save/upload |
| Review screen (side-by-side, yellow highlighting) | Browser / Client | — | Renders the JSON the upload/resolve-hint endpoints return; no server logic here |
| Confirm/export button disabled state | Browser / Client | API / Backend (authoritative) | UI-05 mirrors, API-02 enforces — dual-tier by design (P1) |
| Static asset serving (built React bundle) | API / Backend (FastAPI `app.frontend()`) | CDN / Static (not used in v1) | Single-process demo simplicity; no CDN infra for a 4-day hackathon |
| Export file generation (CSV/xlsx/JSON/manifest) | API / Backend | — | `export/writers.py` writes to a server-side temp/output dir; browser downloads via a response |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.139.0 [VERIFIED: PyPI registry — `uv pip install --dry-run` resolved this version 2026-07-10; already specified as the project's stack in `.claude/CLAUDE.md`] | HTTP framework, Pydantic-based request/response validation, dependency injection | Already the project's declared stack; async-native but supports sync `def` endpoints natively for the blocking Anthropic SDK call |
| uvicorn[standard] | 0.51.0 [VERIFIED: PyPI registry] | ASGI server to run the FastAPI app | The de facto standard ASGI server; `[standard]` extra pulls `httptools`/`uvloop` for the dev+demo run command |
| python-multipart | 0.0.32 [VERIFIED: PyPI registry] | Required by FastAPI/Starlette to parse `multipart/form-data` (file upload + form fields) | FastAPI's own docs mandate installing this explicitly for any `UploadFile`/`Form` endpoint — it is not a transitive dependency of `fastapi` core |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| starlette | 1.3.1 [VERIFIED: PyPI registry — resolved transitively] | FastAPI's ASGI toolkit; provides `StaticFiles`, `TestClient` re-export, `run_in_threadpool` | Already a transitive dep of fastapi; no separate install needed |
| httpx | (transitive via `fastapi[standard]`/`starlette` testing extras) [ASSUMED — training knowledge, not yet verified against the resolved lockfile] | Required by `fastapi.testclient.TestClient` (built on `httpx` since Starlette 0.x) | Test-only; confirm it resolves during planning's dependency-install step — flag as a Wave 0 gap if absent |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FastAPI sync `def` endpoints | `async def` + `starlette.concurrency.run_in_threadpool(client.messages.parse, ...)` | Functionally equivalent (FastAPI runs sync `def` in the same threadpool under the hood) but adds boilerplate with zero benefit here — no other endpoint needs true async concurrency (single-user local demo) |
| `app.frontend()` (FastAPI 0.138+) | Hand-rolled `StaticFiles(directory="dist", html=True)` mount + manual catch-all route for SPA client-side routing | `app.frontend()` is the now-official replacement for exactly this hand-rolled pattern (fallback to `index.html` for unmatched GET/HEAD, correct 404 for missing assets) — prefer it since the resolved fastapi version (0.139.0) already includes it |
| Extracting a new `service.py` | Making `cli.py`'s `_map_one`/`_resolve_proposal` public (drop the underscore) and importing them directly into `api/` | Keeps orchestration in one already-large file mixing print-based CLI rendering with pure logic; a dedicated service module cleanly separates "what happens" from "how each adapter renders it" per Clean Architecture (CLAUDE.md) |

**Installation:**
```bash
uv add fastapi "uvicorn[standard]" python-multipart
```

**Version verification:** Confirmed via `uv pip install --dry-run fastapi uvicorn python-multipart` against the live PyPI index (2026-07-10): resolves `fastapi==0.139.0`, `uvicorn==0.51.0`, `python-multipart==0.0.32`, `starlette==1.3.1`, plus `click==8.4.2` and `annotated-doc==0.0.4` as transitive deps. All four names were already specified by this project's own `.claude/CLAUDE.md` stack declaration prior to this research session (not independently discovered via web search), and their registry existence + official GitHub org URLs (`github.com/fastapi/fastapi`, `github.com/Kludex/uvicorn`, `github.com/Kludex/python-multipart`) were cross-checked.

## Package Legitimacy Audit

| Package | Registry | Age (latest release) | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----------------------|-----------|--------------|---------|-------------|
| fastapi | PyPI | Latest release 2026-07-01 (9 days old at research time); project itself is 7+ years old | Not reported by seam (`unknown-downloads`) — independently known to be one of the most-downloaded Python web frameworks | github.com/fastapi/fastapi (official, 80k+ stars) | SUS (seam flags: `too-new`, `unknown-downloads`) | **Approved** — false positive. The seam's heuristics fire on *release cadence*, not package age; FastAPI ships frequent point releases (this is the same project that shipped `app.frontend()` on 2026-06-20). Verified authoritative via official docs fetch (fastapi.tiangolo.com) in this session. |
| uvicorn | PyPI | Latest release 2026-07-08 (2 days old) | Not reported (`unknown-downloads`) | github.com/Kludex/uvicorn (maintainer's fork/canonical repo for the `encode`-org project) | SUS (seam flags: `too-new`, `unknown-downloads`) | **Approved** — same false-positive pattern; uvicorn is the standard ASGI server referenced by FastAPI's own official docs. |
| python-multipart | PyPI | Latest release 2026-06-04 | Not reported (`unknown-downloads`) | github.com/Kludex/python-multipart | SUS (seam flag: `unknown-downloads`) | **Approved** — this is the exact package FastAPI's own official docs name as the required dependency for `UploadFile`/`Form` support; no postinstall script. |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** fastapi, uvicorn, python-multipart — all three flagged by the automated seam on `too-new`/`unknown-downloads` heuristics, which are known false-positive triggers for extremely active, high-velocity mature projects (frequent releases look "new" to an age heuristic; the seam has no PyPI download-stats source configured in this environment). All three were cross-verified via the official FastAPI documentation site and GitHub org URLs in this research session and are approved. **The planner should still add one lightweight `checkpoint:human-verify` before the first `uv add` in Wave 0**, purely as defense-in-depth given the automated verdict, even though this research found no legitimacy concern.

## Architecture Patterns

### System Architecture Diagram

```
Browser (React)
  │
  │  1. POST /api/upload  (multipart: file + field_set_id|inline field_set + headers_only flag)
  ▼
FastAPI route (api/routes/upload.py)          ── HTTP wire layer ──
  │  - saves UploadFile to a NamedTemporaryFile (P2: deleted in `finally`)
  │  - decodes field_set JSON → domain FieldSet (or loads by template id from store)
  ▼
service.resolve_or_map(path, field_set, hint=None, headers_only=…)   ── new public service module ──
  │
  ├─▶ parsing.table.parse()  ──── StructureQuestion? ──▶ 2a. return {"kind": "structural_question", ...}
  │                                                          (UI-02: browser shows inline hint form)
  │
  └─▶ table resolved
        │
        ├─▶ learning.sqlite_store.find(field_set.signature, column_signature)
        │      │ HIT (API-03)                          │ MISS
        │      ▼                                        ▼
        │   learning.reconstruct.reconstruct_proposal   mapping.mapper.propose_mapping
        │   (no Anthropic client constructed)           (Anthropic API call — blocking,
        │                                                 runs in FastAPI's threadpool)
        │      │                                        │
        │      └────────────────┬───────────────────────┘
        │                       ▼
        │              validation.validator.validate()   (VAL-01/02/03 — runs on BOTH branches)
        │                       ▼
        │              2b. return {"kind": "mapping", ...cli.proposal_to_dict()-shaped JSON...}
        ▼
Browser renders side-by-side review (UI-03), yellow highlighting (UI-04)
  │
  │  3. (optional) POST /api/structural-hint/resolve  (hint + original upload token) → back to step 1's
  │     parse() call, this time with `hint` populated → same response shape as step 2
  │
  │  4. Human resolves yellow fields client-side (D-02: chip / accept / dropdown) — LOCAL ONLY
  │
  │  5. POST /api/confirm  (the full edited MappingProposal JSON + field_set + save_profile flag)
  ▼
FastAPI route (api/routes/confirm.py)
  │  - rebuild domain MappingProposal from the wire body (never trust client's `is_ready`)
  ▼
service.confirm(table_headers, edited_proposal, field_set, save_profile, export=True)  ── SERVER-SIDE GATE (P1) ──
  │  - RE-RUNS validation.validator.validate() against the client's edited mapping
  │  - checks proposal.is_ready — 422 if any field still yellow, REGARDLESS of client claim
  │  - if ready: learning.sqlite_store.save(LearnedProfile) (LEARN-02) + export.writers (EXPORT-02/03/04)
  ▼
6. return {"ready": true, "manifest": {...}, "export_urls": {...}}
  │
  │  7. GET /api/export/{run_id}/{csv|xlsx|json|manifest}
  ▼
Browser downloads file (or all 4 as a zip — planner's call)
```

### Recommended Project Structure

```
src/assayingest/
├── service.py              # NEW — public orchestration: resolve_or_map(), confirm() — no printing
├── cli.py                  # UNCHANGED shape, but _map_one/_resolve_proposal delegate to service.py
├── api/                    # NEW — the FastAPI transport adapter
│   ├── __init__.py
│   ├── app.py               # FastAPI() instance, CORS, app.frontend() mount, router includes
│   ├── deps.py               # get_profile_store(), get_field_set_store(), get_anthropic_client() — DI seams for tests
│   ├── wire.py                # Pydantic HTTP request/response models (siblings of mapping/schema.py's Claude-facing wire models — NOT the same classes)
│   └── routes/
│       ├── upload.py           # POST /api/upload
│       ├── structural_hint.py  # POST /api/structural-hint/resolve
│       ├── confirm.py          # POST /api/confirm  (the server-side gate)
│       ├── field_sets.py       # GET/POST /api/field-sets  (UI-01, D-03)
│       └── export.py           # GET /api/export/{run_id}/{fmt}
├── learning/
│   ├── field_set_store.py   # NEW — FieldSetTemplateStore, mirrors ProfileStore/SqliteProfileStore exactly (D-03)
│   └── ... (existing, unchanged)
└── ... (existing domain/, parsing/, mapping/, validation/, export/, fields/, unchanged)

frontend/                    # NEW — Vite + React app (UI-SPEC governs internals)
├── src/
├── index.html
├── vite.config.ts           # dev proxy: /api → http://localhost:8000
└── package.json
```

### Pattern 1: Extract a public service layer, don't import cli's private functions

**What:** `cli.py`'s `_resolve_proposal`, `_map_one`, `_save_profile_if_ready`, `_export_if_ready` currently both *decide* (call the library) and *render* (print to stdout). Split these: move the decision logic to `service.py` as public functions returning plain data (domain objects / dicts), and have `cli.py` call `service.py` then print, while `api/routes/*.py` call `service.py` then JSON-serialize.

**When to use:** Any time a second adapter (API) needs logic currently living only in a CLI-only module — the underscore-prefix convention (`.claude/CLAUDE.md`: "Public API is everything not prefixed with `_`") makes cross-module import of `_`-prefixed names an explicit convention violation, not just a style nit.

**Example (illustrative — planner designs the exact signatures):**
```python
# src/assayingest/service.py
"""Orchestration used by both the CLI and the API — decides, never renders."""

from __future__ import annotations
from dataclasses import dataclass

from .domain.models import MappingProposal
from .fields.models import FieldSet
from .learning.reconstruct import reconstruct_proposal
from .learning.signature import column_signature
from .learning.store import ProfileStore
from .mapping.mapper import propose_mapping
from .parsing.hint import StructuralHint, StructureQuestion
from .parsing.table import RawTable, parse
from .validation.validator import validate


@dataclass(frozen=True)
class MapResult:
    """What the CLI prints and the API returns as JSON — identical data,
    two renderers."""
    proposal: MappingProposal
    table: RawTable
    provenance: str  # "auto-applied-from-profile" | "fresh-claude"


def resolve_or_map(
    path: str,
    field_set: FieldSet,
    *,
    store: ProfileStore | None,
    hint: StructuralHint | None = None,
    sheet: str | None = None,
    strictness: str = "strict",
    headers_only: bool = False,
    client=None,  # Anthropic client, injectable for tests (mirrors mapper.propose_mapping's own seam)
) -> MapResult | StructureQuestion:
    """The single seam cli.run() and POST /api/upload both call."""
    outcome = parse(path, sheet=sheet, hint=hint)
    if isinstance(outcome, StructureQuestion):
        return outcome
    table = outcome

    if store is not None:
        profile = store.find(field_set.signature, column_signature(table.headers))
        if profile is not None:
            proposal = validate(
                table, reconstruct_proposal(profile, table.headers), field_set,
                strictness=strictness,
            )
            return MapResult(proposal, table, "auto-applied-from-profile")

    proposal = propose_mapping(table, field_set, client, headers_only=headers_only)
    proposal = validate(table, proposal, field_set, strictness=strictness)
    return MapResult(proposal, table, "fresh-claude")
```

### Pattern 2: Sync `def` endpoints for the blocking Anthropic call

**What:** Declare every route that can reach `propose_mapping()` (and therefore the Anthropic SDK) as a plain `def`, not `async def`.

**When to use:** Any endpoint on the "fresh-Claude" branch. FastAPI runs `def` path operations in Starlette's external threadpool automatically — the event loop is never blocked, and no `run_in_threadpool`/`run_in_executor` call is needed in application code. [CITED: fastapi.tiangolo.com/async/, fastapi.tiangolo.com — "When you declare a path operation function with normal `def` instead of `async def`, it is run in an external threadpool that is then awaited"]

**Example:**
```python
# src/assayingest/api/routes/upload.py
from fastapi import APIRouter, Depends, UploadFile, Form
import tempfile, os

router = APIRouter()

@router.post("/api/upload")
def upload(  # <-- plain def, not async def: propose_mapping() blocks on the network call
    file: UploadFile,
    field_set_json: str = Form(...),
    headers_only: bool = Form(False),
    store=Depends(get_profile_store),
):
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name
    try:
        result = service.resolve_or_map(tmp_path, field_set, store=store, headers_only=headers_only)
        return _render_result(result)
    finally:
        os.unlink(tmp_path)  # P2: never leave uploaded content on disk longer than needed
```
An `async def` alternative (only needed if the endpoint later mixes in genuinely async I/O, e.g. an async DB driver) would instead be:
```python
from starlette.concurrency import run_in_threadpool

@router.post("/api/upload")
async def upload(...):
    result = await run_in_threadpool(service.resolve_or_map, tmp_path, field_set, store=store)
```
[CITED: sentry.io/answers/fastapi-difference-between-run-in-executor-and-run-in-threadpool — "run_in_threadpool is integrated with FastAPI's design and is the recommended approach for most use cases" when you must stay inside `async def`]. **Recommendation: use the plain-`def` form (Pattern 2's first example) — it is simpler and matches every other module's synchronous style in this codebase.**

### Pattern 3: Serve the built frontend with `app.frontend()` (FastAPI ≥0.138)

**What:** FastAPI 0.138.0 (2026-06-20) added `app.frontend(path, directory=...)` as the official, built-in way to serve a pre-built SPA bundle (React/Vite, Vue, etc.) — replacing the community hand-rolled `StaticFiles(html=True)` + manual catch-all route pattern. [CITED: fastapi.tiangolo.com/tutorial/frontend/, fastapi.tiangolo.com/release-notes/]

**When to use:** For the demo's "one-command-runnable" requirement — `uvicorn assayingest.api.app:app` alone can serve both the API and the built React bundle from one process, one port, no separate web server.

**Example:**
```python
# src/assayingest/api/app.py
from fastapi import FastAPI
from .routes import upload, structural_hint, confirm, field_sets, export as export_route

app = FastAPI(title="AssayIngest")
app.include_router(upload.router)
app.include_router(structural_hint.router)
app.include_router(confirm.router)
app.include_router(field_sets.router)
app.include_router(export_route.router)

# API routes always win (checked first); frontend is the fallback for everything else.
# fallback="index.html" (the default "auto" behavior already does this if index.html
# exists) gives correct client-side-routing support for React Router.
app.frontend("/", directory="frontend/dist", check_dir=False)  # check_dir=False: dist/
# may not exist yet in a dev checkout before `npm run build` has been run once
```
**Caveat verified:** API routes registered via `app.include_router(...)` are matched *before* `app.frontend()`'s catch-all, by design [CITED: fastapi.tiangolo.com/tutorial/frontend/ — "API Routes Always Win: FastAPI checks path operations first"] — so route ordering in `app.py` (routers first, `app.frontend()` last) is not just style, it is required for `/api/*` paths to ever be reached.

**Dev-mode alternative (Claude's Discretion per CONTEXT.md):** Run Vite's own dev server (`npm run dev`, default port 5173) with `vite.config.ts`'s `server.proxy` forwarding `/api` to `http://localhost:8000`, and run `uvicorn` separately for the backend. This gives React Fast Refresh during frontend development; switch to `app.frontend()` serving the built `dist/` for the recorded demo/submission. Two commands in dev, one command (`uvicorn`) for the demo, once `npm run build` has produced `frontend/dist/`.

### Pattern 4: The wire↔domain boundary at the HTTP edge (reuse, don't duplicate)

**What:** The upload/confirm response JSON should be *byte-shape-identical* to what the CLI already prints via `cli.proposal_to_dict()` — this function is already public (no leading underscore) and already does exactly the wire-shape work an API response needs (`ready`, `source_columns`, `field_mappings[]` with `target_field`/`source_column`/`confidence`/`reasoning`/`needs_confirmation`/`inferred_value`/`alternatives[]`/`validator_note`).

**When to use:** Every endpoint that returns a mapping. Do not hand-write a parallel Pydantic response model that re-derives the same fields — either (a) return `cli.proposal_to_dict(proposal, provenance)`'s dict directly (FastAPI serializes a plain `dict` return value fine, though it loses OpenAPI schema precision), or (b) define a Pydantic `UploadResponse` model in `api/wire.py` whose fields are named identically and populated from the same dict, so `mapping/schema.py`'s existing dict shape and the new HTTP response shape never drift apart.

**Example:**
```python
# src/assayingest/api/wire.py
from pydantic import BaseModel

class FieldMappingOut(BaseModel):
    target_field: str
    source_column: str | None
    confidence: float
    reasoning: str
    needs_confirmation: bool
    inferred_value: str | None = None
    alternatives: list[dict]           # [{"source_column": str, "confidence": float}, ...]
    validator_note: str | None = None

class MappingResponse(BaseModel):
    kind: str = "mapping"              # discriminator vs "structural_question" (Pattern 5)
    ready: bool
    source_columns: list[str]
    field_mappings: list[FieldMappingOut]
    provenance: str
```

### Pattern 5: One discriminated response contract for upload (mapping OR structural question)

**What:** UI-02 requires the browser to distinguish "here is your mapping" from "I need a structural hint first" from the *same* upload endpoint (per the research question's framing — "How to return the ambiguous-structure case vs the mapped case in one contract"). Use a `kind` discriminator field.

**When to use:** `POST /api/upload` and `POST /api/structural-hint/resolve` (both can hit `parse()`'s `StructureQuestion` branch, since a re-submitted hint can itself still be ambiguous — e.g. wrong header row guessed).

**Example:**
```python
# response body, either:
{"kind": "structural_question", "unsure_about": "...", "reason": "...", "confidence": 0.4,
 "proposal": {...StructuralHint.to_dict()...}, "alternatives": [...], "evidence_rows": [[...]],
 "answerable_by_hint": true, "upload_token": "a3f9..."}
# or:
{"kind": "mapping", "ready": false, "source_columns": [...], "field_mappings": [...], "provenance": "fresh-claude"}
```
`StructureQuestion.to_dict()` already exists and is exactly this shape minus `kind` and `upload_token` — reuse it, add the two extra keys at the route layer. `upload_token` (new, API-only concept) is how `POST /api/structural-hint/resolve` finds the *same* uploaded file again without re-uploading bytes (see File Upload Handling below).

### Anti-Patterns to Avoid

- **Re-implementing the mapper/validator/signature/gate logic inside a route handler:** every one of these already exists and is tested; a route handler's only job is HTTP↔domain translation. CONTEXT.md's phase boundary states this explicitly ("never reimplement").
- **Trusting `is_ready` sent by the client on `/api/confirm`:** the request body may carry an edited `MappingProposal`, but the server must rebuild it into domain objects and re-run `validation.validator.validate()` + read `MappingProposal.is_ready` itself — see Server-Side Gate below.
- **`async def` route + calling `anthropic.Anthropic().messages.parse()` directly with no threadpool:** this blocks the entire event loop for the whole duration of the Claude call (can be several seconds with `thinking={"type": "adaptive"}` + `output_config={"effort": "high"}`), freezing every other concurrent request. Either use plain `def` (recommended) or explicit `run_in_threadpool`.
- **Persisting uploaded file bytes to a permanent path:** P2 requires values to leave disk as soon as the run is done — use `tempfile.NamedTemporaryFile(delete=False)` + an explicit `finally: os.unlink(...)`, never `UPLOAD_DIR/`.
- **A second, hand-rolled column-signature or FieldSet-signature implementation inside the API layer:** reuse `learning.signature.column_signature()` and `FieldSet.signature` — these are the exact functions LEARN-01/API-03's correctness depends on; a byte-different reimplementation silently breaks auto-apply.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multipart file upload parsing | A custom `Content-Type: multipart/form-data` parser | `fastapi.UploadFile` + `python-multipart` (already the dependency FastAPI's own docs mandate) | Streaming, spooled-to-disk-above-a-size-threshold behavior is already correct and battle-tested |
| Column signature / field-set signature | A second hash function inside `api/` for HTTP-layer identity checks | `learning.signature.column_signature()`, `fields.models.FieldSet.signature` | These are the exact save-time/lookup-time functions the whole learning loop's correctness (LEARN-01, D-02) depends on being bit-for-bit identical everywhere they're called |
| Server-side re-validation of a submitted mapping | A parallel, simplified "does this look ready" check in the confirm route | `validation.validator.validate()` + `MappingProposal.is_ready` | This is the exact P1 fail-closed gate; any simplification is a security/safety regression by definition |
| SPA static-file serving with client-side-route fallback | `StaticFiles(html=True)` + a manual `@app.get("/{path:path}")` catch-all that reads `index.html` itself | `app.frontend(path, directory="dist")` (FastAPI ≥0.138) | Now the maintained, official implementation of exactly this pattern — handles asset 404s vs navigation-fallback correctly out of the box |
| CORS handling | Manual `Access-Control-Allow-*` header injection in middleware | `fastapi.middleware.cors.CORSMiddleware` | Standard Starlette middleware; correct preflight (`OPTIONS`) handling is easy to get subtly wrong by hand |

**Key insight:** Phase 4's backend has almost no genuinely new domain logic — its entire job is translation and re-verification at a boundary. Every "don't hand-roll" item above is a case where writing new code would either duplicate an existing correctness-critical function (signature, validator) or reinvent a solved transport-layer problem (multipart, CORS, SPA fallback) that a well-maintained library already gets right.

## Field-Set Template Storage (D-03)

Mirror `learning/store.py` + `learning/sqlite_store.py` exactly — same repository-seam pattern, same file (or a sibling table in the same `.assayingest/profiles.db`), same "the domain never imports `sqlite3` directly" discipline.

**Schema sketch:**
```sql
CREATE TABLE IF NOT EXISTS field_set_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    field_set_json TEXT NOT NULL,      -- FieldSet.to_dict(), json.dumps
    signature TEXT NOT NULL,           -- FieldSet.signature, denormalised for fast lookup/dedup
    created_at TEXT NOT NULL,
    UNIQUE(name)                       -- a saved template name is a stable handle the UI lists by
);
CREATE INDEX IF NOT EXISTS idx_field_set_templates_signature ON field_set_templates(signature);
```

**Seam sketch:**
```python
# src/assayingest/learning/field_set_store.py
from abc import ABC, abstractmethod
from ..fields.models import FieldSet

class FieldSetTemplateStore(ABC):
    @abstractmethod
    def save(self, name: str, field_set: FieldSet) -> str: """Returns the template id."""
    @abstractmethod
    def get(self, template_id: str) -> FieldSet | None: ...
    @abstractmethod
    def list(self) -> list[tuple[str, str]]: """[(id, name), ...] for the UI's template picker."""

# src/assayingest/learning/sqlite_field_set_store.py
class SqliteFieldSetStore(FieldSetTemplateStore):
    """Same file, same connection-per-call pattern as SqliteProfileStore."""
    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH) -> None: ...
```
Whether this lives in the *same* `.db` file as `profiles` (two `CREATE TABLE IF NOT EXISTS` statements executed by one `_SCHEMA` script) or a second `.db` file is the planner's call — D-03 only requires "the same SQLite [store]", which the codebase's existing `_DEFAULT_DB_PATH = ".assayingest/profiles.db"` already suggests as one shared file. Reusing one file avoids a second `.gitignore`d path and keeps "local, single SQLite file" easy to narrate to judges (P2 framing).

## Server-Side Gate (API-02, P1)

**Exactly where the gate runs:** in `service.confirm()` (not in the route handler, and not in the domain — the route handler's job is only to deserialize the request body into a `MappingProposal`).

**What the server must recompute vs trust:**

| Field | Trust from client? | Why |
|---|---|---|
| `field_set` (the target field declarations) | Trust — but re-derive `field_set.signature` server-side, never accept a client-sent signature string | The signature is a pure function of the fields; accepting a client-sent one would let a tampered request claim a signature that doesn't match its own fields |
| `table.headers` / original source columns | Trust the value the *original upload's* `parse()` call produced (kept server-side, keyed by `upload_token`) — do NOT re-derive from a client-editable field | The client should never be able to claim a different source file's headers than the one actually uploaded |
| `field_mappings[].source_column` / `.alternatives` (the human's edits — which column resolves which field) | Trust as the human's editorial choice — this is the entire point of the review UI (D-02) | Column *choice* is a legitimate human decision the server cannot second-guess |
| `field_mappings[].needs_confirmation` | **Never trust** — always recomputed | This is exactly the boolean P1 exists to protect; a tampered/buggy client could send `false` for every field |
| `field_mappings[].validator_note` | **Never trust** — always recomputed | Same reasoning; this is the validator's own output, not client-editable data |
| `proposal.is_ready` (or any top-level "ready" flag) | **Never trust** — always recomputed as a `@property` on the freshly-rebuilt domain object | The entire API-02 requirement is this exact re-check |

**Recomputation sequence** (mirrors `cli._map_one`'s existing order exactly):
```python
def confirm(
    upload_token: str, edited_mappings: list[FieldMapping], field_set: FieldSet,
    *, save_profile: bool, strictness: str = "strict", store: ProfileStore,
) -> ConfirmResult:
    table = _lookup_table_by_token(upload_token)   # the ORIGINAL parsed table, never client-supplied
    proposal = MappingProposal(source_columns=table.headers, field_mappings=edited_mappings)
    proposal = validate(table, proposal, field_set, strictness=strictness)  # RE-RUN, ignore any client verdict
    if not proposal.is_ready:
        raise NotReadyError(proposal.unclear_fields)  # → 422, mirrors D-06's CLI refusal
    if save_profile:
        _save_profile(store, field_set, table, proposal, hint)  # reuses cli._save_profile_if_ready's logic
    tidy = canonical.assemble(table, proposal, field_set)
    manifest = build_manifest(field_set, table.headers, proposal, provenance=..., strictness=strictness)
    return ConfirmResult(proposal, tidy, manifest)
```
A `NotReadyError` maps to HTTP `422 Unprocessable Entity` (or `409 Conflict` — planner's call; `422` matches FastAPI's own validation-error convention and signals "the request was well-formed but the domain rule rejected it").

**Where `table` comes from without re-parsing:** the upload endpoint's `MapResult`/`StructureQuestion` response needs an opaque `upload_token` the browser round-trips on `/api/confirm` (and on `/api/structural-hint/resolve`), so the server can look up the *exact* originally-parsed `RawTable` rather than trusting client-sent headers or re-reading a file the client no longer has access to. See File Upload Handling below for how this token maps to server-side state.

## File Upload Handling

**UploadFile → temp path → `parse_file()`:** `parsing.table.parse()`/`parse_file()` takes a filesystem path, not bytes — so the route must materialize the `UploadFile`'s content to a real path before calling into the existing library. [CITED: fastapi.tiangolo.com/tutorial/request-files/ — `UploadFile` wraps a `SpooledTemporaryFile`]

```python
import tempfile, os
from fastapi import UploadFile

def _save_upload_to_temp(file: UploadFile) -> str:
    suffix = os.path.splitext(file.filename or "")[1] or ".csv"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())   # sync def endpoint -> sync .read() is fine, no `await`
        return tmp.name
```

**Cleanup / P2 (values off disk longer than needed):**
- On the **happy path** (mapping resolved, response sent): delete the temp file immediately after `parse()`/`propose_mapping()` finish — the parsed `RawTable` (headers + rows, in memory) is all that's needed for the rest of the flow, not the original file bytes.
- On the **structural-question path** (UI-02): the file must survive until `/api/structural-hint/resolve` re-parses it with the human's hint. Keep the temp path alive, keyed by `upload_token`, in a short-lived server-side dict/cache (or re-derive: store the *original bytes* alongside the token, since a single-user local demo has no concurrency pressure). **Set a TTL / max-count eviction** so a demo left running overnight doesn't accumulate temp files — this is a good `checkpoint:human-verify` / explicit cleanup task for the plan, since P2 explicitly calls out minimizing on-disk retention.
- **Size limit:** FastAPI/Starlette do not enforce a default upload size cap. For a hackathon demo add an explicit check (e.g. `Content-Length` header inspection or reading in bounded chunks and aborting past a threshold like 20 MB) — small but P1-adjacent: an unbounded upload is a resource-exhaustion vector even in a local single-user demo. [ASSUMED — reasonable default for a synthetic-lab-file demo; no specific limit is mandated by REQUIREMENTS.md, flag for user confirmation of the exact threshold]

**In-memory alternative:** `parse()`'s dependency on `pandas.read_csv`/`openpyxl.load_workbook`, both of which *can* accept a file-like/`BytesIO` object instead of a path, means an in-memory-only path is technically possible without ever touching disk — but `parsing/table.py`'s current public signature (`parse_file(path: str | Path, ...)`, `parse(path: str | Path, ...)`) takes only a path, and generalizing it to accept `BytesIO` is a **non-trivial signature change to Phase 1 code** the CONTEXT.md phase boundary says not to touch ("never reimplement... parsing"). **Recommendation: keep the temp-file approach** (simplest, reuses `parse()` verbatim); note the in-memory alternative as a v2 optimization if disk I/O ever becomes a real demo concern (it won't, for a hackathon).

## Endpoints

| Endpoint | Method | Request | Response | Requirements |
|---|---|---|---|---|
| `/api/upload` | POST | `multipart/form-data`: `file` (UploadFile), `field_set` (JSON string, Form) or `field_set_template_id` (Form), `headers_only` (bool, Form), `sheet` (optional str, Form) | `{"kind": "structural_question", ..., "upload_token": str}` OR `{"kind": "mapping", "upload_token": str, ...proposal fields...}` | API-01, API-03, UI-02 |
| `/api/structural-hint/resolve` | POST | JSON: `{"upload_token": str, "hint": {...StructuralHint fields...}}` | Same discriminated shape as `/api/upload` | UI-02 |
| `/api/confirm` | POST | JSON: `{"upload_token": str, "field_set": {...}, "field_mappings": [...edited...], "save_profile": bool, "export": bool}` | `{"ready": true, "manifest": {...}, "export": {"csv_url": ..., "xlsx_url": ..., "json_url": ..., "manifest_url": ...}}` on success; `422` with `{"unclear_fields": [...]}` on gate failure | API-02, UI-06 (learn), EXPORT-02/03/04 |
| `/api/field-sets` | GET | — | `[{"id": ..., "name": ..., "field_set": {...}}, ...]` | UI-01 |
| `/api/field-sets` | POST | JSON: `{"name": str, "field_set": {...FieldSet.to_dict() shape...}}` | `{"id": ...}` | UI-01, D-03 |
| `/api/field-sets/{id}` | GET | — | `{...FieldSet.to_dict()...}` | UI-01 |
| `/api/export/{run_id}/{fmt}` | GET | `fmt` in `{csv, xlsx, json, manifest}` | `FileResponse` (appropriate `Content-Type`/`Content-Disposition`) | EXPORT-02/03/04 |

**`upload_token`/`run_id` lifecycle:** a UUID minted on `/api/upload`, mapping to server-side in-memory state `{table, field_set, headers_only, tmp_path}`. A single-process, single-user local demo makes an in-memory dict (module-level, or a `Depends`-injected singleton) sufficient — no Redis/session store needed. State is cleared after `/api/confirm` completes (export files themselves persist on disk under `output_dir` until the process restarts, or a demo-cleanup step, for the `/api/export/...` download to work).

**`cli.run()` reuse assessment:** `resolve_or_ask`/`resolve_tables` (public, no side effects) are directly reusable as-is. `_resolve_proposal`, `_map_one`, `_save_profile_if_ready`, `_export_if_ready` are NOT directly reusable (private, print-coupled) — extract their decision logic into `service.py` per Pattern 1 above; `cli.py`'s own versions become thin wrappers that call `service.py` then `print()`.

## Common Pitfalls

### Pitfall 1: Trusting the client's `needs_confirmation`/`is_ready` on confirm
**What goes wrong:** A route handler that just checks `if request_body.ready: save_profile(...)` silently reintroduces exactly the vulnerability P1 exists to prevent — a buggy or tampered browser client could persist a stale mapping with real yellow fields.
**Why it happens:** It's the "obvious" fast implementation — the client already computed `is_ready` for the disabled-button UX (UI-05), so it's tempting to just read that flag back.
**How to avoid:** `service.confirm()` must rebuild a fresh `MappingProposal` from only the parts of the request that are legitimately client-editable (column choices), then call `validate()` and read `.is_ready` itself — see Server-Side Gate above.
**Warning signs:** Any route handler code path where `is_ready`/`needs_confirmation`/`validator_note` flow from `request_body.X` straight into a `save()` call without an intervening `validate()` call.

### Pitfall 2: Blocking the event loop with `async def` + a raw Anthropic call
**What goes wrong:** `async def upload(...): result = anthropic_client.messages.parse(...)` compiles and runs, but the synchronous SDK call blocks the single event-loop thread for its full duration — every other concurrent request (even a totally unrelated `GET /api/field-sets`) queues behind it.
**Why it happens:** FastAPI's tutorials default to `async def` everywhere, and it's easy to not notice `anthropic.Anthropic().messages.parse()` is sync, not `AsyncAnthropic`.
**How to avoid:** Plain `def` endpoints for any route that can reach `propose_mapping()` (Pattern 2) — or explicit `run_in_threadpool` if the route must stay `async def` for other reasons.
**Warning signs:** A demo that "hangs" or becomes unresponsive to unrelated requests while a Claude call is in flight.

### Pitfall 3: Re-deriving `column_signature`/`FieldSet.signature` at the HTTP layer
**What goes wrong:** A well-meaning route handler recomputes "a" signature for logging/debugging using `hashlib.sha256(str(headers))` or similar, and that value accidentally leaks into a code path that should have used the canonical function — silently breaking LEARN-01/03/04's exact-match guarantee.
**Why it happens:** The signature functions live in `learning/`, one import hop away from an API route developer who might not immediately think to reuse them.
**How to avoid:** Always call `learning.signature.column_signature(headers)` and `field_set.signature` — never write a parallel hash anywhere in `api/`.
**Warning signs:** Any `hashlib`/`hash(...)` call inside `src/assayingest/api/`.

### Pitfall 4: Leaving uploaded file bytes on disk past the request lifecycle
**What goes wrong:** A temp file written in `/api/upload` is never cleaned up on the happy path (only in an exception handler), or the structural-hint-pending state accumulates unboundedly across a long demo session — violating P2's "values off disk as soon as possible" framing and, separately, filling `/tmp` during a long-running demo/judging session.
**Why it happens:** `tempfile.NamedTemporaryFile(delete=False)` requires an *explicit* `os.unlink()` — the "easy" `delete=True` mode auto-deletes on `.close()`, which is too early here (the file is still needed by `parse()`/`propose_mapping()` after the `with` block that wrote it).
**How to avoid:** `try/finally` around every code path that creates a temp file for a resolved mapping; a small in-memory registry with an eviction policy (LRU or TTL) for the structural-question-pending case.
**Warning signs:** `.assayingest/`-adjacent or `/tmp`-adjacent files accumulating across repeated manual test uploads.

### Pitfall 5: `app.frontend()`/router registration ordering
**What goes wrong:** If `app.frontend("/", directory="dist")` is called *before* `app.include_router(upload.router)`, and the frontend's `fallback="index.html"` behavior is misconfigured, `/api/upload` requests could theoretically be shadowed by the frontend catch-all.
**Why it happens:** Route-registration order intuitions from other frameworks (some match "most specific first" regardless of registration order) don't universally apply.
**How to avoid:** FastAPI's own docs confirm explicit path operations (`@router.post(...)`) are always checked before `app.frontend()`'s fallback regardless of registration order [CITED: fastapi.tiangolo.com/tutorial/frontend/] — so this is actually *not* a real hazard given the confirmed behavior, but the planner should still write one API-route-not-shadowed integration test as cheap insurance, since this is exactly the kind of assumption worth a Nyquist-style regression check.

## Code Examples

### CORS for the Vite dev server (dev-mode only, not needed once `app.frontend()` serves the built bundle from the same origin)
```python
# Source: FastAPI's own CORS tutorial pattern (training knowledge, standard Starlette middleware — [ASSUMED, verify exact import path against installed fastapi==0.139.0 if it changed]
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite's default dev port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
Once `app.frontend()` serves the built bundle from the same FastAPI process/port (the demo-recording configuration), CORS is not needed at all — same-origin requests. Gate the `CORSMiddleware` registration behind an env var / debug flag so it is a dev-only convenience, never shipped active in the demo build (smaller attack surface, and one less thing to explain to judges).

### Vite dev-server proxy config
```typescript
// frontend/vite.config.ts
// Source: community-standard Vite proxy pattern [ASSUMED — training knowledge, standard Vite docs pattern, not independently fetched this session]
export default defineConfig({
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Hand-rolled `StaticFiles(html=True)` + manual `@app.get("/{path:path}")` SPA catch-all | `app.frontend(path, directory=..., fallback="index.html")` | FastAPI 0.138.0, 2026-06-20 [CITED: fastapi.tiangolo.com/release-notes/] | Fewer lines, correct-by-default asset-404-vs-navigation-fallback distinction; directly relevant to this phase's "single-command demo" goal |

**Deprecated/outdated:** Nothing else in this research area is deprecated — FastAPI's sync-`def`-in-threadpool behavior and `TestClient`/`dependency_overrides` testing pattern are long-standing, stable APIs, not recent changes.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `httpx` resolves as a transitive dependency enabling `fastapi.testclient.TestClient` without an explicit `pip install httpx` | Standard Stack, Supporting | Low — if it doesn't resolve, `uv add httpx` as a dev dependency is a one-line fix the planner's Wave 0 dependency-install task should verify empirically rather than assume |
| A2 | A reasonable upload size limit for the demo is roughly 20 MB | File Upload Handling | Low — no requirement specifies a number; if the planner picks a different threshold nothing else depends on this exact figure, but SOME explicit limit should exist rather than none |
| A3 | CORS middleware code example's exact import path (`fastapi.middleware.cors.CORSMiddleware`) is unchanged in fastapi 0.139.0 | Code Examples | Low — this has been stable across many FastAPI major/minor versions; worth a 10-second `python -c "from fastapi.middleware.cors import CORSMiddleware"` sanity check in Wave 0 rather than a research-time web fetch |
| A4 | Vite's `server.proxy` config shape (`{"/api": "http://localhost:8000"}`) is unchanged from the version of Vite the frontend phase will install | Code Examples | Low — this is frontend tooling outside this backend research's authoritative scope; the UI-SPEC/frontend planner should confirm against whatever Vite version is actually installed |

**If this table is empty:** N/A — see rows above; all are low-risk, narrow-scope assumptions with cheap Wave-0 verification paths, not decisions that need upfront user confirmation.

## Open Questions

1. **Where does `upload_token` state live — module-level dict, or a lightweight injected singleton?**
   - What we know: a single-user local demo has no concurrency pressure requiring a real cache/session store.
   - What's unclear: whether the planner wants this as a trivial `dict` on a FastAPI `Depends`-provided singleton (simplest, resets on server restart — arguably a feature for demo hygiene) or something slightly more durable (e.g. a SQLite `pending_uploads` table) for resilience against a server restart mid-review.
   - Recommendation: start with the in-memory dict (simplest possible, matches the "local single-user demo" scope explicitly stated in CONTEXT.md's Phase Boundary); a server restart losing an in-progress (not-yet-confirmed) review is an acceptable demo-scale tradeoff.

2. **Should `/api/confirm`'s export step run synchronously in the same request, or does the browser call `/api/confirm` then separately trigger export?**
   - What we know: `cli.py`'s `_map_one` treats save-profile and export as two independent optional steps triggered by two separate CLI flags (`--save-profile`, `--export`) on the same call.
   - What's unclear: whether the UI-SPEC wants "confirm" and "export" as one browser action (one button) or two (confirm, then a separate download button) — this affects whether `/api/confirm`'s response embeds export URLs directly (as sketched above) or a client makes a follow-up call.
   - Recommendation: keep `/api/confirm` accepting an `export: bool` flag and returning export URLs when true (mirrors the CLI's existing flag shape exactly) — the planner can adjust based on the UI-SPEC once it exists.

3. **Multi-sheet workbooks (Excel with >1 sheet) in the API — does the UI upload flow pick a sheet first, or does `/api/upload` mirror `resolve_tables()`'s "map every sheet" default?**
   - What we know: `cli.run()`'s `resolve_tables()` maps every sheet in a multi-sheet workbook by default unless `--sheet` is given; the CLI prints one report block per sheet.
   - What's unclear: the browser review screen (UI-03) is described as one side-by-side view — CONTEXT.md and REQUIREMENTS.md don't explicitly say how a multi-sheet upload should map onto "one review screen."
   - Recommendation: for the money-shot demo (single-table synthetic files), this is unlikely to matter, but flag it to the planner: either (a) require `sheet` up front via a sheet picker before `/api/upload` for a multi-sheet file (simplest, matches `--sheet` CLI flag), or (b) return a list of per-sheet mapping results and let the UI show a sheet tab-switcher. Recommend (a) for hackathon scope — it is the smaller surface area and the synthetic demo corpus (per DEMO-01/02, Phase 5) is expected to be single-table files.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Backend runtime | ✓ | 3.10.12 (system) — NOTE: `pyproject.toml` declares `requires-python = ">=3.13"`; the project's own `.venv` should be checked in Wave 0, since the ambient `python3` on this machine is 3.10 | Ensure `uv run`/the project `.venv` (not ambient `python3`) is used for every command — `uv` itself resolved correctly against the declared `>=3.13` constraint during this research's dry-run |
| uv | Package management | ✓ | 0.11.28 | — |
| npm / Node | Frontend build tooling | ✓ | npm present (`/home/mesrop_custom_user/.local/bin/npm`); Node v24.18.0 | — |
| Anthropic credentials (`ANTHROPIC_API_KEY`) | Fresh-Claude mapping branch, structural-assist proposal | Not probed this session (secrets) — existing `cli.py::_has_credentials()` already handles absence gracefully (exit code 3) | — | The API layer should reuse the identical `_has_credentials()`-style check and return a clear HTTP error (e.g. 503 with a "configure ANTHROPIC_API_KEY" message) rather than letting `anthropic.AuthenticationError` surface as an unhandled 500 |
| SQLite | Profile + field-set template store | ✓ (Python stdlib `sqlite3`, no separate install) | stdlib | — |

**Missing dependencies with no fallback:** none identified for the backend scope.
**Missing dependencies with fallback:** Ambient Python version mismatch (3.10 vs declared `>=3.13`) — mitigated by always invoking through `uv run`/the project's own `.venv`, which the existing test suite presumably already does successfully (32+ tests green per CLAUDE.md's stated history).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | Explicitly out of scope — local single-user demo, no accounts (deferred DEPLOY-01) |
| V3 Session Management | No | No session/auth state; `upload_token` is a short-lived correlation id, not an auth session |
| V4 Access Control | No | Single-user local demo; no multi-tenant boundary to enforce |
| V5 Input Validation | Yes | Pydantic wire models validate every request body shape at the FastAPI boundary; `fields.loader`'s existing `yaml.safe_load`-only discipline (never the unsafe YAML loader) must be preserved if any field-set-import-by-file endpoint is added; file upload content-type/extension should be checked against the same `.csv`/`.xlsx` allowlist `parsing/table.py` already enforces before even writing to a temp file |
| V6 Cryptography | No | No new cryptographic operation introduced by this phase; SQLite files are plain local files (already the case in Phase 3), not encrypted at rest — consistent with the existing local-file confidentiality control (P2), not a new gap |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| SQL injection via a header string flowing into the profile/field-set-template store | Tampering | Already mitigated in `sqlite_store.py` (parameterised `?` placeholders throughout, explicitly documented as deliberate given "a header string is untrusted file content"); the new `field_set_store.py` must follow the identical pattern — never f-string SQL |
| Path traversal via `UploadFile.filename` (e.g. `../../etc/passwd`) used to derive a temp/output path | Tampering, Information Disclosure | Never use the client-supplied `filename` directly as a path component — derive only the file *extension* from it (as sketched in File Upload Handling above) and use `tempfile.NamedTemporaryFile`'s own generated name for the actual path |
| Unbounded upload size → resource exhaustion (disk fill, memory if buffered) | Denial of Service | Explicit size-limit check on upload (see File Upload Handling, A2) |
| Client-tampered `is_ready`/`needs_confirmation` on confirm | Tampering, Elevation of Privilege (bypassing the human-review control) | Server-side gate re-validation — this IS the entire API-02 requirement; see Server-Side Gate section above |
| XXE via a re-uploaded `.xlsx` on the API path | Tampering, Information Disclosure | Already mitigated at the parser layer — `parsing/structure/sheets.py`'s Phase 1 hardening already uses `defusedxml` per the project's dependency list (`defusedxml>=0.7.1`); the API layer inherits this for free by calling the same `parse()`/`parse_file()` functions, as long as no new Excel-parsing code path is introduced that bypasses them |
| Field-set name / description injected into Claude's system prompt via a malicious template | Tampering (prompt injection) | Already mitigated by `fields/loader.py::_validated_name`'s printable-single-line/length-cap checks — the new `/api/field-sets` POST endpoint's request body validation must apply the *same* validation as `fields.loader`, not a separate weaker check (reuse `Field`/`FieldSet` construction, which already enforces this via the loader's `_build_field`/`_validated_name`, or re-derive equivalent Pydantic validators for the HTTP body that mirror them exactly) |

## Testing the API

**Pattern:** `fastapi.testclient.TestClient` (built on `httpx`) + the *same* monkeypatch seam the existing CLI test suite already uses. `tests/test_cli_run.py` already does exactly this: `monkeypatch.setattr(cli, "propose_mapping", lambda table, field_set, client=None, **kwargs: _ready_proposal())`. The API's `service.py` should import `propose_mapping` the identical way (`from .mapping.mapper import propose_mapping`), so an API test file can `monkeypatch.setattr(service, "propose_mapping", fake_propose_mapping)` with zero new test infrastructure.

```python
# tests/api/test_upload.py — illustrative shape
from fastapi.testclient import TestClient
from assayingest.api.app import app
from assayingest import service

client = TestClient(app)

def test_upload_returns_mapping_json(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "propose_mapping",
                         lambda table, field_set, client=None, **kw: _ready_proposal())
    with open(DATA / "novascreen_batch01.csv", "rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(FIELD_SET.to_dict()), "headers_only": "false"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "mapping"
```

**Proving the SC4 money-shot in an API test (zero yellow, zero Claude call, on the second same-signature upload):**
```python
def test_second_same_signature_upload_auto_applies_with_no_claude_call(monkeypatch, tmp_path):
    call_count = {"n": 0}
    def _spy_propose_mapping(*a, **kw):
        call_count["n"] += 1
        return _ready_proposal()
    monkeypatch.setattr(service, "propose_mapping", _spy_propose_mapping)

    store = SqliteProfileStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_profile_store] = lambda: store

    # 1st upload (novascreen_batch01.csv): fresh-Claude branch
    resp1 = _upload(client, "novascreen_batch01.csv", FIELD_SET)
    assert call_count["n"] == 1
    _confirm(client, resp1, save_profile=True)   # persists the profile (LEARN-02)

    # 2nd upload (novascreen_batch02.csv, byte-identical headers): auto-apply branch
    resp2 = _upload(client, "novascreen_batch02.csv", FIELD_SET)
    assert call_count["n"] == 1   # <-- UNCHANGED: no second Claude call (LEARN-03, SC4)
    body2 = resp2.json()
    assert body2["ready"] is True
    assert all(not m["needs_confirmation"] for m in body2["field_mappings"])  # zero yellow
    assert body2["provenance"] == "auto-applied-from-profile"

    app.dependency_overrides.clear()
```
This directly reuses the codebase's existing `novascreen_batch01.csv`/`novascreen_batch02.csv` fixture pair (`data/synthetic/`) already established by `tests/test_learning_loop_cli.py` for the identical CLI-level money-shot — no new fixture files needed for the API-level equivalent.

**Fake mapper vs fake Anthropic client:** two levels are available depending on what a given test needs to exercise:
1. **Monkeypatch `service.propose_mapping`** (shown above) — fastest, zero SDK involvement, proves routing/orchestration/gate logic.
2. **Inject a fake `anthropic.Anthropic`-shaped object via `client=` parameter** (the existing `propose_mapping(table, field_set, client=None, ...)` signature already supports this) — proves the wire-model/schema-building path without a real network call, useful for one or two deeper integration tests but not needed for every route test.

Reserve any *actual* live Anthropic call for the existing `tests/test_max_tokens_live.py`-style opt-in live integration test — never in the default API test suite (matches the project's stated "32 tests + 1 live integration test" pattern from CLAUDE.md).

## Sources

### Primary (HIGH confidence)
- `src/assayingest/cli.py`, `mapping/mapper.py`, `domain/models.py`, `learning/*.py`, `validation/validator.py`, `export/writers.py`, `fields/*.py`, `parsing/hint.py`, `parsing/structure_assist.py`, `canonical.py` — read in full this session; every architectural claim about "reuse this exact function" is grounded in the actual current source, not a guess.
- `pyproject.toml` — read in full; confirms no fastapi/uvicorn/multipart dependency currently declared.
- `.planning/phases/04-api-review-ui/04-CONTEXT.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md` — read in full.
- `tests/test_cli_run.py`, `tests/test_learning_loop_cli.py`, `tests/test_headers_only.py` — read for the existing monkeypatch/fixture testing conventions this research's Testing section extends.
- fastapi.tiangolo.com/tutorial/frontend/ — fetched directly this session; `app.frontend()` API confirmed (path, directory, fallback, check_dir parameters and behavior).
- fastapi.tiangolo.com/release-notes/ — fetched directly this session; confirms `app.frontend()` shipped in FastAPI 0.138.0 (2026-06-20).
- fastapi.tiangolo.com/tutorial/static-files/ — fetched directly this session.
- `uv pip install --dry-run fastapi uvicorn python-multipart` against the live PyPI index (2026-07-10) — resolved exact versions: fastapi==0.139.0, uvicorn==0.51.0, python-multipart==0.0.32, starlette==1.3.1.
- `curl https://pypi.org/pypi/{fastapi,uvicorn,python-multipart}/json` — cross-checked `info.version` and `project_urls` (GitHub org) for each package directly against the PyPI registry API.
- `gsd-tools query package-legitimacy check --ecosystem pypi fastapi uvicorn python-multipart` — ran this session; all three flagged SUS on `too-new`/`unknown-downloads` heuristics, assessed as false positives per the Package Legitimacy Audit section.

### Secondary (MEDIUM confidence)
- fastapi.tiangolo.com/async/ (via WebSearch summary, not a direct fetch this session) — the `def`-runs-in-threadpool claim; this is also long-standing, widely-corroborated FastAPI documentation, consistent with training knowledge.
- sentry.io/answers/fastapi-difference-between-run-in-executor-and-run-in-threadpool — WebSearch result, standard/uncontroversial technical content, cross-checked against training knowledge.

### Tertiary (LOW confidence)
- Vite `server.proxy` dev-config snippet and CORS middleware import path — presented from training knowledge (marked `[ASSUMED]` inline), not independently re-fetched this session; both are long-stable, low-risk APIs, flagged in the Assumptions Log for a cheap Wave-0 sanity check rather than blocking on further research.

## Metadata

**Confidence breakdown:**
- Standard stack (fastapi/uvicorn/python-multipart choice + versions): HIGH — versions confirmed live against PyPI registry this session; package identities were already the project's declared stack (CLAUDE.md), not independently discovered
- Architecture (service-layer extraction, sync-def pattern, server-side gate, wire↔domain reuse): HIGH — every recommendation is directly grounded in reading the actual existing codebase's structure and conventions, not inferred
- `app.frontend()` frontend-serving recommendation: HIGH — directly fetched from official FastAPI docs this session, cross-confirmed against the exact resolved fastapi version (0.139.0 ≥ 0.138.0 introduction version)
- Pitfalls: HIGH for the ones grounded in codebase reading (gate-trust, signature-reuse, temp-file cleanup); MEDIUM for the generic FastAPI/async pitfalls (well-established but not independently re-verified beyond WebSearch summaries this session)
- Testing approach: HIGH — directly extends an existing, working test pattern already present in this exact codebase (`tests/test_cli_run.py`'s monkeypatch idiom)
- Security domain: MEDIUM — ASVS mapping and STRIDE table are standard analysis grounded in the actual codebase's existing controls (defusedxml, parameterised SQL, safe_load-only YAML), not independently re-verified against a live ASVS checklist this session

**Research date:** 2026-07-10
**Valid until:** 7 days (fast-moving: fastapi is shipping point releases roughly weekly at the time of this research per the resolved version dates; re-verify exact versions before `uv add` if planning is delayed)
