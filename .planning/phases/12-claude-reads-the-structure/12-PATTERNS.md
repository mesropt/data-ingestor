# Phase 12: Claude Reads the Structure - Pattern Map

**Mapped:** 2026-07-13
**Files analyzed:** 16 (7 new, 9 modified) + the test surface (22 rewrites)
**Analogs found:** 13 / 16 (3 genuine inventions — flagged in §No Analog Found)

Every `file:line` below was re-read this session, not copied from RESEARCH.md. Where RESEARCH.md's claim was verified, it is stated as fact; the one soft spot found is noted inline (the `table.py:192` duplicate-header precedent).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/assayingest/parsing/structure/layout.py` (NEW) | domain model (pure) | none (value objects) | `parsing/structure/shape.py:1-22` + `parsing/hint.py:19-61` | exact |
| `src/assayingest/parsing/structure/unpivot.py` (NEW) | utility (pure transform) | transform (grid → headers+rows) | `parsing/table.py:467-503` (target contract only) | partial — core transform is invented |
| `parsing/structure_assist.py` judge function (WIDENED) | service (LLM call site) | request-response (batched) | `mapping/schema_ranker.py:101-145` | exact |
| `parsing/structure_schema.py` `WireSheetLayout`/`WireWorkbookLayout` (WIDENED) | wire model | request-response | `schema_ranker.build_ranking_wire_model` (`schema_ranker.py:64-98`) | exact |
| evidence-grid renderer (`render_evidence_grid`, NEW fn) | utility | transform | `mapping/mapper.py:148-163` (`_render_table`) | role-match — the type redaction is invented |
| `data/synthetic/lab_corpus/layout_truth.json` (NEW) | fixture/config | none | `data/synthetic/lab_corpus/manifest.json:1-30` | role-match — per-sheet keying is new |
| live eval test (NEW) | test | request-response (real API) | `tests/test_cross_domain.py:78-99` | exact |
| `parsing/table.py` (MOD) | parser | file-I/O → transform | itself: `:326-331`, `:440-464`, `:467-503` | exact |
| `parsing/structure/sheets.py` (MOD) | parser (manifest) | file-I/O → describe | itself: `:242-284` | exact |
| `service.py` (MOD) | service orchestration | request-response | itself: `_ranker_for`/`_rank_or_none` (`:1956-1994`) | exact — the canonical analog |
| `api/wire.py` (MOD) | wire model | request-response | itself: `SheetOut:578-611`, `DateFormatQuestionResponse:461-492` | exact |
| `api/routes/upload.py` (MOD) | controller | request-response | itself: `_sheet_question:275-315` | exact |
| `api/routes/sheets.py` (MOD) | controller | request-response | itself: `_validated_selections:121-162` | exact |
| `api/routes/structural_hint.py` (MOD) | controller | request-response | itself: `_to_domain_hint:180-188` | exact |
| `frontend/src/state/sheets.ts` + `lib/types.ts` (MOD) | store / types | request-response | themselves: `sheets.ts:53-99`, `types.ts:225-234` | exact |
| `frontend/src/components/SheetQuestionPanel.tsx` + `StructuralHintPanel.tsx` (MOD) | component | request-response | themselves: `StatusBadge:43-66`, `StructuralHintPanel:36-89` | exact |

DELETED in wave C: `parsing/structure/shape.py` (230 lines, verified: only imported by `table.py:338` and `sheets.py:33`) and `tests/test_structure_shape.py` (all but the purity guard, which is KEPT and re-pointed — see §Test Patterns).

---

## Pattern Assignments

### 1. `parsing/structure/layout.py` (NEW — pure verdict types)

