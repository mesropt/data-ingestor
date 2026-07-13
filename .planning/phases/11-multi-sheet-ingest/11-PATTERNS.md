# Phase 11: Multi-Sheet Ingest - Pattern Map

**Mapped:** 2026-07-13
**Files analyzed:** 12 new/modified artifacts (8 backend, 4 frontend)
**Analogs found:** 12 / 12 (2 have partial "no analog" sub-parts, listed at the end)

Every new artifact in this phase has a working, tested analog already in the tree. The phase is
overwhelmingly **composition, not invention** — the RESEARCH.md verdict ("the only genuinely new
primitive in the whole phase is `describe_sheets`") holds after inspection. This map tells the
planner exactly which file:lines each new file copies, what must be copied verbatim, what differs,
and which existing test file each new test mirrors (strict TDD: tests first, red→green).

---

## File Classification

| New/Modified Artifact | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `parsing/structure/sheets.py::describe_sheets` + `SheetDescription` (NEW fn, same file) | parser utility | file-I/O → immutable snapshot | `sheets.py::rank_sheets` + `SheetRanking` (:42-84) | exact (same file, same shape) |
| `service.py::propose_schemas_for_sheet` + `SchemaProposal` + `_covered_fields` | service (pure scorer) | transform (headers → ranked proposals) | `service.py::_prefill_coverage` (:1572), `_vendor_agnostic_alias_index` (:1451), `recall_vendor` (:1497) | exact (scorer = composition of these three) |
| Claude fallback stage of the scorer (D-11-19) | service (LLM boundary) | request-response (structured output) | `mapping/mapper.py::propose_mapping` (:28-69) + `_to_domain` (:195) | role-match (new prompt, same skeleton) |
| `api/wire.py::SheetQuestionResponse` + `SheetOut` + `SheetResolveRequest` + `SheetGroupResponse` | wire model | request-response | `wire.py::DateFormatQuestionResponse` (:461-492) + `DateFormatChoiceIn`/`DateFormatResolveRequest` (:495-524) | exact (D-11-02 names this precedent) |
| `api/routes/sheets.py::POST /api/sheets/resolve` | route | request-response | `api/routes/date_format.py` (whole file) + `upload.py:113-195` branch shape | exact |
| `api/state.py::UploadGroup` + `GroupRegistry` | state/registry | in-memory CRUD | `state.py::UploadEntry` (:75-155) + `UploadRegistry` (:158-235) | role-match (simpler: memory-only, no persistence) |
| `GET /api/export/group/{group_id}/archive` + zip builder | route + writer | file-I/O | `api/routes/export.py` (:27-59) + `service.export` (:561-589) | role-match (zip part has no analog — stdlib `zipfile`) |
| `__source_sheet` through `canonical.py` + `export/writers.py` | model + writer | transform + file-I/O | `canonical.py::_inferred_constants` (:198-207) + `writers.py:40-67` | exact precedent for "a fact about the file, constant per row" |
| `frontend/src/components/SheetQuestionPanel.tsx` (+ `SheetCard`) | component | request-response (one panel, one submit) | `components/DateFormatQuestionPanel.tsx` (whole file) | exact (multi-item/single-submit sibling) |
| `frontend/src/state/sheets.ts` (panel logic helpers) | store (pure fns) | transform | `state/dateFormat.ts` (:50-98) | exact |
| Review member tabs (`ReviewGroupTabs` wrapping `Review`) | component | request-response | `screens/Review.tsx` (whole) + `components/AppShell.tsx:47-55` Tabs idiom | role-match (forceMount is new) |
| `state/upload.ts` phases + `lib/types.ts` union kinds | store + types | event-driven reducer | `upload.ts:79-85, 119-120, 203-213` (`dateQuestion` pair) + `types.ts:183-209` | exact (mechanical addition) |

---

## Pattern Assignments

### 1. `parsing/structure/sheets.py` — `describe_sheets()` + `SheetDescription` (NEW, sibling of `rank_sheets`)

**Analog:** `src/assayingest/parsing/structure/sheets.py` — `SheetRanking` (:42-64) and `rank_sheets` (:67-84). **Do NOT widen `SheetRanking` or touch `rank_sheets`** (D-11-21, RESEARCH Pattern 2 — 5 tests pin their exact shape).

**Frozen-dataclass + docstring-pins-intent pattern** (`sheets.py:42-64`):
```python
@dataclass(frozen=True)
class SheetRanking:
    """Ranked candidate sheets for PARSE-04 sheet selection.

    `ranked` is sorted highest score first, as `(sheet_name, score)` pairs.
    `confident` is False whenever the top two scores are within
    `_CONFIDENCE_MARGIN` -- the caller must not auto-pick `ranked[0]` in that
    case; ..."""

    ranked: list[tuple[str, float]]
    confident: bool

    @property
    def winner(self) -> str | None:
        ...
```

**Workbook-iteration pattern to copy** (`sheets.py:67-84` — note `list_worksheets` structurally excludes chartsheets, D-17):
```python
def rank_sheets(path: str | Path) -> SheetRanking:
    worksheets = list_worksheets(path)
    rows_by_sheet = {ws.title: list(ws.iter_rows(values_only=True)) for ws in worksheets}
    ...
```

**Copy verbatim:** the frozen dataclass style; module-docstring naming the fixture evidence; `from .grid import list_worksheets` (never raw `openpyxl.load_workbook` — chartsheets would crash it); the `str | Path` signature.
**Differs:** `describe_sheets` must additionally run `detect_header` per sheet and slice headers at `detection.index` (the pattern is at `table.py:314` and `:334-336` — Pitfall 2: zephyr's headers are on row 4, not row 0), call `is_drawing_only_sheet` (`table.py:325` call site) and `classify_shape` (`table.py:341` call site), and return **every** sheet marked-never-dropped. Guard `detection.index is None` (Pitfall 1: orion's `Notes` sheet) → `headers=[]`, `status=header_uncertain`. **No import from `learning/`** — `column_signature` is computed one layer up in `service.py` (dependency direction, CLAUDE.md).
**Deliberately NOT copied:** `_CONFIDENCE_MARGIN = 0.1` (`sheets.py:28`) — D-11-06 forbids any threshold in the new path.

**Test analog:** `tests/test_structure_sheets.py` — copy its shape exactly: module docstring naming *why* each fixture is the reference case, `_FIXTURES = Path(__file__).resolve().parent.parent / "data" / "synthetic"`, one behavioral assertion per test against real fixtures:
```python
def test_rank_sheets_meridian_confident_with_data_as_winner():
    ranking = rank_sheets(_FIXTURES / "meridian_cro_codes.xlsx")
    assert ranking.confident is True
    assert ranking.winner == "DATA"
```
New tests mirror this per the RESEARCH probe table: zephyr Week 1-3 → `ok` with row-4 headers; orion Notes → `header_uncertain`, `headers == []`, no crash; meridian LEGEND → `header_uncertain`; chartsheet fixture excluded.

---

### 2. `service.py` — `_covered_fields()` extraction + `SchemaProposal` + `propose_schemas_for_sheet()`

**Analogs:** `service.py::_prefill_coverage` (:1572-1597), `_vendor_agnostic_alias_index` (:1451-1476), `field_set_from_schema` (:1431-1448), `recall_vendor` (:1497-1557).

**The core to extract, not fork** (`service.py:1584-1597` — the loop that becomes `_covered_fields(headers, index)`):
```python
    index = _vendor_agnostic_alias_index(schema)
    prefilled: dict[str, FieldMapping] = {}
    for header in table.headers:
        canonical_name = index.get(_normalise_header(header))
        if canonical_name is not None and canonical_name not in prefilled:
            prefilled[canonical_name] = FieldMapping(
                target_field=canonical_name,
                source_column=header,
                confidence=1.0,
                reasoning=f"pre-filled from the schema crosswalk for {header!r}",
                needs_confirmation=False,
            )
    remaining = tuple(f for f in field_set.fields if f.name not in prefilled)
    return prefilled, remaining
```
**Preserve exactly:** the **first-header-wins** rule (`canonical_name not in prefilled`) and `_normalise_header` from `learning.signature` (:44) — never `.lower().strip()` (Don't-Hand-Roll: forking normalisation silently splits the crosswalk index from the learning-loop index). `_prefill_coverage`'s public behaviour must be byte-identical after the extraction — `tests/test_python_first_prefill.py` and `tests/api/test_upload_schema_target.py` guard it.

**The collision-refuses-to-guess index pattern** (`service.py:1467-1476` — `None` marks a cross-vendor collision):
```python
    index: dict[str, str] = {}
    collided: set[str] = set()
    for canonical_field in schema.fields:
        for alias in canonical_field.aliases:
            key = _normalise_header(alias.source_column)
            if key in index and index[key] != canonical_field.field.name:
                collided.add(key)
            else:
                index[key] = canonical_field.field.name
    return {key: (None if key in collided else value) for key, value in index.items()}
```
D-11-17 (own-name-as-implicit-alias) lands here or beside it: seed the index with `_normalise_header(canonical_field.field.name) -> field.name` before the alias loop, subject to the same collision rule.

**The fixed-escalation-ladder docstring + shape to copy for the scorer's staging** (`recall_vendor`, `service.py:1538-1557` — stage 1 profile via `store.find(field_set.signature, column_signature(table.headers))`, stage 2 crosswalk, refuse ties):
```python
    if store is not None:
        profile = store.find(field_set.signature, column_signature(table.headers))
        if profile is not None and profile.vendor is not None:
            return VendorMemory(vendor=profile.vendor, source="profile", candidates=())
    ...
    if len(vendors) == 1:
        return VendorMemory(vendor=next(iter(vendors)), source="crosswalk", candidates=())
    if len(vendors) >= 2:
        return VendorMemory(vendor=None, source=None, candidates=tuple(sorted(vendors)))
    return VendorMemory(vendor=None, source=None, candidates=())
```
Copy: the `source: "profile" | "crosswalk"` naming, the graceful `store=None`/`schema=None` degradation, the "two or more = refuse, return sorted candidates" discipline (D-11-06: a tie is shown as a tie). The `Escalation` frozen dataclass (:1560-1569) is the style model for `SchemaProposal`.
**Differs:** the scorer takes a `list[str]` of headers, never a `RawTable` (a headers-only stub is unnecessary — `_covered_fields` reads a list); it enumerates Schemas via `SchemaStore.list_schemas()` **only** (tombstone rule D-10-15 — the filter is structural at `postgres_schema_store.py:311/:336`, the scorer adds none of its own); the alias index is built **once per Schema** and reused across all M sheets.

**Test analog:** `tests/test_python_first_prefill.py`. Mirror its sections one-for-one: index-behaviour tests (`test_vendor_agnostic_index_collides_to_none_when_two_vendors_disagree`, :139), tombstone tests (`test_vendor_agnostic_index_excludes_a_tombstoned_alias`, :162 — mirror against the scorer per RESEARCH §Tombstones: a tombstoned alias contributes zero coverage, a tombstoned field is absent from `total`/`uncovered`), and zero-LLM proofs (`test_full_crosswalk_coverage_calls_the_mapper_zero_times`, :180). Also mirror `tests/api/test_upload_schema_target.py:186/:209` (the tombstone pair) against the scorer.

---

### 3. Claude fallback stage of the scorer (D-11-19 — only when both deterministic stages return zero everywhere)

**Analog:** `src/assayingest/mapping/mapper.py::propose_mapping` (:28-69).

**The structured-output call skeleton to copy** (`mapper.py:45-69`):
```python
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_render_system_prompt(field_set),
        messages=[{"role": "user", "content": _render_request(...)}],
        output_format=build_wire_models(field_set.field_names),
    )
    wire = response.parsed_output
    if wire is None:
        raise ValueError(
            f"Mapping failed for {table.label}: the model returned no "
            f"structured proposal (stop reason: {response.stop_reason})."
        )
```
Copy: `_MODEL = "claude-opus-4-8"` / `_MAX_TOKENS` module constants (:23-24); the `client: anthropic.Anthropic | None = None` injectable-client signature (:31) — this is what lets every test stub it; the `parsed_output is None → ValueError` fail-closed check with the consequence-first message; the wire→domain boundary mapping in a `_to_domain`-style private function (:195-225 — closes the "model names a Schema that does not exist" gap at the boundary, exactly as `_names_a_column_that_does_not_exist` (:256) closes the hallucinated-column gap).

**Headers-only rendering precedent** (`mapper.py:148-157` — the fallback sends headers in BOTH modes, which is all it ever sees, D-11-19):
```python
    labelled = [h if h else "(blank header)" for h in table.headers]
    lines = [f"Columns ({len(table.headers)}): {' | '.join(labelled)}", ""]
    ...
    if headers_only:
        return "\n".join(lines)
```
**Differs:** the prompt asks "rank these governed Schemas for this header list", not "map columns to fields"; output schema is a small ranked-list wire model (build it runtime like `build_wire_models`); the result is still only a **proposal** — it pre-selects, never auto-applies (D-11-06 unchanged).
**Injection pattern for staging:** copy `_python_first_prefill`'s `propose_mapping_fn=None` parameter idiom (`service.py:1600-1631`) so tests can prove "the deterministic stages ran first and Claude was called zero times when coverage exists".

**Test analog:** `tests/test_python_first_prefill.py:180-241` (the zero-calls / only-the-remainder proofs, using the injectable-fn stub) and `tests/api/test_date_format_route.py:79-96`'s `_mapper()` stub factory:
```python
def _mapper(headers_map: dict[str, str]):
    def _fn(table, field_set, client=None, *, headers_only=False):
        return MappingProposal(...)
    return _fn
```
`tests/test_mapper_boundary.py` is the analog for the new wire→domain boundary tests (unknown-Schema-name from the model must be dropped/flagged, never trusted).

---

### 4. `api/wire.py` — `SheetQuestionResponse` (5th arm) + `SheetGroupResponse` (6th) + `SheetResolveRequest`

**Analog:** `wire.py::DateFormatQuestionResponse` (:461-492), `DateFormatColumnOut` (:449-458), `DateFormatChoiceIn` (:495-511), `DateFormatResolveRequest` (:514-524). D-11-02 names this precedent explicitly.

**The question-arm pattern** (`wire.py:461-492`):
```python
class DateFormatQuestionResponse(BaseModel):
    """The `kind="date_question"` 4th arm of `/api/upload`'s discriminated
    response (Pattern 5, D-10-07) ... Bundles EVERY ambiguous column from
    this upload into ONE question ... redaction is never the detector's job,
    never the panel's job, only this classmethod's."""

    kind: str = "date_question"
    upload_token: str
    columns: list[DateFormatColumnOut]

    @classmethod
    def from_question(
        cls, question: DateFormatQuestion, upload_token: str, *, headers_only: bool
    ) -> "DateFormatQuestionResponse":
        columns = []
        for conflict in question.conflicts:
            raw = conflict.to_dict()
            if headers_only:
                raw["example_values"] = []
            columns.append(DateFormatColumnOut(**raw))
        return cls(upload_token=upload_token, columns=columns)
```
Copy: `kind: str = "sheet_question"` defaulted-literal discriminant; one bundled question for the whole workbook (never one per sheet); a `from_*` classmethod holding ALL domain→wire conversion so routes stay adapters; the docstring naming which decision each field serves. **Headers are NOT redacted** under `headers_only` (a header is not a cell value, D-10-05) — say so in the docstring the way `:443` does.

**The resolve-request pattern** (`wire.py:495-524`): `Literal[...]` fields so an invalid value is a **422 at the boundary**; the docstring's "the real state is server-retained under the token, never re-sent by the client (T-08-08)". For `SheetSelectionIn`, `sheet_name`/`schema_name` are validated against the **server-retained manifest** (Pitfall 6) — 422/404, never a `ValueError→500`.
**Differs:** `SheetOut` carries the manifest (headers, row_count, `column_signature`, status Literal, ranked `proposals`, `proposed_schema: str | None` where `None` ⇒ skip, `tie: bool` — RESEARCH Pattern 6 gives the exact field list); `SheetGroupResponse.members[*].response` is a serialized **existing** arm (recursive shape, so a member's structural/date question reuses its panel verbatim).

**Test analog:** the wire arms are tested through the routes — `tests/api/test_date_format_route.py:142-167` is the body-shape assertion model (`assert body["kind"] == "date_question"`, then every field asserted by name).

---

### 5. `api/routes/sheets.py` — `POST /api/sheets/resolve`

**Analog:** `src/assayingest/api/routes/date_format.py` (entire file, 131 lines) for the resolve-route skeleton; `api/routes/upload.py:113-195` for the parse/branch/retain choreography each member goes through.

**Route signature + auth gate** (`date_format.py:52-66`):
```python
@router.post("/api/date-format/resolve")
def resolve_date_format(
    body: DateFormatResolveRequest,
    store=Depends(get_profile_store),
    schema_store=Depends(get_schema_store),
    # D-10-13: a gate only, not a value this route reads -- the dependency's
    # sole job is to raise 401 for a signed-out request.
    user: User = Depends(require_user),
):
    entry = registry.pop(body.upload_token)
    if entry is None or entry.table is None or entry.proposal is None:
        raise HTTPException(
            status_code=404,
            detail=f"no pending date question for token '{body.upload_token}'",
        )
```
Copy: `Depends(require_user)` with the same comment (D-10-13); `registry.pop` + shape-check → 404 naming the consequence; fail-closed 422 on incomplete answers (`date_format.py:74-78`: `UnresolvedDateColumnsError → 422`; the sheet analog is `selections == []` and any `sheet_name` not in the retained manifest); the re-fetch-Schema-by-retained-name idiom (`date_format.py:125`: `schema = schema_store.get_schema(entry.schema_name) if entry.schema_name else None`); the per-member `recall_vendor` + `MappingResponse.from_proposal(..., escalation=, vendor_memory=, source_name=entry.source_file_name)` tail (:126-131).

**Per-member parse/branch choreography** (`upload.py:124-173` — each selected sheet re-runs this with `sheet=X`):
```python
    try:
        result = service.resolve_or_map(
            tmp_path, resolved_field_set,
            store=store, sheet=sheet, headers_only=headers_only, client=client,
            schema=resolved_schema,
        )
    except service.MissingCredentialsError as exc:
        os.unlink(tmp_path)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except anthropic.AuthenticationError as exc:
        os.unlink(tmp_path)
        raise HTTPException(status_code=401, detail="Anthropic rejected the credentials.") from exc
    except (anthropic.APIError, ValueError) as exc:
        os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if isinstance(result, StructureQuestion):
        token = registry.put(UploadEntry(field_set=..., tmp_path=tmp_path, source_file_name=file.filename))
        return StructuralQuestionResponse.from_question(result, token)

    if result.date_question.has_conflicts:
        token = registry.put(UploadEntry(..., tmp_path=None, table=result.table,
                                         proposal=result.proposal, schema_name=schema_name,
                                         escalation=result.escalation, ...))
        os.unlink(tmp_path)
        return DateFormatQuestionResponse.from_question(result.date_question, token, headers_only=headers_only)
```
**Must pass `schema=`, `sheet=`, and check `result.date_question`** — omitting them is exactly the `structural_hint.py:56` bug D-11-22 fixes in this phase (four consequences enumerated in RESEARCH Pitfall 4; the fix mirrors `date_format.py:125`'s re-fetch and `upload.py:154-173`'s date branch). **Temp-file rule (Pitfall 3):** a question-bearing member gets its **own copy** of the temp file (`shutil.copyfile`) so `structural_hint.py`'s unlinks and the registry's eviction-unlink stay correct with zero changes.
**Differs:** this route loops over N selections, retains one ordinary `UploadEntry` per member (Option A, D-11-20), records `(sheet_name → token)` in the new `GroupRegistry`, and wraps each member's arm in `SheetGroupResponse`.

**Test analog:** `tests/api/test_date_format_route.py` — copy its harness verbatim: `_client(profile_store)` with `app.dependency_overrides[get_profile_store]` + `[get_current_user] = lambda: verified_user()` (:99-105), `_clear()` (:108-111), `monkeypatch.setattr(service, "propose_mapping", _mapper({...}))` + `monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")` (:142-147), `_post_upload_file`/`_post_upload_bytes` helpers (:114-136 — extend for `.xlsx` bytes), and one test per arm/edge (invalid literal → 422 at the boundary, :341; extra client key dropped, :360). The multi-sheet upload branch tests go in a new `tests/api/test_sheets_route.py` mirroring this file's structure end to end; `tests/api/test_upload.py` (all-CSV) must stay green untouched.

---

### 6. `api/state.py` — `UploadGroup` + `GroupRegistry` (+3 defaulted fields on `UploadEntry`)

**Analog:** `state.py::UploadEntry` (:75-155) and `UploadRegistry` (:158-235).

**The additive-defaulted-field pattern for `UploadEntry`** (`state.py:137-155` — every prior phase added its retention shape as defaulted fields; the sheet flow adds `group_id: str | None = None`, `sheet: str | None = None` the same way):
```python
    field_set: FieldSet | None
    headers_only: bool
    tmp_path: str | None
    table: RawTable | None = None
    provenance: str | None = None
    ...
    schema_name: str | None = None
    strictness: str = "strict"
    ...
    source_file_name: str | None = None
```
**The registry skeleton** (`state.py:171-181` — token minting; and :224-236 — eviction unlink guard):
```python
    def put(self, entry: UploadEntry) -> str:
        token = str(uuid.uuid4())
        self._entries[token] = entry
        self._evict_oldest_if_over_capacity()
        if _is_review_ready(entry):
            self._persist(token, entry)
        return token
```
Copy: `str(uuid.uuid4())` id minting; the module-level singleton with its one-line justification (`state.py:376-379`); dataclass docstrings that name which route sets and which route reads each field.
**Persistence rule:** the round-trip serializers `_entry_to_json` (:300-334) / `_entry_from_json` (:337-373) gain the new keys **read with `.get()`** — the exact idiom already at `:364-367`:
```python
        # `.get`, not `[...]`: rows persisted before this key existed have
        # nothing truthful to offer here, ...
        source_file_name=raw.get("source_file_name"),
```
`_is_review_ready` (:272-285) is **unchanged** — each group member is an ordinary review-ready entry (D-11-20's decisive argument).
**Differs:** `GroupRegistry` is **memory-only** (no `pending_uploads` write-through — members persist individually; a restart loses only the "download all" convenience — state this in the plan, per RESEARCH Pattern 5) and needs no LRU (a group is a handful of ids). Shape per RESEARCH: `members: dict[str, str]` (sheet_name → upload_token), `runs: dict[str, str]` (sheet_name → run_id, filled by confirm), `source_file_name`.

**Test analog:** `tests/api/test_state.py` — direct registry exercise, no HTTP layer ("seed the registry directly" idiom, its docstring), one contract per test with a consequence-naming docstring. New tests: group round-trip, `record_run`, and the persistence-round-trip additions go beside the existing `_entry_to_json`/`_entry_from_json` tests (an **old** persisted row missing the new keys must still rehydrate).

---

### 7. Group export — `GET /api/export/group/{group_id}/archive` (+ zip builder)

**Analogs:** `api/routes/export.py` (:27-59) for the download route; `service.export` (:561-589) for the writer orchestration it aggregates.

**Validate-before-filesystem pattern** (`export.py:41-59` — the discipline Pitfall 7 extends to zip entry names):
```python
_RUN_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

@router.get("/api/export/{run_id}/{fmt}")
def download_export(run_id: str, fmt: str) -> FileResponse:
    if fmt not in _FORMATS:
        raise HTTPException(status_code=404, detail=f"unknown export format '{fmt}'")
    if not _RUN_ID_PATTERN.match(run_id):
        raise HTTPException(status_code=404, detail=f"no export run '{run_id}'")
    filename, content_type = _FORMATS[fmt]
    path = EXPORT_BASE_DIR / run_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"no '{fmt}' export for run '{run_id}'")
    return FileResponse(path, media_type=content_type, filename=filename)
```
Copy: the same `_RUN_ID_PATTERN`-style validation for `group_id` (also a `uuid4`); the fixed-allowlist posture (a client string never becomes a path component); 404s naming the consequence.
**Gate pattern:** the archive route is enabled only when **every** member has a recorded `run_id` in `UploadGroup.runs` — the per-member gate is `service.confirm`'s existing `NotReadyError` (`service.py:577-578`), **never** a new group-level readiness check (Don't-Hand-Roll table):
```python
    if not proposal.is_ready:
        raise NotReadyError(proposal.unclear_fields)
```
**Differs / no analog:** the zip assembly itself — stdlib `zipfile.ZipFile`, entry names sanitized with an allowlist `[A-Za-z0-9._ -]`, fallback `sheet_<index>` (zip-slip, Pitfall 7). Each member's files come from its own `EXPORT_BASE_DIR / run_id / export.{fmt}` — the fixed per-dir filenames (`service.py:580-582`) are safe because every member owns its directory.

**Test analog:** `tests/api/test_hint_and_export.py` (the existing export-route API test) for download assertions; `tests/api/test_state.py`'s direct style for the group-runs bookkeeping; a dedicated zip-slip test (a sheet titled `../../evil` never escapes the archive root) mirroring `export.py`'s traversal-rejection docstring intent.

---

### 8. `__source_sheet` provenance — `canonical.py` + `export/writers.py`

**Analog:** `canonical.py::_inferred_constants` (:198-207) — the existing "a fact about the file, not about any one row, written as a constant onto every record" precedent:
```python
def _inferred_constants(proposal: MappingProposal) -> dict[str, str]:
    """Each field whose value was INFERRED rather than read from a column
    (`value_source`), and the constant it contributes to every row. ..."""
    return {
        mapping.target_field: mapping.inferred_value
        for mapping in proposal.field_mappings
        if value_source(mapping) == INFERRED
    }
```
**`CanonicalTable` gains a defaulted parallel list** — copy the existing defaulted-field style (`canonical.py:112-127`):
```python
@dataclass(frozen=True)
class CanonicalTable:
    field_names: list[str]
    records: list[dict[str, str | float | None]]
    flagged: list[str] = field(default_factory=list)
    # NEW: record_sources: list[str] = field(default_factory=list)  — parallel to `records`
```
`assemble()` gains keyword-only defaulted `source_sheet: str | None = None` — copy `date_formats`'s own precedent at `:130-145` ("Omitting it entirely preserves every existing call site's exact behavior"). Exactly three call sites exist (`cli.py:598`, `validator.py:130`, `service.py:463`) and only `service.py`'s changes.

**The writer constraint that forces explicit threading** (`writers.py:40-67` — three different behaviours from one smuggled extra key, D-11-14):
```python
def write_csv(tidy: CanonicalTable, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=tidy.field_names)   # extra key -> ValueError RAISED
        writer.writeheader()
        writer.writerows(tidy.records)

def write_xlsx(tidy: CanonicalTable, path: Path) -> None:
    ...
    for record in tidy.records:
        sheet.append([record.get(name) for name in tidy.field_names])  # extra key SILENTLY DROPPED

def write_json(tidy: CanonicalTable, path: Path) -> None:
    path.write_text(json.dumps(tidy.records, indent=2, ensure_ascii=False), ...)  # extra key APPEARS
```
Each writer opts in deliberately (RESEARCH Pattern 4 gives the literal diffs): append `SOURCE_SHEET_COLUMN = "__source_sheet"` to the fieldname list **only when `tidy.record_sources` is non-empty**, zip records with sources. `ensure_ascii=False` everywhere (T-03-12). `build_manifest` (:70-104) gains an additive `source_sheet` key.
**Value sourcing (D-11-15, every ingest):** neither `RawTable.sheet_name` (None for single-sheet/CSV, `table.py:328`) nor `source_name` (a tempfile name on the API path) can supply it — RESEARCH P-A: add defaulted `RawTable.origin_sheet`, set unconditionally at `table.py:133/:464-470`, persisted via the `.get()` idiom in `state.py`; provenance value = `table.origin_sheet or entry.source_file_name`. **Never** put `source_sheet` in the `FieldSet` — it changes `FieldSet.signature` and silently breaks every learned profile (D-11-13, confirmed at `service.py:1436-1440`).

**Test analog:** `tests/test_export_writers.py` — copy its exact structure: a `_tidy()` factory (:20-28, now with/without `record_sources`), per-writer sections, byte-level assertions:
```python
def test_write_csv_header_row_is_field_names_and_none_becomes_empty_string(tmp_path):
    path = tmp_path / "out.csv"
    write_csv(_tidy(), path)
    with path.open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["compound_id", "value", "unit"]
```
New tests per RESEARCH Test Strategy: each writer emits `__source_sheet` when `record_sources` is set and **nothing extra** when empty; pin explicitly that `write_csv` does not raise (the loud failure mode); Unicode `µM` still survives. `tests/test_canonical.py` stays green (defaulted kwarg).

---

### 9. `frontend/src/components/SheetQuestionPanel.tsx` (+ `SheetCard` child block)

**Analog:** `frontend/src/components/DateFormatQuestionPanel.tsx` (whole file, 124 lines) — the multi-item/single-submit question panel, named as the pattern by D-11-02 and UI-SPEC Discretion §1.

**Props + local-answers + gated-submit skeleton** (`DateFormatQuestionPanel.tsx:11-48`):
```tsx
interface DateFormatQuestionPanelProps {
  question: DateFormatQuestionResponse;
  headersOnly: boolean;
  submitting: boolean;
  onResolve: (choices: DateFormatChoice[]) => void;
}
...
export function DateFormatQuestionPanel({ question, headersOnly, submitting, onResolve }: ...) {
  const [answers, setAnswers] = useState<Record<string, DateFormatOrder>>({});

  function handleSubmit() {
    onResolve(toResolvePayload(question.upload_token, answers).choices);
  }

  const ready = allColumnsAnswered(question.columns, answers);
```
**Per-item bordered block + one submit** (:63-70 and :113-116 — the `SheetCard` copies this block idiom):
```tsx
        {question.columns.map((column) => (
            <div key={column.target_field}
                 className="flex flex-col gap-2 rounded-lg border border-border p-3">
              ...
        <Button type="button" disabled={submitting || !ready} onClick={handleSubmit} className="self-start">
          {submitting && <Loader2 className="size-4 animate-spin" />}
          Use This Order and Continue
        </Button>
```
Copy: the `Card`/`CardHeader` + lucide icon + `text-heading` title shape (:51-61, swap `CalendarClock` for `Layers`); `rounded-lg border border-border p-3` per-sheet blocks; the pure-helper split — ALL logic (`allColumnsAnswered` → "every ticked sheet has a Schema", `toResolvePayload` → `SheetResolveRequest`) lives in a new `state/sheets.ts`, mirroring `state/dateFormat.ts` (:50-98), so vitest covers it with zero DOM ("logic is tested, rendering is gsd-ui-checker-validated" — `state/upload.ts` module docstring). Copywriting/colors/pre-selection states come from `11-UI-SPEC.md` verbatim (checkbox + per-sheet `Select`; tie → amber notice + empty Select; zero coverage → unticked + skip line).
**Differs:** one new shadcn official primitive `checkbox` (UI-SPEC Registry Safety — the only install); the per-sheet `Select` over governed Schemas (reuse `SchemaPicker`'s idiom); status badges reuse the `Badge` chip idiom.

**Test analog:** `frontend/src/state/dateFormat.test.ts` (97 lines) for the new `state/sheets.test.ts` — pure-function tests for gating (0 ticked ⇒ blocked; ticked-with-no-Schema ⇒ blocked naming the sheet), payload shape (only ticked sheets appear in `selections`), and pre-selection derivation (proposal/tie/zero-coverage).

---

### 10. Review member tabs — `ReviewGroupTabs` wrapping the existing `Review`

**Analogs:** `frontend/src/screens/Review.tsx` (whole — reused per member, internals unchanged) + `components/AppShell.tsx:47-55` for the installed `Tabs` idiom + `ui/tabs.tsx:82` exports (`Tabs, TabsList, TabsTrigger, TabsContent, tabsListVariants`).

**The Tabs idiom to copy** (`AppShell.tsx:47-55`):
```tsx
          <Tabs value={activeTab} onValueChange={(value) => onTabChange(String(value))}>
            <TabsList>
              {tabs.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
```
**The state-loss hazard the wrapper exists to avoid** (`Review.tsx:85-86` — `mappings` is local `useState` seeded from props; a remount destroys a curator's amber resolutions):
```tsx
export function Review({ mapping, schemaName, signedIn, verified, onRequireSignIn }: ReviewProps) {
  const [mappings, setMappings] = useState(mapping?.field_mappings ?? []);
```
Therefore **every `TabsContent` uses `forceMount` and hides when inactive** (Pitfall 8 / UI-SPEC Discretion §2 — a design requirement, not a nit). Note the existing remount contract: `App.tsx` keys `Review` by `upload_token` so a *fresh upload* remounts it (`Review.tsx:74-77` docstring) — keep that per member (each member has its own stable token as its key), but tab *switching* must never change keys.
**Copy per member, unchanged:** `Review`'s entire internals — `ReviewTable`, vendor input (:216-226), escalation line (:206-208), `ConfirmGate`/`ExportBar` swap (:268-282), `GateRejected → applyGateRejection` re-flag loop (:167-177). A member whose arm is still `structural_question`/`date_question` renders `StructuralHintPanel`/`DateFormatQuestionPanel` verbatim inside its tab.
**Differs:** the tab strip + per-tab status indicators (amber count / amber dot with `aria-label` / green check — UI-SPEC copywriting table) and the group "Download All" bar (enabled only when every member confirmed). **N=1 renders with no strip and no group bar** — pixel-identical to today plus the provenance line (SHEET-01 no-regression; do not pin byte-identity, D-11-15's line wins).

**Test analog:** `frontend/src/state/review.test.ts` for any new pure member-status derivation (put "which badge does this member show" logic in `state/`, not in the component); `state/upload.test.ts` for the flow into the group phase.

---

### 11. `frontend/src/state/upload.ts` — `sheetQuestion` / `resolvingSheets` / `sheetGroup` phases

**Analog:** the existing `dateQuestion`/`resolvingDateFormat` pair — this is a four-times-proven mechanical recipe. Copy each of these five touch points:

**(a) State union arms** (`upload.ts:79-85`):
```ts
  | { phase: "dateQuestion"; file: File; response: DateFormatQuestionResponse; uploadToken: string }
  | { phase: "resolvingDateFormat"; file: File; uploadToken: string }
```
**(b) Action triple** (`upload.ts:99-101`): `SUBMIT_DATE_FORMAT` / `DATE_FORMAT_SUCCESS` / `DATE_FORMAT_ERROR` → `SUBMIT_SHEETS` / `SHEETS_SUCCESS` / `SHEETS_ERROR`.
**(c) `fromResponse` cases + the compile-time net** (`upload.ts:111-126`):
```ts
    case "date_question":
      return { phase: "dateQuestion", file, response, uploadToken: response.upload_token };
    default:
      // Exhaustiveness: a future 5th `kind` is a compile-time error here,
      // not a silent fall-through into the wrong phase.
      return assertNever(response);
```
Adding the kinds to `UploadResponse` breaks this `assertNever` (and `Upload.tsx`'s) at compile time until the real cases exist — the safety net working as designed; never widen a `default`.
**(d) `toDropzonePhase` → `"locked"`** (`upload.ts:149-156`): add the three new phases to the `locked` group.
**(e) Reducer guard-then-transition triple** (`upload.ts:203-213`):
```ts
    case "SUBMIT_DATE_FORMAT":
      if (state.phase !== "dateQuestion") return state;
      return { phase: "resolvingDateFormat", file: state.file, uploadToken: state.uploadToken };

    case "DATE_FORMAT_SUCCESS":
      if (state.phase !== "resolvingDateFormat") return state;
      return fromResponse(state.file, action.response);
```
**`lib/types.ts`:** copy `DateFormatQuestionResponse`'s interface style (:183-187 — `kind` as a string literal, docstring citing the `api/wire.py` class it mirrors) and extend the union (:205-209). `SheetGroupResponse.members[*].response` types as `UploadResponse` minus the group kinds (the recursive arm).
**Differs:** `SHEETS_SUCCESS` lands on `sheetGroup` (a terminal phase handing off to Review), not back into `fromResponse`'s single-arm mapping — the group response wraps N member arms.

**Test analog:** `frontend/src/state/upload.test.ts` — copy its literal-fixture style (:25-78, hand-built `MappingResponse`/`DateFormatQuestionResponse` objects) and its one-transition-per-test shape (:80-110). New tests: `uploading → sheetQuestion` on `kind:"sheet_question"`, the SUBMIT/SUCCESS/ERROR triple, `toDropzonePhase` mapping, and wrong-phase actions returning state unchanged.

---

## Shared Patterns

### Auth gate on resolve routes
**Source:** `api/routes/date_format.py:52-59` (and `structural_hint.py:44`)
**Apply to:** `api/routes/sheets.py`, the group-archive route
```python
    # D-10-13: a gate only, not a value this route reads -- the dependency's
    # sole job is to raise 401 for a signed-out request.
    user: User = Depends(require_user),
```

### Fail-closed error mapping (consequence-first messages)
**Source:** `upload.py:130-140` (exception→status table), `date_format.py:61-78` (404 on missing token, 422 on incomplete answers)
**Apply to:** every new route. `ValueError` from `parse()` must never surface as 500 for client-supplied `sheet_name` — validate against the retained manifest first (Pitfall 6). Error text names what did **not** happen ("nothing was ingested"), per CONVENTIONS.md.

### Server retains, client only chooses (T-08-08)
**Source:** `wire.py:514-524` docstring; `state.py::UploadEntry` retention shapes (:94-135)
**Apply to:** `SheetResolveRequest` (carries token + selections only — the manifest, temp file, and Schema objects are server-retained) and the group flow (the group id is server-minted, member tokens are server-owned).

### Wire ↔ domain boundary
**Source:** `wire.py::*.from_question`/`from_proposal` classmethods (:148-185, :482-492); `mapper.py::_to_domain` (:195-225)
**Apply to:** all new wire models (conversion lives in the classmethod, routes stay adapters) and the Claude Schema-ranker (unknown names closed at the boundary).

### TDD harness idioms (backend API tests)
**Source:** `tests/api/test_date_format_route.py:79-136`
**Apply to:** every new API test file — `_mapper()` stub via `monkeypatch.setattr(service, "propose_mapping", ...)` + `monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")`; DI overrides `_client(profile_store)` / `_clear()`; inline byte fixtures for synthetic cases, real `data/synthetic/*.xlsx` fixtures for acceptance (the four workbooks in CONTEXT §fixtures ARE the acceptance tests).

### Pure-logic / rendering split (frontend)
**Source:** `state/upload.ts` module docstring (:1-15); `state/dateFormat.ts` + `.test.ts`
**Apply to:** `state/sheets.ts` (all panel gating/payload logic) — components stay thin; vitest covers logic under `node` env with no DOM.

### Additive-defaulted evolution (zero-regression discipline)
**Source:** `canonical.py::assemble`'s `date_formats` kwarg (:130-145); `UploadEntry`'s defaulted fields (:137-155); `_entry_from_json`'s `.get()` (:364-367); `MappingResponse`'s defaulted additive fields (:136-146)
**Apply to:** every touched contract — `CanonicalTable.record_sources`, `assemble(source_sheet=None)`, `RawTable.origin_sheet`, `UploadEntry.group_id/.sheet`, persisted-row keys. This is what keeps the RESEARCH "MUST keep passing UNCHANGED" test table green.

---

## No Analog Found

| Artifact (sub-part) | Role | Data Flow | Reason / What to use instead |
|---|---|---|---|
| Zip archive assembly for the group export | writer | file-I/O | No archive code exists anywhere in the tree. Use stdlib `zipfile.ZipFile` (RESEARCH Don't-Hand-Roll); sanitize entry names (allowlist `[A-Za-z0-9._ -]`, fallback `sheet_<index>`) following `export.py:41-43`'s validate-before-filesystem *discipline*, which is the nearest precedent. |
| The Claude Schema-ranking **prompt** (D-11-19 stage 3) | LLM prompt | request-response | No existing prompt ranks Schemas; only column-mapping prompts exist. Copy `mapper.py`'s skeleton (§3 above) for the call/boundary/injection; the prompt text itself is new — keep it headers-only and derived entirely from `SchemaStore` data, zero compiled-in vocabulary (D-18 discipline, `mapper.py:72-79`). |
| `ui/checkbox` primitive | component | — | Not installed. One official shadcn install, pre-approved by `11-UI-SPEC.md` Registry Safety. No custom build. |

---

## Metadata

**Analog search scope:** `src/assayingest/{parsing/structure,mapping,api,api/routes,export,learning}/`, `src/assayingest/{service,canonical}.py`, `frontend/src/{components,state,screens,lib}/`, `tests/`, `tests/api/`, `frontend/src/state/*.test.ts`
**Files read:** 21 (13 source, 6 test, 2 planning inputs beyond CONTEXT/UI-SPEC)
**Key upstream evidence reused:** `11-RESEARCH.md` Patterns 1-6, Pitfalls 1-8, Test Strategy tables (line references spot-verified against the live files during this mapping — all held)
**Pattern extraction date:** 2026-07-13

---

## PATTERN MAPPING COMPLETE
