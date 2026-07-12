# Architecture Research

**Domain:** AI-assisted data ingestion tool (CRO assay files) — adding validation, persistence, and a web layer to an existing Clean Architecture Python core
**Researched:** 2026-07-09
**Confidence:** HIGH (grounded directly in the existing, already-mapped codebase; MEDIUM/cross-checked web sources for generic FastAPI/repository-pattern and schema-fingerprinting conventions — see Sources)

## Standard Architecture

### System Overview

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION (two entry points)                     │
│  ┌──────────────────┐                    ┌────────────────────────────┐   │
│  │   CLI (existing)  │                    │  FastAPI app (new)          │   │
│  │   cli.py           │                    │  api/routes.py, api/schema  │   │
│  └─────────┬─────────┘                    └───────────────┬────────────┘   │
│            │  both call the SAME orchestration function     │              │
└────────────┼──────────────────────────────────────────────┼───────────────┘
             │                                              │
             ▼                                              ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                    APPLICATION / ORCHESTRATION (new, thin)                  │
│  ingest_use_case.py: parse → propose → apply_profile_or_validate →         │
│                       return proposal (never writes without confirm)       │
│  confirm_use_case.py: accept confirmed proposal → save_profile             │
└─────────┬───────────────┬───────────────┬───────────────┬─────────────────┘
          │                │               │               │
          ▼                ▼               ▼               ▼
┌────────────────┐ ┌───────────────┐ ┌──────────────┐ ┌──────────────────────┐
│ Parsing Layer   │ │ Mapping Layer │ │ Domain Layer │ │ Storage Layer (new)   │
│ (existing)      │ │ (existing)    │ │ (existing +  │ │ storage/lab_profile.py│
│ parsing/table.py│ │ mapping/      │ │  validator)  │ │ SQLite repository,    │
│                 │ │ mapper.py     │ │ domain/      │ │ implements domain     │
│ CSV/Excel →     │ │ (Claude call) │ │  models.py   │ │ ProfileRepository     │
│ RawTable        │ │               │ │  reference.py│ │ interface (Protocol)  │
│                 │ │               │ │  validator.py│ │                        │
│                 │ │               │ │ (new, no-LLM)│ │                        │
└────────┬────────┘ └───────┬───────┘ └──────┬───────┘ └───────────┬──────────┘
         │                  │                │                     │
         └──────────────────┴───────┬────────┘                     │
                                     ▼                              ▼
                          ┌──────────────────────┐        ┌──────────────────┐
                          │   Anthropic SDK       │        │  SQLite file      │
                          │   (Claude API)        │        │  lab_profiles.db  │
                          └──────────────────────┘        └──────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|-------------------------|
| Validator | Check Claude's proposed mapping against `reference.py` (assay-type vocab, unit vocab, assay-type/unit compatibility, unit-vs-value-range plausibility); force `needs_confirmation=true` on any mismatch | Pure function in `domain/validator.py`, stdlib only, no I/O |
| Profile repository (interface) | Define the contract for "find a profile by signature" / "save a profile" that the domain/use-case layer depends on | `Protocol` or ABC in `domain/ports.py` (or co-located in `domain/models.py`) — zero SQL, zero SQLite import |
| Profile repository (implementation) | Fulfil the contract using SQLite | Concrete class in `storage/lab_profile.py`, imports `sqlite3`, implements the `Protocol` structurally |
| Signature builder | Turn a `RawTable`'s headers into a stable, order-independent signature string/hash | Pure function in `domain/models.py` or a small `domain/signature.py` — stdlib only (`hashlib`) |
| Ingest use case | Orchestrate parse → (lookup profile → apply-at-1.0 OR propose via Claude) → validate → return proposal | `application/ingest.py` (new top-level package, or a function group in `cli.py`-adjacent module) — depends on ports, not concrete infra |
| Confirm use case | Take a curator-confirmed proposal, persist it as a lab profile via the repository interface | `application/confirm.py` — same dependency direction |
| FastAPI app | HTTP boundary: upload endpoint, propose endpoint, confirm endpoint; translates HTTP DTOs ↔ domain calls | `api/routes.py`, `api/schemas.py` (Pydantic request/response models — a *second*, HTTP-facing wire layer, distinct from the Claude wire layer in `mapping/schema.py`) |
| React app | Renders the review screen from the FastAPI JSON, posts confirm | `frontend/` (separate Vite project) — knows nothing about Python |

