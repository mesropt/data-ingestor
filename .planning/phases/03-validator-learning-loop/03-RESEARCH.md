# Phase 3: Validator + Learning Loop - Research

**Researched:** 2026-07-10
**Domain:** Pure-Python constraint validation, deterministic content-addressed signatures, a repository-pattern local store (SQLite), and multi-format export — layered onto an existing Clean-Architecture CLI pipeline (parser → mapper → domain → canonical).
**Confidence:** HIGH (this phase adds zero new third-party dependencies; almost every finding is verified directly against this codebase's existing files and Python 3.13 stdlib behavior confirmed by running code in the project's own `.venv` this session)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Profile store (LEARN-02/03)**
- **D-01:** SQLite file, default `.assayingest/profiles.db` in the working directory (add to `.gitignore`), overridable with `--profiles-db PATH`. Persists across CLI runs so the demo money-shot ("second file from lab X = zero yellow") works out of the box and the store's location is visible. A local file is also a confidentiality win (P2): the profile store never travels over a network, unlike a DB server. Postgres is a future swap, not a v1 dependency — the domain (signature, validator) never imports SQLite; a store interface (repository pattern) makes the swap possible without touching domain logic.

**Column signature and format drift (LEARN-01/05)**
- **D-02:** Signature normalisation is strict (P1): case-fold + trim + collapse internal whitespace + Unicode NFC, then order-independent (sorted header set) → hash. It does NOT touch typos, punctuation, or column membership. A typo, a renamed column, or an added/removed column yields a different signature → a different profile. The header set and column count define the signature. Rationale: over-normalising would let one lab's profile apply to a different file, sliding a value into the wrong field — unacceptable for medical data.
- **D-05:** Auto-apply (LEARN-03) only on an exact signature match for the chosen field set → apply the stored column mapping at confidence 1.0 without calling Claude. Any mismatch, including a vendor's format drifting over time (LEARN-04/05), NEVER applies a stale profile: it falls back to a fresh Claude proposal, which can itself be saved as an additional profile. One vendor → several profiles, one per signature; old-format files keep matching their old profile.

**Validator always runs on values (VAL-01/02/03)**
- **D-03:** The validator runs on every value, even when a saved profile auto-mapped the file at confidence 1.0 (P1). A profile records only which column → which field; the values in a new file are new and must be checked. A constraint violation forces the field to needs-confirmation despite the profile's 1.0 or Claude's own confidence. Every one of Claude's ranked alternatives is validated, not only the top pick (VAL-02). OPEN QUESTION — revisit (builder flagged 2026-07-10): whether always re-validating under an auto-applied profile is exactly right, or whether some cases need finer logic. This is the Phase 3 default; do not treat it as final.
- **D-04:** A field with no declared constraints is never silently trusted (VAL-03) — it still depends on Claude's confidence and the human gate; the validator's objection, or its explicit absence, is shown alongside Claude's own reasoning in the CLI review.

**Learning saves and transparency (LEARN-02/06)**
- **D-06:** Saving a profile (LEARN-02) is blocked unless the mapping is fully clear (zero yellow). Key: (field set, signature, mapping).
- **D-07:** A structural hint the user gave for an unfamiliar file in Phase 1 (StructuralHint / PARSE-06) is saved with its profile, so the same odd layout parses automatically next time without re-asking (LEARN-06).
- **D-08:** An auto-applied profile is shown explicitly in output ("applied saved profile <id>"), never disguised as a fresh parse (P1/P2 transparency). The manifest records provenance: auto-applied-from-profile vs fresh-Claude.

**Export and manifest (EXPORT-02/03/04)**
- **D-09:** Export produces CSV + `.xlsx` + JSON, all derived from the one Phase 2 canonical table (Phase 2 D-15). Blocked until the mapping is_ready (zero yellow). Each export is accompanied by a JSON manifest = the saved profile in structure (field set, column signature, field→source-column mapping, inferred/confirmed flags, per-field confidence). Output dir via `-o DIR`, default beside the source file. The tool never writes on its own — export is always an explicit human command (P1).

**Privacy mode (from P2)**
- **D-10:** A `--headers-only` (a.k.a. `--no-sample-rows`) flag makes the mapper send column headers only, no data values, to Anthropic. Mapping is less confident (more yellow for the human to resolve) but no value ever leaves the machine. High priority under P2; MUST be highlighted for the judges in the Phase 5 video and README as a first-class privacy feature.

**Configurable strictness (from P1)**
- **D-11:** A user-selectable strictness setting (e.g. `--strictness strict|lenient` or config), default = strictest / fail-closed. Relaxing it is explicit and recorded in the manifest. Signature matching (D-02) is exempt — never relaxed at any level.

### Claude's Discretion
- Exact SQLite schema, hashing algorithm (e.g. sha256 of the normalised joined header set), and CLI subcommand shape (`export`, `--save-profile`, etc.) are the planner's call, within the decisions above.

### Deferred Ideas (OUT OF SCOPE)
- **Formal medical certification / regulatory path** — CLIA, IEC 62304, ISO 13485, FDA SaMD. Raise explicitly at project close.
- **Data-confidentiality legal/contractual angle** — Anthropic API terms, zero-data-retention configuration, data-ownership rights when values are sent for mapping. Raise together with certification.
- **Fully-local model option** — run the mapper on a local model so no data ever leaves the perimeter. Out of scope while the project is Claude-bound per competition rules.
- **Postgres-backed profile store** — swap SQLite for Postgres once the multi-user API exists (Phase 4+). Enabled by the D-01 store interface; not a v1 dependency.
- **Revisit D-03** (always-validate-under-profile) — builder flagged for a second look; default stands for Phase 3.
- **Not in Phase 3 scope:** Parser hardening (encoding detection, .xls, ragged rows, Excel hazards) — filed in `.planning/todos/pending/`, belongs to a parser-hardening phase.

### Binding Principles (govern every decision above)
- **P1 — Accuracy over convenience. Lives are at stake.** Fail-closed: any ambiguity, any signature mismatch, any doubt → stop and ask the human or fall back to a fresh Claude proposal. Never auto-apply a stale or approximate profile. Speed and convenience never justify a silent guess.
- **P2 — Data confidentiality.** Field values may be confidential scientific IP that must not reach a competitor or a third party (including Anthropic). The learning loop is itself a privacy control (zero Claude calls on a profile hit); `--headers-only` lets the mapper send headers only; the profile store is local SQLite — memory never leaves the machine.
</user_constraints>

## Summary