**Analogs:** `parsing/structure/shape.py` (the module it replaces — copy its purity contract), `parsing/hint.py` (the enum + frozen-dataclass idioms), `parsing/structure/sheets.py:55-77` (frozen dataclass with a computed property and a docstring that names the caller's obligation).

**Purity contract to copy verbatim in spirit** (`shape.py:12-16`):
```python
Pure module: no I/O, no `pandas`, no `openpyxl`, no `anthropic` import (D-04)
-- every signal is computed from the native-typed row tuples
`structure/grid.py` reads, so this module is fully testable without a file
on disk.
```

**str-Enum idiom** (`hint.py:19-31` — `TableShape`; `LayoutKind` is its direct successor):
```python
class TableShape(str, Enum):
    """The structural shapes the parser can classify a table's raw grid as.

    Only `row_per_record` produces a `RawTable` (D-10) -- every other shape is
    unsupported in v1 and surfaces as a `StructureQuestion` instead of a
    silently-wrong table (D-11).
    """
    ROW_PER_RECORD = "row_per_record"
    ...
```

**Frozen dataclass with all-optional dimensions** (`hint.py:47-61` — `StructuralHint`; `SheetLayout`'s optional `header_row_index`/`first_data_row` follow this):
```python
@dataclass(frozen=True)
class StructuralHint:
    """The structural dimensions a human (or Claude) can pin down.

    Every field is optional so a hint can carry just the one dimension in
    question ..."""
    sheet_name: str | None = None
    header_row_index: int | None = None
    ...
```

**Serialisation:** `StructuralHint.to_dict()` uses `_jsonable(asdict(self))` (`hint.py:63-65`, `:108-116`). `_jsonable` recurses into dicts and lists and coerces `Enum` — it should handle a nested frozen `SheetLayout` (asdict recurses into nested dataclasses), **but tuples of `KeyValueBlock` become lists via asdict and `_jsonable` handles `list` not `tuple` at the top level** — asdict converts tuples to tuples in some Python versions... it converts them to tuples of dicts, and `_jsonable` has no `tuple` branch (`hint.py:108-116` handles `Enum`/`dict`/`list` only). **Verify with a round-trip test before assuming** (RESEARCH A5 says the same). The loader must tolerate a missing `layout` key in old stored profiles.

**Do NOT copy:** `shape.py`'s corpus-tuned constants and homogeneity math (`shape.py:24-45`, `:127-160`) — the whole point of the phase is that they are structurally blind. Do not carry any threshold into `layout.py`; it holds *types only*, no logic.

**Field naming rule (SHAPE-03 as a type):** every field is `int`, `bool`, `float`, enum, or free-text `reasoning`. If a field of type `str` other than `reasoning` appears in review, it is a hole where a cell value can be transcribed. The contract itself (multi-block `KeyValueBlock` tuple, `one_record_per_value_column`) is locked by D-12-13 in CONTEXT — the planner should copy the shape from CONTEXT verbatim, not re-derive it.

---

### 2. `parsing/structure/unpivot.py` (NEW — pure grid transform) ⚠ partial invention

**No un-pivot exists anywhere in `src/`** (verified: the word appears only in docstrings refusing to do it, e.g. `table.py:446-447`). The *transform* is invented. Its **input contract** and **output contract** both have exact analogs:

**Input:** native-typed row tuples from `grid.read_grid` (`grid.py:22-32`) — same input `classify_shape` consumed, same purity rules.

**Output contract — mirror `_raw_table_from_header_row` line for line** (`table.py:467-503`). The sibling `_raw_table_from_key_value` in `table.py` (see §4) does the `RawTable` assembly; `unpivot.py` produces only `(headers, string_rows)`:
```python
# table.py:488-503 — the assembly the un-pivot's output must feed
header_row = rows[header_index]
data_rows = rows[header_index + 1 :]
headers = [_clean_header(h) for h in header_row]
string_rows = [_row_to_strings(row) for row in data_rows]

locales = _resolve_locales_or_ask(path, headers, string_rows, hint)
if isinstance(locales, StructureQuestion):
    return locales
return RawTable(
    headers=headers, rows=string_rows, source_name=path.name,
    sheet_name=sheet_tag,
    column_locales=[loc.value for loc in locales],
    origin_sheet=origin_sheet,
)
```

**Cell stringification — copy `_row_to_strings`'s contract exactly** (`table.py:524-526`):
```python
def _row_to_strings(row: tuple) -> list[str]:
    """Convert one native-typed grid row to the strings-only `RawTable` shape."""
    return ["" if cell is None else str(cell) for cell in row]
```
A native `float` becomes `'0.19'` with no thousands comma — this is what keeps the locale gate honest on the un-pivoted table.

**Label cleaning:** reuse `_clean_header` (`table.py:206-215`) on the label cells so blank labels stay `""` (an unlabelled row is signal, not noise — same rationale as the docstring there).

**Duplicate labels (the invented policy):** disambiguate deterministically (`Collected`, `Collected (2)`). The data-loss hazard is real and verified: `canonical._column_index` resolves `source_column` by first occurrence (`canonical.py:259-269` per RESEARCH — `headers.index(name)`), so a duplicate's second column is silently unreachable. The nearest precedent for mangling is weak: pandas' own `col.1` mangling arrives via `frame.columns` at `table.py:192` on the legacy CSV path — cite it as precedent for the *idea*, not a pattern to copy. **This policy has no true analog — flag the task as invention** and pin it with a hand-built-grid unit test first (TDD, it is a pure function).

**Do NOT copy:** any pandas usage. The module must pass the purity guard (see §Test Patterns — the re-pointed `test_structure_shape.py:101` test).

---

### 3. The structure judge — widen `parsing/structure_assist.py` (a new sibling fn, not a new module)

`structure_assist.py:9-11` already designates the module: *"this module is the only place a Claude call for structure ... is made."* Add `judge_workbook_layout(...)` beside `propose_structure` (`structure_assist.py:43-71`). **The most recent and most complete Claude call-site analog is `schema_ranker.propose_schema_ranking` (`schema_ranker.py:101-145`)** — it has everything the judge needs that `propose_structure` lacks: a runtime-`Literal` wire model, a refuse-before-calling guard, and a `_to_domain` that closes the boundary a second time.

**Call posture — identical across all three existing sites; copy it** (`schema_ranker.py:127-137`, same shape at `structure_assist.py:55-64` and `mapper.py:46-59`):
```python
client = client or anthropic.Anthropic()
response = client.messages.parse(
    model=_MODEL,                       # "claude-opus-4-8"
    max_tokens=_MAX_TOKENS,
    thinking={"type": "adaptive"},
    output_config={"effort": "high"},
    system=_render_system_prompt(...),
    messages=[{"role": "user", "content": _render_request(...)}],
    output_format=build_ranking_wire_model(schema_names),
)
wire = response.parsed_output
if wire is None:
    raise ValueError(
        f"No Schema ranking was produced for sheet "
        f"{sheet_name or '(unnamed)'!r}: the model returned no structured "
        f"proposal (stop reason: {response.stop_reason})."
    )
return _to_domain(wire, schema_names)
```
Note the error message names the consequence and the stop reason — copy that idiom (it is also what `test_propose_structure_raises_value_error_when_parsed_output_is_none` pins, `tests/test_structure_assist.py:64-68`).

**Runtime `Literal` over real sheet names — copy `build_ranking_wire_model`** (`schema_ranker.py:64-98`):
```python
wire_ranked_schema = create_model(
    "WireRankedSchema",
    schema_name=(
        Literal[tuple(schema_names)],
        Field(description="The name of one of the listed schemas."),
    ),
    ...
)
return create_model(
    "WireSchemaRanking",
    ranking=(list[wire_ranked_schema], Field(description=...)),
)
```
The judge's version is `build_layout_wire_model(sheet_names)` with `sheet_name: Literal[tuple(sheet_names)]` per sheet verdict, `sheets: list[...]` at the top. Names need no sanitising — the docstring at `schema_ranker.py:72-75` says why ("a space, a dash, or a leading digit all work unmodified as Literal VALUES").

**Boundary closed twice — copy `schema_ranker._to_domain`'s posture** (`schema_ranker.py:207-230`, rule stated at `:19` — *"A boundary closed once is a boundary closed by luck"*):
```python
governed = set(schema_names)
kept: dict[str, str] = {}
for item in wire.ranking:
    if item.schema_name in governed and item.schema_name not in kept:
        kept[item.schema_name] = item.reason
```
The judge's `_to_domain` does the same *plus two things with no analog*: **clamp every integer index against the real grid dimensions** (out-of-grid ⇒ that sheet becomes `UNKNOWN`, never `IndexError`, never silent truncation) and **fill any omitted sheet with `UNKNOWN`** (a forgotten sheet must ask, never default). Both are small but invented — see §No Analog Found.

**Prompt structure — copy `_render_system_prompt`** (`schema_ranker.py:148-176`): numbered non-negotiable rules; the closing "You are shown X and nothing else" line (`:174-175`); zero compiled-in domain vocabulary (D-18). The old two-rule prompt at `structure_assist.py:25-40` ("Propose, never decide" / "Never guess silently") supplies rules 1-2 verbatim; rule 3 ("you return indices, never cell contents") is new. Also copy the anti-injection whitespace collapse: `_one_line` (`schema_ranker.py:192-194`, identical at `mapper.py:133-135`) on every cell rendered into the evidence grid — both docstrings name the exact hazard (a newline inside a cell escapes its bullet and reads as a top-level instruction).

**Truncation honesty — copy `mapper._render_table:158-160`:**
```python
f"First {min(_SAMPLE_ROWS, table.row_count)} of {table.row_count} rows:"
```
The judge's grid header must state true sheet dimensions ("this sheet is 118 rows × 6 cols; showing the first 20 × 10") for exactly the same reason.

**Do NOT copy:** `propose_structure`'s `evidence: str` single-question signature (`structure_assist.py:43-44`) — the judge answers about N sheets with one call (D-12-14) and takes structured grids, not a pre-rendered string. Do not touch `propose_structure` itself: `cli._enrich_question` (`cli.py:391-410`) still calls it and its 8 tests stay green (`tests/test_structure_assist.py` — KEEP all 8).

**Do NOT merge into `schema_ranker`:** the ranker is deliberately the last rung of the Python→Claude→human ladder (`schema_ranker.py:5-9`, `service.py:1935-1946`). D-12-14 explicitly rejects the merge.

---

### 4. `parsing/table.py` (MODIFIED — the gate stays where it is)

**The choke point to preserve, verbatim rationale** (`table.py:326-331`, inside `_parse_excel_structurally`'s docstring):
```
Only `TableShape.ROW_PER_RECORD` may ever
reach `_raw_table_from_header_row` (D-10/D-11) — this single choke point
covers both the auto-detected and the explicit-hint-override paths, so
no path can attach a shape caveat to a `RawTable` and return it anyway.
```
The dispatch site is `table.py:362-365`:
```python
data_region = rows[header_index + 1 :] if header_index is not None else rows
shape = classify_shape(data_region)
if shape != TableShape.ROW_PER_RECORD:
    return _shape_unsupported_question(path, target, shape, data_region)
```
Replace *what fills the verdict* (`hint.layout` when present; `classify_shape` fallback in waves A-B; fail-closed question in wave C), never *where the gate sits*. Single-level-of-abstraction rule: the layout dispatch goes into a named private helper (e.g. `_table_from_layout`), not a fourth inline branch — `_parse_excel_structurally` (`table.py:312-371`) is already at its limit.

**`_raw_table_from_key_value` — mirror `_raw_table_from_header_row`** (`table.py:467-503`, excerpted in §2 above), including: the two-argument `sheet_tag`/`origin_sheet` distinction (docstring `table.py:483-486` explains why they are deliberately two arguments), and the **unchanged `_resolve_locales_or_ask` gate** (`table.py:493`; the gate's shared-by-both-branches rationale is at `table.py:274-277`: *"a comma decimal corrupts an Excel value by 1000x exactly as readily ... so neither branch may skip the gate"*). Do NOT special-case one-row tables past the locale/date gates (RESEARCH Pitfall 5; `table.py:298-304` names the 1000× consequence).

**`_shape_unknown_question` — mirror `_shape_unsupported_question`** (`table.py:440-464`) with three deliberate differences:
```python
# table.py:449-464 — the template
return StructureQuestion(
    unsure_about=f"{path.name}: table shape is {shape.value}, not row-per-record",
    reason=(
        f"{path.name} :: {sheet_name}: the data reads as {shape.value}, not "
        "one row per record — mapping it as-is would produce a "
        "clean-looking table with every field wrong. ..."
    ),
    confidence=0.0,
    proposal=StructuralHint(sheet_name=sheet_name, table_shape=shape),
    evidence_rows=[_row_to_strings(row) for row in data_region[:8]],
    answerable_by_hint=False,
)
```
Copy: the consequence-first `reason` ("a clean-looking table with every field wrong"), `evidence_rows=[... rows[:8]]`, `confidence=0.0`. Change: `answerable_by_hint=True` (the whole point — `hint.layout` finally *does* something; today `hint.table_shape` is write-only, verified: writes at `structure_assist.py:86` and `structural_hint.py:187`, zero reads), `proposal` carries the judge's layout when one exists or `None` honestly when the judge failed.

---

### 5. `parsing/structure/sheets.py` (MODIFIED — suppression re-keyed, only ever widened)

**The two functions that change, as they are today:**

`_sheet_status` (`sheets.py:272-284`) — the only other production caller of `classify_shape`:
```python
if classify_shape(data_region) is not TableShape.ROW_PER_RECORD:
    return SheetStatus.UNSUPPORTED_SHAPE
if detection.index is None or not detection.confident:
    return SheetStatus.HEADER_UNCERTAIN
return SheetStatus.OK
```

`_reportable_headers` (`sheets.py:242-269`) — suppresses on `UNSUPPORTED_SHAPE` **only**, deliberately not on `HEADER_UNCERTAIN` (`sheets.py:255-265` — the meridian-LEGEND rationale, D-11-24). This is the verified live leak: `Patient Info` is `header_uncertain` today, so `'TAYLOR, James'` ships as a header and into `column_signature` (`service.py:2184`). **Suppression may only ever widen** (wave B invariant): `NOT_A_TABLE`/`MULTIPLE_TABLES`/`UNKNOWN` ⇒ `[]`; a `key_value` sheet reports its *labels* (safe and useful — they are what the crosswalk and the signature want).

**Copy the docstring discipline:** `_reportable_headers`'s docstring names the downstream consequence chain (screen → `service._manifest_entry` → `column_signature` → learning store). The rewritten version must keep that chain named.

**Pitfall to honour (RESEARCH Pitfall 7):** `SheetStatus` (`sheets.py:147-160`) answers "which gate failed"; `LayoutKind` answers "how is this laid out". Do not conflate — a `key_value` sheet is `status="ok"` (or a new readable status) *plus* a `layout` field on `SheetOut`, so `sheets.ts:67-69` (`isUnreadableShape`) does not accidentally strip its Schema control.

---

### 6. `service.py` (MODIFIED — the `judge_fn` seam; the canonical analog, quoted)

**`_ranker_for` (`service.py:1956-1972`) — copy this function shape exactly for `_judge_for`:**
```python
def _ranker_for(client, rank_fn):
    """The stage-3 ranker: the injected one when a test supplied it, else the
    real one bound to the caller's client, else NOTHING.

    `None` is a legitimate answer, not an error. Without credentials there is no
    ranker, and a sheet the crosswalk could not resolve simply proposes skip --
    exactly as it did before this stage existed.
    """
    if rank_fn is not None:
        return rank_fn
    if client is None:
        return None

    def _with_client(headers, schemas, *, sheet_name=None):
        return propose_schema_ranking(headers, schemas, client=client, sheet_name=sheet_name)

    return _with_client
```

**`_rank_or_none` (`service.py:1975-1994`) — the availability boundary, rationale quoted because D-12-16 requires the plan to carry it:**
```python
def _rank_or_none(ranker, headers, schemas, sheet_name) -> tuple[RankedSchema, ...]:
    """Call the ranker, or answer "nothing" if it fails.

    The `except` is deliberately broad, and this is the one place in the module
    where that is right: this is an AVAILABILITY boundary, not a logic one. Every
    way a remote call can fail -- auth, network, rate limit, timeout, a malformed
    response -- must land the human on the same safe answer ("no proposal; you
    choose"), and enumerating those failures invites the one that was missed to
    block them instead. Logged once and swallowed; never logged AND raised.
    """
    try:
        return tuple(ranker(headers, schemas, sheet_name=sheet_name))
    except Exception:
        _LOGGER.warning(
            "No Schema could be suggested for sheet %r: the ranking call failed. "
            "The sheet is still offered, with no pre-selected Schema.",
            sheet_name or "(unnamed)",
            exc_info=True,
        )
        return ()
```
The judge's `_judge_or_unknown` copies this **and states the difference in its own docstring** (D-12-16, verbatim requirement): a *ranker* failure costs a **suggestion** (the human picks a Schema); a *judge* failure costs a **question** (the human is asked about the layout). Neither guesses. The warning message must likewise name the consequence ("every sheet will ask about its layout"), not the symptom.

**`describe_workbook` (`service.py:2115-2167`):** add `judge_fn=None` and `headers_only: bool = False` beside `rank_fn` (`:2121`). One judge call per workbook, **before** the per-sheet `_manifest_entry` loop (`:2164-2167`) — ordering is load-bearing because `_manifest_entry` scores `description.headers` (`:2186`) and a key-value sheet's headers only exist after the verdict. **The docstring at `:2157-2161` becomes false and must be rewritten in the same commit** — it currently states *"There is still no `headers_only` parameter, and still nothing for one to do"*, and two tests enforce that prose by signature inspection (see §Test Patterns).

**`resolve_or_map` (`service.py:296-364`):** the seam-parameter precedent is `propose_mapping_fn` (`:306`, resolved at `:258` — `fn = propose_mapping_fn if propose_mapping_fn is not None else propose_mapping`; rationale at `:251-256`). Add `judge_fn=None` the same way, defaulted so every existing call site is unchanged (verified callers: `upload.py`, `structural_hint.py:74`, `sheets.py:196`, CLI via `resolve_table_mapping`). Credential gating: `has_credentials()` (`service.py:99-107`) — the judge checks it *before* constructing anything, same as `:266`.

**`SheetManifestEntry` (`service.py:2086-2112`):** gains a `layout` field. Copy the docstring's wire-discipline note (`:2095-2098`): the status is stored as the *value*, never the enum member, because this dataclass is what the wire model serialises — the layout must follow the same rule (store `layout.kind.value` or a plain dict, decided at the wire boundary).

---

### 7. `api/wire.py` (MODIFIED)

**`SheetOut` (`wire.py:578-611`):** gains `layout` (and a widened `status` Literal if a new status member is chosen). The current Literal to widen: `status: Literal["ok", "drawing_only", "unsupported_shape", "header_uncertain"]` (`:608`). Copy the class docstring's habit of stating the redaction posture out loud (`:582-587`: headers are not redacted under `headers_only` and *why*).

**`StructuralHintIn` (`wire.py:371-381`):** gains a `layout` sub-model, "mirroring the domain dataclass exactly" per its own docstring (`:372-374`). This is **untrusted client input** — see §8 for the validation analog.

**Redaction-at-the-wire-boundary analog** (if the plan redacts anything on the way out): `DateFormatQuestionResponse.from_question` (`wire.py:482-492`) is the established one-place-only pattern:
```python
@classmethod
def from_question(cls, question, upload_token, *, headers_only: bool):
    columns = []
    for conflict in question.conflicts:
        raw = conflict.to_dict()
        if headers_only:
            raw["example_values"] = []
        columns.append(DateFormatColumnOut(**raw))
    return cls(upload_token=upload_token, columns=columns)
```
Its docstring (`:469-476`) states the rule: redaction is "never the detector's job, never the panel's job, only this classmethod's". **Known pre-existing leak, explicitly out of scope (CONTEXT §deferred):** `StructuralQuestionResponse.from_question` (`wire.py:364-368`) passes `evidence_rows` through unredacted; only `StructuralHintPanel.tsx:48-53` hides them. Do not fix it in this phase; do not make it worse.

---

### 8. `api/routes/structural_hint.py` + `api/routes/sheets.py` (MODIFIED — untrusted input)

**`_to_domain_hint` (`structural_hint.py:180-188`) — the wire→domain mapping to extend:**
```python
def _to_domain_hint(wire: StructuralHintIn) -> StructuralHint:
    return StructuralHint(
        sheet_name=wire.sheet_name,
        header_row_index=wire.header_row_index,
        ...
        table_shape=TableShape(wire.table_shape) if wire.table_shape is not None else None,
    )
```
A client-posted `layout` with `label_column: 999999` or `first_row: -1` is Tampering/DoS input (ASVS V5). **The 422-not-500 idiom to copy:** `ReconcileChoiceIn.decision` / `DateFormatChoiceIn.order` use a `Literal` "so an invalid value is a 422 AT THE BOUNDARY (never a silent mis-apply)" (`wire.py:426-427`, `:497-499`). Integer bounds cannot be a Literal, so the index clamp lives in `_to_domain_hint` (or a validator on the Pydantic model) and must raise a 422 naming the consequence — never let an `IndexError` become a 500 (the exact bug class `upload.py:53-62`/WR-02 fixed once, per RESEARCH).

**`_validated_selections` (`sheets.py:121-162`) — the all-or-nothing validation posture** for anything the client claims about server-retained state:
```python
known = {sheet.name for sheet in entry.sheet_manifest or ()}
for selection in selections:
    if selection.sheet_name not in known:
        raise HTTPException(status_code=422, detail=(
            f"Nothing was ingested: this workbook has no sheet named "
            f"'{selection.sheet_name}'."))
```
Copy the "Nothing was ingested: ..." consequence-first detail-message shape.

**`_resolve_one_sheet` (`sheets.py:175-219`):** the verdict rides to parse time on the retained `SheetManifestEntry` → `resolve_or_map(hint=StructuralHint(layout=...))` here; the exception ladder (`:201-211` — `MissingCredentialsError`→503, `AuthenticationError`→401, `(APIError, ValueError)`→500, always `_unlink` first) is the route-level error idiom for every touched route; `structural_hint.py:79-95` is the same ladder with the temp-file-cleanup rationale written out (CR-03/P2 comment at `:88-94`).

**`upload.py` wiring:** `_sheet_question` (`upload.py:275-315`) calls `describe_workbook(tmp_path, schema_store.list_schemas(), store=store, client=client)` at `:305-307` — this call gains `headers_only=headers_only`, which is already in scope (`:279`) and currently unforwarded. `_asks_which_sheets` (`upload.py:247-272`) is **unchanged** — D-12-15 explicitly rejects widening `> 1` to `>= 1` (it would break `tests/api/test_sheets_route.py:554`).

---

### 9. Evidence-grid renderer (NEW function) ⚠ redaction is invention

**Analog for the branch structure only — `mapper._render_table`** (`mapper.py:148-163`):
```python
def _render_table(table: RawTable, *, headers_only: bool = False) -> str:
    """The one send site D-10's privacy dial gates: `headers_only=True`
    stops after the column list and locale evidence ..."""
    ...
    if headers_only:
        return "\n".join(lines)
    lines.append(f"First {min(_SAMPLE_ROWS, table.row_count)} of {table.row_count} rows:")
```
Copy: `headers_only` as a keyword; the docstring that names itself as a send-site gate. **Differ deliberately:** per D-12-06/RESEARCH, make `headers_only` a **required** keyword (no default) on `render_evidence_grid(rows, *, max_rows=20, max_cols=10, headers_only: bool)` so a future call site cannot forget it — this is stricter than the analog and intentionally so.

**Native types come from `grid.read_grid`** (`grid.py:22-32`; module docstring `:1-11` explains why `pd.read_excel(dtype=str)` is forbidden here — it erases the type signal the redacted grid is made of).

**The type-bucket redaction itself (`str:short/med/long`, `num`, `date`, `blank`) has no analog** — see §No Analog Found. Pin it with pure-function tests on hand-built grids first.

---

### 10. `data/synthetic/lab_corpus/layout_truth.json` (NEW fixture)

**Analog: `manifest.json`** (`data/synthetic/lab_corpus/manifest.json:1-30`) — copy its top-level shape: a `description` string, a glossary/legend object explaining every label used, then the data list. Verified limitation (D-12-17): its `layout` label is per-*file*, covers 20 of 30 workbooks, and omits the driving file — the new file is per-*sheet* (`{file: {sheet_name: layout_kind}}` or a list of `{file, sheet, kind}` records). **Declare in-file that it is a sample, not a census** (D-12-17's wording). Keys must use `LayoutKind` values verbatim so the eval needs no mapping table.

---

### 11. Frontend (MODIFIED)

**`lib/types.ts:225-234`** — `SheetOut.status` union gains members / `layout` field added; copy the doc-comment style that cites the backing `wire.py` class by name (`types.ts:217-224`).

**`state/sheets.ts`** — the three gate functions to re-point (all verified):
- `isUnreadableShape` (`sheets.ts:67-69`): `return sheet.status === "unsupported_shape";` — must **not** treat a `key_value` sheet as unreadable (it now has labels and a Schema control). Whatever statuses replace `unsupported_shape` (`not_a_table` etc.) slot in here.
- `showsDetectedHeaders` (`sheets.ts:89-91`) and `showsSchemaSelect` (`sheets.ts:97-99`) both derive from `isUnreadableShape` — change the predicate once, both follow. The doc comment at `:82-88` ("a patient's name (`TAYLOR, James`) came to be shown to a curator as a column header ... this is the second lock on the same door") must be updated to the verdict-based story, not deleted.
- `UNREADABLE_SHAPE_LINE` (`sheets.ts:79-80`) currently says "un-pivoting such a layout is PARSE-V2-01, deliberately not v1" — **that sentence becomes false this phase**; rewrite it.

**`SheetQuestionPanel.tsx` `StatusBadge` (`:43-66`)** — the switch to extend; copy the muted-fact vs amber-act-on-this distinction its doc comment draws (`:39-42`). New badge copy for a key-value sheet ("labels down the side" per RESEARCH) is a *muted fact* (outline/muted variant), not amber.

**`StructuralHintPanel.tsx` (`:36-89`)** — the derive-controls-from-non-null-proposal-fields pattern (`proposalField`, `:36-40`; `show*Control` flags `:61-64`): the layout-confirmation control follows it exactly — it appears when `question.proposal` carries a layout, never keyed off `unsure_about`'s free text (the doc comment at `:44-47` states this rule). The headers-only evidence redaction (`:48-53`) is component-enforced; keep it working for the new question.

**Frontend test analog:** `sheets.test.ts` builds `SheetOut` literals via a `sheet({...})` factory and asserts the gates (e.g. the `unreadableShape()` helper and its describe block, seen near `:180-195`); the rewritten tests keep that factory style.

---

## Test Patterns (the phase rewrites 22 tests — these are the molds)

### T1. The injected-fake seam (`judge_fn` fakes) — copy `tests/test_describe_workbook.py`

**The recorder fake** (`test_describe_workbook.py:266-273`):
```python
def _ranker(result):
    calls: list[dict] = []
    def _fn(headers, schemas, *, sheet_name=None):
        calls.append({"headers": headers, "sheet_name": sheet_name})
        return result
    return _fn, calls
```
Used at `:276-291` (asserts exactly one call, for the right sheet, with the right args). **The failing-fake test** (`:293-303`): a `rank_fn` that raises `RuntimeError` proves the manifest still builds — the judge's equivalent proves every sheet degrades to `UNKNOWN`/questions, not a 500. **The no-client test** (`:306-312`): no seam, no client, manifest still builds. **The explode-fake** (`:200-211`): a `rank_fn` that raises `AssertionError` if touched pins "the deterministic path never calls Claude" — reuse for "a confident `row_per_record` workbook makes exactly one judge call, zero extra at resolve time".

**Three tests in this file are now WRONG and must be rewritten, not deleted** (verified):
- the autouse `_no_claude` fixture (`:45-53`) asserts *"propose_mapping must NOT be called: describe_workbook is pure Python"* — the fixture stays (the *mapper* is still never called) but the module docstring claim "pure Python" dies;
- `test_the_manifest_has_no_headers_only_parameter_because_it_reads_no_values` (`:188-197`) — signature inspection, now false, **invert it** (assert the parameter exists);
- `test_the_client_and_rank_fn_seams_exist_now_for_plans_11_05_and_11_07` (`:214-224`) — extend the signature assertions with `judge_fn`.

### T2. The SDK-boundary capture fake (the privacy test) — copy `tests/test_headers_only.py:64-89` and `tests/api/test_upload.py:270-314`

**Unit level** (`test_headers_only.py:64-89`):
```python
captured: dict = {}
class _FakeMessages:
    def parse(self, **kwargs):
        captured["content"] = kwargs["messages"][0]["content"]
        class _Resp:
            parsed_output = None
            stop_reason = "end_turn"
        return _Resp()
class _FakeClient:
    messages = _FakeMessages()
...
try:
    propose_mapping(table, field_set, client=_FakeClient(), headers_only=True)
except ValueError:
    pass  # parsed_output is None -- expected; we only care what was sent
assert "CONFIDENTIAL-VALUE-42" not in captured["content"]
```
**HTTP level** (`test_upload.py:270-314`): same fake injected at the DI seam — `app.dependency_overrides[get_anthropic_client] = lambda: _FakeClient()` (`:300`) — through the **real** route and the **real** production chain ("not monkeypatched", the docstring at `:271-276` insists). The judge's SHAPE-04 test copies this at the `/api/upload` → `describe_workbook` → real `judge_workbook_layout` chain, posting a multi-sheet key-value workbook with `headers_only=true`, asserting `"TAYLOR, James"`, `"CS-2026-698392"`, `"3809217"` absent from `captured["content"]`.
**The mirror test is mandatory** (D-12-09): `test_headers_only.py:92-116` (`test_propose_mapping_default_still_sends_sample_rows`) is the existing precedent — with `headers_only=false` assert the real values ARE in the captured content, so a future over-zealous redaction cannot silently degrade default-path accuracy.

### T3. The module-purity guard — KEEP and RE-POINT `tests/test_structure_shape.py:101-118`

```python
def test_classify_shape_module_imports_no_anthropic_or_pandas():
    source = (Path(__file__).resolve().parent.parent / "src" / "assayingest"
              / "parsing" / "structure" / "shape.py")
    text = source.read_text()
    import_lines = [line.strip() for line in text.splitlines()
                    if line.strip().startswith("import ") or line.strip().startswith("from ")]
    assert not any("anthropic" in line for line in import_lines)
    assert not any("pandas" in line for line in import_lines)
    assert not any("openpyxl" in line for line in import_lines)
```
Re-point at `layout.py` **and** `unpivot.py` (parametrize over both paths). The other 7 tests in the file test `classify_shape` and die with it in wave C. Companion guards to keep: `tests/test_parse_entry_shape.py:62` (`test_no_raw_table_construction_path_attaches_a_shape_field`) **verbatim** — it must still hold after the un-pivot exists; `:71` (`test_parse_source_never_returns_a_raw_table_for_a_non_row_per_record_shape`) — watch it does not pass vacuously (RESEARCH Pitfall 1's warning sign). `tests/test_structure_assist.py:119-131` (`test_structure_assist_module_exposes_no_apply_or_raw_table_function`) constrains the judge too: its name must not contain apply/resolve/raw_table.

### T4. Judge unit tests — copy `tests/test_structure_assist.py`'s fake-client suite

The reusable class fakes (`:22-40`: `_FakeParsedResponse`/`_FakeMessages`/`_FakeClient(parsed_output)`); `parsed_output=None` ⇒ `pytest.raises(ValueError, match="no structured proposal")` (`:64-68`); the never-constructs-a-real-client guard via `monkeypatch.setattr(anthropic, "Anthropic", _boom)` (`:71-91`); direct `_to_domain` mapping tests (`:94-116`). New, no analog: the index-clamp test and the omitted-sheet-fills-UNKNOWN test — pure `_to_domain` tests on hand-built wire objects.

### T5. The live eval — copy `tests/test_cross_domain.py:78-81`'s gate

```python
@pytest.mark.skipif(
    os.environ.get("ASSAYINGEST_LIVE_TESTS") != "1",
    reason="live cross-domain mapping proof costs real money -- opt in with ASSAYINGEST_LIVE_TESTS=1",
)
```
Same gate at `tests/test_max_tokens_live.py:46-47` and `tests/test_cli_run.py:125-126,144-145`. The judge's live tests (driving-case, corpus accuracy vs `layout_truth.json`, redacted-grid accuracy, out-of-grid-index probe) all wear it; results go in VERIFICATION.md, per D-12-17 measured-not-asserted.

### T6. The wave-B regression test MUST fail on `main` first (D-12-12)

Shape: `describe_workbook(cascade)` ⇒ `"TAYLOR, James" not in entries["Patient Info"].headers`. The existing signature-suppression test to widen: `tests/test_structure_describe_sheets.py:268` (`test_an_unsupported_shapes_signature_is_never_computed_from_fabricated_headers`) — it asserts `column_signature(description.headers) != column_signature(["Patient Name", "TAYLOR, James"])`. The `_key_value_workbook(tmp_path)` builder (`test_structure_describe_sheets.py:43ff`) says outright no committed key-value fixture exists — the driving file `data/synthetic/lab_corpus/cascade_allergy_CS-2026-698392.xlsx` is already in the repo; use it directly per RESEARCH.

### T7. Round-trip/persistence extensions

`tests/test_structure_hint.py:17` (full-population round trip) and `:36` (enum→string serialisation) — EXTEND with `layout`/`LayoutKind`. `tests/test_profile_store.py:52` (`test_structural_hint_round_trips`, hint built at `:53`: `StructuralHint(header_row_index=2, table_shape=TableShape.ROW_PER_RECORD)`) — EXTEND with a `layout`-carrying hint; this is where the nested-frozen-dataclass `_jsonable` question (§1) gets its verifying test. `tests/test_hint_and_locale.py:153` (`test_unsupported_shape_question_is_not_answerable_by_a_hint`) — **INVERT**: after this phase the shape question IS answerable.

### T8. Ranker-style hygiene tests for the judge module

Copy `tests/test_schema_ranker.py:306-311` (`test_the_module_itself_compiles_in_no_domain_vocabulary` — greps the module source for banned domain words) and its runtime sibling just above (`:295-303`, greps the captured `system` + `content`). D-18 requires the same pair for the judge: `Patient Name` may appear in a fixture, never in a prompt string.

---

## Shared Patterns

### Wire→domain boundary mapping (`_to_domain` at every seam)
**Sources:** `structure_assist._to_domain` (`structure_assist.py:74-87`), `schema_ranker._to_domain` (`schema_ranker.py:207-230`), `structural_hint._to_domain_hint` (`structural_hint.py:180-188`).
**Apply to:** the judge's wire models, `StructuralHintIn.layout`. Rule stated at `schema_ranker.py:19-21`: constrain at the SDK/HTTP boundary AND drop/clamp again in `_to_domain` — "A boundary closed once is a boundary closed by luck."

### Fail-closed availability boundary
**Source:** `service._rank_or_none` (`service.py:1975-1994`, quoted in full in §6).
**Apply to:** the judge's caller in `service.py`. Broad `except Exception`, logged once with `exc_info=True`, never logged AND raised; the docstring must state how the judge's degradation differs from the ranker's (question vs suggestion — D-12-16).

### Injectable fn-seam, not monkeypatching
**Sources:** `_ranker_for` (`service.py:1956-1972`), `propose_mapping_fn` (`service.py:251-258`, `:306`).
**Apply to:** `describe_workbook(judge_fn=None)`, `resolve_or_map(judge_fn=None)`. Keyword-only, defaulted `None`, so every existing call site is byte-for-byte unchanged. `dependency_overrides` stays for the *client*; the fn-seam is for the *logic*.

### Per-site `headers_only` enforcement + captured-outbound proof
**Sources:** `mapper.py:148-163` (render branch), `cli.py:376-384` (skip, with the rationale comment), `wire.py:482-492` (wire-boundary emptying); proof shape `tests/api/test_upload.py:270-314`.
**Apply to:** the judge's grid renderer (D-12-06: there is no choke point; this phase adds a fourth site and it must implement the guarantee itself — required-kwarg design in §9).

### Consequence-first error/question copy
**Sources:** `table.py:449-457` ("would produce a clean-looking table with every field wrong"), `table.py:296-304` ("guessing risks corrupting the value by 1000x"), `sheets.py`(routes)`:135-141` ("Nothing was ingested: ...").
**Apply to:** `_shape_unknown_question.reason`, every new 422 detail, the judge's log lines.

### Prompt injection hardening at render time
**Sources:** `_one_line` (`mapper.py:133-135`, `schema_ranker.py:192-194`) — both docstrings name the newline-escapes-the-bullet hazard.
**Apply to:** every cell rendered into the judge's evidence grid (newly relevant because D-12-09 sends real values). Note in the plan: the `Literal`-constrained output + the human confirmation gate is the anti-injection control (RESEARCH §Security).

---

## No Analog Found

Files/pieces where the executor is genuinely inventing — the planner should mark these tasks as the risky ones and order them TDD-first (all four are pure functions or data, testable on hand-built inputs):

| Piece | Role | Why no analog | Risk containment |
|------|------|-----------|-----------------|
| `unpivot.py` core transform (blocks → one record; `one_record_per_value_column` → transposed melt; duplicate-label disambiguation `Collected (2)`) | pure transform | No un-pivot exists in `src/` (verified — only refusals mention it). The duplicate-header policy has only a weak precedent (pandas' mangled `col.1` arriving via `frame.columns` at `table.py:192`) | Pure function; write red tests on hand-built grids first; the two driving sheets' expected outputs are already computed in RESEARCH (`Summary` → 10 headers/1 row, `Patient Info` → 17/1, zero duplicates) |
| Type-redacted evidence grid (`str:short/med/long` / `num` / `date` / `blank` buckets, D-12-17) | pure renderer | The only existing redactions *omit* content (`mapper.py:156`, `cli.py:383`, `wire.py:489-490`); nothing in the repo *transforms* content into types | Pure function; RESEARCH §headers_only shows the expected redacted output for the real `Patient Info` grid — use it as the golden test; accuracy cost is measured live, not assumed |
| `_to_domain` index clamp + omitted-sheet→`UNKNOWN` fill | boundary validation | `schema_ranker._to_domain` drops invented *names*; nothing clamps invented *integers* or fills *omissions* | Pure `_to_domain` unit tests (T4); the live `test_live_judge_never_returns_an_out_of_grid_index` proves whether the clamp is ever exercised |
| `layout_truth.json` per-sheet ground truth | fixture | `manifest.json` is per-file, 20/30 coverage, missing the driving file (verified: `cascade_allergy` absent) | Hand-authored; declared in-file as a sample; ~50 sheets per D-12-17 |

Also mildly new but low-risk: the batched one-call-per-workbook request rendering (per-sheet delimited grids in one user message) — no multi-subject Claude request exists yet, but it is a composition of verified pieces (`_render_request` at `schema_ranker.py:197-204` per sheet + the dimension line from `mapper.py:158-160`).

## Metadata

**Analog search scope:** `src/assayingest/` (parsing, mapping, service, api), `frontend/src/` (state, components, lib), `tests/`, `tests/api/`, `data/synthetic/lab_corpus/`.
**Files read this session:** 24 source/test files (targeted reads for `service.py`, `wire.py`, `upload.py`, `mapper.py`, `cli.py`; full reads for everything ≤600 lines that is load-bearing).
**Verified corrections to upstream docs:** none material — every RESEARCH.md `file:line` checked landed within ±2 lines; the single soft citation is `table.py:192` as a "pandas mangles duplicates" precedent (the mangling happens inside pandas before that line; the line itself just receives `frame.columns`).
**Pattern extraction date:** 2026-07-13
