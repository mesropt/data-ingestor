# Phase 12: Claude Reads the Structure - Context

**Gathered:** 2026-07-13
**Status:** Ready for planning

<domain>
## Phase Boundary

**Claude judges the layout. Python reads the values.** That sentence is the whole phase.

The Python shape classifier is removed, because it does not merely mis-*read* an unfamiliar layout — it cannot reliably *detect* one. Claude instead judges each sheet's shape from a bounded evidence grid and the human confirms it on the sheet screen Phase 11 already built. A key-value sheet then becomes a real dataset instead of a refusal, un-pivoted **by Python**, per the human-confirmed verdict.

**Delivers:** SHAPE-01 (Claude judges the shape; `classify_shape` removed), SHAPE-02 (key-value / transposed sheets are actually read — the un-pivot), SHAPE-03 (the model never *writes* a value), SHAPE-04 (`headers_only` keeps working, via a redacted type grid).

**NOT in this phase:** the mapper's own behaviour is not restructured. Column splitting stays deferred. Wide-matrix un-pivot is in scope only if the same verdict/transform machinery covers it for free — the driving case is key-value.

</domain>

<decisions>
## Implementation Decisions

### The evidence that forced this phase

- **D-12-01 (why the heuristic dies):** `classify_shape` (`parsing/structure/shape.py:48-78`) has **no key-value predicate at all**, and its thresholds are corpus-tuned. Measured on `data/synthetic/lab_corpus/cascade_allergy_CS-2026-698392.xlsx` (8 sheets): `Summary` was ruled `unsupported_shape` **only by accident** — it happens to contain a blank separator row, tripping the *unrelated* `multiple_tables` test — while `Patient Info`, **the identical key-value layout without that blank row**, classified as `row_per_record`: a perfectly good table. The `transposed` inversion metric is **exactly 0.000** on such a sheet (an all-strings grid makes rows and columns equally type-homogeneous), against a 0.1 margin. Only low header confidence stopped a patient's name shipping as a column header. **The classifier is not tuned wrong; it is structurally blind here.** The builder's ruling: *"давай может тогда без python code — пусть claude сам изначально и парсит файл, раз уж python code не может такие вещи различать."*

### The division of labour (the load-bearing decision)

- **D-12-02:** **Claude judges; Python reads.** Claude receives a bounded evidence grid (~20 rows × ~10 cols — the cost is capped no matter how large the file), returns a structured verdict (shape, orientation, where the header or the labels sit), and **proposes**. The human confirms on the existing sheet screen (D-11-06: always shown, never auto-applied). Python then performs the extraction deterministically over **every** row.
- **D-12-03 (SHAPE-03, CORRECTED — the first draft of this requirement was wrong and would have shipped a regression):** the rule is **not** "no cell value ever reaches the model". Scouting proved that would contradict what already ships: `mapper.py:161` sends Claude the **first 6 real rows** today by default, pinned by `tests/test_headers_only.py:43`. And it *should*: a header reading `Value` cannot be identified from its name alone. **The real rule is that the model never *writes* a value.** Claude may *see* a bounded sample in order to **judge**; every value that reaches the output is **read from the file by Python**. Rationale: an LLM transcription slip — `12.4` silently becoming `12.5` — is **invisible to the validator**, which knows constraints but not truth. The defence is not that the model never sees a value; it is that the model never produces one. `headers_only` remains the strict mode for those who need more.

### Privacy (SHAPE-04)

- **D-12-04:** In `headers_only`, the structure judge **still runs** — with the grid redacted to **cell types, not cells**: `str(12)` / `num` / `date` / `blank` instead of `TAYLOR, James` / `12.4`. Layout survives redaction: a key-value sheet's column A is all `str` while column B is mixed; a real table has a `str` header row above a per-column-homogeneous body. The shape is judged without one real value leaving the server.
- **D-12-05 (this ADDS a call where none exists — chosen, not stumbled into):** today `headers_only` doesn't redact the structural call, it **skips it entirely** (`cli.py:383-384`, pinned by `tests/test_headers_only.py:204`). That was fine while Python judged the shape; it is fatal once Claude is the only judge, because the private mode would have **no judge at all**. So the redacted call is a deliberate addition. The alternative — asking the human for every sheet's shape in private mode — was rejected as unusable friction.
- **D-12-06 (the enforcement hazard):** the headers-only guarantee is enforced **per call site** — a render branch in `mapper.py:156`, a skip in `cli.py:383`. **There is no single choke point.** Every new Claude call site must therefore re-implement it, and this phase adds one. The plan must carry a test that captures the *actual outbound request* in headers-only mode and asserts no real cell value appears in it (the pattern already exists: `tests/api/test_upload.py:270`).

### Accepted consequences (chosen by the builder, not discovered later)