Phase 3 is not "add a library" work — it is "wire three new pure-Python layers into an existing pipeline correctly." All three subsystems (validator, learning store, export) can be built entirely from the Python 3.13 standard library (`sqlite3`, `csv`, `json`, `hashlib`, `unicodedata`, `dataclasses`) plus `openpyxl`, which is already a project dependency used today only for *reading* — this phase is its first *writing* use. No new packages need to be added to `pyproject.toml`.

The most consequential finding is architectural reuse, not new code: `canonical.assemble()` (Phase 2, already shipped) already performs a large share of VAL-01's per-row type/date/unit-for-text checking and exposes it as `CanonicalTable.flagged` — but that result is currently only *printed*, never wired to `FieldMapping.needs_confirmation`. The validator's highest-leverage move is to call `canonical.assemble()` *before* the human confirms (it has no readiness gate — it's safe to call on an unclear proposal), read `flagged`, and force `needs_confirmation=True` on any field it names. That reuses 100% of Phase 2's decimal-comma, date-format, and text-unit-equality logic with zero duplication, and the *new* code the validator actually has to write shrinks to exactly two checks Phase 2 never implemented: `allowed_values` (case-insensitive, per D-07) and `min`/`max` numeric bounds.

The second most consequential finding is a genuine correctness hazard in the learning loop, not mentioned by name in CONTEXT.md: because the column signature is deliberately case/whitespace/order-independent (D-02), a stored profile's `source_column` string is *not guaranteed to appear verbatim* in a new file with a matching signature — a header can differ in case or incidental spacing and still match the same signature. If the profile stores the raw original-cased header and the reconstruction code does an exact-string `headers.index(...)` lookup (which is what `canonical._column_index` already does), auto-apply will silently and non-obviously fail to resolve columns on a large fraction of legitimately-matching files. The fix is straightforward once seen (store the *normalized* source column plus a duplicate-occurrence rank, resolve against the new file's normalized headers at apply time) but is exactly the kind of trap that produces a demo that works once, in testing, on the exact file used to save the profile, and then mysteriously fails on the "same" file re-exported with different casing.

**Primary recommendation:** Build four new sibling packages mirroring the existing `parsing/`, `mapping/`, `fields/`, `domain/` layering — `validation/` (pure), `learning/` (signature + domain model pure; SQLite store is the one infrastructure module), and `export/` (writers + manifest) — and change `cli.py`'s `_map_one`/`run()` to insert signature lookup, validator, and export/save steps into the existing pipeline rather than bolting them on afterward.

## Architectural Responsibility Map

This project has no browser/API tiers yet (those are Phase 4). The tiers below are this codebase's Clean-Architecture layers, mapped onto the closest generic-tier equivalents so future phases stay legible against the same table shape.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Column signature computation | API/Backend (pure domain logic) | — | No I/O; must be importable and testable without SQLite or a network call, exactly like `FieldSet.signature` today |
| Validator (constraint checks) | API/Backend (pure domain logic) | — | Zero LLM calls, zero I/O (D-03); reuses `canonical.assemble()`'s existing pure computation |
| Profile domain model (`LearnedProfile`) | API/Backend (pure domain logic) | — | Frozen dataclass; no `sqlite3` import (CONTEXT.md code_context) |
| Profile store interface (`ProfileStore` ABC) | API/Backend (pure domain logic) | — | The seam Postgres will implement later (Phase 4+); no `sqlite3` import here either |
| SQLite profile store implementation | Database/Storage | — | The one infrastructure module in the learning package; owns the `sqlite3` import |
| Export writers (CSV/XLSX/JSON) | API/Backend | Database/Storage (filesystem) | Pure transformation of `CanonicalTable` to bytes, then a file write — no business logic |
| Manifest builder | API/Backend | — | Reuses `LearnedProfile.to_dict()` shape (D-09) |
| CLI orchestration (`run()`) | API/Backend | — | Wires signature → profile lookup → (auto-apply \| Claude) → validator → review → save/export |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlite3` (stdlib) | Python 3.13 built-in (SQLite engine 3.53.1 verified this session) | Local profile store | D-01 explicitly chose SQLite behind a store interface; stdlib means zero new install, zero network, which is itself a confidentiality control (P2) |
| `csv` (stdlib) | Python 3.13 built-in | CSV export (EXPORT-02) | Verified this session: `csv.DictWriter` converts `None` to an empty string automatically — no manual `str()`/`""` coercion needed `[VERIFIED: tested in project .venv this session]` |
| `openpyxl` | 3.1.5 (already installed, satisfies `>=3.1` in `pyproject.toml`) | `.xlsx` export (EXPORT-02) | Already the project's Excel *reader*; `Workbook()`/`ws.append()`/`wb.save()` is the same package's write API — no new dependency `[VERIFIED: npm/pip-equivalent — checked installed version via `.venv/bin/python -c "import openpyxl; print(openpyxl.__version__)"` this session]` |
| `json` (stdlib) | Python 3.13 built-in | JSON export + manifest (EXPORT-03/04) | Already used throughout `cli.py`, `canonical.py`, `fields/models.py` |
| `hashlib` (stdlib) | Python 3.13 built-in | Column signature hash (LEARN-01) | `FieldSet.signature` (Phase 2, `fields/models.py`) already establishes this exact pattern (`hashlib.sha256(json.dumps(...).encode("utf-8")).hexdigest()`) — Phase 3 should mirror it verbatim for consistency |
| `unicodedata` (stdlib) | Python 3.13 built-in | NFC normalization for the column signature | Not yet used anywhere in this codebase — first use in Phase 3; verified behavior this session (see Code Examples) |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `uuid` (stdlib) | Python 3.13 built-in | Profile IDs (`LearnedProfile.profile_id`), shown in D-08's "applied saved profile `<id>`" transparency message | Simpler and more collision-proof than composing an ID from truncated signature hashes |
| `dataclasses.replace` | Python 3.13 built-in | Validator's additive update of a `FieldMapping` | Already the established project idiom — `mapping/mapper.py::_cleared_if_optional_and_absent` uses exactly this pattern on the same (non-frozen) `FieldMapping` class |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `sqlite3` (stdlib) | SQLAlchemy / SQLModel ORM | D-01 explicitly says "No ORM" and the domain/infra boundary (repository pattern) is the actual seam that matters, not the ORM — an ORM would also make the future Postgres swap (Phase 4+) *harder*, not easier, since it couples the domain to the ORM's model classes |
| `str.casefold()` | `str.lower()` | D-02 literally says "case-fold"; `casefold()` is the Unicode-correct choice (handles cases `lower()` misses, e.g. German ß) and costs nothing extra — use `casefold()`, not `lower()`, despite `FieldSet._normalise_field` (Phase 2) using `.lower()` for field *names* |
| Sorted list (multiset) for signature | Python `set()`/`frozenset()` | **Do not use a `set`.** Verified this session: `set()` collapses duplicate/blank headers, destroying the "column count defines the signature" invariant D-02 requires. Use `sorted(list_of_normalized_headers)`, which preserves duplicate counts |

**Installation:**
```bash
# No new dependencies. sqlite3/csv/json/hashlib/unicodedata/uuid are stdlib;
# openpyxl is already in pyproject.toml and already installed (3.1.5).
```

**Version verification:** No new packages — verified via `.venv/bin/python -c "import openpyxl; print(openpyxl.__version__)"` → `3.1.5`, and `.venv/bin/python -c "import sqlite3; print(sqlite3.sqlite_version)"` → `3.53.1`, both this session.

## Package Legitimacy Audit

**Not applicable — no new external packages.** Phase 3 is implementable entirely with Python 3.13 stdlib (`sqlite3`, `csv`, `json`, `hashlib`, `unicodedata`, `uuid`, `dataclasses`, `abc`) plus `openpyxl`, which is already a declared and installed project dependency (verified `3.1.5`, satisfying `pyproject.toml`'s `openpyxl>=3.1`). The Package Legitimacy Gate protocol (registry lookup, postinstall-script check, SLOP/SUS/OK verdicts) has no packages to evaluate this phase.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```text
                         ┌─────────────────────────┐
   file path, --fields   │   cli.py :: run()        │
   ─────────────────────▶│                          │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │ parsing.table.parse()      │  (Phase 1, unchanged)
                         │  → RawTable | StructureQ.  │
                         └────────────┬─────────────┘
                                      │ RawTable
                         ┌────────────▼─────────────┐
                         │ learning.signature          │  NEW
                         │  column_signature(headers)  │
                         └────────────┬─────────────┘
                                      │ column_signature (+ field_set.signature)
                         ┌────────────▼─────────────┐
                         │ learning.store.ProfileStore  │  NEW
                         │  .find(field_set_sig,        │
                         │        column_sig)            │
                         └──────┬───────────────┬─────┘
                     hit (exact)│               │ miss / mismatch
                         ┌──────▼──────┐  ┌──────▼─────────────┐
                         │ reconstruct  │  │ mapping.mapper       │  (Phase 2, unchanged
                         │ MappingProposal│ │  .propose_mapping()  │   except headers_only
                         │ at confidence  │ │  → MappingProposal    │   kwarg, D-10)
                         │ 1.0 — NO       │ │  (Claude call)         │
                         │ Anthropic      │ └──────┬─────────────┘
                         │ client built   │        │
                         └──────┬─────────┘        │
                                └─────────┬─────────┘
                                          │ MappingProposal
                             ┌────────────▼─────────────┐
                             │ canonical.assemble()        │  (Phase 2, reused
                             │  → CanonicalTable            │   for its `.flagged`
                             │     (.records, .flagged)      │   side-effect too)
                             └────────────┬─────────────┘
                                          │ CanonicalTable + MappingProposal
                             ┌────────────▼─────────────┐
                             │ validation.validator        │  NEW
                             │  seeds needs_confirmation    │
                             │  from .flagged, adds          │
                             │  allowed_values/min/max,       │
                             │  checks every alternative       │
                             └────────────┬─────────────┘
                                          │ MappingProposal (mutated)
                             ┌────────────▼─────────────┐
                             │ cli.py :: render_report()    │  (Phase 1/2, extended
                             │  is_ready gate (unchanged)     │   to show validator note)
                             └──────┬───────────────┬─────┘
                            ready   │               │ not ready
                    ┌───────────────▼──┐   ┌────────▼─────────┐
                    │ --save-profile     │   │ BLOCKED — same    │
                    │  → learning.store    │   │ exit 5 as today    │
                    │    .save(profile)      │   └───────────────┘
                    │ export.writers        │
                    │  → CSV/XLSX/JSON +      │
                    │    manifest (D-09)       │
                    └───────────────────────┘
