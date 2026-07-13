# Phase 11: Multi-Sheet Ingest - Research

**Researched:** 2026-07-13
**Domain:** Internal architecture — parser/service/API/wire/frontend seams of this codebase. No external technology domain.
**Confidence:** HIGH (every claim below is `[VERIFIED: codebase]` with a file:line, or a live probe run against the real fixtures)

---

## Summary

This phase needs **no new library, no new dependency, and no external research**. Every question the planner has is a question about *this* codebase's existing seams, and every one of them is answerable by reading code. This document answers them with file:line evidence and a live probe of the four multi-sheet fixtures.

The single most important finding is architectural and it makes the phase **far cheaper than CONTEXT.md fears**: `parse()` already honours an explicit `sheet=` and skips ranking entirely (`table.py:359-367`). If the sheet manifest and the sheet question live **above** `parse()` (at the service/API layer), and each selected sheet is then parsed with `parse(path, sheet=<name>)`, then:

- `parse()`, `_resolve_sheet`, `rank_sheets`, `SheetRanking` are **never touched** — every parsing test stays green (SHEET-04's "each sheet passes the structural gates independently" comes for **free**, because each `parse()` call runs the full header/shape/locale gate for its own sheet);
- the run group can be a **group id owning N existing `upload_token`s**, which leaves `service.confirm`, `service.export`, `_is_review_ready`, the `pending_uploads` write-through, and `GET /api/export/{run_id}/{fmt}` **completely unchanged** (evidence and the rejected alternative are enumerated in §Run Group below);
- every existing API upload test uses a **CSV** (verified: no `.xlsx` is uploaded anywhere in `tests/api/`), so the multi-sheet branch breaks **zero** API tests — D-11-01's no-regression contract is satisfied structurally, not by careful aim.

The second finding is a **contradiction in CONTEXT.md** that the planner must resolve before writing a plan: D-11-01 says the sheet question fires only on "a multi-sheet workbook arriving **without a Schema**". But the browser's only upload path *always* sends a `schema_name` (D-10-01/D-10-02, `SchemaPicker.tsx`), so under that literal reading **SHEET-01/03/04/05 would be unreachable from the UI** and the phase would ship dead code. See §Contradictions.

The third finding is a **latent bug confirmed and larger than CONTEXT.md flagged**: `structural_hint.py:56` drops not just `schema=` but also `sheet=`, `strictness=`, *and* it never checks `result.date_question` — so an ambiguous date column behind a structural question re-creates exactly the Confirm dead-end that quick task `260712-qgc` fixed on `/api/upload`. This phase's sheet question sits upstream of that path and must not inherit the hole.

**Primary recommendation:** Put the sheet manifest + Schema scorer in a new pure-Python module above `parse()`; add a 5th (`sheet_question`) and 6th (`sheet_group`) response arm; implement the run group as a **group index over N ordinary upload tokens**; thread row provenance as a `CanonicalTable.record_sources` list + a reserved `__source_sheet` trailing column threaded explicitly through all four writers; never touch `parse()`/`rank_sheets`/`_prefill_coverage`'s existing behaviour.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-sheet header/row/signature extraction (SHEET-05 primitive) | Parsing (`parsing/structure/sheets.py`) | — | Reads the workbook grid; already owns `list_worksheets`/`detect_header`/`classify_shape`. Must NOT import `learning/` (layer inversion). |
| Column-signature computation | Service | — | `learning/signature.py::column_signature` is a learning-layer concern; `service.py` already imports both parsing and learning (`service.py:59,65`). |
| Schema scoring (N schemas × M sheets) | Service (`service.py`) | — | `_prefill_coverage` / `_vendor_agnostic_alias_index` / `field_set_from_schema` / `SchemaStore.list_schemas` all already live/are reachable here. Pure Python, no LLM (D-11-04). |
| Sheet selection question + retention | API (`api/routes/`, `api/state.py`) | — | It is a *question to a human over HTTP*; the parser must stay network-free and question-free at this level (the `parse()` contract). |
| Run group (1 upload → N member datasets) | API (`api/state.py` + a group index) | — | A group is a *session/correlation* concept, not a domain one. `UploadRegistry` is already exactly this kind of index. |
| Per-row provenance value | Domain (`canonical.py`) | Export (`export/writers.py`) | The value is a fact about the file (`_inferred_constants`, `canonical.py:198`, is the existing precedent); the writers own how each format surfaces it. |
| Archive of N exports | API (`api/routes/export.py`) | — | Serving files is already this module's only job (`export.py:1-12`). |
| Tabbed N-member Review | Frontend (`screens/Review.tsx` + `App.tsx`) | — | — |

---

## Contradictions Between CONTEXT.md and the Code

> The planner MUST resolve these before writing tasks. Each is stated with evidence.

### C-1 (BLOCKING): D-11-01's trigger condition makes the phase unreachable from the UI

**CONTEXT says** (D-11-01): "The new behavior triggers only when the tool cannot proceed without asking: a **multi-sheet workbook** arriving **without a Schema**."

**The code says:**
- `_resolve_field_set` (`upload.py:358-410`) requires exactly one of `schema_name` / `field_set` / `field_set_template_id`, else **422**.
- The browser sends `schema_name` on **every** upload — `SchemaPicker` is the Upload screen's first of exactly three controls (D-10-01/D-10-02).
- Therefore *no* browser upload ever "arrives without a Schema". Under the literal reading, `sheet_question` would only ever fire for a CLI/legacy caller that omits the target — a path that 422s today.

**Worse, the code shows the current multi-sheet UX is already broken in the way SHEET-01 describes.** Live probe (`.venv/bin/python`, `parse()` on the real fixtures):

| Fixture | `rank_sheets` confident? | `parse()` today returns |
|---|---|---|
| `zephyr_bio_ZB-2025.xlsx` (Week 1/2/3, identical layouts) | **False** (0.918 / 0.918 / 0.918) | `StructureQuestion` "which sheet holds the data" |
| `delta_screening_per_target.xlsx` (EGFR/JAK2/BRAF) | **False** (1.0 / 1.0 / 1.0) | `StructureQuestion` |
| `orion_pk_report.xlsx` (Summary/Raw timepoints/Notes) | **False** (1.0 / 0.922 / 0.614) | `StructureQuestion` |
| `meridian_cro_codes.xlsx` (DATA/LEGEND) | **True** (1.0 / 0.829) | `RawTable` for `DATA` — **LEGEND silently discarded** |

So *with* a Schema selected, a multi-sheet workbook today either (a) asks a **single-select** "which sheet" structural question (zephyr/delta/orion), or (b) **silently discards** every other sheet (meridian). Both are exactly the guesses the phase exists to kill. Gating the fix on "no Schema was sent" leaves both in place.

**Recommended reading (and what the planner should build):** the trigger is
> **`>1` real worksheet AND no explicit `sheet=` form param** → `sheet_question`.

`schema_name`'s presence changes only the **pre-selection** (a supplied Schema is pre-selected for every sheet, with its coverage still shown), never whether the question is asked — which is exactly D-11-06 ("for a multi-sheet workbook the sheet-selection screen is **always** shown… no silent auto-apply"). D-11-01's no-regression clause is then satisfied *literally* as written — it scopes itself to "**single sheet** + a Schema chosen upfront", and that path is untouched.

**Making `schema_name` optional is still required** (SHEET-05: "the human never has to know [the Schema] in advance") — but it becomes an *additional* allowance, not the trigger. `_resolve_field_set` must gain a branch: if `schema_name` is absent AND the file is a multi-sheet workbook, do not 422 — go to the sheet question and let the human pick a Schema per sheet there.

### C-2 (minor): D-11-15's "`RawTable.sheet_name` … needs care for CSV/single-sheet" understates it

`RawTable.source_name` is a **tempfile name** on the API path — stated explicitly in `wire.py:141-146` ("Sourced from the route's `UploadFile.filename` … never from `RawTable.source_name`, which is a tempfile's name on the API path"). So neither `sheet_name` (None for single-sheet/CSV, `table.py:328`, `table.py:132`) **nor** `source_name` is usable as a provenance value on the API path. The value must be threaded from the caller. See §Provenance.

### C-3 (scope): "a sheet that fails a gate raises its own question" collides with the single retained temp file

SHEET-04 requires a selected-but-structurally-broken sheet to raise its own `StructureQuestion`. The structural-question retention shape keeps `tmp_path` alive (`upload.py:146-151`) and `/api/structural-hint/resolve` unlinks it on success (`structural_hint.py:99`). With N members sharing **one** temp path, the first member's resolve deletes the file out from under the others. See §Pitfall 3 for the fix (per-member copy).

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| — | — | — | **No new packages are needed for this phase.** |

Everything required already exists in-tree: `openpyxl` (per-sheet grid, `parsing/structure/grid.py`), `pydantic` (wire models), `fastapi` (routes), stdlib `zipfile` (the N-dataset archive), stdlib `shutil` (per-member temp copy).

**Package Legitimacy Audit:** N/A — this phase installs **zero** external packages. No `npm install` / `uv add` task belongs in the plan. If a planner is tempted to add a zip library: `zipfile` is stdlib (`import zipfile`, `ZipFile(path, "w", ZIP_DEFLATED)`) and is the correct answer. [VERIFIED: codebase — no new imports required]

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `zipfile` archive | `tar`/`tarfile` | Zip is what a browser + Windows curator expects on double-click. Tar buys nothing here. Recommend **zip**. |
| Server-side archive route | Client-side "download all" looping the 4 existing per-run URLs | Cheaper, but D-11-10 explicitly says "**exports with one action (an archive of N result sets)**". Build the server route. |

---

## Architecture Patterns

### System Architecture Diagram

```
POST /api/upload  (file, [schema_name], headers_only, [sheet], [map_file])
  │
  ├─ single sheet / CSV / explicit `sheet=` ──► service.resolve_or_map ──► (unchanged 4 arms)
  │                                              mapping | structural_question | reconcile_question | date_question
  │
  └─ >1 worksheet AND no explicit `sheet=`  ──► NEW: service.describe_workbook(path)
                                                  │  (pure Python, no LLM, headers only)
                                                  │
                                                  ├─ parsing.structure.sheets.describe_sheets(path)
                                                  │     per sheet: name, headers, data_row_count, status
                                                  │     status ∈ {ok, drawing_only, unsupported_shape, header_uncertain}
                                                  │
                                                  ├─ learning.signature.column_signature(headers)   per sheet
                                                  │
                                                  └─ NEW: service.propose_schemas_for_sheet(headers, schemas, store)
                                                        1. ProfileStore.find(fs.signature, col_sig)   ← exact learned hit
                                                        2. crosswalk coverage per Schema             ← _prefill_coverage core
                                                        → ranked proposals + coverage detail + tie flag
                                                  │
                                              retain tmp_path + manifest under ONE upload_token
                                                  │
                                                  ▼
                                       kind:"sheet_question"  (5th arm)
                                                  │
                              human picks: [(sheet, schema) …]  — zero-coverage sheets default to SKIP
                                                  │
                                                  ▼
                    POST /api/sheets/resolve  (upload_token, selections[])
                                                  │
                     for each selected sheet:  parse(path, sheet=<name>)   ← existing explicit-sheet branch
                                                  │  (full per-sheet gates: header, shape, decimal locale)
                                                  │  then service.resolve_or_map's mapping half
                                                  ▼
                                       ONE UploadEntry per member (existing shape)
                                       + group_id + sheet + schema_name retained
                                                  │
                                                  ▼
                                       kind:"sheet_group"  (6th arm)
                                       { group_id, members: [ {sheet_name, response: <one of the 4 arms>} … ] }
                                                  │
                    ┌─────────────────────────────┴─────────────────────────────┐
                    ▼                                                            ▼
       Review (tabbed, N members)                              a member may itself still ask:
       each member confirms on its OWN gate                    structural_question | date_question
       POST /api/confirm (per member token)  ← UNCHANGED       (their existing panels, inside the tab)
                    │
                    ▼
       service.export → EXPORT_BASE_DIR/{run_id}/  ← UNCHANGED, one run_id per member
       group index records: group_id → [run_id …]
                    │
                    ▼
       GET /api/export/group/{group_id}/archive   (NEW)  → zip of N run dirs
```

### Recommended Project Structure

```
src/assayingest/
├── parsing/structure/sheets.py      # + describe_sheets() + SheetDescription  (NEW fn, rank_sheets UNTOUCHED)
├── service.py                       # + describe_workbook(), propose_schemas_for_sheet(), SheetProposal
│                                    # + _covered_fields() extracted core (shared with _prefill_coverage)
├── canonical.py                     # CanonicalTable + record_sources; assemble(*, source_sheet=None)
├── export/writers.py                # SOURCE_SHEET_COLUMN = "__source_sheet"; all 4 writers thread it
├── api/
│   ├── state.py                     # UploadEntry + group_id/sheet; NEW GroupRegistry
│   ├── wire.py                      # + SheetQuestionResponse, SheetGroupResponse, SheetResolveRequest
│   └── routes/
│       ├── upload.py                # + multi-sheet branch
│       ├── sheets.py                # NEW: POST /api/sheets/resolve
│       ├── structural_hint.py       # BUGFIX: pass schema=/sheet=/strictness=, handle date_question
│       └── export.py                # + GET /api/export/group/{group_id}/archive
frontend/src/
├── lib/types.ts                     # + SheetQuestionResponse, SheetGroupResponse → UploadResponse union
├── state/upload.ts                  # + sheetQuestion/resolvingSheets/sheetGroup phases + fromResponse cases
├── components/SheetSelectionPanel.tsx   # NEW (multi-select + per-sheet Schema + coverage)
└── screens/Review.tsx               # extract ReviewMember; add tab shell over N members
```

### Pattern 1: The sheet question lives ABOVE `parse()`, never inside it

**What:** Do not teach `parse()` to return N tables or a new question type. Add a pre-parse *description* step, ask the human, then call `parse(path, sheet=<name>)` once per selected sheet.

**Why (the load-bearing evidence):**

```python
# parsing/table.py:349-367  — _resolve_sheet
def _resolve_sheet(path, names, sheet, hint) -> str | StructureQuestion:
    explicit = sheet if sheet is not None else (hint.sheet_name if hint else None)
    if explicit is not None:
        if explicit not in names:
            raise ValueError(f"Cannot ingest {path.name}: sheet '{explicit}' not found …")
        return explicit          # ← ranking is SKIPPED entirely
    if len(names) == 1:
        return names[0]
    ranking = rank_sheets(path)  # ← only reached when NO sheet was named
    ...
```

An explicit `sheet=` short-circuits ranking. So the per-sheet parse of a *selected* sheet takes the exact code path that `tests/test_parse_entry_sheets.py::test_parse_orion_explicit_sheet_proceeds_to_a_raw_table` (`:30`) already pins as green. And because `_parse_excel_structurally` (`table.py:289-346`) runs `detect_header` → `classify_shape` → locale gate → header-confidence gate for **whatever sheet it was given**, SHEET-04's "each selected sheet passes the structural gates independently" is delivered by *doing nothing*.

**Consequence for the test suite:** `parse()`, `_resolve_sheet`, `_sheet_ambiguous_question`, `rank_sheets`, `SheetRanking` all keep today's behaviour byte-for-byte. `tests/test_parse_entry_sheets.py`, `tests/test_structure_sheets.py`, `tests/test_parse_entry_shape.py`, `tests/test_excel_sheets.py`, `tests/test_hint_and_locale.py` all stay green **unchanged**.

### Pattern 2: Per-sheet description — a sibling function, not a widened `SheetRanking`

**What:** Add `describe_sheets(path) -> list[SheetDescription]` to `parsing/structure/sheets.py`. Do **not** widen `SheetRanking`.

**Why not widen:** `SheetRanking` is a frozen dataclass (`sheets.py:42`) consumed by `_resolve_sheet` (`table.py:371`) and `_sheet_ambiguous_question` (`table.py:377-395`), and pinned by `tests/test_structure_sheets.py` (5 tests). Widening it forces `rank_sheets` to compute headers/shape for every sheet on *every* parse of *every* multi-sheet workbook — work the ranking path does not need — and puts a new field in front of tests that assert its exact shape. A sibling function costs one extra `load_workbook` pass on the multi-sheet upload path only.

**Why not "reuse `rows_by_sheet`":** CONTEXT (Claude's Discretion) offers reusing `rank_sheets`'s already-materialized `rows_by_sheet` (`sheets.py:75`). That is real — it does materialize every sheet's grid and discard all but the winner's name — but harvesting it means changing `rank_sheets`'s return type, i.e. the thing Pattern 2 exists to avoid. The saving is one `openpyxl.load_workbook` on a ≤20 MB file (`upload.py:71`), once per upload. **Rejected: not worth the contract change.**

**Shape:**

```python
# parsing/structure/sheets.py  (NEW — rank_sheets and SheetRanking are NOT touched)

class SheetStatus(str, Enum):
    OK = "ok"
    DRAWING_ONLY = "drawing_only"           # is_drawing_only_sheet(ws)  — grid.py
    UNSUPPORTED_SHAPE = "unsupported_shape" # classify_shape(...) != ROW_PER_RECORD
    HEADER_UNCERTAIN = "header_uncertain"   # detect_header(...).confident is False, or .index is None

@dataclass(frozen=True)
class SheetDescription:
    name: str
    headers: list[str]      # [] when no header row was resolvable
    row_count: int          # DATA rows below the header (never the raw grid height)
    status: SheetStatus

def describe_sheets(path: str | Path) -> list[SheetDescription]:
    """Every real worksheet's headers + data-row count + structural status, in
    workbook order. A sheet that fails a structural gate is DESCRIBED and
    MARKED, never omitted -- the manifest must show it (SHEET-01) and the
    human may still select it (SHEET-04), in which case parse() raises that
    sheet's own StructureQuestion."""
```

Reuses, verbatim: `list_worksheets` (`grid.py:37`, chartsheets structurally excluded — D-17), `is_drawing_only_sheet` (`grid.py`, called at `table.py:325`), `detect_header` (called per sheet at `table.py:314`), `classify_shape` (`table.py:341`).

**The probe proves every status branch is reachable on the real corpus:**

| Fixture | Sheet | `detect_header` | shape | ⇒ status |
|---|---|---|---|---|
| zephyr | Week 1/2/3 | idx=4, confident | row_per_record | `ok` (header on row 5 — the manifest must show *resolved* headers, not row 0) |
| delta | EGFR / JAK2 / BRAF | idx=0, confident | row_per_record | `ok` (3 different header spellings — the crosswalk case) |
| orion | Summary | idx=0, confident | row_per_record | `ok` |
| orion | Raw timepoints | idx=0, confident | row_per_record | `ok` |
| orion | **Notes** | **idx=None, confident=False** | row_per_record | **`header_uncertain`** ← `detect_header().index` **can be `None`**; `describe_sheets` must not `rows[None]` |
| meridian | DATA | idx=0, confident | row_per_record | `ok` |
| meridian | **LEGEND** | idx=0, **confident=False** | row_per_record | **`header_uncertain`** → headers `['CMP','compound identifier']` → **zero coverage** → propose **skip** (D-11-06) |

`describe_sheets` must **not** import from `learning/` — `column_signature` is computed one layer up, in `service.py`, which already imports both (`service.py:59,65`). Keeping `parsing/` free of `learning/` preserves the dependency direction CLAUDE.md mandates.

### Pattern 3: The Schema scorer — hoist the index, don't fork `_prefill_coverage`

`_prefill_coverage` (`service.py:1572-1597`) returns exactly what SHEET-05 needs and reads `table.headers` only (`:1586`) — headers-only-safe by construction (D-11-04). But it rebuilds `_vendor_agnostic_alias_index(schema)` (`:1584`) on **every** call. Scoring M sheets × N schemas would rebuild each schema's index M times.

**Recommended:** extract the shared core, so both callers use one implementation (no fork, no duplication):

```python
# service.py
def _covered_fields(headers: list[str], index: dict[str, str | None]) -> dict[str, str]:
    """canonical field name -> the header that matched it. First header wins;
    a colliding alias (index value None) matches nothing (T-10-12)."""
    covered: dict[str, str] = {}
    for header in headers:
        name = index.get(_normalise_header(header))
        if name is not None and name not in covered:
            covered[name] = header
    return covered

def _prefill_coverage(table, field_set, schema):          # UNCHANGED signature/return
    index = _vendor_agnostic_alias_index(schema)
    covered = _covered_fields(table.headers, index)
    prefilled = {name: FieldMapping(target_field=name, source_column=header,
                                    confidence=1.0,
                                    reasoning=f"pre-filled from the schema crosswalk for {header!r}",
                                    needs_confirmation=False)
                 for name, header in covered.items()}
    remaining = tuple(f for f in field_set.fields if f.name not in prefilled)
    return prefilled, remaining
```

`tests/test_python_first_prefill.py` + `tests/api/test_upload_schema_target.py` guard this refactor (they pin the exact prefill/escalation behaviour). Note the **first-header-wins** rule is preserved (`:1588` `canonical_name not in prefilled`) — do not change it.

**The scorer:**

```python
@dataclass(frozen=True)
class SchemaProposal:
    schema_name: str
    matched: dict[str, str]        # canonical field -> the header that matched it  (D-11-03: "which fields matched which header")
    uncovered: tuple[str, ...]     # canonical fields with no header
    total: int                     # len(schema.fields)
    source: str                    # "profile" | "crosswalk"
    @property
    def score(self) -> float: return len(self.matched) / self.total if self.total else 0.0

def propose_schemas_for_sheet(headers, schemas, store) -> tuple[SchemaProposal, ...]:
    """Ranked, best first. D-11-05 order: (1) exact learned-profile hit,
    (2) crosswalk alias coverage. Pure Python, no LLM, headers only.
    NEVER auto-applies and NEVER breaks a tie (D-11-06)."""
```

- Stage 1 (profile): for each schema, `fs = field_set_from_schema(schema)` (`service.py:1431`), then `store.find(fs.signature, column_signature(headers))` (`store.py:30`, exact-match only, `UniqueConstraint` ⇒ at most one row — `recall_vendor`'s docstring, `service.py:1511-1516`). A hit ⇒ `source="profile"`, full coverage, ranked first.
- Stage 2 (crosswalk): `_covered_fields(headers, _vendor_agnostic_alias_index(schema))`, index built **once per schema**, reused across all M sheets.
- Ranking: sort by `(source == "profile", score)` descending. **Tie** = top two scores equal ⇒ report `tie=True` and pre-select **nothing** (D-11-06: "a tie is shown as a tie — the tool does not break it"). **Zero coverage** (`score == 0.0` for every schema) ⇒ pre-select **skip** (D-11-06). There is deliberately **no threshold constant** — unlike `_CONFIDENCE_MARGIN = 0.1` (`sheets.py:28`).
- Input: a headers-only stub is sufficient — `_covered_fields` reads a `list[str]`, never a `RawTable`, so no stub table is needed at all (an improvement on CONTEXT's "a headers-only stub `RawTable` is sufficient").

### Pattern 4: Row provenance — a parallel list, never a `Field`

D-11-12/D-11-13 are correct and the code confirms *why*, precisely:

- `FieldSet.signature` hashes **only** each `Field`'s own attributes (`service.py:1436-1440` documents this). Adding `source_sheet` as a `Field` changes the signature ⇒ `store.find(field_set.signature, …)` (`service.py:254`) misses ⇒ **every learned profile silently stops matching**. The learning loop *is* the product differentiator.
- `_assemble_record` (`canonical.py:166-187`) iterates `field_names` **only** (`:178`), so an extra key in `records` can only come from an explicit code path.
- `write_csv` uses `csv.DictWriter(fh, fieldnames=tidy.field_names)` (`writers.py:45`) — an extra key in a record dict **raises `ValueError`**.
- `write_xlsx` does `[record.get(name) for name in tidy.field_names]` (`writers.py:58`) — an extra key is **silently dropped**.
- `write_json` dumps `tidy.records` verbatim (`writers.py:66`) — an extra key **appears**, inconsistently with the other two.

So the provenance column *must* be explicit. Recommended shape:

```python
# canonical.py
SOURCE_SHEET_COLUMN = "__source_sheet"   # reserved; leading "__" cannot collide with a
                                         # canonical field name (fields.loader rejects it)

@dataclass(frozen=True)
class CanonicalTable:
    field_names: list[str]
    records: list[dict[str, str | float | None]]
    flagged: list[str] = field(default_factory=list)
    record_sources: list[str] = field(default_factory=list)   # NEW, parallel to `records`, len == len(records)

def assemble(table, proposal, field_set, *, date_formats=None, source_sheet: str | None = None) -> CanonicalTable:
    ...
    return CanonicalTable(..., record_sources=[source_sheet or "" for _ in records])
```

`record_sources` is a **parallel list**, not a key inside `records` — so `records` stays exactly the shape `write_json`/`write_xlsx`/`write_csv` already consume, and each writer opts in deliberately:

```python
def write_csv(tidy, path):
    fieldnames = tidy.field_names + ([SOURCE_SHEET_COLUMN] if tidy.record_sources else [])
    writer = csv.DictWriter(fh, fieldnames=fieldnames)
    writer.writeheader()
    for record, source in zip_longest(tidy.records, tidy.record_sources, fillvalue=""):
        writer.writerow({**record, SOURCE_SHEET_COLUMN: source} if tidy.record_sources else record)

def write_xlsx(tidy, path):
    sheet.append(tidy.field_names + ([SOURCE_SHEET_COLUMN] if tidy.record_sources else []))
    for record, source in zip(...):
        sheet.append([record.get(n) for n in tidy.field_names] + ([source] if tidy.record_sources else []))

def write_json(tidy, path):
    payload = [{**r, SOURCE_SHEET_COLUMN: s} for r, s in zip(tidy.records, tidy.record_sources)] \
              if tidy.record_sources else tidy.records

def build_manifest(..., source_sheet: str | None = None):
    return { …, "source_sheet": source_sheet, … }   # additive key
```

**Why the defaulted-empty `record_sources` matters:** `validate()` calls `canonical.assemble()` as its type/date engine (`validator.py:130`) and must keep behaving identically. With `source_sheet` keyword-only and defaulted `None`, the validator's call is untouched and `flagged` cannot change. `assemble()` has exactly **three** call sites: `cli.py:598`, `validator.py:130`, `service.py:463`. The writers have exactly **one** call site: `service.export` (`service.py:580-582`). Small, enumerable blast radius. [VERIFIED: codebase grep]

**Where the value comes from (D-11-15 — write it on EVERY ingest):** neither `RawTable.sheet_name` nor `RawTable.source_name` can supply it:
- `sheet_name` is `None` for a single-sheet workbook (`table.py:328`, `:132` — `tag = target if len(names) > 1 else None`) and for every CSV (`_parse_csv_structurally`, `table.py:234`, never sets it).
- `source_name` is a **tempfile name** on the API path (`wire.py:141-146`).

Two options:

| Option | Change | Verdict |
|---|---|---|
| **P-A (recommended)** Add `RawTable.origin_sheet: str \| None = None`, set **unconditionally** to the worksheet title in `_raw_table_from_header_row` (`table.py:464-470`) and `_parse_excel_sheet` (`table.py:133`); leave `sheet_name` (the disambiguation *tag*) alone. CSV ⇒ `origin_sheet=None`. The provenance value written = `table.origin_sheet or entry.source_file_name` (the client's real filename, already retained at `state.py:155`). | Additive defaulted field; `RawTable.label` (`table.py:44-48`) and therefore the **Claude prompt** (`mapper.py:143 "Source file: {table.label}"`) and the CLI banner (`cli.py:494`) are unchanged. Persist it in `_entry_to_json`/`_entry_from_json` (`state.py:316-322`, `:354-360`) with a `.get()` default so old rows rehydrate. | **Recommended** |
| P-B Drop the `len(names) > 1` condition so `sheet_name` is always set. | 1 line — but it changes `RawTable.label` for every single-sheet workbook, which changes the **text sent to Claude** (`mapper.py:143`) and the CLI output (`cli.py:494`), and `tests/test_excel_sheets.py:71` asserts `tables[0].sheet_name is None` for a one-sheet workbook. | **Rejected** — a behaviour change to the mapper prompt for a bookkeeping win. |

### Pattern 5: The run group — a group id over N ordinary upload tokens

**Recommended: Option A.** A `group_id` owning N existing `upload_token`s. `UploadEntry` gains three defaulted fields (`group_id`, `sheet`, and — for the structural-hint bugfix — `schema_name` is already there at `state.py:145`).

**Exhaustive enumeration of what each option forces you to change** (the evidence CONTEXT asked for):

| Function / contract | Option A (group of tokens) | Option B (`UploadEntry` holds N tables) |
|---|---|---|
| `UploadEntry` (`state.py:75-155`) | +3 defaulted fields | `table: RawTable \| None` → `tables: list[RawTable]` — **breaking** |
| `_is_review_ready` (`state.py:272-285`) | **unchanged** (each member is independently review-ready: `table` + `field_set`, no `tmp_path`, no `proposal`, no `map_envelope`) | must be re-derived "per member inside one entry" — a *partially* confirmed entry has no honest answer to "is this row persistable?" |
| `pending_uploads` write-through `_persist`/`_entry_to_json`/`_entry_from_json` (`state.py:240-373`) | +3 additive JSON keys, read with `.get()` | the persisted row's `table` object becomes a list; `_entry_from_json` must rebuild N tables; **`tests/api/test_pending_upload_persistence.py` breaks** |
| `service.confirm` (`service.py:360-472`) | **unchanged** | signature must take a member index or a table; the `FieldCoverageError`/`NotReadyError` gates become per-member |
| `confirm.py` route (`confirm.py:82-212`) | **unchanged** for the gate; +5 lines to record `run_id` into the group index | `entry.table` is read at `:83`, `:145`, `:196` — all three break; the 422 bodies must name a member |
| `service.export` (`service.py:561-589`) | **unchanged** (still one run per member) | must loop, and `export_dir`'s fixed filenames (`export.csv`…) collide across sheets — the exact hazard STATE.md already records ("a multi-sheet export into one DIR would overwrite across sheets") |
| `GET /api/export/{run_id}/{fmt}` (`export.py:46-59`) | **unchanged**; add a sibling group-archive route | must learn a member axis: `/{run_id}/{member}/{fmt}` — a URL contract change |
| `MappingResponse` (`wire.py:108-185`) | **unchanged** (one per member) | must carry N proposals ⇒ `types.ts::MappingResponse` and `Review.tsx` (which takes a single `mapping: MappingResponse`, `Review.tsx:39`) both break |
| `date_format.py` (`:62,71,98,112,126`) | **unchanged** (a member with a date question is just a normal date-question entry) | five `entry.table` / `entry.proposal` reads break |
| Registry LRU/eviction (`state.py:219-236`) | N tokens instead of 1 — `_MAX_ENTRIES = 200` is ample | unchanged |

**Verdict: Option A is decisively less invasive.** It changes **0** of the single-table read paths and adds new surface only where genuinely new capability exists. Option B breaks the confirm gate, the date-question route, the persistence round-trip, the wire contract, and the Review screen's props. **Rejected.**

```python
# api/state.py  (NEW, beside UploadRegistry)
@dataclass
class UploadGroup:
    """One multi-sheet upload's N member datasets (D-11-08: N INDEPENDENT
    datasets, never merged). `members` is (sheet_name -> upload_token); `runs`
    accumulates each member's export run_id as it confirms, so the group
    archive route can find them."""
    members: dict[str, str]              # sheet_name -> upload_token
    runs: dict[str, str] = field(default_factory=dict)   # sheet_name -> run_id
    source_file_name: str | None = None

class GroupRegistry:
    def put(self, group: UploadGroup) -> str: ...   # mints group_id = str(uuid.uuid4())
    def get(self, group_id: str) -> UploadGroup | None: ...
    def record_run(self, group_id: str, sheet_name: str, run_id: str) -> None: ...
```

Memory-only is acceptable and consistent: the *members* are already persisted individually by the existing `pending_uploads` write-through (each is review-ready ⇒ `_is_review_ready` is True ⇒ `_persist`), so a restart loses only the "download all" convenience, never a curator's review. Say so explicitly in the plan rather than silently accepting it.

**`run_id` minting stays exactly where it is:** `confirm.py:194` `run_id = str(uuid.uuid4())`, one per confirmed member, one export dir each (`EXPORT_BASE_DIR / run_id`, `confirm.py:43`). The fixed export filenames (`export.csv` etc., `service.py:580-582`) are safe because each member gets its **own directory**.

### Pattern 6: The 5th and 6th response arms

`/api/upload` gains `kind:"sheet_question"`. `/api/sheets/resolve` returns `kind:"sheet_group"`, whose members each carry **one of the existing four arms** — so a member that still needs a structural or date question reuses `StructuralHintPanel` / `DateFormatQuestionPanel` verbatim, inside its tab. This is why a *recursive* group arm beats inventing a "multi_mapping" arm: it is the only shape that is honest about a member still having a question.

```python
# api/wire.py  (follow date_format.py's precedent exactly — CONTEXT D-11-02)

class SheetSchemaProposalOut(BaseModel):
    schema_name: str
    matched: list[dict]            # [{"field": "...", "header": "..."}]  ← D-11-03: coverage must be VISIBLE
    uncovered: list[str]
    matched_count: int
    total_fields: int
    source: Literal["profile", "crosswalk"]

class SheetOut(BaseModel):
    sheet_name: str
    row_count: int
    headers: list[str]             # NOT redacted under headers_only: a header is not a cell value (D-10-05)
    column_signature: str
    status: Literal["ok", "drawing_only", "unsupported_shape", "header_uncertain"]
    proposals: list[SheetSchemaProposalOut]   # ranked; [] means zero coverage
    proposed_schema: str | None    # the pre-selection; None ⇒ propose SKIP (zero coverage OR a tie)
    tie: bool

class SheetQuestionResponse(BaseModel):
    kind: str = "sheet_question"
    upload_token: str
    sheets: list[SheetOut]

class SheetSelectionIn(BaseModel):
    sheet_name: str
    schema_name: str               # the human's Schema for THIS sheet (different sheets may differ — SHEET-05)

class SheetResolveRequest(BaseModel):
    upload_token: str
    selections: list[SheetSelectionIn]   # empty ⇒ 422 (fail closed; nothing to ingest)

class SheetMemberOut(BaseModel):
    sheet_name: str
    response: dict                 # one of the four existing arms, serialized

class SheetGroupResponse(BaseModel):
    kind: str = "sheet_group"
    group_id: str
    source_name: str | None
    members: list[SheetMemberOut]
```

Route `POST /api/sheets/resolve` in a new `api/routes/sheets.py`, gated by `Depends(require_user)` — mirroring `date_format.py:59` and `structural_hint.py:44` exactly (D-10-13: a signed-out client must not be able to drive a retained upload to completion).

Frontend (`types.ts:205` union + `upload.ts:124` `assertNever`) — adding the two kinds is a **compile-time error until handled**, which CONTEXT rightly calls a feature:

```ts
export type UploadResponse =
  | MappingResponse | StructuralQuestionResponse | ReconcileQuestionResponse
  | DateFormatQuestionResponse
  | SheetQuestionResponse            // NEW
  | SheetGroupResponse;              // NEW

// state/upload.ts — new phases
| { phase: "sheetQuestion";  file: File; response: SheetQuestionResponse; uploadToken: string }
| { phase: "resolvingSheets"; file: File; uploadToken: string }
| { phase: "sheetGroup";     file: File; response: SheetGroupResponse; groupId: string }
// + actions SUBMIT_SHEETS / SHEETS_SUCCESS / SHEETS_ERROR, and two new cases in fromResponse()
// + toDropzonePhase(): "sheetQuestion" | "resolvingSheets" | "sheetGroup" → "locked"  (upload.ts:137-159)
```

### Anti-Patterns to Avoid

- **Teaching `parse()` to return N tables.** It breaks the `RawTable | StructureQuestion` contract that `service.resolve_or_map` (`service.py:332-335`), `reconcile_or_map` (`:1163`), `apply_reconcile_resolution` (`:1226`) and every parsing test depend on. Parse per selected sheet instead.
- **Putting `source_sheet` in the `FieldSet`.** Breaks `FieldSet.signature` ⇒ every learned profile stops matching (D-11-13, confirmed at `service.py:1436-1440`).
- **Smuggling the provenance value into `CanonicalTable.records`.** `write_csv`'s `DictWriter` **raises**; `write_xlsx` **silently drops**; `write_json` **keeps** it. Three different behaviours from one "harmless" extra key (`writers.py:45,58,66`).
- **Auto-applying a Schema proposal above some coverage threshold.** D-11-06 is explicit: no threshold exists, therefore none can be mis-tuned. `_CONFIDENCE_MARGIN` (`sheets.py:28`) is the anti-pattern being deliberately *not* repeated.
- **Merging sheets.** SHEET-02 is struck from the product (`REQUIREMENTS.md:57`, Out of Scope `:80`). Nothing in this phase may combine records across sheets.
- **Remounting the Review tab on switch.** `App.tsx` keys `Review` by `upload_token` so a fresh upload remounts it (`Review.tsx:75-77`). If tabs remount per member, a curator's in-tab amber resolutions are **destroyed** on tab switch. Keep every member mounted and hide the inactive ones, or lift `mappings` state to the parent.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-sheet header detection | A second header heuristic for the manifest | `structure.header.detect_header` (already run per-sheet at `table.py:314`) | Two heuristics = two answers; the manifest would show a header the parse then disagrees with. |
| Per-sheet shape/drawing gates | A "is this sheet real data" score | `classify_shape` (`table.py:341`) + `is_drawing_only_sheet` (`table.py:325`) | Already corpus-tuned; the phase must reuse the same verdict the parse will reach. |
| "Which Schema fits these headers" | A fuzzy matcher / similarity score | `_vendor_agnostic_alias_index` + `_covered_fields` (extracted from `_prefill_coverage`, `service.py:1572`) | Exact-normalised matching only — `ProfileStore.find` is exact-match by design (`store.py:30`) and D-02 forbids fuzzy. A fuzzy Schema pick is a *wrong-Schema* corruption vector. |
| Header normalisation | `.lower().strip()` | `learning.signature._normalise_header` (`signature.py:44`) | NFC + casefold + whitespace-collapse; the exact function the crosswalk and the learning loop already key on. Forking it silently splits the two indexes. |
| Column signature | A new hash | `learning.signature.column_signature` (`signature.py:30`) | Order-independent, duplicate-preserving, `PYTHONHASHSEED`-stable. |
| Tombstone filtering in the scorer | A `removed_at IS NULL` filter in the scorer | Nothing — go through `SchemaStore.get_schema` / `list_schemas` | See §Tombstones. The filter is **structural**, one level down. Adding a second one invites drift. |
| Archive of N exports | A hand-rolled multipart/zip writer | stdlib `zipfile.ZipFile` | — |
| A "which member is ready" gate | A new group-level readiness check | `service.confirm`'s existing per-member `NotReadyError` (`service.py:460-461`) | D-11-08: N independent datasets, each with **its own** gate. A group gate would weaken or strengthen a member's amber gate — both are wrong. |

**Key insight:** SHEET-05's scorer is a **composition** of four functions that already exist and are already tested. The only genuinely new primitive in the whole phase is `describe_sheets` — everything else is plumbing plus two wire arms.

---

## Tombstones: the D-10-15 audit the CONTEXT demanded

CONTEXT (canonical_refs) warns: "the Schema scorer is a **new read path**… a single missed filter silently resurrects a deleted field."

**Verified: the scorer needs no filter of its own, provided it sources Schemas only through `SchemaStore`.** The tombstone filter is structural, at the ORM→domain boundary:

```python
# learning/postgres_schema_store.py:301-321  — _entity_to_schema
field_rows = self._session.scalars(
    select(CanonicalFieldRow).where(
        CanonicalFieldRow.schema_id == row.id,
        CanonicalFieldRow.removed_at.is_(None),   # ← :311  "a tombstoned field is invisible to
    ).order_by(CanonicalFieldRow.seq)             #            every caller of this method"
).all()

# :330-340  — _aliases_for_field
select(AliasRow).where(
    AliasRow.canonical_field_id == field_id,
    AliasRow.removed_at.is_(None),                # ← :336  "a tombstoned alias is invisible to every caller"
)
```

Both `get_schema` (`:76-84`) and `list_schemas` (`:86-88`) return through `_entity_to_schema`. Therefore:

| Scorer input | Tombstone-safe? | Evidence |
|---|---|---|
| `SchemaStore.list_schemas()` | ✅ yes | `postgres_schema_store.py:88` → `_entity_to_schema` → `:311` |
| `service.field_set_from_schema(schema)` | ✅ yes | `service.py:1441-1446` documents it explicitly ("already absent from `schema.fields` by the store's own structural filter") |
| `service._vendor_agnostic_alias_index(schema)` | ✅ yes | `service.py:1464-1465` documents it ("A tombstoned alias never appears here at all") |
| `service._prefill_coverage(...)` | ✅ yes | consumes the index above |
| `ProfileStore.find(fs.signature, col_sig)` | ✅ correct-by-design | tombstoning a field **changes** `FieldSet.signature`, so an old profile correctly stops matching — intended, documented at `service.py:1443-1446` |

**The one rule to enforce and test:** the scorer must obtain Schemas **only** via `SchemaStore.get_schema`/`list_schemas` — never a raw ORM/SQL query. Existing precedent for the test: `tests/api/test_upload_schema_target.py:186` (`test_a_tombstoned_field_is_absent_from_the_target_field_list`) and `:209` (`test_a_tombstoned_alias_no_longer_prefills_and_escalates_to_claude`). Mirror both against the **scorer** (a tombstoned alias must not contribute coverage; a tombstoned field must not appear in `total_fields` or `uncovered`). `tests/test_schema_store_tombstones.py` already exists as the store-level guard.

---

## Common Pitfalls

### Pitfall 1: `detect_header().index` can be `None`

**What goes wrong:** `describe_sheets` does `rows[detection.index]` and crashes on `orion_pk_report.xlsx :: Notes` — a real fixture in-tree.
**Evidence:** live probe — Notes returns `hdr_idx=None confident=False`. `table.py:336` only survives because `_shape_unsupported_question`/`_header_uncertain_question` intercept first; `table.py:339` guards with `if header_index is not None`.
**How to avoid:** `SheetDescription.headers == []` and `status = header_uncertain` when `index is None`. A sheet that cannot be described must still **appear in the manifest, marked** — never crash the whole manifest, never be dropped.

### Pitfall 2: A sheet's headers are not on row 0

`zephyr`'s three sheets have their header on **row index 4** (probe). A manifest built from `rows[0]` would show `['ZEPHYR BIOSCIENCES', '', '', …]` as the headers, score **zero coverage** against every Schema, and propose **skip** for all three data sheets — silently destroying the phase's own flagship fixture. `describe_sheets` must run `detect_header` and slice at its index, exactly as `_parse_excel_structurally` does (`table.py:334-336`).

### Pitfall 3: N members, one temp file — the first structural-hint resolve deletes it for everyone

`/api/structural-hint/resolve` unlinks `entry.tmp_path` on success (`structural_hint.py:99`) and on **every** error branch (`:61,64,75`). The registry also unlinks on eviction (`state.py:225-236`). If two selected sheets both raise a structural question and both entries hold the *same* `tmp_path`, the first resolve destroys the second's file.

**Fix (recommended): copy the temp file per question-bearing member** (`shutil.copyfile`, ≤20 MB, `upload.py:71`). Each member entry then owns its own path, and every existing unlink/eviction rule stays correct with zero changes. Members that resolved straight to a mapping get `tmp_path=None` (existing happy-path cleanup, `upload.py:185`), and the *original* temp file is unlinked once all members are parsed.
**Rejected alternative:** refcounting the shared path in the group — it puts a second, subtler lifecycle owner beside the registry, contradicting `state.py:40-42`'s stated invariant ("the registry remains the one place a temp file's lifecycle is fully owned").

### Pitfall 4: `structural_hint.py:56` — a bigger hole than CONTEXT flagged (confirm + fix it in this phase)

```python
# api/routes/structural_hint.py:56-59  — the actual call
result = service.resolve_or_map(
    entry.tmp_path, entry.field_set,
    store=store, hint=hint, headers_only=entry.headers_only, client=client,
)   # ← no schema=, no sheet=, no strictness=
```
compared with `upload.py:125-129`, which passes `schema=resolved_schema` and `sheet=sheet`.

**Four confirmed consequences:**
1. **No Python-first pre-fill.** `resolve_table_mapping`'s `if schema is not None:` branch (`service.py:275`) is skipped ⇒ the D-10-03 crosswalk pass never runs on the hint path ⇒ every field goes to Claude, at cost, even when the crosswalk covers all of them.
2. **`escalation` is `None`** (`service.py:343` requires `schema is not None`) ⇒ the Review screen's escalation line silently disappears after a structural hint. `structural_hint.py:100-102` also omits `escalation=` from `MappingResponse.from_proposal`.
3. **`vendor_memory` is never computed** on this path (compare `upload.py:190` and `date_format.py:126`) ⇒ the vendor field is not pre-filled ⇒ and `/api/confirm` **requires** a vendor (`confirm.py:69-80`, 422 otherwise).
4. **`result.date_question` is never checked** (contrast `upload.py:154`). An ambiguous date column behind a structural question therefore **never raises the date question**: the field stays amber and Confirm 422s with no way out — a re-creation of the exact dead-end quick task `260712-qgc` fixed on `/api/upload` (STATE.md, Quick Tasks).

**Root cause:** the structural-question `UploadEntry` (`upload.py:146-151`) retains only `field_set`/`headers_only`/`tmp_path`/`source_file_name` — it drops `schema_name` (a field that already exists on `UploadEntry`, `state.py:145`) and `sheet`.
**Fix:** retain `schema_name` + `sheet` on that entry; in `structural_hint.py`, re-fetch the Schema via `get_schema_store` (exactly as `date_format.py:125` does) and pass `schema=`/`sheet=`/`strictness=`; then mirror `upload.py:154-173`'s date-question branch. This is a prerequisite for the sheet flow, because **every member of a sheet group re-enters `/api/structural-hint/resolve` with an explicit sheet** — and without `sheet=` retained, the resolve would **re-rank the workbook and parse the wrong sheet**.

### Pitfall 5: Ordering of the three questions

With the sheet manifest above `parse()`, the order is total and unambiguous:

**sheet_question (workbook-level) → per-member structural_question (`parse(path, sheet=X)`) → per-member date_question → per-member amber gate.**

A structural question can never *precede* a sheet question on a multi-sheet workbook, because after this phase no multi-sheet workbook is ever parsed without an explicit `sheet=`. This kills the "may precede or follow" ambiguity CONTEXT raises. Single-sheet/CSV is unchanged.

### Pitfall 6: `sheet_name` from the client is untrusted input

`/api/sheets/resolve`'s `selections[].sheet_name` is client-supplied and reaches `parse(path, sheet=...)`, which raises `ValueError` for an unknown sheet (`table.py:362-366`) → the route's generic `ValueError` catch maps it to **500** (`upload.py:138-140`). Validate each `sheet_name` against the **server-retained manifest** and return **422** naming the consequence. Likewise `schema_name` → `get_schema` → **404** (mirrors `upload.py:375-377`).

### Pitfall 7: Zip entry names built from sheet titles

A worksheet title is arbitrary user text. Building zip entries as `f"{sheet_name}/export.csv"` is a **zip-slip** vector (`../../etc/x`) and can also break on `/` or `\`. Sanitize: allowlist `[A-Za-z0-9._ -]`, fall back to `sheet_<index>`. The existing precedent for this discipline is `export.py:41-43`'s `_RUN_ID_PATTERN` — validate before touching the filesystem, never after.

### Pitfall 8: The Review tabs must not remount

See Anti-Patterns. `Review.tsx:86` holds `mappings` in local `useState` seeded from props; a keyed remount on tab switch throws away every amber resolution the curator made in that tab.

---

## Code Examples

### Verifying the explicit-sheet short-circuit (the phase's load-bearing assumption)

```python
# tests/test_parse_entry_sheets.py:30  — ALREADY GREEN, pins exactly what this phase relies on
def test_parse_orion_explicit_sheet_proceeds_to_a_raw_table():
    outcome = parse(ORION, sheet="Summary")
    assert isinstance(outcome, RawTable)   # ranking skipped; full per-sheet gates ran
```

### The existing per-sheet gate chain (what `parse(path, sheet=X)` gives SHEET-04 for free)

```python
# parsing/table.py:317-346  (abridged)
worksheets = list_worksheets(path)                       # chartsheets excluded (D-17)
target = _resolve_sheet(path, names, sheet, hint)        # explicit sheet ⇒ returned as-is
if is_drawing_only_sheet(worksheet): return _drawing_only_question(...)
detection = detect_header(rows)                          # per-sheet header row
shape = classify_shape(data_region)
if shape != TableShape.ROW_PER_RECORD: return _shape_unsupported_question(...)
if not confident: return _header_uncertain_question(...)
return _raw_table_from_header_row(...)                   # + decimal-locale gate inside
```

### The coverage the manifest must SHOW (D-11-03 / the builder's "6/7 canonical fields matched")

```python
# service.py:1572-1597 — _prefill_coverage already returns which fields matched, via which header
prefilled, remaining = _prefill_coverage(table, field_set, schema)
# prefilled: {"compound_id": FieldMapping(source_column="Cmpd ID", …), …}
# remaining: (Field(name="unit"), …)
# ⇒ matched_count = len(prefilled); total = len(field_set.fields); uncovered = [f.name for f in remaining]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `cli.resolve_tables()` looped **every** sheet of a workbook | `parse()` resolves **one** chosen table per file | Phase 01-03 (STATE.md) | `resolve_tables`/`parse_file` still exist and are still tested (`tests/test_excel_sheets.py:53`) but are **not** on the live path. Do not resurrect them for this phase — they bypass every structural gate. |
| Multi-sheet ⇒ single-select "which sheet" structural question, or silent discard | Multi-sheet ⇒ multi-select sheet question, N independent datasets | **This phase** | — |
| SHEET-02 merge | **Struck from the product** | 2026-07-13 | `REQUIREMENTS.md:57`, Out of Scope `:80`. Not a deferred idea. |

**Deprecated/outdated in CONTEXT.md:**
- SHEET-04's cross-sheet-disagreement clause — moot under D-11-08/D-11-09 and already struck in `REQUIREMENTS.md:59`.
- The ROADMAP's old merge criterion — obsolete.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The archive should be a **zip** (not tar) | Standard Stack | Cosmetic; CONTEXT leaves it to Claude's discretion. |
| A2 | The reserved column is named `__source_sheet` | Provenance | Cosmetic; must only be non-collidable with a canonical field name. |
| A3 | A CSV's provenance value is the client's **file name** (via `UploadEntry.source_file_name`) | Provenance | If the builder prefers `""` or a second `__source_file` column, one line changes. Flag at plan-review. |
| A4 | The group index may be **memory-only** (members are already persisted individually) | Run Group | A server restart mid-review loses only the "download all" convenience, not any review. If unacceptable, the group needs a `pending_groups` table. |

Everything else in this document is `[VERIFIED: codebase]` with a file:line or a live probe.

---

## Open Questions (RESOLVED — 2026-07-13, both answered before planning)

> **Q1 → RESOLVED as recommended.** The builder confirmed the trigger is **`>1` worksheet AND no explicit `sheet=`, regardless of `schema_name`**; a supplied Schema only pre-selects. Locked as **D-11-16** in `11-CONTEXT.md`, superseding D-11-01. Plan 11-07 implements it and pins it with the meridian test (the question fires *even though* a Schema was supplied).
>
> **Q2 → RESOLVED as recommended.** A member with a pending question does not block the others; the archive lists only confirmed members' `run_id`s. Implemented in plan **11-08**; no new gate was needed.

1. **C-1 — the sheet-question trigger.** MUST be answered before planning.
   - What we know: D-11-01 says "multi-sheet **without a Schema**"; the browser always sends a Schema; the current multi-sheet UX already guesses (probe table above).
   - What's unclear: whether the builder intended to gate the fix on the schema's absence, or simply described the *new capability* (Schema-less upload) and did not notice it also reads as the trigger.
   - Recommendation: trigger on **`>1` worksheet AND no explicit `sheet=`**, regardless of `schema_name`; a supplied Schema only pre-selects. Confirm with the builder in one sentence at plan-review — this is the one question whose wrong answer ships a dead feature.

2. **Does a member with a pending structural/date question block the group's archive?**
   - Recommendation: yes, trivially — the archive lists only confirmed members' `run_id`s, and the Review screen shows which tabs are still unconfirmed. No new gate needed.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 + uv venv | everything | ✓ | `.venv/bin/python` present, probe ran | — |
| `openpyxl` | `describe_sheets` | ✓ | already a dependency (`grid.py:17`) | — |
| stdlib `zipfile` / `shutil` | archive, per-member temp copy | ✓ | stdlib | — |
| Postgres (`pending_uploads`, schemas) | member persistence | ✓ | already wired (`persistence/engine.py`) | — |
| Anthropic API key | mapping the members | ✓/env | `ASSAYINGEST_LIVE_TESTS=1` opt-in for live tests (STATE.md) | The scorer and manifest are **pure Python** — the whole sheet-question path is testable with **no key at all** (D-11-04). |
| Multi-sheet fixtures | acceptance tests | ✓ | 4 in `data/synthetic/` (probe) | — |

**Missing dependencies:** none.

---

## Test Strategy (TDD — tests first, red→green)

### Contracts that MUST keep passing UNCHANGED (D-11-01's no-regression clause)

Verified by inspection — **none of these need to change** under the recommended architecture:

| File | Why it stays green |
|---|---|
| `tests/api/test_upload.py` (13 tests) | Every upload in it is a **CSV** or an inline-generated CSV — no `.xlsx` is posted anywhere in `tests/api/` (verified by grep). The multi-sheet branch is never entered. |
| `tests/api/test_money_shot.py` | `novascreen_batch01.csv` / `batch02.csv` — CSV. |
| `tests/api/test_upload_schema_target.py` (9 tests) | CSV-driven; the Python-first prefill contract is preserved by the `_covered_fields` extraction (which these tests guard). |
| `tests/api/test_date_format_route.py`, `test_confirm_dates.py`, `test_confirm_gate.py`, `test_confirm_vendor_required.py`, `test_pending_upload_persistence.py`, `test_hint_and_export.py`, `test_reconcile.py` | All CSV / in-memory `RawTable`. `UploadEntry`'s new fields are **defaulted**; `_entry_to_json`'s new keys are read with `.get()`. |
| `tests/test_parse_entry_sheets.py` (7), `tests/test_structure_sheets.py` (5), `tests/test_parse_entry_shape.py`, `tests/test_excel_sheets.py`, `tests/test_hint_and_locale.py` | `parse()`, `_resolve_sheet`, `rank_sheets`, `SheetRanking` are **not touched**. |
| `tests/test_canonical.py`, `test_canonical_dates.py`, `test_validator*.py` | `assemble(*, source_sheet=None)` is keyword-only + defaulted; `validator.py:130`'s call is unchanged; `flagged` cannot change. |
| `tests/test_python_first_prefill.py` | Guards the `_covered_fields` extraction (behaviour identical). |

### Contracts that WILL change (update deliberately)

| File | Change |
|---|---|
| `tests/test_export_writers.py:21` | `CanonicalTable(...)` gains `record_sources` (defaulted ⇒ the existing construction still compiles). **New tests:** each of `write_csv` / `write_xlsx` / `write_json` emits `__source_sheet` when `record_sources` is set, and emits **nothing extra** when it is empty (the CLI path). Plus: `write_csv` must not raise (`DictWriter` extra-key) — pin this explicitly, it is the one that fails loudly. |
| `tests/api/test_state.py` | `_entry_to_json` / `_entry_from_json` round-trip the new `group_id` / `sheet` / `origin_sheet` keys; an **old** persisted row (missing them) still rehydrates. |
| `frontend` vitest (`state/upload.test.ts`) | `fromResponse` handles the two new kinds; `assertNever` still exhaustive; `toDropzonePhase` maps the new phases to `locked`. |

### New tests (the acceptance suite) — fixtures ARE the tests

| Case | Fixture | Assertion |
|---|---|---|
| N independent datasets | `zephyr_bio_ZB-2025.xlsx` | 3 sheets in the manifest, each with headers from **row 4** (not row 0); selecting all 3 ⇒ `sheet_group` with 3 members, 3 distinct `upload_token`s, 3 independent confirms, 3 export dirs. |
| Per-sheet Schema proposal across header drift | `delta_screening_per_target.xlsx` | 3 sheets, 3 **different** header spellings (`Compound` / `Cmpd ID` / `compound_id`), all resolving to the same Schema once the crosswalk carries the aliases — the coverage number must be **shown** per sheet. Also the natural test that a sheet with **no** aliases yet scores lower and does not auto-apply. |
| Ambiguous ranking is irrelevant now | `orion_pk_report.xlsx` | The sheet question fires **regardless** of `rank_sheets.confident` — the manifest lists Summary (7 cols), Raw timepoints (4 cols), **and Notes marked `header_uncertain`**. Notes must appear, marked, not crash the manifest. |
| Zero coverage ⇒ propose SKIP | `meridian_cro_codes.xlsx` | DATA + **LEGEND**; LEGEND (headers `['CMP','compound identifier']`, `header_uncertain`) scores zero coverage ⇒ `proposed_schema is None` ⇒ pre-selected as **skip**, never force-mapped. **And the sheet question fires even though `rank_sheets` IS confident here (0.171 margin)** — this is the test that pins D-11-06's "always shown, no silent auto-apply". |
| No regression | `novascreen_batch01.csv` | A CSV upload returns `kind:"mapping"` exactly as today (byte-identical body apart from nothing). |
| Provenance on every ingest (D-11-15) | `novascreen_batch01.csv` **and** a single-sheet `.xlsx` | The export carries `__source_sheet` on **every** row in all 3 formats — including the CSV/single-sheet case. |
| Tombstone (D-10-15) | synthetic Schema | A tombstoned alias contributes **zero** coverage to the scorer; a tombstoned field is absent from `total_fields` and `uncovered`. |
| Temp-file lifecycle | two structurally-broken sheets | Both members' `tmp_path`s are distinct; resolving one does not delete the other's file; both are unlinked eventually. |

### Is a NEW fixture needed for "two sheets, two DIFFERENT Schemas"? — **No.**

`orion_pk_report.xlsx` already **is** that case, and the probe proves it:

- `Summary` → `Test Article | Parameter | Mean | Unit | Molecular Target | N animals | Study Day` — a 7-column assay-shaped sheet (maps to `assay-potency`: `compound_id, assay_type, value, unit, target, n_replicates, assay_date`).
- `Raw timepoints` → `Test Article | Timepoint (h) | Conc | Unit` — a concentration-time series, a **structurally different** dataset (closest to `pk-parameters`: `compound_id, cmax, tmax, auc, half_life, clearance, dose, study_date`).

Two sheets, two genuinely different canonical models, in one workbook already in the repo. Use it. **Caveat the planner must handle:** with a stock `assay-potency` Schema carrying **no aliases yet**, crosswalk coverage for *both* sheets is **0** and both would propose *skip* — which is correct-but-useless as a demo. The acceptance test must therefore **seed the crosswalk first** (the aliases are what the product learns, via `ALIAS-04`/`confirm`), i.e. the honest demo sequence is: ingest Summary once → confirm → aliases accrete → re-upload → Summary now proposes `assay-potency` at high coverage while Raw timepoints still proposes skip/another Schema. That sequence *is* the learning-loop money shot applied to sheets, and it should be an explicit test.

If the builder wants a **zero-setup** two-Schema demo (both sheets proposing a *different* Schema with real coverage on first upload, no prior confirms), a new fixture is needed: one workbook, sheet A with headers matching `assay-potency`'s field names closely enough to be pre-aliased by the seeded presets, sheet B matching `reagent-inventory`'s (`catalogue_number, name, quantity, unit, expiry_date, shelf`). That depends on whether the **seeded preset Schemas ship with aliases** — verify at plan time (`learning/seed.py`); if they seed fields only (no aliases), no first-upload crosswalk coverage exists for *any* Schema and the scorer's stage 2 is inert until a first confirm. **This is the highest-value thing for the planner to check before writing the SHEET-05 tasks.**

---

## Security Domain

### Applicable ASVS Categories (L1)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `POST /api/sheets/resolve` and `GET /api/export/group/{id}/archive` MUST be `Depends(require_user)` — mirroring `date_format.py:59` / `structural_hint.py:44` (D-10-13). Closing `/api/upload` alone leaves the continuation open. |
| V3 Session Management | yes | The group id and every member token are server-minted `uuid4`; the client never supplies one that becomes state. |
| V4 Access Control | yes | Group archive: validate `group_id` against the `uuid4` shape **before** any filesystem access — reuse `export.py:41-43`'s `_RUN_ID_PATTERN` discipline verbatim. |
| V5 Input Validation | yes | `selections[].sheet_name` and `.schema_name` are untrusted: validate `sheet_name` against the **server-retained manifest** (422, not 500 — see Pitfall 6) and `schema_name` via `get_schema` (404). `SheetSelectionIn` is a Pydantic model at the boundary. |
| V6 Cryptography | no | — |
| V12 Files & Resources | yes | **Zip-slip** (Pitfall 7): sanitize sheet titles before they become zip entry names. **Temp-file lifecycle** (Pitfall 3): per-member copies must each be unlinked on every error branch, mirroring `structural_hint.py:105-112`. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via `group_id` | Tampering | uuid4 regex allowlist before `Path` join (`export.py:41`) |
| Zip-slip via worksheet title | Tampering | Character allowlist + `sheet_<i>` fallback on entry names |
| XSS via worksheet title / header text in the sheet panel | Tampering | React escape-by-default; the same rule `ReconcilePanel` follows for untrusted crosswalk text (T-08-11) |
| Unauthenticated drive-to-completion of a retained upload | Elevation | `require_user` on the new resolve + archive routes (D-10-13) |
| Cell values at rest | Info disclosure | Unchanged: members ride the existing `pending_uploads` TTL + confirm-purge (`state.py:23-32`). **N members ⇒ N persisted rows** — each purged by its own `registry.pop` at confirm (`confirm.py:207`). Note the group's *unconfirmed* members still expire on the same TTL. |
| Header leakage under `headers_only` | Info disclosure | **Not a leak.** `headers_only` restricts what **Claude** sees, never what the server reads or shows the human (D-10-05, `service.py:1581-1583`). The sheet manifest shows headers, never cell values — no `evidence_rows` equivalent exists on this arm, so no redaction hook is needed (unlike `DateFormatQuestionResponse.from_question`'s `example_values`, `wire.py:483-492`). |

---

## Sources

### Primary (HIGH confidence — read in full this session)
- `src/assayingest/api/state.py` (1-379), `api/wire.py` (1-524), `api/routes/upload.py`, `confirm.py`, `export.py`, `structural_hint.py`, `date_format.py`
- `src/assayingest/service.py` (1-1646), `canonical.py` (1-369), `export/writers.py` (1-127)
- `src/assayingest/parsing/table.py` (1-492), `parsing/structure/sheets.py` (1-131), `parsing/structure/grid.py`
- `src/assayingest/learning/schema_store.py`, `learning/postgres_schema_store.py` (tombstone filters), `learning/signature.py`
- `frontend/src/state/upload.ts`, `frontend/src/lib/types.ts`, `frontend/src/screens/Review.tsx`
- **Live probe** (`.venv/bin/python`): `rank_sheets` / `detect_header` / `classify_shape` / `parse()` over `zephyr_bio_ZB-2025.xlsx`, `delta_screening_per_target.xlsx`, `orion_pk_report.xlsx`, `meridian_cro_codes.xlsx`
- `.planning/phases/10-frictionless-correct-ingest/10-CONTEXT.md` (D-10-03/05/07/13/15), `.planning/REQUIREMENTS.md`, `.planning/STATE.md`

### Secondary / Tertiary
- None. No external source was needed or used; nothing in this phase depends on knowledge outside the repository.

---

## Project Constraints (from CLAUDE.md)

- **Clean Architecture:** dependencies point inward. `parsing/` must **not** import `learning/` — hence `column_signature` is computed in `service.py`, not in `describe_sheets`.
- **Single level of abstraction per function:** `describe_sheets` orchestrates; `_describe_one_sheet` does the per-sheet work.
- **Log-or-raise, never both.** Error messages name the **consequence**, not the symptom (e.g. "Nothing was ingested: sheet 'X' is not in this workbook…", not "sheet not found").
- **Wire ↔ domain boundary:** Pydantic wire models never leak inward; `SheetDescription`/`SchemaProposal` are frozen domain dataclasses, and `wire.py` translates.
- **Absolute imports in `__init__.py`; relative inside modules.**
- **TDD (tests-first, red→green)** — a standing user preference recorded in memory and `workflow.tdd_mode: true` in `.planning/config.json`.
- **Git commit messages:** English, capitalized, one short imperative line (≤150 chars).
- **`workflow.nyquist_validation: false`** ⇒ no Validation Architecture section (deliberately omitted).

---

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — no new packages; every needed function verified in-tree with a line number.
- Architecture (run group, provenance, per-sheet parse): **HIGH** — each recommendation's blast radius enumerated by grep over the real call sites (`assemble`: 3 call sites; writers: 1 call site; `entry.table` reads: 8).
- Pitfalls: **HIGH** — Pitfalls 1, 2, 4 were each confirmed by a live probe or by reading the exact failing line; Pitfall 3 by tracing the unlink call sites.
- The C-1 contradiction: **HIGH** that it is a contradiction; the *resolution* needs one sentence from the builder.

**Research date:** 2026-07-13
**Valid until:** valid while the repo is at `2191625` — this is an internal-architecture study, so it goes stale only when the files it cites change.
