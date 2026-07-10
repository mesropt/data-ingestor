# Phase 3: Validator + Learning Loop - Pattern Map

**Mapped:** 2026-07-10
**Files analyzed:** 9 new files (+ 2 modified: `cli.py`, `domain/models.py`)
**Analogs found:** 9 / 9 (all have a strong or exact analog already in this codebase; zero library research needed per RESEARCH.md)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/assayingest/learning/signature.py` | utility (pure domain, hash) | transform | `src/assayingest/fields/models.py::FieldSet.signature` (lines 65-79) | exact |
| `src/assayingest/learning/profile.py` | model (pure domain) | transform | `src/assayingest/parsing/hint.py::StructuralHint` (lines 47-65) | exact |
| `src/assayingest/learning/store.py` | service (abstract repository interface) | CRUD | no direct analog — net-new pattern (see below) | none (net-new) |
| `src/assayingest/learning/sqlite_store.py` | service (infra, CRUD, DB) | CRUD | no direct analog — net-new pattern; boundary style borrowed from `mapping/mapper.py::_to_domain` | partial (style only) |
| `src/assayingest/validation/validator.py` | service (pure domain, batch check) | transform / batch | `src/assayingest/canonical.py::assemble()`/`_assemble_record` (lines 73-158) + `mapping/mapper.py::_cleared_if_optional_and_absent` (lines 208-216) | exact (composed of two analogs) |
| `src/assayingest/export/writers.py` | utility (file I/O) | file-I/O | no direct analog — net-new pattern (parser only reads today); serialization shape borrowed from `cli.py::proposal_to_dict`/`canonical.CanonicalTable.to_dict` | partial (shape only) |
| `domain/models.py::FieldMapping.validator_note` (new field) | model (pure domain, additive) | transform | `mapping/mapper.py::_with_hallucination_note` (lines 244-248) | role-match (precedent for a tool-added, textually-distinct annotation) |
| `cli.py::run()` auto-apply/reconstruct branch | controller (CLI orchestration) | request-response | `mapping/mapper.py::propose_mapping` (lines 28-55, optional-client seam) + `cli.py::_map_one` (lines 305-326) | exact |
| `cli.py` new flags (`--profiles-db`, `--save-profile`, `--headers-only`, `--strictness`, `-o`) | controller (arg parsing) | request-response | `cli.py::main()`/`_hint_from_args` (lines 339-411) | exact |

## Pattern Assignments

### `src/assayingest/learning/signature.py` (utility, pure, transform)

**Analog:** `src/assayingest/fields/models.py` — `FieldSet.signature` property, lines 65-79, and its private helper `_normalise_field` (lines 86-102).

**What to copy:**
- The exact "normalise each item → sort the normalised list → `json.dumps(..., sort_keys=True)` → `hashlib.sha256(...).hexdigest()`" shape. `FieldSet.signature` is this project's one existing precedent for a content-addressed identity hash — mirror it verbatim rather than inventing a new hashing convention.
- Docstring style: explain *why* order-independence matters and *what must not* be order-independent (RESEARCH.md Pitfall 1 — sort a **list**, never collapse into a `set`, or duplicate/blank headers vanish and corrupt the D-02 invariant).
- Module docstring convention: state the invariant plainly up front, as `fields/models.py`'s module docstring does ("Pure Python dataclasses with no dependency on pandas...").

**Core excerpt to copy the shape of** (`fields/models.py:75-79`):
```python
normalised = sorted(
    json.dumps(_normalise_field(f), sort_keys=True) for f in self.fields
)
digest = hashlib.sha256(json.dumps(normalised, sort_keys=True).encode("utf-8"))
return digest.hexdigest()
```

**What differs:** the input is `list[str]` headers, not `Field` dataclasses; normalisation adds Unicode NFC + `casefold()` + whitespace-collapse (RESEARCH.md Pattern 3 gives the exact function — `unicodedata.normalize("NFC", header).casefold()` then `" ".join(...split())`). Use `casefold()`, not `.lower()` — `FieldSet._normalise_field` uses `.lower()` for field *names* only, which is a deliberate difference the research calls out (D-02 requires Unicode-correct case-folding for headers, `fields/models.py` doesn't need that strength for its own field-name comparison).

---

### `src/assayingest/learning/profile.py` (model, pure domain)

**Analog:** `src/assayingest/parsing/hint.py` — `StructuralHint` (lines 47-65) for the frozen-dataclass-plus-`to_dict()` shape; also note its own docstring explicitly says it "mirrors `domain/models.py`'s 'propose + confidence + gate' shape" — `LearnedProfile` should mirror this same family style a third time.

**What to copy:**
- `@dataclass(frozen=True)` + all-optional-except-identity fields + a `to_dict()` method returning a plain JSON-safe dict (`hint.py:63-65`, `StructuralHint.to_dict`).
- Compose `StructuralHint` directly as a field (`structural_hint: StructuralHint | None`) and reuse its own `to_dict()`/reconstruction rather than re-flattening it — same idiom `hint.py`'s `StructureQuestion.to_dict()` uses for its nested `proposal: StructuralHint | None` (`hint.py:101`).
- Docstring convention: state which requirement/decision motivates each field (`hint.py`'s docstrings cite `D-02`, `D-07`, `LEARN-06` inline — do the same for `LearnedProfile`/`StoredFieldMapping`, citing D-06/D-08).

**Core excerpt to copy the shape of** (`hint.py:47-65`):
```python
@dataclass(frozen=True)
class StructuralHint:
    sheet_name: str | None = None
    header_row_index: int | None = None
    ...
    def to_dict(self) -> dict:
        return _jsonable(asdict(self))