```

### Recommended Project Structure
```
src/assayingest/
├── validation/
│   ├── __init__.py
│   └── validator.py       # pure; validate_mapping(), validate_alternatives()
├── learning/
│   ├── __init__.py
│   ├── signature.py       # pure; column_signature(headers) -> str
│   ├── profile.py         # pure domain; LearnedProfile, StoredFieldMapping
│   ├── store.py           # pure; ProfileStore(ABC) — repository interface
│   └── sqlite_store.py    # infra; SqliteProfileStore(ProfileStore) — the ONLY module importing sqlite3
├── export/
│   ├── __init__.py
│   └── writers.py         # write_csv(), write_xlsx(), write_json(), build_manifest()
└── cli.py                 # extended: signature lookup, auto-apply branch, validator call, --save-profile/export flags
```

### Pattern 1: Reuse `canonical.assemble()` as the validator's type/date/unit-for-text engine

**What:** `canonical.assemble()` has no readiness gate — it can be called on an *unclear* `MappingProposal` safely, and its `CanonicalTable.flagged` set already names every field where a decimal-comma conversion failed, a date didn't match `date_format`, or a text field's value didn't equal its declared `unit`.
**When to use:** As the *first* step of the validator, before writing any new per-value logic.
**Example:**
```python
# Source: src/assayingest/canonical.py (existing, Phase 2 — read this session)
tidy = canonical.assemble(table, proposal, field_set)   # safe pre-confirmation; no gate
for mapping in proposal.field_mappings:
    if mapping.target_field in tidy.flagged:
        # This is new-code-you-write in validation/validator.py:
        proposal_field = replace(
            mapping,
            needs_confirmation=True,
            validator_note=(mapping.validator_note or "") +
                " Phase 2 conversion check objected (type/date/unit mismatch)."
        )
```
This is the "Don't Hand-Roll" insight of this phase: writing a second decimal-comma/date-format parser for the validator would duplicate `canonical._convert_by_type`/`canonical.convert_decimal_comma`/`canonical.convert_date` (already correct, already tested) instead of reusing them.

### Pattern 2: Additive-only validator — never clear an existing `needs_confirmation=True`

**What:** The validator may only ever *set* `needs_confirmation=True`; it must never flip an existing `True` back to `False`. VAL-03 requires that a field with *no* declared constraints still depends on Claude's own confidence/gate — the validator's silence must never be read as "safe to clear."
**When to use:** Every call site that produces a new `FieldMapping`.
**Example:**
```python
# NEW — validation/validator.py
def _apply_objection(mapping: FieldMapping, objects: bool, note: str) -> FieldMapping:
    return dataclasses.replace(
        mapping,
        needs_confirmation=mapping.needs_confirmation or objects,  # additive-only
        validator_note=note,
    )