## Recommended Project Structure

```
src/assayingest/
├── domain/                    # unchanged home, extended
│   ├── models.py              # existing: TargetField, FieldMapping, MappingProposal
│   ├── reference.py           # existing: allowed assay types/units (no LLM)
│   ├── validator.py           # NEW: validate_proposal(proposal) -> MappingProposal (re-flags fields)
│   ├── signature.py           # NEW: build_signature(headers: list[str]) -> str
│   └── ports.py                # NEW: ProfileRepository Protocol (interface only, no sqlite3 import)
├── parsing/                   # unchanged
│   └── table.py
├── mapping/                   # unchanged
│   ├── mapper.py
│   └── schema.py
├── storage/                   # NEW — infrastructure, mirrors parsing/mapping as a sibling
│   ├── __init__.py
│   ├── lab_profile.py         # SQLite implementation of ProfileRepository; SQL, connection, migrations
│   └── db.py                  # connection/schema bootstrap (CREATE TABLE IF NOT EXISTS ...)
├── application/                # NEW — thin orchestration layer, the one new "layer" in the strict sense
│   ├── __init__.py
│   ├── ingest.py               # ingest_file(path, repo) -> MappingProposal (checks profile, else calls mapper, then validator)
│   └── confirm.py              # confirm_mapping(proposal, lab_name, headers, repo) -> None (persists profile)
├── api/                        # NEW — HTTP boundary, thin, imports application not the reverse
│   ├── __init__.py
│   ├── app.py                  # FastAPI() instance, CORS, dependency wiring
│   ├── routes.py                # POST /upload, POST /confirm
│   └── schemas.py               # Pydantic request/response DTOs (HTTP wire, distinct from mapping/schema.py)
└── cli.py                      # unchanged in spirit, refactored to call application/ingest.py + application/confirm.py

frontend/                       # NEW — separate Vite + React project, not part of the Python package
├── src/
│   ├── components/ReviewTable.tsx
│   ├── api/client.ts            # fetch wrapper against FastAPI
│   └── App.tsx
└── package.json
```

### Structure Rationale