```

**What differs:** `LearnedProfile`/`StoredFieldMapping` need a nested `to_dict()` that recurses manually (RESEARCH.md's Code Examples block already gives the exact working code) because `asdict()` alone won't call `StructuralHint.to_dict()` for the nested field — follow RESEARCH.md's `LearnedProfile.to_dict()` verbatim, it already handles this correctly.

---

### `src/assayingest/learning/store.py` (ABC repository interface) — **net-new pattern**

**No existing analog in this codebase.** This is the first abstract-base-class / repository-interface seam the project has needed (RESEARCH.md explicitly frames this as new architecture, not a reuse). Flag for the planner: there is no precedent to copy structurally, only a principle to follow — the Clean Architecture boundary already stated in `CLAUDE.md` ("Map infrastructure models to domain models at the layer boundary — don't mix layers in one dataclass") and echoed in this module's own docstring per RESEARCH.md's Code Examples (`ProfileStore(ABC)` with `save`/`find`/`list_for_field_set`, zero `sqlite3` import). Use RESEARCH.md's `learning/store.py` code example directly — it is already correct and was verified against project conventions (docstring citing D-01, `abstractmethod` per method).

**Naming convention to follow project style:** abstract base class named for the *role* (`ProfileStore`), concrete implementation prefixed by its infrastructure (`SqliteProfileStore(ProfileStore)`) — this mirrors how `parsing/table.py`'s `parse()`/`parse_file()` free functions are named for role vs mechanism, though there's no existing ABC to copy verbatim.

---

### `src/assayingest/learning/sqlite_store.py` (infra, CRUD) — **net-new pattern, style borrowed**

**No direct analog** — this is the project's first `sqlite3` import and first infrastructure-only module (everything else in the codebase is either pure domain or the Anthropic SDK boundary in `mapping/mapper.py`). Borrow **error-handling style, not structure** from `mapping/mapper.py::propose_mapping` (lines 28-55): keep the function minimal, let the caller (`cli.py`) decide how to report a failure, never both log and raise (`CLAUDE.md` "Log-or-raise, never both").

**Boundary-mapping precedent to imitate:** `mapping/mapper.py::_to_domain` (lines 175-205) is this codebase's one existing "wire → domain, at the layer edge" translator. `sqlite_store.py::_row_to_profile` (RESEARCH.md's Code Examples has the exact working implementation) plays the identical role for `sqlite3.Row → LearnedProfile`: a private, single-purpose free function that only this module calls, doing exactly the same job `_to_domain` does one layer over (infra row → domain object), never mixing the two shapes in one class.

**What to copy verbatim (from RESEARCH.md, already correct):**
- `contextlib.closing(sqlite3.connect(...))` pattern (`with conn:` alone does NOT close the connection — RESEARCH.md Anti-Pattern, verified this session).
- Parameterized `?` placeholders always — never f-string SQL (`CLAUDE.md`/RESEARCH.md ASVS V5 concern: a header string is untrusted file content).
- `ON CONFLICT(...) DO UPDATE` upsert for re-saving the same signature pair.

**What differs from every existing module:** this is the *only* file in the project allowed to `import sqlite3` — enforce that as a review checklist item, not a code pattern per se.

---

### `src/assayingest/validation/validator.py` (pure domain, batch transform)

**Analog 1 (primary — reuse, don't reimplement):** `src/assayingest/canonical.py::assemble()` / `_assemble_record` (lines 73-158). Per RESEARCH.md Pattern 1, the validator's *first* step must be calling `canonical.assemble(table, proposal, field_set)` and reading `.flagged` — this function already implements the decimal-comma/date/text-unit checking VAL-01 needs; do not write a second parser. `canonical.py`'s docstring itself says as much (line 231: "Cross-checking a number against a unit... is the Phase 3 validator's job, not this function's" — i.e. `canonical.py` was written anticipating exactly this reuse).

**Analog 2 (mutation idiom):** `mapping/mapper.py::_cleared_if_optional_and_absent` (lines 208-216) — the established idiom for producing a new, slightly-modified `FieldMapping` via `dataclasses.replace(mapping, needs_confirmation=..., ...)`. `FieldMapping` is a mutable (non-frozen) dataclass by project convention specifically to allow this additive pattern (`domain/models.py:27`, `@dataclass` not `@dataclass(frozen=True)`).

**Core excerpt to copy the shape of** (`mapping/mapper.py:208-216`):
```python
def _cleared_if_optional_and_absent(
    mapping: FieldMapping, optional_fields: frozenset[str]
) -> FieldMapping:
    is_absent = mapping.source_column is None and mapping.inferred_value is None
    if mapping.target_field in optional_fields and is_absent:
        return replace(mapping, needs_confirmation=False)
    return mapping