```

### Pattern 3: Signature normalization must be a sorted LIST (multiset), never a `set`

**What:** `column_signature()` must sort a *list* of normalized header strings, preserving duplicate blank/repeated headers, then hash the JSON-serialized list.
**When to use:** Every place a column signature is computed (save-time and lookup-time — they must be bit-identical or auto-apply never fires).
**Example:**
```python
# NEW — learning/signature.py
# Source: verified this session in .venv (see Common Pitfalls for the set() failure demo)
from __future__ import annotations
import hashlib
import json
import unicodedata


def _normalise_header(header: str) -> str:
    """NFC + case-fold + trim + collapse internal whitespace — D-02 STRICT.

    NFC does not fold meaning: it only canonicalises Unicode code-point
    sequences that render as the SAME visual character (e.g. an accented
    letter encoded as one code point vs. base+combining-accent). Without it,
    two files with visually-identical headers could hash differently purely
    from encoding artifacts — a false LEARN-05 drift signal, which D-02
    exists to prevent, not cause. A typo or a genuinely different word is
    UNCHANGED by this function and correctly produces a different signature.
    """
    nfc = unicodedata.normalize("NFC", header)
    return " ".join(nfc.casefold().split())  # trims + collapses all runs at once


def column_signature(headers: list[str]) -> str:
    """Order-independent, duplicate-preserving signature (LEARN-01/D-02).

    A sorted LIST, not a `set` — a `set` silently collapses two blank or
    duplicate headers into one, corrupting the "column count defines the
    signature" invariant D-02 requires.
    """
    normalised = sorted(_normalise_header(h) for h in headers)
    digest = hashlib.sha256(json.dumps(normalised).encode("utf-8"))
    return digest.hexdigest()
```

### Pattern 4: Reconstruct a `MappingProposal` from a stored profile against the NEW file's headers — via normalized lookup, not exact string match

**What:** Because the signature match is normalization-tolerant, the new file's headers are not guaranteed to be byte-identical to the ones the profile was saved against. `canonical._column_index` resolves `FieldMapping.source_column` via `table.headers.index(source_column)` — an **exact** string match. Reconstruction must therefore translate the stored *normalized* source column back into whichever exact header string the new file actually uses.
**When to use:** In the auto-apply branch, before constructing the reconstructed `MappingProposal`.
**Example:**
```python
# NEW — learning/profile.py or cli.py's auto-apply glue
def _resolve_new_header(
    new_headers: list[str], normalised_source: str | None, occurrence: int
) -> str | None:
    """Find the new file's actual header string matching a stored
    (normalised_header, occurrence_rank) pair — occurrence disambiguates
    duplicate/blank headers deterministically by left-to-right order."""
    if normalised_source is None:
        return None
    seen = 0
    for header in new_headers:
        if _normalise_header(header) == normalised_source:
            if seen == occurrence:
                return header
            seen += 1
    return None  # exact-signature match guarantees this should not happen
```

### Pattern 5: The optional-client seam already in `propose_mapping` means auto-apply must not even reach it

**What:** `mapping/mapper.py::propose_mapping(table, field_set, client=None)` only constructs `anthropic.Anthropic()` (which raises `AuthenticationError` if no credentials are configured) when the function is actually **called**. The auto-apply path must therefore never call `propose_mapping` at all — and `run()`'s current unconditional `_has_credentials()` check (D-10/P2: a profile-only user may have no API key configured) must move so it only gates the Claude-required branch.
**When to use:** `cli.py::run()`'s control flow after signature lookup.
**Example:**
```python
# cli.py — sketch of the new run() branch order
def run(path, sheet=None, hint=None, field_set=None, *, profiles_db=None, headers_only=False):
    ...
    tables = outcome
    store = SqliteProfileStore(profiles_db) if profiles_db else SqliteProfileStore()
    for table in tables:
        column_sig = column_signature(table.headers)
        profile = store.find(field_set.signature, column_sig)
        if profile is not None:
            proposal = reconstruct_proposal(profile, table.headers)   # NO client built
            print(f"{_GREEN} auto-applied saved profile {profile.profile_id} "
                  f"(no Claude call)")                                  # D-08
        else:
            if not _has_credentials():                                 # moved here, not global
                ...
            proposal = propose_mapping(table, field_set, headers_only=headers_only)
        proposal = validate(table, proposal, field_set)                # D-03: runs on BOTH paths
```

### Anti-Patterns to Avoid
- **Using `hash()` (Python's builtin) for the signature:** it is salted per-process by `PYTHONHASHSEED` (a security hardening default since Python 3.3) and produces a *different* value every run — a profile saved in one process would never match a lookup in the next. Always use `hashlib.sha256`, exactly as `FieldSet.signature` already does.
- **Duplicating `canonical.py`'s decimal-comma/date logic inside the validator:** Pattern 1 above — call `canonical.assemble()` and read `.flagged` instead.
- **Storing the raw, un-normalized `source_column` string in the profile row:** breaks auto-apply on any header whose case or incidental whitespace differs from the file the profile was saved against — see Pattern 4.
- **Treating `sqlite3.connect(...)`'s `with conn:` block as closing the connection:** verified this session — it only commits/rolls back the transaction; the connection remains open and usable afterward. Not fatal for a short-lived CLI process, but don't rely on it for cleanup; use `contextlib.closing()` or an explicit `conn.close()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-row decimal-comma/date/unit-for-text checking | A second value-conversion parser inside the validator | `canonical.assemble(table, proposal, field_set).flagged` (call it pre-confirmation; it has no gate) | Already correct, already tested (`tests/test_canonical.py`), zero duplication (Pattern 1) |
| Column signature hashing | A hand-rolled string-concatenation hash, or Python's `hash()` | `hashlib.sha256(json.dumps(sorted(normalised_headers)).encode()).hexdigest()`, mirroring `FieldSet.signature` in `fields/models.py` | `hash()` is salted per-process (verified); the project already has one correct, tested pattern for exactly this shape of problem — signature computation should look like a sibling of `FieldSet.signature`, not a new invention |
| CSV `None`-to-empty-string coercion | Manual `"" if v is None else str(v)` per cell before writing | `csv.DictWriter` — verified this session it already writes `None` as `""` automatically | One less place for a silent off-by-one/type bug |
| SQL query building for the profile store | String-formatted SQL (`f"... WHERE sig = '{sig}'"`) | Parameterized `?` placeholders (`conn.execute("... WHERE column_signature = ?", (sig,))`) | Not just style — untrusted file-derived strings (a header could contain a stray `'`) flow into signature computation upstream; SQL injection on a local file is still a real ASVS V5 concern once this store exists |

