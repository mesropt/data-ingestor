# Phase 10: Frictionless & Correct Ingest - Research

**Researched:** 2026-07-12
**Domain:** Server-side date-order detection (no LLM), deterministic pre-mapping, governed-schema edit semantics on PostgreSQL, frontend page deletion/rename
**Confidence:** HIGH (grounded in this repo's own code, verified by reading and executing against real fixtures) for date-detection mechanics and the Postgres store; MEDIUM for the exact escalation-composition and delete-semantics recommendations (genuine design forks not settled by CONTEXT.md, presented with a reasoned pick)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-10-01:** The Upload screen shows **exactly three things**: the target Schema, an optional map file (merged into the master map), and the headers-only toggle. Everything else is removed from the visual.
- **D-10-02:** The target fields **are** the selected Schema's canonical fields. There is no field-set picker, no field-set proposal UI, and no field-set concept anywhere the user can see. `FieldSet` remains an internal type; it is not a user-facing noun.
- **D-10-03:** Mapping resolves in a fixed order, and each stage only sees what the previous could not resolve: (1) Python — match the file's headers against the Schema's crosswalk aliases (deterministic, free, no LLM); (2) Claude — only the columns Python could not resolve; (3) Human — only what Claude could not resolve confidently (the existing amber/confirm gate). This is a re-ordering, not a rewrite.
- **D-10-04:** Date-format detection is **pure Python, server-side, no LLM** — it lives where `validation/validator.py` and `canonical.assemble()` already read values. Deterministic, testable without an API key.
- **D-10-05:** `headers_only` is therefore **unaffected**: it restricts what *Claude* sees, not what the server reads. Date detection behaves identically in both modes.
- **D-10-06:** The detector **always runs**, even when the field declares a `date_format`. A declared format is a *human claim*, checked against the data — if the column contradicts it, the field is flagged and the human is asked. **This supersedes D-13** ("declared format = permission to convert").
- **D-10-07:** An ambiguous format (`03/04/2025` — DD/MM or MM/DD?) **fails closed**: ask the human **once per column**, then apply that answer to every row of that column. Never infer the order silently.
- **D-10-08:** Excel **numeric date serials** (`45678` → a date) are **in scope**. "Excel corrupted *other* data into dates" (gene names → dates, `wild/10_genelab_date_disaster.xlsx`) stays **out of scope**, in the `parser-excel-hazards` todo.
- **D-10-09:** **Delete Define Fields. Rename Registry → Schemas.** Tabs become: Schemas, Upload, Review (+ Docs).
- **D-10-10:** The Schemas page is one table per Schema, **one row per canonical field**, carrying *both* the field's constraints and its vendor aliases with provenance. Both are **editable**.
- **D-10-11:** Nothing new needs storing. `Schema` → `CanonicalField` → `Field` already carries every constraint.
- **D-10-12:** A new **explicit edit endpoint** is required. `POST /api/schemas/{name}/master-map` **stays augment-only** (D-07-04). Only a human may remove or rewrite, and only through the explicit edit path, gated by `require_verified_user`, with provenance recorded as a manual edit.
- **D-10-13:** **Sign-in is required to use the tool.** There is no anonymous upload path.
- **D-10-14:** The four shipped presets are **seeded as Schemas** at startup. This re-targets quick task `260712-e0e`, which seeded them as *field sets* into a picker this phase deletes.

### Claude's Discretion

- The exact Python alias-matching strategy in D-10-03 (exact match, normalized match, or crosswalk lookup — and whether a near-miss escalates to Claude or is treated as unresolved).
- The exact shape of the "ask once per column" date question — whether it reuses the existing `StructureQuestion` / `/api/structural-hint/resolve` / `StructuralHintPanel` machinery (strongly preferred) or needs its own analogous flow.
- The visual layout of the Schemas page (row expansion vs side panel) — **already resolved** in `10-UI-SPEC.md`: inline row-expansion (accordion), one row open at a time.
- Migration handling for existing field-set rows in the store, including the empty-named row the builder has not asked to delete.

### Deferred Ideas (OUT OF SCOPE)

- **Column splitting (was INGEST-03)** — a merged key/value column (`Age / Sex` → `65 / M`) feeding two target fields. Deferred by the builder; do not touch mapping-split logic in this phase.
- **Two source columns → one target field** — the mirror of splitting, never raised as a need.
- **Excel corrupting non-dates into dates** (gene names → dates, scientific notation IDs) — stays in `.planning/todos/pending/parser-excel-hazards.md`; only the *serial* mechanism (D-10-08) is in scope, not the whole `10_genelab_date_disaster.xlsx` fixture's other hazards.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INGEST-01 | Upload shows exactly Schema + optional map file + headers-only; no field-set picker in the UI | See "Frontend deletion/rename" section — `App.tsx`/`routing.ts` already have the allowlist-fallback mechanism this needs; `upload.py::_resolve_field_set` needs a Schema→FieldSet adapter |
| INGEST-02 | Python-first deterministic alias match against the Schema's crosswalk, before any Claude call, for whatever the profile auto-apply did not already resolve | See "Python-first alias matching" — `service._reconcile_map`/`_alias_index` is the exact mechanism to generalize, vendor-scoping is the key design fork |
| INGEST-04 | Every date normalizes to ISO 8601; ambiguity detected in pure Python and asked once per column; Excel serials handled; declared `date_format` is checked, not trusted | See "Date-format detection" — full ambiguity predicate, candidate-format list, Excel-serial mechanics, and where detection plugs into `canonical.py`/`validation/validator.py`/`service.py` |
| INGEST-05 | Define Fields deleted, Registry renamed to Schemas, single editable page over `CanonicalField` constraints + aliases, new explicit edit endpoint (augment-only master-map route untouched) | See "Schema editing endpoint" — HTTP shape, SCHEMA-04 isolation, the Postgres `ON DELETE` cascade gap, hard-delete vs soft-delete/provenance fork |
| INGEST-06 | Four presets seeded as Schemas at startup; no anonymous path | Existing `_lifespan` preset-seeding + `require_verified_user`/`SignInRequiredGate` precedent already covers the mechanics; flagged as low-risk, not deep-researched here (out of this phase's four priority areas) |
</phase_requirements>

## Summary

This phase is pure hardening of an already-shipped, well-tested pipeline (615 backend / 118 frontend tests). Every one of its four hard problems already has a directly analogous, working precedent in this exact codebase — the job is to imitate those precedents faithfully, not invent new architecture.

For **date-format detection** (the hardest, safety-critical part), `src/assayingest/parsing/structure/locale.py` is the load-bearing precedent: it already solves "detect an ambiguous numeric convention from column evidence, fail closed, let a human resolve once, never guess" for decimal commas. The date-order detector is its structural sibling and should mirror its shape exactly (a pure classifier module, an explicit ambiguity predicate, a `resolve_ambiguity`-style function). Verified against this repo's real fixtures: `helixbio_export.csv`'s `Experiment Date` column (`03/11/2025` .. `08/11/2025`) is **genuinely ambiguous** — every value has both components ≤ 12. `meridian_cro_codes.xlsx`'s `DT` column (`01-01-2025` .. `21-01-2025`) and `pinnacle_labs_export.csv`'s `Date` column (`01/01/2025` .. `14/01/2025`) are **unambiguous** — a day value >12 appears, proving day-first order. `castlebio_native_dates.xlsx` and the legacy `pd.read_excel(dtype=str)` path both confirm Excel-native date cells arrive as the Python string `"2025-01-01 00:00:00"` (a `str(datetime)`, not a bare date), which the candidate-format list must include explicitly. `dateutil.parser` is present only as a transitive dependency (via pandas) and its default behavior — silently assuming MM/DD (or worse, guessing) on an ambiguous string — is the exact failure mode this requirement exists to prevent. **Recommendation: do not use `dateutil`; use an explicit candidate-format list + `datetime.strptime`, exactly mirroring `locale.py`'s own approach.**

For **Python-first alias matching**, `service._reconcile_map`/`_alias_index` (already shipped in Phase 08) is not just a precedent — it is *nearly* the exact mechanism INGEST-02 asks for: an exact-normalized-name pre-fill against a Schema's crosswalk, followed by a mapper call on a *reduced* `FieldSet` holding only the uncovered fields. The one substantive design fork is vendor scoping: `_reconcile_map`'s index is keyed `(vendor, normalised_header)` because a reconcile always has a chosen vendor; a **plain** upload (no map file) has no vendor selected at all under the locked D-10-01 three-control UI. Recommendation: build a vendor-agnostic index for the plain-upload path, and treat a header whose normalized name maps to two *different* canonical fields across different vendors as **unresolved** (never guess which vendor), letting it fall through to Claude.

For the **Schema editing endpoint**, the store already migrated from SQLite to PostgreSQL (commit `3f8168e`, quick task `260712-ghn`) — verified by reading `src/assayingest/learning/postgres_schema_store.py` and `src/assayingest/persistence/models.py` directly, not assumed. The existing store is strictly augment-only (`ON CONFLICT DO NOTHING` throughout); a genuine edit/delete endpoint needs new store methods that issue real `UPDATE`/`DELETE` statements — the ABC has none today. A real gap: `AliasRow`'s and `CanonicalFieldRow`'s foreign keys have **no `ON DELETE CASCADE`**, so a naive `DELETE FROM canonical_field` while an alias still references it will raise a foreign-key violation; the new store method must delete dependent aliases first, in the same transaction. A second genuinely open question: does "provenance recorded as a manual edit" (D-10-12) mean a **soft delete** (tombstone, preserving who/when removed something, consistent with `ALIAS-03`'s whole point) or a plain hard `DELETE`? This needs a decision, not just an assumption — flagged in Open Questions.

For **frontend page deletion**, `frontend/src/state/routing.ts`'s `tabFromPath`/`pathForTab` functions are a pure, already-unit-tested allowlist fallback: removing `"define-fields"`/`"registry"` from `TAB_VALUES` in `App.tsx` makes a stale bookmark to either path resolve to `TAB_VALUES[0]` automatically, with zero new code. This was verified by reading the actual implementation, not assumed from the UI-SPEC's claim.

**Primary recommendation:** build the date detector as a new pure module `src/assayingest/parsing/structure/date_order.py` (mirrors `locale.py`'s shape byte-for-byte), invoke it from a new `service.py` orchestration step that sits between the Python/Claude mapping resolution and the existing `validate()` call, and represent the ambiguous case as a new `DateFormatQuestion`/`DateFormatConflict` pair in `domain/models.py` (mirrors `ReconcileQuestion`/`ReconcileConflict`'s exact shape) rather than overloading `parsing/hint.py`'s `StructureQuestion`, since the date question needs post-mapping context (which field a column was mapped to, and that field's declared `date_format`) that a pre-mapping structural question never carries.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Date-order ambiguity detection | API / Backend (pure Python) | — | D-10-04 explicitly forbids an LLM call; must run identically under `headers_only` |
| Date-order human question + resolution | API / Backend (orchestration) + Frontend (panel) | — | Mirrors `StructureQuestion`/`ReconcileQuestion`: backend decides+asks, frontend renders+submits, backend re-resolves |
| Python-first alias crosswalk matching | API / Backend | — | Reuses `Schema`'s already-persisted crosswalk; no client involvement, no LLM |
| Schema constraint + alias CRUD | API / Backend (store) | Frontend (Schemas page) | The store owns SCHEMA-04 isolation and ALIAS-03 provenance structurally (foreign keys, unique constraints); the frontend is a thin view/edit surface over it |
| Sign-in-required gate | Frontend (interstitial) | API / Backend (`require_user`/`require_verified_user`, unchanged) | The frontend gate is UX-only; the real gate is already server-side per-endpoint (existing convention, unchanged by this phase) |
| Page deletion / rename routing fallback | Frontend | — | `tabFromPath`'s allowlist is pure client-side routing; no backend involvement |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `datetime.strptime`/`re` | 3.13 (project baseline) | Date parsing against an explicit candidate-format list | Zero new dependency; mirrors `canonical.convert_date`'s and `structure/locale.py`'s existing approach exactly `[VERIFIED: codebase — canonical.py:39-52, parsing/structure/locale.py]` |
| `openpyxl.utils.datetime.from_excel` | 3.1+ (already a project dependency) | Convert a raw numeric Excel serial to a `datetime` when a date-formatted cell arrives unconverted | `openpyxl` already solves the 1900-epoch/leap-year-bug arithmetic correctly; hand-rolling it would duplicate a tested library function (Don't Hand-Roll) `[CITED: openpyxl docs — openpyxl.utils.datetime module]` |
| SQLAlchemy Core (`update`, `delete`) | 2.x (already a project dependency, per `postgres_schema_store.py`'s `sqlalchemy.dialects.postgresql.insert` usage) | Real `UPDATE`/`DELETE` statements for the new Schema edit endpoint | The existing store only ever uses `insert(...).on_conflict_do_nothing(...)`; a genuine edit/delete needs the plain `update()`/`delete()` constructs from the same already-imported `sqlalchemy` package — no new dependency `[VERIFIED: codebase — persistence/models.py, learning/postgres_schema_store.py]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Alembic | already a project dependency (`api/app.py::_require_schema_at_head` reads it) | Only if the planner chooses the soft-delete/tombstone design (new nullable columns on `AliasRow`/`CanonicalFieldRow`) | Not needed if hard-delete is chosen (see Open Questions) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Explicit candidate-format list + `strptime` | `python-dateutil`'s `parser.parse(dayfirst=...)` | `dateutil` is already present transitively (via `pandas`) but is **not a declared project dependency**; more importantly, its whole design is to *guess* a format and return a best-effort date — even with `dayfirst=True` it silently resolves an ambiguous string rather than refusing, which is precisely the anti-pattern D-10-07 exists to prevent. `[ASSUMED — dateutil's guessing behavior is training-knowledge; not executed against this repo's fixtures in this research session, but consistent with its documented API contract.]` |
| Vendor-agnostic Python-first alias index (new, for plain uploads) | Reusing `service._alias_index`/`_reconcile_map` verbatim (vendor-scoped) | The existing function requires a `vendor` string; a plain (non-map-file) upload under the locked D-10-01 three-control UI has no vendor field to supply. Forcing a vendor prompt onto every plain upload would violate D-10-01's "exactly three controls" contract. |
| Hard `DELETE` for a removed field/alias | Soft delete (tombstone: `removed_at`/`removed_by` columns) | Hard delete is simpler and needs no migration, but loses the "who removed this and when" audit trail that D-10-12's "provenance recorded as a manual edit" phrase suggests should survive — see Open Questions |

**Installation:** No new packages needed for this phase — every recommended tool (`openpyxl`, `sqlalchemy`, stdlib `datetime`/`re`) is already a declared dependency in `pyproject.toml`. If the planner adopts the soft-delete design, no new package is needed either (Alembic is already present); only a new migration file under `alembic/versions/`.

**Version verification:** `openpyxl>=3.1` and `sqlalchemy` (version pinned via `uv.lock`, imported already in `postgres_schema_store.py`) are both already resolved in this project's `uv.lock` — verified by reading `pyproject.toml`'s dependency list directly; no registry lookup needed since nothing new is added.

## Package Legitimacy Audit

**Not applicable.** This phase installs zero new external packages — every tool recommended above (`openpyxl`, `sqlalchemy`, stdlib `datetime`/`re`, and optionally Alembic) is already a declared, in-use dependency of this project (`[VERIFIED: codebase — pyproject.toml dependencies list, read directly]`). No package-legitimacy check is required.

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────────────────┐
                         │           POST /api/upload                │
                         │  (Schema selected -> FieldSet derived)    │
                         └───────────────────┬───────────────────────┘
                                             │
                                             v
                              ┌───────────────────────────┐
                              │  parse()  (unchanged)       │
                              │  -> RawTable | StructureQ   │
                              └──────────┬─────────────────┘
                                         │ RawTable
                                         v
                    ┌───────────────────────────────────────────┐
                    │ resolve_table_mapping()  (extended)          │
                    │                                              │
                    │  1. profile store exact-signature hit? ─yes─>│──> auto-apply (existing, unchanged, zero Claude)
                    │        │no
                    │        v
                    │  2. NEW: Python alias-crosswalk pre-fill      │
                    │     (schema.fields[*].aliases, normalised      │
                    │     header match, vendor-agnostic for a        │
                    │     plain upload)                              │
                    │        │ (fields still unresolved)
                    │        v
                    │  3. Claude propose_mapping() on REDUCED         │
                    │     FieldSet (only unresolved fields)           │
                    └───────────────────┬──────────────────────────┘
                                        │ merged MappingProposal
                                        v
                    ┌───────────────────────────────────────────┐
                    │ NEW: resolve_date_formats()                  │
                    │  for every FieldMapping whose target field    │
                    │  is type="date":                              │
                    │   - classify_column_date_order(mapped values)  │
                    │   - unambiguous, no declared format -> use it  │
                    │   - unambiguous, declared format DISAGREES     │
                    │      -> flag amber (existing validator path)   │
                    │   - AMBIGUOUS -> collect into DateFormatQuestion│
                    └───────────────────┬──────────────────────────┘
                                        │ (if ambiguous columns exist)
                                        v
                    ┌───────────────────────────────────────────┐
                    │ kind="date_question" response (NEW, 4th arm) │
                    │  -> DateFormatQuestionPanel (frontend)         │
                    │  -> POST /api/date-format/resolve (NEW)        │
                    │     re-runs assemble()/validate() with the     │
                    │     human's chosen per-column format, NO        │
                    │     re-parse needed (table already in memory)  │
                    └───────────────────┬──────────────────────────┘
                                        │ (once resolved, or if none were ambiguous)
                                        v
                    ┌───────────────────────────────────────────┐
                    │ validate()  (existing, unchanged call site,   │
                    │  now receives resolved per-file date formats)  │
                    └───────────────────┬──────────────────────────┘
                                        v
                              MappingResponse (existing shape)
```

### Recommended Project Structure

```
src/assayingest/
├── parsing/
│   └── structure/
│       ├── locale.py          # existing precedent (decimal-comma ambiguity)
│       └── date_order.py      # NEW — pure classifier, mirrors locale.py's shape
├── domain/
│   └── models.py              # ADD DateFormatConflict/DateFormatQuestion (mirrors ReconcileConflict/ReconcileQuestion)
├── service.py                 # ADD resolve_date_formats() orchestration step
├── canonical.py                # _convert_field_date signature extended to accept a resolved-format override
├── validation/
│   └── validator.py            # objection note updated to name "declared format contradicts data" distinctly
├── learning/
│   ├── schema_store.py          # ABC gains update_field / delete_field / remove_alias
│   └── postgres_schema_store.py # real UPDATE/DELETE implementations
└── api/
    ├── routes/
    │   ├── schemas.py           # ADD PUT/PATCH edit + DELETE field + DELETE alias routes
    │   └── date_format.py       # NEW — POST /api/date-format/resolve (mirrors reconcile.py's shape)
    └── wire.py                  # ADD DateFormatQuestionResponse, DateFormatChoiceIn, DateFormatResolveRequest

frontend/src/
├── App.tsx                     # TABS array shrinks/renames; DefineFields import removed
├── screens/
│   ├── Schemas.tsx              # NEW (replaces DefineFields.tsx + Registry.tsx)
│   └── Upload.tsx               # SchemaPicker replaces FieldSetPicker; new DateFormatQuestionPanel branch
├── components/
│   ├── SchemaFieldRow.tsx        # NEW
│   ├── DateFormatQuestionPanel.tsx # NEW (mirrors ReconcilePanel.tsx's shape)
│   └── SignInRequiredGate.tsx    # NEW
└── state/
    └── routing.ts               # UNCHANGED — TAB_VALUES allowlist already handles the deleted paths
```

### Pattern 1: The ambiguity-predicate module (mirror of `structure/locale.py`)

**What:** A pure, dependency-free module exposing a classifier over a column's raw string values, an enum of outcomes, and a "resolve with the human's answer" function — exactly `locale.py`'s three-function shape (`classify_column`, `locale_from_separator`, `resolve_ambiguity`).

**When to use:** Any time a structural fact must be inferred from *variance across a column*, never a single cell, and must fail closed to a human question rather than guess.

**Example (recommended shape, adapted from the real `locale.py`):**

```python
# Source: src/assayingest/parsing/structure/locale.py (existing, read verbatim)
# Recommended sibling: src/assayingest/parsing/structure/date_order.py

class DateOrder(str, Enum):
    DAY_FIRST = "day_first"     # DD/MM/YYYY-shaped, proven by a day value > 12
    MONTH_FIRST = "month_first" # MM/DD/YYYY-shaped, proven by a "day"-position value > 12
    ISO = "iso"                 # YYYY-MM-DD or YYYY-MM-DD HH:MM:SS — no order ambiguity at all
    COMPACT = "compact"         # YYYYMMDD, 8 digits — order fixed by convention
    AMBIGUOUS = "ambiguous"     # every value's first two numeric components are both <= 12
    INVALID = "invalid"         # a value has BOTH components > 12 -- not a valid date under either order
    NON_DATE = "non_date"       # no value in the column looks like a date at all
```

The key structural insight (verified against real fixtures, not assumed): unlike `locale.py`'s decimal-comma predicate — which genuinely needs *multiple* values to disambiguate (a single 3-digit comma group can never prove anything) — a date-order predicate can resolve from a **single** value if that value is asymmetric (one component > 12). `data/synthetic/lab_corpus/quill_coag_QF2630229.xlsx`'s single-value `Received='13/07/2026'` field is self-disambiguating (day=13 > 12) even though it appears only once. Do not port `locale.py`'s "single-value column = ambiguous" special case (Pitfall 7) verbatim into the date detector — it does not apply here for the same reason.

### Pattern 2: Post-mapping orchestration, not pre-parse structural detection

**What:** Unlike `locale.py` (invoked from `parsing/table.py::parse()`, before any field semantics exist), the date detector needs to know **which mapped column feeds a `type="date"` field**, and that field's **declared `date_format`** — both only known after Python/Claude mapping resolves. It must therefore run from `service.py`, between the mapping stage and the existing `validate()` call, not from `parse()`.

**When to use:** This is the reason the new domain type belongs beside `ReconcileQuestion`/`ReconcileConflict` in `domain/models.py` (which also arise post-mapping, needing `Schema`/field context) rather than beside `StructureQuestion` in `parsing/hint.py` (which is deliberately parse()-only and field-agnostic).

**Example:**
```python
# Source: src/assayingest/domain/models.py (existing ReconcileQuestion/ReconcileConflict, read verbatim) — mirror this shape
@dataclass(frozen=True)
class DateFormatConflict:
    """One date-typed field whose mapped column's order Python cannot determine."""
    target_field: str
    source_column: str
    example_values: tuple[str, ...]   # first few raw values, for the evidence panel

    def to_dict(self) -> dict: ...

@dataclass(frozen=True)
class DateFormatQuestion:
    conflicts: tuple[DateFormatConflict, ...]

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    def to_dict(self) -> dict: ...
```

### Pattern 3: Python-first alias pre-fill (generalizing `service._reconcile_map`)

**What:** `service._reconcile_map` (`src/assayingest/service.py:655-715`, read verbatim) already implements exactly the shape INGEST-02 asks for: build an index from the Schema's crosswalk, pre-fill every header whose normalized name matches at confidence 1.0 with `needs_confirmation=False`, reduce the `FieldSet` to only the fields no alias covered, and call the mapper (or skip it entirely — `test_short_circuit_never_calls_the_mapper_when_every_field_is_covered`, `tests/test_reconcile_service.py:249`) only on the remainder.

**When to use:** For every plain (non-reconcile) upload, once a Schema is selected and no profile auto-apply hit. This is a genuinely new function (`_python_first_prefill` or similar), not a call to `_reconcile_map` itself, because of the vendor-scoping fork below.

**The vendor-scoping fork (the one substantive design decision for INGEST-02):**

`_alias_index` (`src/assayingest/service.py:638-652`) keys its lookup `(vendor, normalised_header) -> canonical_field_name`. A reconcile always has a chosen vendor (the map-file attach flow). A **plain** upload under the locked D-10-01 three-control UI has no vendor selector at all in the mapping path (the Vendor input that exists on Upload lives inside `MapFileAttach`, only meaningful when a map file is actually attached — see `10-UI-SPEC.md` Screen 2, and Discretion §6 confirms Review's own vendor field is a *post-hoc* label for confirm-time alias recording, not an input to the mapping stage). Recommendation:

```python
def _vendor_agnostic_alias_index(schema: Schema) -> dict[str, str | None]:
    """normalised_header -> canonical_field_name, or None if the SAME
    normalised header maps to two DIFFERENT fields across different vendors
    (an unresolvable collision -- never guess which vendor is right)."""
    index: dict[str, str] = {}
    collided: set[str] = set()
    for cf in schema.fields:
        for alias in cf.aliases:
            key = _normalise_header(alias.source_column)
            if key in index and index[key] != cf.field.name:
                collided.add(key)
            else:
                index[key] = cf.field.name
    return {k: (None if k in collided else v) for k, v in index.items()}
```

A collided (`None`) or absent key is treated as unresolved and falls through to Claude — identical fail-closed posture to the date detector and the existing reconcile-conflict machinery. This function, plus a `field_set`-reducing loop copied from `_reconcile_map`'s existing logic (lines 700-715), is the whole of the new Python-first pass.

**Composition with the EXISTING profile auto-apply (a second design decision worth stating explicitly):** `resolve_table_mapping` already has a *stronger* deterministic mechanism — a whole-file `column_signature` match against a previously-confirmed `LearnedProfile`, applied before any Claude call (`service.py:207-213`). This is not the same mechanism as the new per-column alias crosswalk match, and should not be replaced by it. Recommended composition, in order: (1) exact-signature profile hit — as today, zero Claude calls, skip both the new pass and Claude entirely; (2) **new** Python alias-crosswalk pre-fill on the remaining (no-profile-hit) case; (3) Claude on whatever (2) left uncovered; (4) human, via the existing amber gate. This ordering is not explicitly stated in CONTEXT.md/REQUIREMENTS.md and is this research's own recommendation, grounded in the fact that (1) is already free and already stronger — do not weaken it.

### Anti-Patterns to Avoid

- **Guessing a date order from a training-knowledge heuristic ("most CROs use MM/DD"):** Exactly the class of silent inference D-10-07 forbids. The predicate must be evidence-based (a value with a component > 12) or it must ask.
- **Treating a single-value date column as automatically ambiguous:** Unlike the decimal-locale case, a lone asymmetric date value (day > 12) IS sufficient evidence. Do not import `locale.py`'s Pitfall-7 special case wholesale.
- **Mutating `Field.date_format` on the Schema when a per-file order is resolved:** The detected order is a fact about *this specific upload's column*, not a permanent property of the canonical field (a different vendor's file may use the opposite order for the same target field). The resolved format must be threaded through `canonical.assemble()`/`validate()` as a per-run override, never written back to the stored `Schema`/`Field`.
- **Assuming `openpyxl` always hands back a `datetime` for a date-formatted cell:** Verified false for the raw-serial case — `openpyxl` only converts a cell to a Python `datetime` when its `number_format` is itself recognized as a date format; a genuinely date-valued cell stored under `number_format="General"` (or a corrupted format) comes back as a bare `int`/`float`, and only that case needs `openpyxl.utils.datetime.from_excel()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Excel-serial-to-date conversion (1900 epoch, leap-year bug) | A custom `date(1899,12,30) + timedelta(days=n)` formula | `openpyxl.utils.datetime.from_excel(serial)` | `openpyxl` is already a project dependency and already correctly implements the well-known Excel 1900 leap-year-bug compensation; a hand-rolled formula risks an off-by-one that only manifests for dates before March 1900 |
| Date string parsing/guessing | `dateutil.parser.parse` | Explicit candidate-format list + `datetime.strptime`, mirroring `locale.py` | `dateutil` guesses when ambiguous by design; this requirement exists specifically to replace guessing with an explicit human question |
| SQL update/delete safety for the Schema edit endpoint | Hand-rolled string-interpolated SQL | SQLAlchemy Core `update()`/`delete()` with bound parameters, matching the existing `insert(...)` parameterization already used throughout `postgres_schema_store.py` | The existing store's own docstring states the reason plainly: "a schema name, vendor label, or source-column name is untrusted text... never f-string SQL" (T-07-01, ASVS V5) — the new methods must uphold the same discipline |

**Key insight:** every piece of infrastructure this phase needs (an ambiguity classifier, a "pre-fill then reduce the mapper's scope" pattern, a parameterized-SQL store, an allowlist-fallback router) already exists once in this codebase for an adjacent problem. The research task here was to *find* those precedents precisely, not to survey the wider ecosystem.

## Runtime State Inventory

> This phase renames a page (Registry → Schemas), deletes a page (Define Fields), and touches the persistence layer (new store methods, possibly a new migration). The Runtime State Inventory protocol applies.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `field_set_templates` table (PostgreSQL, per `persistence/models.py:81-92`) still holds every row quick task `260712-e0e` seeded/saved, including an **empty-named row** the builder has explicitly not asked to delete (CONTEXT.md Discretion #4). Deleting the Define Fields UI does not delete these rows — they remain queryable via `GET /api/field-sets` (still used internally by `_resolve_field_set` in `upload.py`). | Code edit only for this phase: leave the table and its rows untouched; `_resolve_field_set` is being replaced by a Schema→FieldSet adapter (see below), so the field-set-template store becomes dead code reachable only by its own (now UI-less) endpoints — a data migration to delete these rows is explicitly NOT required by CONTEXT.md and would risk destroying data the builder wants preserved for now. |
| Live service config | None found. This project has no external service (n8n, Datadog, Tailscale, etc.) whose config lives outside git — verified by grepping `.planning/` and the codebase for any such integration; none exists. | None. |
| OS-registered state | None found. No Task Scheduler entries, no `pm2`/`launchd`/`systemd` units reference "define-fields" or "registry" by name — this is a single-process FastAPI + Vite dev app with no OS-level process registration by name. | None. |
| Secrets/env vars | None found. No `.env` key, SOPS entry, or CI variable references `define-fields`/`registry`/`field_set` by name — verified by grepping `.env.example`. | None. |
| Build artifacts | None found specific to this rename. The frontend is Vite-built on demand; no stale `.egg-info`-style artifact carries the old page names. | None. |
| **Schema store migration (new for this phase)** | The `canonical_field`/`alias` foreign keys have **no `ON DELETE CASCADE`** (verified by reading `persistence/models.py`'s `ForeignKey(...)` declarations directly — no `ondelete=` kwarg anywhere). A field-delete or alias-delete added by this phase must therefore either (a) delete dependent rows explicitly in the same transaction, or (b) add a new Alembic migration granting cascade delete. | Code edit (a) is sufficient and needs no migration; only pursue (b) if the planner also wants the database itself to enforce the cascade (defense in depth) — either way, this is a **new** piece of runtime state behavior this phase introduces, not a pre-existing gap to fix. |

**Nothing found in the "stored data requiring a migration" sense beyond the field-set-template rows and the new cascade-delete gap above** — both are explicitly documented, not silently skipped.

## Common Pitfalls

### Pitfall 1: Assuming a date-formatted Excel cell always arrives as a bare string like `"13/07/2026"`

**What goes wrong:** A detector built only against slash/dot/dash-separated numeric strings silently fails (or worse, mis-parses) on every genuinely Excel-native date cell.
**Why it happens:** Verified directly against `data/synthetic/castlebio_native_dates.xlsx`: `openpyxl.iter_rows(values_only=True)` returns a Python `datetime.datetime(2025, 1, 1, 0, 0)` object for a date-formatted cell (not a string at all), and `parsing/table.py::_row_to_strings`'s `str(cell)` turns that into `"2025-01-01 00:00:00"` — a `str(datetime)` with a literal midnight time suffix, not a bare `"2025-01-01"`. The legacy `pd.read_excel(dtype=str)` path (`_parse_excel_sheet`) produces the **identical** string shape (verified by executing both paths against the same fixture in this research session) — so both code paths agree, which simplifies the detector's job, but only if it explicitly includes `"%Y-%m-%d %H:%M:%S"` in its candidate-format list.
**How to avoid:** Include the `str(datetime)` shape as an explicit, first-class candidate format (order is never ambiguous for this shape — it is already ISO), not an afterthought.
**Warning signs:** A "declared format doesn't match" false-positive on a file that has zero human error — the value simply carries a Python-native time suffix the format list didn't anticipate.

### Pitfall 2: Treating a raw Excel serial (`45678`) as always convertible with a bare arithmetic formula

**What goes wrong:** An off-by-one error for dates before March 1, 1900 (the historical Lotus 1-2-3 leap-year bug Excel preserves for compatibility), or a wrong-by-4-years error on a 1904-epoch workbook (old Mac Excel files).
**Why it happens:** `openpyxl.utils.datetime.from_excel()` already encodes the correct 1900-epoch-with-leap-bug arithmetic; the workbook's own `epoch`/`date1904` flag is needed to pick the right one, but `RawTable` (this project's parsed-table type) currently carries **no** epoch information at all — by the time a string value like `"46092"` reaches the date detector, the workbook object is long gone.
**How to avoid:** Default to the standard 1900 system (correct for the overwhelming majority of real-world `.xlsx` files, including every fixture in this corpus) and add a defensive sanity-range check (e.g. reject a converted date outside roughly 1970–2100) rather than silently accepting an implausible result. Document this as a known limitation, not a silent gap.
**Warning signs:** A converted "date" decades in the past or future relative to the rest of the file's dates.

### Pitfall 3: Silently accepting a declared `date_format` that "successfully" parses every row — even when it is the wrong order

**What goes wrong:** `datetime.strptime("03/04/2025", "%m/%d/%Y")` succeeds with no exception even if the true intended order was day-first — `strptime` cannot detect a semantically-wrong-but-syntactically-valid interpretation. This is the actual danger D-10-06 exists to catch, not merely "a value that fails to parse at all" (which `canonical.convert_date` already catches today, per `tests/test_canonical.py:63-64`).
**Why it happens:** A parse succeeding is not the same as a parse being *correct*. The existing `_conversion_objection_note` in `validation/validator.py` only distinguishes "no date_format declared at all" from a generic "conversion check objected" bucket — it has no mechanism today to compare a *declared* format's implied order against what the column's own independent evidence proves.
**How to avoid:** Always run the evidence-based classifier (Pattern 1 above) regardless of whether a `date_format` is declared. If the classifier finds *unambiguous* evidence (a component > 12 somewhere in the column) that contradicts the declared format's implied order, that is the D-10-06 objection — flag it, even though `strptime` never raised. If the column's own evidence is itself ambiguous, trust the declared format (no independent evidence exists to contradict it) — do not re-ask a human who already made an explicit declaration.
**Warning signs:** A field that looks "clean" (declared format, no parse failures) but was never actually cross-checked against the data — this is precisely the gap the requirement calls out.

### Pitfall 4: Building the ambiguity question inside `parsing/hint.py`'s `StructureQuestion`

**What goes wrong:** `StructureQuestion` is built and answered entirely within `parse()`, before any `FieldSet`/mapping exists — it has no way to carry "which target field" or "what date_format that field declares." Retrofitting those onto it would blur a deliberately field-agnostic, pre-mapping type.
**Why it happens:** Surface-level, `StructureQuestion` "looks like" the right shape to reuse (confidence, proposal, evidence_rows, ask-once). But `ReconcileQuestion`/`ReconcileConflict` in `domain/models.py` are the closer precedent — they already exist specifically for a post-mapping, Schema-aware question.
**How to avoid:** Model the new type after `ReconcileQuestion`, in `domain/models.py`, not after `StructureQuestion`.
**Warning signs:** Needing to smuggle a `target_field`/`date_format` string into `StructuralHint`'s fields, which were never designed to carry them.

### Pitfall 5: Forgetting the `assertNever` exhaustiveness check on the frontend

**What goes wrong:** `Upload.tsx::handleResponse`'s `switch (response.kind)` currently ends in `default: assertNever(response)` (`frontend/src/screens/Upload.tsx:156-159`) specifically so a new response `kind` is a **compile-time** TypeScript error, not a silent fallthrough. Adding `"date_question"` to the `UploadResponse` union without adding its `case` will fail the build, which is the intended safety net — but a planner unaware of this pattern may be surprised by the compile error and try to "fix" it by widening the `default` case instead of adding the real branch.
**How to avoid:** Add `case "date_question":` explicitly, mirroring the existing `reconcile_question`/`structural_question` cases.
**Warning signs:** A TypeScript build failure at `assertNever(response)` after adding the new wire type — this is the mechanism working as designed, not a bug to route around.

## Code Examples

### The verified ambiguity examples (from real fixtures in this repo, executed in this research session)

```python
# Genuinely AMBIGUOUS (every value's two leading numeric components are both <= 12):
# data/synthetic/helixbio_export.csv, column "Experiment Date"
["03/11/2025", "03/11/2025", "04/11/2025", "04/11/2025", "05/11/2025", ...]
# first component: 03,03,04,04,05... (<=12)   second component: 11,11,11,11,11... (<=12)
# -> DateOrder.AMBIGUOUS -- neither "day=03,month=11" nor "month=03,day=11" can be ruled out.

# Genuinely UNAMBIGUOUS by day > 12 (day-first proven):
# data/synthetic/meridian_cro_codes.xlsx, sheet "DATA", column "DT"
["01-01-2025", "03-01-2025", "05-01-2025", ..., "21-01-2025"]
# row with "21-01-2025": first component 21 > 12 -> cannot be a month -> DAY_FIRST, unambiguous.

# Genuinely UNAMBIGUOUS by day > 12 (day-first proven), also present:
# data/synthetic/pinnacle_labs_export.csv, column "Date"
["01/01/2025", ..., "13/01/2025", "14/01/2025"]
# row "13/01/2025": first component 13 > 12 -> DAY_FIRST, unambiguous.

# Genuinely AMBIGUOUS, unpadded single-digit variant:
# data/synthetic/summit_discovery_mixed.xlsx, column "date"
["1/1/2025", "1/2/2025", "1/3/2025", "1/4/2025", "1/5/2025", "1/6/2025", "1/7/2025"]
# first component always "1" (<=12), second ranges 1-7 (<=12) -> AMBIGUOUS.

# Excel-native datetime string (both real openpyxl-direct AND pandas dtype=str paths
# produce this IDENTICAL shape -- verified by executing both in this session):
# data/synthetic/castlebio_native_dates.xlsx, column "Tested On"
"2025-01-01 00:00:00"   # str(datetime.datetime(2025, 1, 1, 0, 0))
# -> ISO, unambiguous, but the candidate-format list MUST include "%Y-%m-%d %H:%M:%S".

# Compact 8-digit, order fixed by convention:
# data/synthetic/cascade_assays_nounit.xlsx, column "run"
["20250101", "20250102", "20250103", ...]  # %Y%m%d

# Raw (unformatted) Excel serial -- the D-10-08 in-scope mechanism, only found today
# embedded in the explicitly OUT-OF-SCOPE fixture (do not use this whole file as a test
# fixture; extract just the mechanism):
# data/synthetic/lab_corpus/wild/10_genelab_date_disaster.xlsx, row 6, "Collection Date"
46092  # a bare Python int via openpyxl -- number_format was NOT a recognized date format
# -> needs openpyxl.utils.datetime.from_excel(46092) rather than strptime at all.

# 2-digit year + time, real fixture:
# data/synthetic/lab_corpus/quill_coag_QF2630229.xlsx, row 4, "Reported"
"07/14/26 13:44"
# second component 14 > 12 -> cannot be a month -> unambiguous MONTH_FIRST (%m/%d/%y %H:%M),
# even though this is a DIFFERENT column than the file's own "Received" (DD/MM) column --
# confirms column-level (not file-level) detection is correct.
```

### Existing "ask once, resolve, re-map" precedent to imitate

```python
# Source: src/assayingest/api/routes/structural_hint.py (existing, read verbatim)
# This exact "pop the retained entry, re-resolve, re-put a fresh token" shape
# is what POST /api/date-format/resolve should mirror -- except it does NOT
# need to re-parse the file (the RawTable is already fully resolved by the
# time a date question is pending), so it only needs to re-run
# canonical.assemble()/validate() with the human's chosen per-column order,
# not service.resolve_or_map() end-to-end.
```

### The exact pre-fill mechanism to generalize

```python
# Source: src/assayingest/service.py:655-715 (_reconcile_map, existing, read verbatim)
# The loop building `prefilled: dict[str, FieldMapping]` from a
# (vendor, normalised_header) -> canonical_field index, then reducing
# `field_set.fields` to only the names NOT in `prefilled` before ever
# constructing a mapper call, is exactly INGEST-02's Python-first pass --
# generalize its index-building function only (drop the vendor key for a
# plain upload), reuse the pre-fill/reduce loop verbatim.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| A date field with a declared `date_format` was unconditionally converted (D-13: "declared = permission to convert") | The declared format is checked against the column's own independent evidence; a contradiction flags the field even if `strptime` never raised | This phase (D-10-06, explicitly supersedes D-13) | The `canonical.py` module docstring's own framing ("a date is converted to ISO-8601 only when the field declares a `date_format`") needs updating alongside the code — it is now a necessary-but-not-sufficient condition |
| Field-set templates (`FieldSetTemplateStore`, `GET/POST /api/field-sets`) were the user-facing "define your fields" concept | The governed `Schema` (Phase 07) is the sole user-facing concept; `FieldSet` survives only as an internal derivation from a `Schema`'s fields | This phase (D-10-02, INGEST-01/05) | `upload.py::_resolve_field_set` needs a new code path: given a `schema_name`, fetch the `Schema` and build a `FieldSet` from `tuple(cf.field for cf in schema.fields)` — verified compatible with `FieldSet.signature` (`fields/models.py:66-79`), since the signature hash depends only on each `Field`'s own attributes (name/type/unit/allowed_values/required/min/max/date_format), not on any alias data, so a Schema-derived `FieldSet` produces the identical signature a previously-promoted field-set-derived one did, and existing learned profiles keep matching |
| `Schema`'s master-map route was the only write path (augment-only, `POST /api/schemas/{name}/master-map`) | A second, explicit edit path exists for real UPDATE/DELETE, gated identically (`require_verified_user`) but never conflated with the augment-only route | This phase (D-10-12) | New `SchemaStore` ABC methods are required; the Postgres store's existing `ON CONFLICT DO NOTHING`-only style must NOT be copied for these new methods — they need real `UPDATE`/`DELETE` |

**Deprecated/outdated:**
- The field-set picker (`FieldSetPicker.tsx`) and its e0e auto-select helpers (`pickDefaultTemplateId`/`readLastTemplateId`/`writeLastTemplateId`/`submitBlockedReason`) are deleted outright, not extended (per `10-UI-SPEC.md` Discretion §5, already locked).
- `Registry.tsx`/`RegistryTable.tsx` are folded into the new `Schemas.tsx`/`SchemaFieldAliasList` (logic reused, not a literal file rename — per the UI-SPEC's Component Inventory).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | `dateutil.parser`'s default behavior silently guesses an order on an ambiguous string rather than raising | Standard Stack / Alternatives Considered | Low — this is a well-known, long-documented property of the library's public API; even if some newer `dateutil` version behaves slightly differently, the core recommendation (explicit candidate list + `strptime`, matching this project's own established pattern) holds regardless |
| A2 | Assuming the standard Excel 1900-epoch system for raw-serial conversion (no 1904-system fixture or workbook-epoch plumbing exists in this codebase to verify against) | Common Pitfalls #2 | Low-medium — a 1904-epoch file (rare, old Mac Excel) would silently convert to a date ~4 years off; mitigated by the recommended sanity-range check, but the check itself is a design recommendation, not a verified requirement |
| A3 | The recommendation to compose the new Python alias pre-fill AFTER the existing profile auto-apply (not replacing or racing it) | Architecture Patterns / Pattern 3 | Medium — CONTEXT.md's D-10-03 does not explicitly address this composition; if the planner instead inserts the new pass BEFORE profile auto-apply, a previously-learned, fully-confirmed profile could be partially overridden by a fresher-but-less-authoritative crosswalk match. Recommend confirming this ordering explicitly with the user during planning/discuss-phase if any doubt remains |
| A4 | Hard-delete vs soft-delete/tombstone is genuinely undecided by CONTEXT.md; this research recommends soft-delete as more consistent with ALIAS-03's provenance principle, but the requirement text does not mandate it | Standard Stack / Alternatives Considered, Open Questions | Medium — choosing wrong means either an unnecessary migration (soft-delete, if the user only wanted simple hard-delete) or a lost audit trail (hard-delete, if the user actually wanted history preserved) |

## Open Questions

1. **Hard delete vs. soft delete (tombstone) for a removed canonical field or alias**
   - What we know: D-10-12 says "only a human may remove or rewrite... with provenance recorded as a manual edit." `ALIAS-03`'s entire design principle is that provenance is *immutable once first seen* — the existing store never overwrites or deletes an alias row today.
   - What's unclear: Does "provenance recorded as a manual edit" mean the *removal itself* must be recorded (who removed it, when) — requiring new columns and a migration — or is it satisfied by the ordinary `require_verified_user` gate plus normal application logs, with a plain hard `DELETE`?
   - Recommendation: Surface this explicitly to the user during `/gsd-discuss-phase` or plan review before committing to a migration; default to hard-delete (simpler, no migration) unless the user confirms an audit trail is required, since REQUIREMENTS.md's INGEST-05 text does not explicitly demand a persisted removal history.

2. **Should `add_or_update_fields`'s name stop being a lie once real updates exist?**
   - What we know: The existing method name (`add_or_update_fields`) already claims to "update," but its actual behavior is `ON CONFLICT DO NOTHING` (never updates an existing field) — the docstring is explicit about this ("an existing field's definition is kept, never overwritten").
   - What's unclear: Whether the planner should rename this existing augment-only method (to avoid the now-doubly-misleading name once a genuinely updating sibling method exists) or leave it as-is and add a differently-named new method (`update_field_constraints` or similar).
   - Recommendation: Leave the existing augment-only method's name unchanged (it is used by the still-augment-only `import_master_map` path, D-07-04, which must not change behavior) and give the new edit method a clearly distinct name (e.g. `update_field`) so the two are never confused at a call site.

3. **Exact HTTP shape for the new edit endpoint(s): one endpoint or several?**
   - What we know: The requirement needs to edit a field's constraints, delete a field, add an alias manually, and remove an alias — four distinct mutations, per the UI-SPEC's "Save Field" / delete-field / "Add Alias" / remove-alias affordances.
   - What's unclear: Whether this collapses into one `PATCH /api/schemas/{name}/fields/{field_name}` (body carries partial constraint updates) plus one `DELETE /api/schemas/{name}/fields/{field_name}` plus one `POST/DELETE .../aliases`, or a single combined edit endpoint.
   - Recommendation: Favor RESTful separation (`PATCH` for constraint edits, `DELETE` for field/alias removal, `POST` for manual alias addition — the manual "Add Alias" mini-form is functionally identical to today's `service._record_aliases`'s manual-provenance path, already exercised by `POST /api/confirm`, so it may not even need a brand-new route — it could reuse the existing alias-recording code path with `provenance_kind="manual"`), matching this codebase's existing convention of one route per HTTP verb per resource (see `schemas.py`'s existing `GET`/`POST` split).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | `SchemaStore`, every other store this phase touches | ✓ (per `persistence/engine.py`'s `DATABASE_URL` requirement and the already-completed `260712-ghn` migration) | Per project's `docker compose` setup (not independently re-verified in this research session) | None needed — already the project's sole persistence layer |
| `openpyxl` | Excel-serial-to-date conversion | ✓ | 3.1+ (declared in `pyproject.toml`) | None needed |
| `python-dateutil` | Explicitly NOT recommended for use | present (transitive, via `pandas`) | Per `uv.lock` (2.9.0.post0) | N/A — recommendation is to not add it as a direct dependency at all |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None — everything needed is already present.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V4 Access Control | Yes | New edit/delete routes gated by `require_verified_user` (the existing FastAPI dependency, already used identically by `schemas.py`'s create/import routes) — never a UI-only mirror |
| V5 Input Validation | Yes | Constraint edits (`type`, `allowed_values`, `min`/`max`, `date_format`) must go through the SAME `fields.loader`/`_validated_name`/`FIELD_TYPES` guards a promoted or imported field already gets (T-07-08 precedent) — never a second, weaker Pydantic-only check at the route layer |
| V1/V11 Business Logic | Yes | SCHEMA-04 isolation (two Schemas never share fields/aliases) must hold for the new edit/delete methods exactly as it does for the existing create/read methods — every new store query must filter by `schema_id`/`canonical_field_id`, never a bare `WHERE name=...` across schemas |
| V6 Cryptography | No | Not applicable to this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| SQL injection via a field name, alias vendor, or source-column string in the new UPDATE/DELETE statements | Tampering | SQLAlchemy Core bound parameters (`update(...).where(...).values(...)`), exactly matching the existing `insert(...)` parameterization pattern already used throughout `postgres_schema_store.py` — never f-string SQL |
| A tampered client claiming `needs_confirmation=False`/a fabricated resolved date order to bypass the ambiguity gate | Tampering / Elevation of Privilege | Mirrors the existing `service.confirm`'s "rebuild fresh, then validate, never trust the client's readiness claim" discipline — the date-format resolve endpoint must re-run `canonical.assemble()`/`validate()` server-side from the human's chosen order, never accept a client-supplied `ready`/`is_ready` flag |
| Cross-schema data leakage via the new edit endpoints (editing/deleting a field that belongs to a *different* Schema than the one named in the URL) | Information Disclosure / Tampering | Every new store method must take `schema_id` as an explicit filter (mirroring `_canonical_field_id`'s existing `WHERE schema_id == ... AND name == ...` pattern) — never look up a field purely by name across all schemas |
| Foreign-key violation surfaced as an unhandled 500 (deleting a field that still has aliases, given the missing `ON DELETE CASCADE`) | Denial of Service (of the edit feature, not the whole app) | Explicitly delete dependent `AliasRow`s before the `CanonicalFieldRow` in the same transaction, inside the store method — never let this surface as a raw `IntegrityError` at the route layer |

## Sources

### Primary (HIGH confidence)

- `src/assayingest/parsing/structure/locale.py` — read and executed against; the direct precedent for the date-order ambiguity predicate.
- `src/assayingest/parsing/structure/header.py` — read; the confidence-margin idiom precedent (not directly reused by the date detector, since the date question fails closed to "ask" rather than picking a best guess, but confirms this project's established "confident vs not, still name a best guess" pattern).
- `src/assayingest/parsing/hint.py` — read; confirms `StructureQuestion`'s pre-mapping, field-agnostic scope.
- `src/assayingest/canonical.py` — read; `convert_date`/`_convert_field_date`'s existing per-row mismatch-flagging behavior, verified against `tests/test_canonical.py`.
- `src/assayingest/validation/validator.py` — read; the existing "date field with no declared format is always flagged" behavior and its objection-note construction.
- `src/assayingest/parsing/table.py` — read; verified the exact string shape Excel-native dates and raw serials arrive as, through BOTH the `parse()`/openpyxl-direct path and the legacy `parse_file()`/pandas path.
- `src/assayingest/service.py` — read in full; `_reconcile_map`/`_alias_index`/`resolve_table_mapping`/`resolve_or_map` are the direct precedents for INGEST-02's Python-first pass and its composition with the existing profile auto-apply.
- `src/assayingest/domain/models.py` — read in full; `Schema`/`CanonicalField`/`Alias`/`ReconcileConflict`/`ReconcileQuestion` shapes, used as the template for the new `DateFormatConflict`/`DateFormatQuestion` types.
- `src/assayingest/learning/schema_store.py` + `src/assayingest/learning/postgres_schema_store.py` + `src/assayingest/persistence/models.py` — read in full; confirmed the PostgreSQL migration's actual current shape (augment-only `ON CONFLICT DO NOTHING`, no `ON DELETE CASCADE`, `seq` Identity columns for deterministic ordering).
- `src/assayingest/api/routes/upload.py`, `structural_hint.py`, `reconcile.py` (referenced), `schemas.py`, `src/assayingest/api/state.py`, `src/assayingest/api/wire.py` — read in full; the discriminated-response-kind pattern and the retained-upload-token registry mechanism this phase's new 4th response kind must mirror.
- `src/assayingest/fields/models.py`, `src/assayingest/fields/loader.py` — read in full; `FieldSet.signature`'s exact hash inputs (confirmed alias-independent, so Schema-derived field sets keep matching existing learned profiles), `MAX_FIELDS=50`, `_validated_name`'s guard.
- `frontend/src/App.tsx`, `frontend/src/state/routing.ts` — read in full; confirmed the allowlist-fallback mechanism the deleted-page bookmark case relies on.
- `frontend/src/screens/Upload.tsx`, `frontend/src/components/ReconcilePanel.tsx`, `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts` — read; the `assertNever`/discriminated-`kind` pattern and the `resolveHint`/`resolveReconcile` frontend-call precedent for the new `resolveDateFormat`-style function.
- Executed directly in this research session: `openpyxl.load_workbook(..., data_only=True).iter_rows(values_only=True)` and `pandas.read_excel(..., dtype=str)` against `data/synthetic/castlebio_native_dates.xlsx` and `data/synthetic/lab_corpus/wild/10_genelab_date_disaster.xlsx`, plus `pandas.read_csv`/`openpyxl` reads of `helixbio_export.csv`, `meridian_cro_codes.xlsx`, `pinnacle_labs_export.csv`, `summit_discovery_mixed.xlsx`, `cascade_assays_nounit.xlsx`, and `lab_corpus/quill_coag_QF2630229.xlsx` — every concrete date value quoted in this document was read from the actual file, not copied from a prior manifest claim.
- `.planning/phases/05-demo-assets-submission/05-CORPUS-MAP.md` — read; cross-checked against the live file reads above (not trusted standalone) to confirm which fixtures cover which date hazards.
- `git show 3f8168e --stat`, `.planning/quick/260712-ghn-migrate-persistence-from-sqlite-to-postg/` — confirmed the Postgres migration commit exists and is the current state.

### Secondary (MEDIUM confidence)

- `openpyxl.utils.datetime.from_excel` API existence and purpose — `[CITED: openpyxl package docs, training knowledge]`, not independently executed against a real serial value in this research session (only read the *symptom*, a bare int, in the real fixture).

### Tertiary (LOW confidence)

- `dateutil.parser`'s exact default-guessing behavior — `[ASSUMED]`, training knowledge about the library's documented public contract, not executed against it in this session.

## Metadata

**Confidence breakdown:**
- Date-format detection mechanics (ambiguity predicate, Excel-native/serial shapes, existing conversion seam): HIGH — every claim was verified by reading this repo's own code and executing it against this repo's own real fixtures.
- Python-first alias matching architecture: HIGH for the reusable precedent (`_reconcile_map`), MEDIUM for the two design forks (vendor-scoping, composition-with-profile-auto-apply) since CONTEXT.md leaves both genuinely open.
- Schema store / edit endpoint: HIGH for the current Postgres store's actual shape (read directly, not assumed stale from the pre-migration docstrings), MEDIUM for the hard-delete-vs-soft-delete recommendation (a real open question, not settled by any locked decision).
- Frontend deletion/rename: HIGH — the allowlist-fallback mechanism was read directly and is exactly as strong as the UI-SPEC claims.

**Research date:** 2026-07-12
**Valid until:** 30 days (stable, hardening-phase codebase; no fast-moving external dependency involved) — but re-verify immediately if any subsequent quick task touches `persistence/models.py`, `service.py`, or `canonical.py` before this phase is planned.