```
The validator's `_apply_objection` (RESEARCH.md Pattern 2) is the mirror-image function: it may only ever OR a `True` in (`needs_confirmation=mapping.needs_confirmation or objects`), never flip one back to `False` — this is the critical divergence from the mapper's own idiom above, which *does* clear a flag under a specific condition. State this divergence explicitly in the validator's docstring so a future reader doesn't "fix" it into a symmetric clear/set function.

**Error handling:** none needed — the validator is pure, deterministic, no I/O, no exceptions expected in normal operation (mirrors `canonical.py`'s own "flag instead of raise" convention, lines 10-12 of its module docstring: "Every conversion failure or mismatch flags the field instead of rewriting or raising").

**What's genuinely new code (not reuse):** exactly two checks per RESEARCH.md — `allowed_values` (case-insensitive) and `min`/`max` numeric bounds — plus the "validate every alternative, not just the top pick" loop (VAL-02), which has no existing precedent since `canonical.assemble()` only ever looks at the chosen `source_column`, not `alternatives`.

---

### `domain/models.py::FieldMapping` — add `validator_note: str | None = None`

**Analog:** `mapping/mapper.py::_with_hallucination_note` (lines 244-248) — the existing precedent for a **tool-added, textually-distinct annotation** kept separate from Claude's own `reasoning` string, rather than concatenated into it.

```python
# mapping/mapper.py:244-248 — existing precedent for "tool note, kept separate"
def _with_hallucination_note(reasoning: str, source_column: str) -> str:
    return (
        f"{reasoning} [Flagged by the tool: no column named "
        f"'{source_column}' exists in this file.]"
    )