- **`domain/validator.py` sits in `domain/`, not `mapping/`:** validation is ground-truth business logic ("is this assay_type/unit combination real?"), not an API integration concern. It has the same "pure, no I/O" invariant as `reference.py` and `models.py`. It must be importable and testable with zero network/DB access — this is non-negotiable per the project's "no-LLM validator" principle.
- **`domain/ports.py` (repository interface) lives in domain, `storage/lab_profile.py` (repository implementation) lives in infrastructure:** this is the one deliberate Dependency Inversion in the new work. The application layer and CLI depend on the `ProfileRepository` *Protocol*, never on `sqlite3` directly. Python's structural typing (`typing.Protocol`) means `storage/lab_profile.py` doesn't even need to import from `domain/ports.py` to satisfy it — but importing it explicitly documents intent and lets tests use `isinstance` checks or a fake in-memory implementation for `test_ingest.py` without touching SQLite.
- **`application/` is new and deliberately thin:** the codebase currently has no orchestration layer between `cli.py` and the parsing/mapping/domain layers — `cli.py` does the orchestrating directly. Introducing a shared `application/ingest.py` + `application/confirm.py` is what lets **both** the CLI and the FastAPI routes call the *exact same* propose→validate→(profile-apply) flow without duplicating logic or making `api/routes.py` import `cli.py` (wrong direction — CLI and API are both presentation, neither should depend on the other). This is the layer FastAPI and the CLI both sit on top of.
- **`storage/` is a sibling of `parsing/` and `mapping/`, not nested under either:** it is a third infrastructure adapter with the same shape (translate outside world ↔ domain at the boundary) as parsing (files → domain) and mapping (Claude API → domain). Matches the codebase's own "Where to Add New Code" guidance in `STRUCTURE.md`.
- **`api/` is presentation, same rank as `cli.py`, not a wrapper around it:** both are entry points that call into `application/`. This avoids the common anti-pattern of an HTTP layer shelling out to CLI functions (fragile, hard to test, mixes concerns like `sys.exit` codes into HTTP responses).
- **`api/schemas.py` is a *second* wire-model boundary, separate from `mapping/schema.py`:** `mapping/schema.py` defines Claude's JSON contract; `api/schemas.py` defines the FastAPI request/response contract. They must not be the same Pydantic models — the API DTOs describe what the *browser* needs (e.g., a `lab_name` field the curator types in, an `upload_id`), which is different from what Claude returns. Conflating them would let a Claude API shape change silently break the frontend contract, and vice versa. Map API DTO ↔ domain at the `api/routes.py` boundary the same way `mapper.py` maps wire ↔ domain today.
- **`frontend/` is a wholly separate project**, not inside `src/assayingest/`: keeps the Python package installable/testable independent of `npm`, matches the stack's Vite+React choice, and lets `frontend/` be gitignored differently (`node_modules/`, `dist/`) from the Python `.venv/`.

## Architectural Patterns

### Pattern 1: Repository behind a Protocol (Dependency Inversion for the learning store)

**What:** Define `ProfileRepository` as a `typing.Protocol` (structural interface) in `domain/ports.py` with two methods — `find_by_signature(signature: str) -> LabProfile | None` and `save(profile: LabProfile) -> None`. The domain also gains a `LabProfile` frozen dataclass (`lab_name`, `signature`, `mapping_json` or a typed `MappingProposal`, `created_at`). `storage/lab_profile.py` implements the Protocol using `sqlite3` directly (stdlib — no ORM needed for this scope and timeline).

**When to use:** Any time the domain/application layer needs persistence but must stay ignorant of *how* it's persisted. Here specifically: the "auto-apply on repeat signature" flow is domain logic (a business rule: "if we've seen this exact signature before, treat it as trusted") that must not import `sqlite3`.