- **D-12-07: no offline path.** Without the Python classifier, every upload needs a model call to know the shape. Today 1132 backend tests run with **zero** network calls; structural tests will run against an injected fake.
- **D-12-08: no second opinion.** If Claude misjudges a shape, no deterministic check contradicts it. **The human is the check** — on the sheet screen they already confirm. This is consistent with the product (the tool proposes, the human disposes), but it is a real reduction in defence-in-depth and is accepted as such.

### The builder's accuracy-over-privacy ruling (2026-07-13) — and what it does NOT license

The builder said: *"Если мои указания по конфиденциальности данных будут мешать получению точных результатов, то я разрешаю тебе гонять данные в Claude, поскольку первичнее — получить точные результаты, вторичнее — конфиденциальность."*

- **D-12-09 (what it frees):** on the **default** path, nothing is redacted for privacy's sake. The structure judge receives the **real** evidence grid — labels like `Patient Name` and `Accession #` are the single strongest signal for a key-value layout, and a type-redacted grid throws them away. If the mapper's 6-row sample proves too thin to identify a column, raise it; no permission needed.
- **D-12-10 (what it does NOT touch — and this is the important half):** **"Python extracts, Claude never writes a value" (D-12-03) is an ACCURACY rule, not a privacy rule.** Letting the model transcribe values would make results **less** accurate, not more: `12.4` silently becoming `12.5` passes straight through the validator, which knows constraints but not truth, and lands in the export. The rule therefore **stands, and now for the very reason the builder ranks first**. Do not read the accuracy-over-privacy ruling as permission to let Claude produce data.
- **D-12-11 (`headers_only` is not the builder's constraint to waive — it is a promise to the curator):** it is a **toggle in the UI that the end user flips**, and it is printed as a feature. If the curator turns it on, the tool must honour it, or the feature is a lie — the worst possible failure for a product that sells itself on honesty. The redacted type grid (D-12-04) exists so that the tool still *works* in that mode; it costs the default path nothing. Both goals are met; neither is sacrificed.

### Claude's Discretion

- The exact evidence-grid bounds (~20×10 is a starting point, not a locked number) and whether the grid is rendered as text or structured.
- Whether `TableShape` gains a `KEY_VALUE` member or the verdict carries a richer orientation object — nothing today can express "labels in column A, values in column B" (`StructuralHint`, `hint.py:47-61`, has no field for it).
- Whether the un-pivot also covers `wide_matrix` / `transposed`, if the same machinery gives it for free. Key-value is the driving case.
- How the removal of `classify_shape` is sequenced so the Phase 11 header-suppression (`sheets.py:267-284`) is never silently un-done in between.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The heuristic being removed, and everything that touches it
- `src/assayingest/parsing/structure/shape.py:48-78` — `classify_shape`, the whole heuristic (transposed margin :32, wide-matrix cluster :39-45, blank-separator :85-99).
- **Only two production callers:** `parsing/table.py:363` (the parse-time gate → `_shape_unsupported_question` :440-464, `answerable_by_hint=False`) and `parsing/structure/sheets.py:280` (`_sheet_status` → `UNSUPPORTED_SHAPE`).
- **`sheets.py:267-284`** — `_sheet_status` also drives `_reportable_headers`, the Phase-11 header suppression that stops a patient's name shipping as a column header. **Removing the classifier must not silently un-suppress it.**
- **Tests that pin the heuristic and must be rewritten (expected, ~15+):** `tests/test_structure_shape.py` (8 tests), `tests/test_parse_entry_shape.py` (7), plus `UNSUPPORTED_SHAPE` assertions in `tests/test_structure_describe_sheets.py:194,205,232,253,264` and `tests/api/test_sheets_route.py:335-371`.

### The Claude structural layer that already exists (this is mostly a WIRING job)
- `src/assayingest/parsing/structure_assist.py:43` — `propose_structure(evidence, client)`. Already "proposes, never decides".
- `src/assayingest/parsing/structure_schema.py:40-90` — `WireStructureProposal`: the structured output. `table_shape` is a **required** Literal (`:18-24`) with **no `key_value` member**. No label-column/value-column fields exist.
- `src/assayingest/parsing/hint.py:19-31` (`TableShape`), `:47-61` (`StructuralHint`) — **nothing here can express a key-value orientation.**
- **The API never calls it.** `src/assayingest/api/routes/structural_hint.py:6-11` says so verbatim. The only production call site is `cli.py:405`, via `_enrich_question` (`cli.py:391-410`), reached only from `cli.py:383-384` and **only when not headers-only**.

### The un-pivot's target contract
- `src/assayingest/parsing/table.py:18-67` — `RawTable`: `headers`, `rows` (all strings), `source_name`, `sheet_name`, `column_locales`, `origin_sheet`. **This is what the un-pivot must produce.**
- `src/assayingest/parsing/table.py:467-503` — `_raw_table_from_header_row`, the template to mirror (header cleaning, `_row_to_strings`, `_resolve_locales_or_ask`).
- **Downstream is 1-row-safe:** `canonical.assemble` (`canonical.py:190`), the validator (`validator.py:300`) and the mapper (`mapper.py:161`) all iterate rows without a minimum. `_MIN_PLAUSIBLE_ROWS` (`sheets.py:52`) scores the *raw grid*, not the `RawTable`.
- **Two frictions the planner will meet:** (1) locale detection is *variance-based* — `classify_column` calls a lone `1,234` AMBIGUOUS by design (`locale.py:1-38`), so a **one-row** un-pivoted table can bounce into the locale question; the date-order question can bounce the same way. (2) duplicate labels in column A become duplicate headers (`turablo_duplicate_headers.csv` is the existing precedent).

### The privacy contract as it actually is (weaker than the UI implies)
- Honoured at: `mapper.py:156-157` (sample rows skipped), `cli.py:383-384` (structural call **skipped**, not redacted), `api/wire.py:489-490` (`example_values` emptied on the wire).
- **The strongest existing test — copy its shape:** `tests/api/test_upload.py:270` — real mapper, fake client at the DI seam, asserts the literal values `"12.5"` / `"NVS-0012"` are absent from the **captured outbound content**.
- **Known leak, pre-existing, NOT this phase's to fix but worth knowing:** `StructureQuestion.evidence_rows` reach the **browser** unredacted even under headers-only (`wire.py:360`, no redaction in `from_question` :364-368); only the frontend hides them (`StructuralHintPanel.tsx:48-53`).

### Fixtures
- **The driving file:** `data/synthetic/lab_corpus/cascade_allergy_CS-2026-698392.xlsx` — 8 sheets (Summary, Patient Info, IgE Results, Reference Ranges, Historical Trend, Result Visualization, Quality Control, Methodology & Notes). `Summary` and `Patient Info` are both key-value; **only the first is caught today, and only by accident.**
- **No committed key-value fixture exists** — `tests/test_structure_describe_sheets.py:43-47` says so outright and builds one in `tmp_path`. A real one should be committed.
- Other non-row-per-record sheets: `apex_labs_wide_matrix.xlsx`, `bionexus_transposed.xlsx`, `triton_screening_two_tables.xlsx`, `quantex_scanned_report.xlsx` (drawing-only), `nimbus_labs_chartsheet.xlsx`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`structure_assist.propose_structure` + `structure_schema.WireStructureProposal`** — a complete Claude structural-proposal path, already "propose, never decide", already degrading safely on auth/API/parse failure. It needs **widening** (a key-value verdict) and **wiring** (an API call site), not inventing.
- **`_raw_table_from_header_row`** — the exact template the un-pivot must mirror to produce a legal `RawTable`.
- **The sheet screen (Phase 11)** — the confirmation surface for the structural verdict already exists and is already always shown.

### Established Patterns
- **The tool proposes, the human disposes** — now applied to the *shape* of the sheet.
- **Fail-closed on ambiguity** — a shape Claude is unsure of must ask, not guess.
- **Per-site privacy enforcement** — there is no choke point; a new Claude call site is a new place to get headers-only wrong.

### Integration Points
- `parsing/table.py:363` and `parsing/structure/sheets.py:280` — the two places the heuristic is consulted, and therefore the two places the verdict must arrive instead.
- `service.describe_workbook` (`service.py:2115-2167`) — the Phase 11 manifest, already takes a `client`; it is the natural home for the structural judge.
- `sheets.py:267-284` — the header-suppression that currently keys off the heuristic's verdict and must keep working off Claude's.

</code_context>

<specifics>
## Specific Ideas

- The builder's words that opened this: *"Столбцы могут быть как вертикальными, так и горизонтальными. Видимо, здесь нужен Claude на первом этапе, так как python code это не определит."* He was right, and more right than he knew: the classifier could not even *detect* the layout, let alone read it.
- The correction that matters most: **"the model never sees a value" was my formulation, and it was wrong.** The builder chose the accurate one — *the model never **extracts** a value*. Claude sees a bounded sample to judge; Python reads every value that ships.

</specifics>

<deferred>
## Deferred Ideas

- **The `evidence_rows` → browser leak under headers-only** (`wire.py:360`): real cell values cross the server→browser wire even in private mode, and only the frontend hides them. Pre-existing, orthogonal to this phase, but it undercuts the privacy story the README tells. Worth its own quick task.
- **Column splitting** (`Age / Sex` → two fields) — still deferred (Future Requirements).

### Reviewed Todos (not folded)
- `parser-encoding-detection.md`, `parser-excel-hazards.md`, `parser-legacy-xls.md`, `parser-ragged-and-preamble.md` — matched only on the shared `area: parsing` tag. All four are parser-hardening concerns (encodings, `#REF!`, legacy `.xls`, ragged rows); none touches shape judgment or the un-pivot. Not folded.

</deferred>

---

*Phase: 12-claude-reads-the-structure*
*Context gathered: 2026-07-13*