```

**What differs:** the hallucination note is appended *into* `reasoning` (a string concatenation); RESEARCH.md Open Question 3 recommends the *opposite* choice for the validator — a **separate field** (`validator_note`) rather than concatenation, specifically because VAL-03 needs Claude's reasoning and the tool's own deterministic check to remain visibly distinct sources of truth in the CLI review, and because `FieldMapping` is already a project precedent for adding optional fields backward-compatibly (`inferred_value`, `alternatives` were both added this way — see `domain/models.py:45-46`). Both `FieldMapping` and `MappingProposal` are non-frozen (`@dataclass`, not `@dataclass(frozen=True)`) specifically to allow this kind of additive evolution — confirmed by re-reading `domain/models.py:27-46`.

**CLI render change:** `cli.py::_render_field` (lines 67-83) already branches on `mapping.needs_confirmation` to show `reason:`/`options:` — add a `validator_note:` line inside that same `if not mapping.needs_confirmation: return head` / detail-list branch, following the identical `detail.append(f"      reason: {mapping.reasoning}")` (line 76) pattern.

---

### `src/assayingest/export/writers.py` (file I/O) — **net-new pattern for this codebase, shape borrowed**

**No direct analog for *writing*.** The project has read `openpyxl`/`pandas` only (`parsing/table.py`) — this is the first file-write code in the repo. Flag explicitly for the planner: there is no existing "write a file" function anywhere to copy structurally.

**What to borrow the *shape* of (serialization contract, not I/O mechanics):**
- `canonical.CanonicalTable.to_dict()` (`canonical.py:64-70`) and `cli.py::proposal_to_dict()` (`cli.py:34-40`) both establish the project's "plain JSON-safe dict, `ensure_ascii=False`" convention — `write_json` in RESEARCH.md's Code Examples already follows this (`json.dumps(tidy.records, indent=2, ensure_ascii=False)`), matching `cli.py:197`/`316`/`322`'s existing `ensure_ascii=False` calls verbatim. Keep this consistent — do not default to `ensure_ascii=True` anywhere in the new export path (µM/± and other Unicode unit symbols must survive).
- Input contract: every writer takes a `canonical.CanonicalTable` (already the single source per D-15/Phase 2) — never re-derive records from `RawTable`/`MappingProposal` directly inside a writer; that duplication is exactly what `canonical.assemble()` exists to prevent.

**What's genuinely new:** `write_csv`/`write_xlsx` themselves — RESEARCH.md's Code Examples give working implementations (`csv.DictWriter`, `openpyxl.Workbook()`), already verified in-session (`None` → `""` auto-coercion for CSV). Use those directly; there's no codebase precedent to reconcile them against.

**Manifest builder:** reuse `LearnedProfile.to_dict()` (from `learning/profile.py`) as the manifest's base shape per D-09 — append `provenance`/`strictness`/`exported_at` on top, following the same "base dict + extra keys" idiom `cli.py::_field_to_dict` (lines 43-55) uses when flattening a `FieldMapping` into JSON.

---

### `cli.py::run()` — signature lookup / auto-apply / validator / save / export wiring

**Analog 1 (optional-client seam):** `mapping/mapper.py::propose_mapping(table, field_set, client=None)` (lines 28-36) — the client is constructed *inside* the function body, only when called. This is the seam that makes RESEARCH.md Pattern 5 possible: the auto-apply branch must call **neither** `propose_mapping` nor construct an `anthropic.Anthropic()` client at all — it's not "pass `client=None`", it's "don't call the function on this path."

**Analog 2 (credential-check placement, must move):** `cli.py::run()` currently checks `_has_credentials()` unconditionally at lines 174-180, *before* any mapping is attempted. RESEARCH.md Pitfall 3 requires this move to occur *inside* the "no matching profile" branch only — copy `run()`'s existing try/except shape (lines 164-182) but split it: signature/lookup first, then branch.

**Analog 3 (per-table exit-code aggregation):** `cli.py::_map_and_report`/`_map_one` (lines 289-326) already establish "worst exit code across tables wins" and the exit-code table (2/3/1/4/5) `CLAUDE.md` documents. The new save/export exit paths must extend this same table (e.g. a new code for "export blocked, not ready" — D-09 already reuses is_ready, so this can likely reuse exit 5 rather than invent a new code — planner's call, but follow the existing convention of *documenting* the new code in the module docstring, as `_ask_and_report`'s docstring does for code 4, lines 192-200).

**Core excerpt showing the seam to preserve** (`mapper.py:28-36`):
```python
def propose_mapping(
    table: RawTable, field_set: FieldSet, client: anthropic.Anthropic | None = None
) -> MappingProposal:
    client = client or anthropic.Anthropic()
    ...