**Key insight:** The single biggest risk in this phase is *not* "which library to use" (there is no library decision to make) — it is silently reimplementing logic Phase 2 already got right, or silently breaking the exact-signature-match guarantee through a subtle normalization mismatch between save-time and lookup-time. Every "Don't Hand-Roll" row above is really the same lesson twice: reuse the deterministic function that already exists, at both the write and the read side of learning-loop data.

## Common Pitfalls

### Pitfall 1: `set()`/`frozenset()` silently collapses duplicate or blank headers in the signature
**What goes wrong:** Two files with a different number of unlabelled/duplicate-named columns hash to the *same* signature, and a stored profile auto-applies onto a structurally different file — the exact "wrong-file match corrupts data" scenario the binding P1 principle forbids.
**Why it happens:** `set()` is the natural first instinct for "order-independent" — but "order-independent" and "duplicate-collapsing" are different properties, and D-02 explicitly needs only the first.
**How to avoid:** `sorted(list(...))`, never `set(...)`. Verified this session: `set(_normalise_header(h) for h in ['A', '', '', 'B'])` produces `{'', 'a', 'b'}` — the second blank header vanishes.
**Warning signs:** A test asserting "signature is identical when duplicate blank headers are present in different files with different actual column counts" would catch this — write it.

### Pitfall 2: Exact-string source-column lookup breaks auto-apply reconstruction across a normalization-tolerant signature match
**What goes wrong:** A profile saved from a file with header `"Compound ID"` is asked to auto-apply onto a signature-matching file whose same column reads `"compound id"` (lower-case export from a different run of the same vendor's tool). `table.headers.index("Compound ID")` raises `ValueError`, `canonical._column_index` swallows it and returns `None`, and the reconstructed mapping for that field silently loses its column — turning a "zero yellow, auto-applied" demo moment into a wrong or missing field with **no error**, because the auto-applied proposal is (by D-05) built at confidence 1.0/`needs_confirmation=False`.
**Why it happens:** D-02's signature is intentionally case/whitespace-tolerant, but `canonical.py`'s existing column lookup is not — the two were never designed together until now.
**How to avoid:** Store the normalized source column (+ duplicate-occurrence rank) in the profile row; resolve it against the new file's headers via `_normalise_header` equality at apply time, not exact string equality (Pattern 4).
**Warning signs:** A demo-money-shot test using the exact same file twice would NOT catch this (headers are byte-identical to themselves) — it requires a second fixture with a deliberately different case/whitespace variant of the same signature to expose it. Recommend adding exactly that fixture.

### Pitfall 3: Auto-apply still calling `_has_credentials()` (or worse, still constructing an `anthropic.Anthropic()` client) defeats D-10's "learning loop is itself a privacy control"
**What goes wrong:** A user with a matching profile but no `ANTHROPIC_API_KEY` configured gets a spurious exit-3 "no credentials" error even though the whole point of the profile hit is that no API call is needed.
**Why it happens:** `run()`'s current credential check happens unconditionally, before the mapping step, because today there is only one path (always-Claude).
**How to avoid:** Move the credential check inside the "no matching profile" branch only (Pattern 5).
**Warning signs:** A test that unsets `ANTHROPIC_API_KEY`, seeds a matching profile, and asserts a successful (exit 0) auto-apply run would catch this immediately.

### Pitfall 4: `sqlite3`'s WAL/journal side files are not covered by the existing `*.db` `.gitignore` pattern
**What goes wrong:** If SQLite's default rollback-journal mode is ever changed to WAL (or a crash leaves a `-journal` file behind), files like `.assayingest/profiles.db-wal` / `.assayingest/profiles.db-shm` do not match the repo's current `.gitignore` glob (`*.sqlite`, `*.sqlite3`, `*.db`) and could get committed.
**Why it happens:** The existing `.gitignore` was written before this phase existed and only anticipated the main DB file extension.
**How to avoid:** Add a directory-level ignore, `/.assayingest/`, in addition to the existing `*.db` glob — belt-and-suspenders, and also future-proofs against any other file the store might drop in that directory.
**Warning signs:** `git status` showing an untracked `-wal`/`-shm` file after running the CLI a few times.

### Pitfall 5: `Field.unit` on a *numeric* field has no defined cross-field validation semantics yet
**What goes wrong:** `canonical.py`'s own `_unit_mismatch` docstring explicitly punts this: *"Cross-checking a number against a unit carried in some other column is the Phase 3 validator's job, not this function's"* — but the `Field` model has no reference from a numeric field to which *other* field in the same `FieldSet` carries its per-row unit. Attempting to "just check the field named `unit`" would hardcode a domain-specific field-naming convention, violating the project's zero-hardcoded-domain-vocabulary principle.
**Why it happens:** Phase 2 deliberately deferred this (its own code comment says so), and CONTEXT.md's D-03/D-04 don't resolve it either.
**How to avoid:** Scope VAL-01's "unit" check for v1 to exactly what `canonical._unit_mismatch` already checks — a **text**-typed field's cell literally equal to its own declared `Field.unit` (reused via Pattern 1, for free). Do not attempt cross-field unit matching this phase.
**Warning signs:** None — this is a scope decision, not a bug. Flagged below as an Open Question so the planner makes it explicitly rather than by omission.

## Code Examples

### `LearnedProfile` domain model (pure, mirrors `StructuralHint`'s "frozen dataclass + `to_dict()`" shape)
```python
# NEW — learning/profile.py
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..parsing.hint import StructuralHint


@dataclass(frozen=True)
class StoredFieldMapping:
    """One field's resolved mapping, as persisted — enough to reconstruct a
    `domain.models.FieldMapping` at confidence 1.0 without calling Claude."""

    target_field: str
    source_column_normalised: str | None   # None only when inferred_value carries it
    source_column_occurrence: int          # disambiguates duplicate/blank headers
    inferred_value: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LearnedProfile:
    """A confirmed mapping, saved only when the proposal was fully clear
    (D-06). Key is (field_set_signature, column_signature) — one vendor may
    hold several profiles across format drift (LEARN-05)."""

    profile_id: str
    field_set_signature: str
    column_signature: str
    field_mappings: tuple[StoredFieldMapping, ...]
    structural_hint: StructuralHint | None
    created_at: str  # ISO-8601, e.g. datetime.now(UTC).isoformat()

    def to_dict(self) -> dict:
        """The exact shape EXPORT-04's manifest reuses (D-09)."""
        return {
            "profile_id": self.profile_id,
            "field_set_signature": self.field_set_signature,
            "column_signature": self.column_signature,
            "field_mappings": [m.to_dict() for m in self.field_mappings],
            "structural_hint": self.structural_hint.to_dict()
            if self.structural_hint is not None
            else None,
            "created_at": self.created_at,
        }
```

### `ProfileStore` repository interface (pure — no `sqlite3` import)
```python
# NEW — learning/store.py
from __future__ import annotations

from abc import ABC, abstractmethod

from .profile import LearnedProfile


class ProfileStore(ABC):
    """The seam a Postgres-backed store (Phase 4+) implements identically —
    domain and validator code depend only on this, never on `sqlite3`
    (CONTEXT.md code_context, D-01)."""

    @abstractmethod
    def save(self, profile: LearnedProfile) -> None: ...

    @abstractmethod
    def find(self, field_set_signature: str, column_signature: str) -> LearnedProfile | None: ...

    @abstractmethod
    def list_for_field_set(self, field_set_signature: str) -> list[LearnedProfile]:
        """All profiles for one field set — one vendor may hold several
        (LEARN-05); useful for a future `--list-profiles` diagnostic."""
```

### `SqliteProfileStore` (the one module that imports `sqlite3`)
```python
# NEW — learning/sqlite_store.py
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .profile import LearnedProfile, StoredFieldMapping
from .store import ProfileStore
from ..parsing.hint import StructuralHint

_DEFAULT_DB_PATH = ".assayingest/profiles.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    field_set_signature TEXT NOT NULL,
    column_signature TEXT NOT NULL,
    mapping_json TEXT NOT NULL,
    structural_hint_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(field_set_signature, column_signature)
);
CREATE INDEX IF NOT EXISTS idx_profiles_lookup
    ON profiles(field_set_signature, column_signature);
"""


class SqliteProfileStore(ProfileStore):
    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path)) as conn:
            conn.executescript(_SCHEMA)

    def save(self, profile: LearnedProfile) -> None:
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute(
                "INSERT INTO profiles "
                "(id, field_set_signature, column_signature, mapping_json, "
                " structural_hint_json, created_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(field_set_signature, column_signature) DO UPDATE SET "
                "id=excluded.id, mapping_json=excluded.mapping_json, "
                "structural_hint_json=excluded.structural_hint_json, "
                "created_at=excluded.created_at",
                (
                    profile.profile_id,
                    profile.field_set_signature,
                    profile.column_signature,
                    json.dumps([m.to_dict() for m in profile.field_mappings]),
                    json.dumps(profile.structural_hint.to_dict())
                    if profile.structural_hint
                    else None,
                    profile.created_at,
                ),
            )

    def find(self, field_set_signature: str, column_signature: str) -> LearnedProfile | None:
        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM profiles WHERE field_set_signature = ? "
                "AND column_signature = ?",
                (field_set_signature, column_signature),
            ).fetchone()
        return _row_to_profile(row) if row is not None else None

    def list_for_field_set(self, field_set_signature: str) -> list[LearnedProfile]:
        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM profiles WHERE field_set_signature = ?",
                (field_set_signature,),
            ).fetchall()
        return [_row_to_profile(r) for r in rows]


def _row_to_profile(row: sqlite3.Row) -> LearnedProfile:
    mappings = [StoredFieldMapping(**m) for m in json.loads(row["mapping_json"])]
    hint_json = row["structural_hint_json"]
    hint = StructuralHint(**json.loads(hint_json)) if hint_json else None
    return LearnedProfile(
        profile_id=row["id"],
        field_set_signature=row["field_set_signature"],
        column_signature=row["column_signature"],
        field_mappings=tuple(mappings),
        structural_hint=hint,
        created_at=row["created_at"],
    )
```
Note the `ON CONFLICT ... DO UPDATE` (SQLite's upsert syntax, available since SQLite 3.24, well under the installed 3.53.1): re-saving a confirmed mapping for the *same* exact signature pair (e.g. the curator corrects a mistake and re-confirms) overwrites the existing profile rather than erroring — the sane default for "same file layout, corrected again," which is a different situation from LEARN-05's format-drift case (that always produces a *different* signature and therefore a *different* row).

### CSV/XLSX/JSON export (writers.py)
```python
# NEW — export/writers.py
from __future__ import annotations

import csv
import json
from pathlib import Path

import openpyxl

from ..canonical import CanonicalTable


def write_csv(tidy: CanonicalTable, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=tidy.field_names)
        writer.writeheader()
        writer.writerows(tidy.records)  # None -> "" automatically (verified this session)


def write_xlsx(tidy: CanonicalTable, path: Path) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(tidy.field_names)
    for record in tidy.records:
        sheet.append([record.get(name) for name in tidy.field_names])
    workbook.save(path)


def write_json(tidy: CanonicalTable, path: Path) -> None:
    path.write_text(
        json.dumps(tidy.records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Day-1: fixed 7-field schema + hardcoded `ASSAY_TYPES`/`ALLOWED_UNITS` reference dict, no learning loop | User-defined `FieldSet` with declared constraints (Phase 2); Phase 3 adds the no-LLM validator against those *user* constraints and a signature-keyed learning loop | Phase 2 (2026-07-10) generalized fields; Phase 3 (this phase) adds validation/learning against them | The "reference dictionary" concept from the original brief is fully superseded — there is no built-in vocabulary anywhere in the tool now, only what a user's `FieldSet` declares |
| `canonical.assemble()`'s `.flagged` computed but never gates anything | Phase 3 wires `.flagged` into `FieldMapping.needs_confirmation` pre-confirmation | This phase | Closes a real gap: today a `MappingProposal` can be `is_ready` (all green) while `CanonicalTable.flagged` silently names a broken conversion — export was never actually blocked by that |

**Deprecated/outdated:**
- `domain/reference.py`'s original fixed `ASSAY_TYPES`/`ALLOWED_UNITS`/`UNIT_VALUE_RANGES` module: already removed in Phase 2 per `02-PATTERNS.md`; migrated into `presets/assay-potency.yaml` as ordinary user-editable data. Nothing in Phase 3 should resurrect a compiled-in vocabulary.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | "Lenient" strictness (D-11) should reduce validation *coverage* (sample rows only, not every row) while never reducing the *severity* of an in-scope violation — i.e., a two-level strict/lenient switch, not a numeric threshold API | Validator (D-11 discussion, Common Pitfalls) | If the intended meaning is different (e.g., a per-check-type on/off matrix, or a numeric violation-rate threshold), the planner's CLI flag shape and manifest field for `strictness` would need to change; this is a genuine product-design gap CONTEXT.md leaves open, not a technical unknown |
| A2 | VAL-01's "unit" check is scoped to text-typed fields only for v1 (reusing `canonical._unit_mismatch`'s existing semantics exactly); cross-field unit validation for numeric fields (e.g. a `value` field's declared `unit` checked against a *separate* `unit` column) is out of scope this phase | Pitfall 5, Don't Hand-Roll | If the planner or user expects numeric-field unit cross-checking in Phase 3, this narrows VAL-01/VAL-03's actual coverage below what a literal reading might imply — needs explicit sign-off before planning locks it in |
| A3 | Duplicate/blank-header disambiguation in profile reconstruction (occurrence rank, left-to-right) assumes a vendor's duplicate/blank columns keep the same relative order across repeat exports of the "same" format | Pattern 4 | If a vendor's export tool reorders duplicate-named columns between runs (rare but not impossible), auto-apply could map a duplicate column to the wrong field despite an exact signature match — a genuine residual risk with no signature-preserving fix available in v1 (flagged as Open Question 1 below) |
| A4 | CLI stays a single flat command (adds flags: `--profiles-db`, `--save-profile`, `--headers-only`, `--strictness`, `--export DIR`) rather than argparse subcommands, to minimize breakage of the existing `tests/test_cli*.py` suite | CLI shape (Architecture) | CONTEXT.md explicitly leaves subcommand shape to discretion — a subcommand design (`assayingest ingest ...` / `assayingest export ...`) is equally valid and arguably clearer; this is a low-risk, reversible choice either way |

**If this table is empty:** N/A — see rows above.

## Open Questions

1. **Duplicate/blank-header reordering across repeat exports of the "same" vendor format (A3).**
   - What we know: An exact column-signature match guarantees the same *multiset* of normalized headers, including duplicate/blank counts.
   - What's unclear: Whether the *relative left-to-right order* of same-named duplicate/blank columns is also guaranteed to be stable across two exports from the same vendor tool. It very likely is in practice (templates don't reorder columns run-to-run), but nothing enforces it.
   - Recommendation: Ship the occurrence-rank resolution in Pattern 4 as the v1 answer (it is correct whenever order is stable, which is the overwhelmingly common case), and note the residual risk in the manifest/README rather than trying to solve it with additional signal in v1 (would require per-column content-shape heuristics, which is exactly the kind of "silent guess" P1 forbids).

2. **Strictness semantics beyond "default strictest" (A1).**
   - What we know: D-11 requires a user-selectable strictness with a safe-by-default, and that any relaxation is recorded in the manifest; signature matching itself is never relaxed at any level.
   - What's unclear: The exact behavioral difference between "strict" and "lenient" for the validator specifically (row coverage? check-type severity? both?).
   - Recommendation: Confirm A1's proposed interpretation (coverage-only relaxation) with the user during planning/discuss, since it directly shapes the `--strictness` flag's implementation and the manifest schema's `strictness` field.

3. **Where exactly `FieldMapping.validator_note` (a new field this research recommends adding to `domain/models.py`) should be rendered.**
   - What we know: VAL-03 requires the validator's objection *or its explicit absence* to be shown alongside Claude's reasoning in the CLI review.
   - What's unclear: Whether this belongs as a new dataclass field (this research's recommendation) or should instead be appended directly into the existing `reasoning` string (simpler, but conflates two distinct sources of truth — Claude's own reasoning vs. the tool's own deterministic check, which the project's existing hallucination-note pattern in `mapper.py::_with_hallucination_note` already treats as worth keeping textually separate).
   - Recommendation: Add the new field — it mirrors the `_with_hallucination_note` precedent of keeping tool-added annotations legible as distinct from the model's own text, and it is a strictly additive, backward-compatible dataclass change (both `FieldMapping` and `MappingProposal` are already non-frozen "mutable aggregate" dataclasses per project convention, and prior phases have added optional fields to `FieldMapping` before — `inferred_value`, `alternatives`).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `sqlite3` (stdlib) | Learning store (LEARN-02/03) | ✓ | SQLite engine 3.53.1 (verified this session) | — |
| `openpyxl` | `.xlsx` export (EXPORT-02) | ✓ | 3.1.5 (verified this session; satisfies `pyproject.toml`'s `>=3.1`) | — |
| `csv`, `json`, `hashlib`, `unicodedata`, `uuid` (stdlib) | Signature, export, manifest | ✓ | Python 3.13 built-in | — |
| `anthropic` SDK | Fresh-mapper fallback path only (NOT the auto-apply path — Pitfall 3/Pattern 5) | ✓ | 0.116.0 (verified this session; satisfies `>=0.69`) | Auto-apply path works with zero Anthropic credentials by design |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none — everything this phase needs is already present.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface added — the learning store is a local file, not a network service |
| V3 Session Management | no | N/A — CLI, stateless per invocation |
| V4 Access Control | no | Single-user local file; no multi-tenant boundary exists yet (deferred to Phase 4's API) |
| V5 Input Validation | yes | The validator itself (VAL-01/02/03) IS a V5 control — constraint-checking untrusted file content against declared types/ranges/allowed-values before it is trusted. Also: SQL parameterization in `SqliteProfileStore` (never string-format a query with a header-derived value), and the existing `yaml.safe_load`-only field-set loader (Phase 2, unchanged, still the highest-priority security control in the codebase per its own docstring) |
| V6 Cryptography | no (not new this phase) | SHA-256 is used here for content-addressing/deduplication (a signature), not for a security/authentication property — no cryptographic secret is involved, so ASVS V6's stronger requirements (constant-time comparison, key management) don't apply to this specific use |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via a maliciously-crafted header string flowing into the profile store | Tampering | Parameterized `?` placeholders in every `sqlite3` query (Don't Hand-Roll table) — never f-string-format SQL, even though the DB is local; a header comes from an untrusted uploaded file |
| Wrong-profile auto-apply corrupting exported data (P1's core concern) | Tampering / Repudiation | Exact-signature-only matching (D-02/D-05, never relaxed by strictness), plus the normalized-lookup fix in Pattern 4 that prevents a *false negative* (a real match silently failing to resolve a column) from masquerading as export-time data corruption |
| Confidential field values leaving the machine via the Claude API | Information Disclosure | `--headers-only` privacy mode (D-10) sends column names only; the learning loop itself is a privacy control (zero Claude calls on a profile hit, D-10 binding principle) |
| Zip/archive-bomb or path-traversal via a manipulated `--profiles-db` / `-o` path argument | Tampering | Out of this phase's direct scope (no archive handling here), but export/`-o DIR` should resolve to an absolute path and reject a path escaping the intended working directory if this becomes a server-facing feature in Phase 4 — noted for that phase, not blocking here since Phase 3 is still a trusted local CLI operator |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VAL-01 | Validator checks each mapped field against user-declared constraints, no LLM call, flags violations | Pattern 1 (reuse `canonical.assemble().flagged`) + new `allowed_values`/`min`/`max` checks (validator module design, Code Examples) |
| VAL-02 | Objected field forced to needs-confirmation regardless of Claude's confidence; every ranked alternative checked, not only the top pick | Pattern 2 (additive-only update); alternatives checked via `canonical.convert_decimal_comma`/`canonical.convert_date` (already public functions) reused per-alternative without duplicating locale logic |
| VAL-03 | Field with no declared constraints never silently trusted; validator's objection (or its explicit absence) shown alongside Claude's reasoning | Pitfall 5 (unit-check scope decision) + Open Question 3 (`validator_note` field recommendation) |
| LEARN-01 | Order-independent, normalised column signature | Pattern 3 + Code Examples (`learning/signature.py`), verified empirically this session |
| LEARN-02 | Profile saved keyed by (field set, column signature, mapping); blocked unless fully clear | `LearnedProfile`/`StoredFieldMapping` domain model (Code Examples); D-06 gate enforced at the CLI call site (`--save-profile` only proceeds when `proposal.is_ready`) |
| LEARN-03 | Exact signature match auto-applies stored mapping at confidence 1.0, no Claude call | Pattern 5 (client seam) + Pattern 4 (normalized reconstruction) |
| LEARN-04 | Signature mismatch never auto-applies; falls back to Claude | `ProfileStore.find()` returns `None` on any non-exact match — the CLI's existing Claude-call branch is the fallback, unchanged |
| LEARN-05 | One vendor may hold several profiles across format drift | `UNIQUE(field_set_signature, column_signature)` schema constraint (Code Examples: `SqliteProfileStore`) — a drifted format naturally produces a new row, never overwrites the old |
| LEARN-06 | Structural hint saved with its profile, replays automatically | `LearnedProfile.structural_hint: StructuralHint | None` field (Code Examples), reusing `StructuralHint.to_dict()`/reconstruction already established in `parsing/hint.py` |
| EXPORT-02 | CSV and `.xlsx` export | `export/writers.py::write_csv`/`write_xlsx` (Code Examples), zero new dependencies |
| EXPORT-03 | JSON export (array of records) | `export/writers.py::write_json` (Code Examples) — `tidy.records` is already exactly this shape |
| EXPORT-04 | Manifest JSON: field set, signature, mapping, flags, confidence — same shape as saved profile | `LearnedProfile.to_dict()` reused directly as the manifest base, plus appended `provenance`/`strictness`/`exported_at` fields (Architecture Patterns, Summary) |

## Sources

### Primary (HIGH confidence — direct codebase reads and in-session verification)
- `src/assayingest/canonical.py` — read in full; `assemble()`'s no-gate behavior and `.flagged` semantics, and the `_unit_mismatch` docstring's explicit "this is Phase 3's job" pointer
- `src/assayingest/domain/models.py` — `FieldMapping`/`MappingProposal` mutability, `is_ready`/`is_clear` gate logic
- `src/assayingest/fields/models.py` — `FieldSet.signature`'s existing sha256/sorted-JSON pattern (the template this phase's `column_signature` should mirror), D-07 case-insensitive `allowed_values` comment
- `src/assayingest/mapping/mapper.py` — optional-client seam (`propose_mapping(..., client=None)`), `dataclasses.replace` idiom (`_cleared_if_optional_and_absent`), public `convert_decimal_comma`/`convert_date` reuse targets
- `src/assayingest/parsing/hint.py` — `StructuralHint`'s frozen-dataclass + `to_dict()` shape, mirrored for `LearnedProfile`
- `src/assayingest/parsing/table.py`, `src/assayingest/cli.py` — full pipeline read; `_has_credentials()` placement, exit-code scheme (2/3/4/5), `_render_table`'s privacy-mode insertion point
- `.planning/phases/03-validator-learning-loop/03-CONTEXT.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md` — locked decisions D-01..D-11, requirement text
- `.planning/phases/02-user-defined-fields-dynamic-mapper/02-CONTEXT.md` — D-07 (allowed_values case-insensitivity) quoted verbatim, confirming this is a NEW check for Phase 3 (not already implemented in Phase 2)
- In-session verification (`.venv/bin/python`, this project's own virtualenv): `csv.DictWriter` None→"" behavior, `sqlite3`'s `with conn:` not closing the connection, `unicodedata.normalize("NFC", ...).casefold()` collapsing case/whitespace variants to identical strings, `set()` collapsing duplicate blank headers, installed versions of `openpyxl` (3.1.5), `sqlite3`/SQLite (3.53.1), `anthropic` (0.116.0), `pandas` (3.0.3)
- `data/synthetic/novascreen_batch01.csv` / `novascreen_batch02.csv` — read and diffed this session; confirmed byte-identical headers, the ready-made "second file, zero yellow" demo pair
- `data/synthetic/lab_corpus/MAP.md`, `manifest.json`, `README.md` — read; confirmed this corpus is 20+ distinct single-vendor files (no same-vendor signature-matching pair inside `lab_corpus/` itself — see Demo Corpus note below)

### Secondary (MEDIUM confidence)
- SQLite upsert syntax (`ON CONFLICT ... DO UPDATE`) availability since SQLite 3.24 — general SQLite documentation knowledge, not independently re-verified this session beyond confirming the installed engine (3.53.1) is far newer than that minimum

### Tertiary (LOW confidence)
- None — this phase required no external library research; all claims are either direct codebase verification or stdlib behavior tested in-session.

## Demo Corpus Note (for the planner / Phase 5)

`data/synthetic/novascreen_batch01.csv` and `novascreen_batch02.csv` have byte-identical headers (`cmpd, assay, potency, "", target_gene, replicates, date` — verified this session) — this is the ready-made "same signature, second file auto-maps at zero yellow" pair for the learning-loop demo, requiring no new fixture. `data/synthetic/lab_corpus/` (53 files) is a *different* corpus purpose-built for **parser** stress-testing (Phase 1) — every file there is a distinct single vendor per `MAP.md`, so it does not currently contain an in-corpus same-vendor signature-matching pair; it remains excellent material for exercising the *validator* (many vendors' quirks: `operator_vals`, `pending_states`, `unicode_units`, `typos` are exactly VAL-01/VAL-02 test material) but is not itself a learning-loop demo source without either picking two files that happen to share a signature or adding a deliberate same-signature pair.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; every library choice is either already in `pyproject.toml` or Python 3.13 stdlib, versions verified in-session
- Architecture: HIGH — every pattern is grounded in a specific existing file this codebase already ships (canonical.py's flagged/no-gate behavior, mapper.py's optional-client seam, fields/models.py's signature pattern)
- Pitfalls: HIGH for Pitfalls 1-4 (empirically verified in-session); MEDIUM for Pitfall 5 (a scope-boundary judgment call, not a factual claim)

**Research date:** 2026-07-10
**Valid until:** No expiry driver — zero new external dependencies means no library-version drift risk; re-research only if the phase's requirements change