**Trade-offs:** A `Protocol` (structural typing) avoids the ceremony of an ABC + explicit inheritance and is idiomatic in modern Python (matches the codebase's `str | None` / `list[str]` style — light, current syntax). Cost: slightly less explicit than an ABC (no `NotImplementedError` at import time if a method is missing) — acceptable for a 4-day scope with tests covering it. For a bigger project, consider `abc.ABC` for stricter enforcement.

**Example:**
```python
# domain/ports.py
from __future__ import annotations
from typing import Protocol
from .models import MappingProposal

class ProfileRepository(Protocol):
    def find_by_signature(self, signature: str) -> MappingProposal | None: ...
    def save(self, *, lab_name: str, signature: str, proposal: MappingProposal) -> None: ...
```
```python
# storage/lab_profile.py
from __future__ import annotations
import sqlite3
from ..domain.models import MappingProposal
from ..domain.ports import ProfileRepository

class SqliteProfileRepository(ProfileRepository):
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._bootstrap()

    def find_by_signature(self, signature: str) -> MappingProposal | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT mapping_json FROM lab_profile WHERE signature = ?",
                (signature,),
            ).fetchone()
        return _deserialize(row[0]) if row else None
```

### Pattern 2: Application-layer use-case functions shared by CLI and API

**What:** A single `ingest_file(path, repo: ProfileRepository) -> MappingProposal` function that both `cli.py` and `api/routes.py` call. It (a) parses via `parsing/table.py`, (b) builds the signature via `domain/signature.py`, (c) checks `repo.find_by_signature()` — if hit, returns that proposal at confidence 1.0 with zero yellow fields (no Claude call, instant); if miss, calls `mapping/mapper.py:propose_mapping()`, then (d) runs the result through `domain/validator.py` before returning.

**When to use:** Whenever two presentation layers (CLI + HTTP) need identical business behavior. Prevents the FastAPI route from re-implementing the "check profile, else call Claude, then validate" sequencing — which is exactly the kind of orchestration logic that drifts out of sync if duplicated.

**Trade-offs:** Adds one new package (`application/`) the existing codebase doesn't have yet — a deliberate, small addition, not scope creep, because it's the only way to keep `api/` from depending on `cli.py` or vice versa. For a solo 4-day hackathon, keep it to two files (`ingest.py`, `confirm.py`); don't over-abstract into a use-case-per-file if it isn't earning its keep yet.

**Example:**
```python
# application/ingest.py
from __future__ import annotations
from ..domain.models import MappingProposal
from ..domain.ports import ProfileRepository
from ..domain.signature import build_signature
from ..domain.validator import validate_proposal
from ..mapping.mapper import propose_mapping
from ..parsing.table import RawTable

def ingest_table(table: RawTable, repo: ProfileRepository) -> MappingProposal:
    signature = build_signature(table.headers)
    cached = repo.find_by_signature(signature)
    if cached is not None:
        return cached  # already confirmed once; confidence 1.0, no gate
    proposal = propose_mapping(table)
    return validate_proposal(proposal)
```

### Pattern 3: FastAPI dependency injection for the repository (no framework leakage into domain)

**What:** FastAPI's `Depends()` constructs a `SqliteProfileRepository` (concrete, infra) per-request and injects it into route handlers, which pass it straight into `application/ingest.py` and `application/confirm.py` functions typed against `ProfileRepository` (the Protocol). The route handler is the *only* place that knows the concrete class exists.

**When to use:** Any FastAPI app that needs to keep its domain framework-agnostic while still using FastAPI's DI ergonomics. Confirmed as the standard idiom by current FastAPI/Clean-Architecture guides: interfaces live in the core, `Depends()` wires the concrete implementation at the edge.

**Trade-offs:** FastAPI's `Depends()` is itself a light form of coupling at the route layer — acceptable because `api/routes.py` is presentation/infrastructure by definition, not domain. Avoid the temptation to import `Depends` or FastAPI types anywhere under `domain/` or `application/`.

**Example:**
```python
# api/app.py
from fastapi import Depends, FastAPI
from ..storage.lab_profile import SqliteProfileRepository
from ..domain.ports import ProfileRepository

def get_repository() -> ProfileRepository:
    return SqliteProfileRepository(db_path="lab_profiles.db")

app = FastAPI()
```
```python
# api/routes.py
from fastapi import Depends
from .app import app, get_repository
from ..application.ingest import ingest_table
from ..domain.ports import ProfileRepository

@app.post("/upload")
def upload(..., repo: ProfileRepository = Depends(get_repository)):
    proposal = ingest_table(table, repo)
    return proposal_to_dto(proposal)  # map domain -> HTTP DTO at the boundary
```

## Data Flow

### Request Flow — full propose → validate → confirm → persist → auto-apply loop

```
[Curator uploads file]  (React → POST /upload, or CLI arg)
         ↓
[api/routes.py or cli.py]  — presentation, unchanged responsibility: receive input, call application layer
         ↓
[application/ingest.py: ingest_table()]
         ↓
   parsing/table.py: parse_file() → RawTable
         ↓
   domain/signature.py: build_signature(headers) → signature string
         ↓
   storage/lab_profile.py (via ProfileRepository.find_by_signature) — SQLite lookup
         ↓
   ┌─────────────────┴─────────────────┐
   │ HIT (known signature)              │ MISS (new lab / new columns)
   ▼                                     ▼
[return stored MappingProposal   [mapping/mapper.py: propose_mapping()]
 at confidence 1.0, zero yellow]        ↓ Claude structured-output call
   │                              [domain/validator.py: validate_proposal()]
   │                                     ↓ re-flags any field that fails
   │                              reference-dict checks (assay_type/unit
   │                              vocab, compatibility, value-range)
   │                                     ↓
   └─────────────────┬─────────────────┘
                      ▼
         [MappingProposal returned to presentation layer]
                      ▼
        api/routes.py maps domain → HTTP DTO (api/schemas.py)
                      ▼
        [React review screen: side-by-side diff, yellow = needs_confirmation]
                      ▼
        Curator edits/accepts each yellow field → clicks Confirm
                      ▼
        POST /confirm { lab_name, headers, corrected proposal }
                      ▼
        [application/confirm.py: confirm_mapping()]
             — gate check: refuse if any field still needs_confirmation
             (server-side re-check of the "nothing saved until all fields
             are clear" rule — never trust the client alone)
                      ▼
        storage/lab_profile.py: repo.save(lab_name, signature, proposal)
                      ▼
        [Next file, same lab, same column signature]
                      ▼
        ingest_table() → find_by_signature() HIT → confidence 1.0, zero
        yellow, no Claude call — the demonstrable learning-loop moment
```

### State Management

```
Stateless per request (matches existing "no mutation" invariant):
  RawTable (immutable) → MappingProposal (immutable-ish, list of frozen-ish
  FieldMapping) → validated MappingProposal → HTTP DTO (Pydantic, immutable
  by convention) → React component state (client-side, mutable, local only)

Only durable state in the whole system: SQLite `lab_profile` table.
No server-side session state; no in-memory cache across requests (a request-
scoped repository instance per FastAPI Depends() call is sufficient at this
scale — do not add a global cache/singleton, it isn't needed for a handful
of demo labs and it would violate "Global state: Minimal" from the existing
architecture doc).
```

### Key Data Flows

1. **First file from an unseen lab:** parse → no signature match → Claude proposes → validator flags any reference-dict mismatches → several yellow fields shown in UI → curator corrects → confirm gate passes → profile saved.
2. **Second file, same lab, same columns:** parse → signature match → stored proposal returned verbatim at confidence 1.0 → zero yellow fields → confirm is a no-op re-save (idempotent) or skipped entirely — this is the money-shot the demo video needs to show back-to-back.
3. **Second file, same lab, but one column renamed:** signature differs (by design — see below) → falls through to the Claude-propose path again, not a partial/fuzzy match. This is a deliberate MVP simplification (see Anti-Patterns).

## Column-Signature Design (order-independent, normalized)

The signature is the join key for the learning store and must be **stable across re-uploads of an unchanged schema, order-independent (columns can be reordered by the lab's export tool), and insensitive to incidental whitespace/case differences** without being so fuzzy that it silently merges genuinely different schemas.

**Recommended approach** (confirmed as the standard lightweight pattern via cross-checked sources — see Sources):

1. Normalize each header: `strip()`, collapse internal whitespace, casefold (`.casefold()` not `.lower()` for correctness with non-ASCII lab codes), keep blank headers as `""` (matches the existing parser's blank-header convention — a blank column is signal, not noise, per `parsing/table.py`'s own doc-comment).
2. **Do not** strip punctuation or apply fuzzy/phonetic matching for the MVP — that risks silently conflating two different labs' schemas, which directly violates the "never guess silently" principle. Exact-normalized-match only.
3. Sort the normalized header list (order-independence) — a lab that exports the same columns in a different order should still hit the cached profile.
4. Join with a delimiter unlikely to appear in a header (e.g. `"\x1f".join(sorted_headers)`), then hash with `hashlib.sha256(...).hexdigest()` for a compact, comparison-friendly key. Store the raw sorted-header-list alongside the hash in SQLite too (debuggability — a curator or you, mid-demo, may need to see *why* two files matched or didn't).
5. Scope the signature **per lab_name**, not globally: the SQLite lookup should be `WHERE lab_name = ? AND signature = ?` (or make `lab_name` part of the hashed input) so two different labs that coincidentally share a header set don't cross-pollinate mappings — mapping meaning can differ by lab even with identical column names.

```python
# domain/signature.py
from __future__ import annotations
import hashlib

def build_signature(headers: list[str]) -> str:
    """Order-independent, case/whitespace-normalized signature for a header set.

    Exact match only — no fuzzy matching, so two genuinely different schemas
    never silently collide. Renamed columns intentionally produce a new
    signature and fall through to a fresh Claude proposal.
    """
    normalized = sorted(_normalize(h) for h in headers)
    joined = "\x1f".join(normalized)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()

def _normalize(header: str) -> str:
    return " ".join(header.split()).casefold()
```

This keeps `domain/signature.py` pure (stdlib `hashlib` only), testable without SQLite, and consistent with the existing `_clean_header()` philosophy in `parsing/table.py`.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Hackathon demo (1 curator, 4-5 synthetic labs) | Exactly the structure above. SQLite file on local disk. FastAPI single process, `uvicorn` dev server. No auth. |
| Small team (a handful of curators, dozens of labs) | Same structure holds. Add a `lab_name` foreign-key/unique index on `(lab_name, signature)`. Consider WAL mode for SQLite if concurrent writers. Still no need for Postgres. |
| Production (many curators, hundreds of labs, concurrent uploads) | Swap `SqliteProfileRepository` for a Postgres-backed implementation of the *same* `ProfileRepository` Protocol — zero changes to `domain/` or `application/`. This is the payoff of the repository-interface pattern: the swap is confined to `storage/`. |

### Scaling Priorities

1. **First bottleneck (won't happen in 4 days, but note it):** SQLite single-writer lock under concurrent confirms — irrelevant at demo scale, mitigated later by WAL mode or a Postgres swap behind the same interface.
2. **Second bottleneck:** Claude API latency on the propose path — already out of scope to optimize; the learning loop *is* the optimization (repeat signatures skip the call entirely).

## Anti-Patterns

### Anti-Pattern 1: FastAPI routes calling `sqlite3` (or the mapper) directly

**What people do:** Write `@app.post("/upload")` handlers that open a SQLite connection and call `anthropic.Client()` inline, because it's fast to hack together.
**Why it's wrong:** Duplicates the propose→validate→auto-apply sequencing that the CLI also needs; makes the flow untestable without spinning up FastAPI; couples the domain rule "check profile before calling Claude" to the HTTP framework.
**Do this instead:** Routes only parse the HTTP request into domain-shaped arguments, call an `application/*.py` function, and map the domain result back to a DTO. All business sequencing lives in `application/`.

### Anti-Pattern 2: Fuzzy/similarity matching on the column signature for MVP

**What people do:** Reach for Levenshtein distance or embedding similarity to match "close enough" column sets so more files hit the cache.
**Why it's wrong:** Directly contradicts "never guess silently" — a fuzzy match that's wrong silently applies a stale, possibly-incorrect mapping with *zero* yellow flags, which is worse than the LLM guessing, because the human never even sees a chance to catch it. It also adds real complexity in a 4-day budget for a benefit (catching minor renames) that isn't the judged differentiator (the differentiator is the *demonstrable* exact-repeat case).
**Do this instead:** Exact-normalized-signature match only. If a lab renames a column, that's a new signature, a fresh Claude proposal, and — because the reference dict and Claude context are unchanged — usually a fast, mostly-green proposal anyway.

### Anti-Pattern 3: Reusing `mapping/schema.py` Pydantic models as the FastAPI request/response models

**What people do:** Import `WireMappingProposal` from `mapping/schema.py` directly in `api/routes.py` to avoid writing "duplicate" Pydantic models.
**Why it's wrong:** Couples the Claude API contract to the browser API contract. If Claude's schema needs a field for prompting reasons (e.g., an internal-only `alternatives` shape) that shouldn't reach the frontend as-is, or if the frontend needs a field Claude doesn't produce (e.g., `upload_id`, `lab_name` typed by the curator), the two contracts diverge and this shortcut breaks. It's the same "Mixing Wire and Domain Models" anti-pattern the codebase's own `ARCHITECTURE.md` already flags, one layer further out.
**Do this instead:** `api/schemas.py` defines its own DTOs; map domain `MappingProposal` → DTO explicitly at the route boundary, same pattern as `mapper.py`'s `_to_domain()`.

### Anti-Pattern 4: Trusting the client's "all fields confirmed" flag

**What people do:** Let the confirm endpoint save whatever proposal JSON the browser POSTs, trusting the frontend's own gate (button disabled until no yellow cells) as the sole enforcement.
**Why it's wrong:** Violates "Nothing saved until all fields are clear" as a *system* invariant, not just a UI nicety — a malformed request, a race condition, or a bug in the React gate could persist an unconfirmed mapping as if it were trusted.
**Do this instead:** `application/confirm.py` re-runs the `is_ready` check (already a `MappingProposal` property per the existing domain model) server-side before calling `repo.save()`, and raises/returns an error if any field still needs confirmation. The gate must exist at the domain/application boundary, not only in `cli.py`'s `render_report()` or the React button.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Anthropic API | Existing `mapping/mapper.py:propose_mapping()`, unchanged | Only called on signature-miss; the learning loop's entire value is *avoiding* this call on repeat |
| SQLite | New `storage/lab_profile.py`, stdlib `sqlite3`, no ORM | A single-file DB (`lab_profiles.db`) is sufficient; bootstrap schema with `CREATE TABLE IF NOT EXISTS` on repository construction, not a separate migration tool — no Alembic needed for this scope |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `application/` ↔ `domain/` | Direct function calls, domain types only | `application/` is allowed to import `domain/`, `parsing/`, `mapping/`, and depend on the `ProfileRepository` Protocol — never on `storage/`'s concrete class |
| `application/` ↔ `storage/` | Only via the `ProfileRepository` Protocol, injected as a parameter | `application/ingest.py` never does `from ..storage.lab_profile import SqliteProfileRepository` — that import only happens in `api/app.py` / `cli.py` at the composition root |
| `api/` ↔ `application/` | Direct function calls; `api/routes.py` maps HTTP DTO → domain args → calls use case → maps domain result → HTTP DTO | `api/` may import `application/` and `domain/` (for type hints on DTOs' mapping functions), never `mapping/schema.py` or `storage/lab_profile.py` internals directly |
| `cli.py` ↔ `application/` | Direct function calls, same use cases as `api/` | Refactor `cli.py` to call `application/ingest.py` / `application/confirm.py` instead of calling `parsing`/`mapping` directly, so CLI and API never drift apart in behavior |
| `frontend/` ↔ `api/` | HTTP/JSON only (`fetch`/`axios` against FastAPI) | No shared code between Python and TypeScript; the wire contract is `api/schemas.py`'s Pydantic models, documented via FastAPI's auto-generated OpenAPI schema (useful to point the frontend at during Day 3) |

## Suggested Build Order for the 4-Day Timeline

This maps directly onto the project's own "Day 2 / Day 3 / Day 4" plan in `CLAUDE.md`, sequenced so each piece is independently testable before the next depends on it (no layer is built before what it depends on exists):

1. **Validator first** (`domain/validator.py`, pure, no new dependencies): can be written and tested today against the existing `MappingProposal`/`reference.py` with zero new infrastructure. Wire it into `cli.py` immediately after `propose_mapping()` so the CLI demo already benefits before anything else changes. This is the smallest, lowest-risk addition and unblocks nothing else, so do it first.
2. **Signature builder** (`domain/signature.py`, pure, stdlib only): tiny, independent, testable in isolation with plain lists of strings — no SQLite needed yet.
3. **Repository interface + SQLite implementation** (`domain/ports.py` + `storage/lab_profile.py`): build the Protocol and the concrete class together (interface without an implementation to test against is speculative; build both, test the concrete class directly with an in-memory `:memory:` SQLite DB in `test_storage.py`).
4. **Application layer** (`application/ingest.py`, `application/confirm.py`): wires validator + signature + repository + existing parsing/mapper into the full flow described in Data Flow above. Refactor `cli.py` to call these instead of orchestrating directly — this is the point where the CLI demo can show the full "first file yellow, second file zero-yellow" loop *before any UI exists*, which de-risks the differentiator early (per the project's own Day-1 priority: "Build the money shot early").
5. **FastAPI layer** (`api/app.py`, `api/routes.py`, `api/schemas.py`): thin wrapper around the now-proven `application/` functions. Low risk once step 4 works, because all business logic is already tested.
6. **React UI** (`frontend/`): builds against the FastAPI OpenAPI contract from step 5. This is explicitly the last major piece per the project's own plan ("Day 3... This makes the demo") — correctly sequenced last because it's presentation over an already-correct backend, not because it's unimportant.
7. **Demo polish** (Day 4, unchanged from `CLAUDE.md`): synthetic multi-lab files, video, README — no architecture implications, just content.

**Why this order, explicitly:** every step only depends on layers already built (validator and signature depend on nothing new; the repository depends on nothing but SQLite; the application layer is the first thing that composes all of them; API and UI are strictly additive presentation on top of a working, CLI-provable core). This means a demo is always recordable at every checkpoint from step 4 onward, which matters given the hard deadline — if Day 3/4 UI work runs over, the CLI-only version of the full learning loop is already a legitimate, demonstrable fallback.

## Sources

- Existing codebase (ground truth for current structure and conventions): `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`, `.planning/codebase/CONVENTIONS.md` (all dated 2026-07-09, produced by `/gsd-map-codebase`) — HIGH confidence, primary source.
- [Clean Architecture Structure (FastAPI) · launch.ist](https://www.launch.ist/blog/clean-architecture-structure/) — MEDIUM confidence, cross-checked
- [Practical FastAPI × Clean Architecture Guide — router splitting, service layer, repository pattern](https://blog.greeden.me/en/2025/12/23/practical-fastapi-x-clean-architecture-guide-growing-a-maintainable-api-with-router-splitting-a-service-layer-and-the-repository-pattern/) — MEDIUM confidence
- [How To Implement Clean Architecture in FastAPI: A Step-by-Step Guide — Medium](https://medium.com/@bhagyasithumini/how-to-implement-clean-architecture-in-fastapi-a-step-by-step-guide-8b73a75c650b) — MEDIUM confidence
- [Clean Architecture with Python — Medium](https://medium.com/@shaliamekh/clean-architecture-with-python-d62712fd8d4f) — MEDIUM confidence
- [GitHub: jujumilk3/fastapi-clean-architecture](https://github.com/jujumilk3/fastapi-clean-architecture) — MEDIUM confidence, illustrative reference implementation
- Column-signature/schema-fingerprinting: general schema-matching literature confirms textual/metadata (header) matching and hashing/n-gram fingerprinting as the standard techniques; no single canonical source for the exact "sorted-hash" MVP recipe recommended here — that recipe is this document's own synthesis for the project's exact-match, no-silent-guessing constraint (see [Zeenea: What is Data Fingerprinting?](https://zeenea.com/what-is-data-fingerprinting-and-similarity-detection/) for general background) — LOW-MEDIUM confidence on background, HIGH confidence on the recommendation itself (it follows directly from the project's own "never guess silently" principle, not from external authority).

---
*Architecture research for: AI-assisted CRO assay ingestion — adding validation, SQLite learning store, and FastAPI/React layer to an existing Clean Architecture core*
*Researched: 2026-07-09*