```
Auto-apply reconstruction (`reconstruct_proposal(profile, table.headers)` per RESEARCH.md Pattern 4/5) is a **sibling** function at the same call site as `propose_mapping`, never a wrapper around it — it returns the same `MappingProposal` shape via a completely different, client-free path. This mirrors `mapping/mapper.py::_to_domain` (lines 175-205) as its analog target shape: both are "build a `MappingProposal` from some non-domain source" functions, one from Claude's wire response, one from a stored profile row.

**What differs:** reconstruction must resolve headers via `_normalise_header` equality (learning/signature.py) plus an occurrence rank, **not** `canonical._column_index`'s exact `headers.index(...)` (RESEARCH.md Pattern 4/Pitfall 2) — an important divergence from the otherwise-similar-looking `_column_index` (`canonical.py:122-134`), which the planner must not reuse verbatim here.

---

### `cli.py::main()` — new flags

**Analog:** `cli.py::main()` (lines 376-411) and `_hint_from_args`/`_coerce_hint_value` (lines 339-373) — the existing convention for adding a validated, error-raising CLI flag: `argparse.add_argument(...)` in `main()`, a small parsing/validation helper that raises `ValueError` with a consequence-describing message (`CLAUDE.md` convention), caught in the same `try/except (FileNotFoundError, ValueError)` block at lines 405-410 that already exists.

**What to copy:** the exact try/except-around-argument-resolution shape (lines 405-411) — add `--profiles-db`, `--save-profile` (store_true or path), `--headers-only` (store_true), `--strictness` (choices=["strict","lenient"], default="strict" per D-11), `-o`/`--export` as new `parser.add_argument` calls following the existing `--sheet`/`--fields` style (required vs optional, `metavar`, `help` text) at lines 382-403.

**What differs:** none structurally — this is the most direct one-to-one analog in the whole phase.

## Shared Patterns

### Boundary mapping (wire/infra → domain)
**Source:** `mapping/mapper.py::_to_domain` (lines 175-205), `canonical.py::_row_to_profile`-equivalent role (new, in `sqlite_store.py`)
**Apply to:** `learning/sqlite_store.py::_row_to_profile`, `cli.py`'s auto-apply `reconstruct_proposal`
```python
# The one existing precedent — study its shape, not its content
def _to_domain(wire, headers, field_names, optional_fields=frozenset()) -> MappingProposal:
    proposed = {item.target_field: item for item in wire.field_mappings}
    mappings = [...]
    return MappingProposal(source_columns=headers, field_mappings=mappings)
```

### Additive-only dataclass mutation via `dataclasses.replace`
**Source:** `mapping/mapper.py::_cleared_if_optional_and_absent` (lines 208-216)
**Apply to:** `validation/validator.py`'s objection-application function
```python
return replace(mapping, needs_confirmation=..., ...)  # never construct a new object by hand
```

### Frozen-dataclass + `to_dict()` domain model shape
**Source:** `parsing/hint.py::StructuralHint` (lines 47-65), `fields/models.py::Field`/`FieldSet` (lines 25-83)
**Apply to:** `learning/profile.py::LearnedProfile`, `StoredFieldMapping`
```python
@dataclass(frozen=True)
class X:
    ...
    def to_dict(self) -> dict:
        return asdict(self)  # or manual recursion for nested to_dict() objects
```

### Content-addressed sha256 signature
**Source:** `fields/models.py::FieldSet.signature` (lines 65-79)
**Apply to:** `learning/signature.py::column_signature`
```python
normalised = sorted(...)
digest = hashlib.sha256(json.dumps(normalised, sort_keys=True).encode("utf-8"))
return digest.hexdigest()
```

### Error messages describe the consequence, not the symptom
**Source:** `cli.py::_coerce_hint_value` (lines 363-373), project-wide `CLAUDE.md` convention
**Apply to:** every new `ValueError`/`FileNotFoundError` raised in `learning/`, `validation/`, `export/`
```python
raise ValueError(
    f"Cannot apply the hint header-row='{value}': expected a 0-based row number"
) from None
```

### JSON serialization: `ensure_ascii=False`, plain dict shape
**Source:** `cli.py` (lines 197, 316, 322), `canonical.py::CanonicalTable.to_dict` (lines 64-70)
**Apply to:** `export/writers.py::write_json`, manifest builder
```python
json.dumps(payload, indent=2, ensure_ascii=False)
```

## No Analog Found

Files/subsystems with no close existing match — net-new architecture for this phase, called out so the planner treats them as first-of-kind rather than searching further for a codebase precedent that doesn't exist:

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `learning/store.py` (`ProfileStore` ABC) | service | CRUD | First abstract-base-class / repository-interface seam in the project; use RESEARCH.md's Code Examples verbatim, it is already validated against project conventions |
| `learning/sqlite_store.py` | service (infra) | CRUD | First `sqlite3` import in the project; first infrastructure-only (non-domain, non-Anthropic) module |
| `export/writers.py` | utility | file-I/O | First file-*write* code in the project (Excel/CSV/JSON have only ever been read via `parsing/table.py`); `openpyxl`'s write API (`Workbook()`, `ws.append()`, `wb.save()`) has zero prior use in this repo despite the package already being a dependency |

## Metadata

**Analog search scope:** `src/assayingest/` (all modules: `parsing/`, `mapping/`, `domain/`, `fields/`, `canonical.py`, `cli.py`)
**Files scanned:** 9 (all existing source modules read in full this session: `fields/models.py`, `mapping/mapper.py`, `domain/models.py`, `parsing/hint.py`, `canonical.py`, `cli.py`)
**Pattern extraction date:** 2026-07-10
