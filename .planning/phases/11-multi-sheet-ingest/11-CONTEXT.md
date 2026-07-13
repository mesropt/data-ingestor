# Phase 11: Multi-Sheet Ingest - Context

**Gathered:** 2026-07-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Two silent guesses meet on a multi-sheet workbook, and this phase kills both.

1. **The tool guesses the sheet.** `_resolve_sheet` (`parsing/table.py:349`) ranks the worksheets structurally, takes the winner, and discards every other sheet without a word. Right for a data sheet plus a legend; wrong for a workbook holding one plate, one timepoint, or one batch per sheet.
2. **The human guesses the Schema.** It must be chosen from a dropdown *before* upload, with the file unparsed and no header yet seen (`SchemaPicker.tsx`; `upload.py::_resolve_field_set` 422s without `schema_name`). No code path maps a column signature *back* to a candidate Schema.

The phase inverts the order — **parse first, propose per sheet second, human confirms third** — and lets one upload produce **several independent datasets**, one per selected sheet.

**Delivers:** SHEET-01 (human picks which sheets), SHEET-03 (every row records its source sheet), SHEET-04 (structural gates run per sheet, independently), SHEET-05 (the tool proposes a Schema per sheet from its column signature, in pure Python).

**NOT in this phase — and not anywhere, by the builder's explicit decision:** **merging** sheets into one dataset. SHEET-02 is **removed from the phase and from the requirements**, not deferred-with-intent. See `<deferred>`.

</domain>

<decisions>
## Implementation Decisions

### When the Schema is chosen (SHEET-05)

- **D-11-01 (SUPERSEDED by D-11-16 — kept for the record):** the original wording fired the sheet question only on "a multi-sheet workbook arriving **without a Schema**". Research proved this unreachable: the browser *always* sends `schema_name` (`upload.py:358` 422s without it; `Upload.tsx:83` blocks submit until one is picked), so under the literal reading SHEET-01/03/04/05 could never be triggered from the UI.
- **D-11-16 (replaces D-11-01):** the sheet question fires on **`>1 worksheet` AND no explicit `sheet=`** — *regardless of whether a Schema was chosen*. A Schema picked in the dropdown becomes the **default pre-selection** for every sheet, still overridden per sheet by the scorer's proposal and always confirmable by the human. Consequences: `schema_name` becomes genuinely optional on `POST /api/upload`; the single-sheet path (CSV, one-sheet workbook, or any upload with an explicit `sheet=`) is **untouched and must not regress** (`tests/api/test_upload.py`, `test_money_shot.py` pin it); and `meridian_cro_codes.xlsx` stops silently discarding its LEGEND sheet, which today it does.
- **D-11-02:** The ask rides a **5th response arm**, `kind: "sheet_question"`, alongside `mapping` / `structural_question` / `reconcile_question` / `date_question`. It does **not** ride `StructureQuestion` / `StructuralHint`: that contract is single-sheet, single-answer (`sheet_name: str | None`, one `StructuralHint` per alternative) and `StructuralHintPanel` is a single-select. It cannot carry a multi-select, a per-sheet Schema proposal, or per-sheet metadata. The precedent to copy is `date_question` — its own wire model, its own resolve route, its own panel, its own retention shape on `UploadEntry` (which `state.py:103-121` was explicitly designed to absorb). The client union (`types.ts:205`) and its `assertNever` (`upload.ts:124`) make the 5th kind a compile-time-enforced mechanical addition.
- **D-11-03:** The sheet manifest carries, **per sheet**: name, row count, detected headers, `column_signature`, and the **ranked Schema proposals** with the coverage that produced each ("6/7 canonical fields matched", and *which* fields matched *which* header — `_prefill_coverage` already returns exactly this).

### The Schema proposal itself (SHEET-05)

- **D-11-04 (AMENDED by D-11-19):** the scorer reads **headers only**, never row values — so the privacy story is untouched and the proposal behaves identically under `headers_only`. Its *deterministic* stages are pure Python; a final LLM stage is added by D-11-19 below, but only after both deterministic stages return nothing.
- **D-11-05 (AMENDED by D-11-19):** ranking order per sheet: (1) exact learned-profile hit (`store.find(field_set.signature, column_signature(headers))`), then (2) crosswalk alias coverage (`_prefill_coverage` against each `SchemaStore.list_schemas()` entry).

### The scorer's dictionary is empty on a fresh install — three fixes, all three taken

**The problem research surfaced:** both deterministic stages are **empty on day one**. There are no learned profiles until something is confirmed, and there are no aliases either — the four `presets/*.yaml` carry **none**, and `_vendor_agnostic_alias_index` (`service.py:1451`) builds its index **exclusively** from `canonical_field.aliases`, so a canonical field's *own name* is not one of its aliases. A column literally headed `compound_id` therefore does **not** match the field `compound_id`. First upload → 0/N coverage for every Schema on every sheet → every sheet proposed as *skip*. SHEET-05 would ship dead.

- **D-11-17:** **A canonical field's own name is an implicit alias of itself.** A header spelled like the field (`compound_id`, `Compound ID` — normalised through the existing `_normalise_header`) matches it with no crosswalk entry required. This is a **logic hole being closed**, not a feature: the current behavior is simply wrong. Code change, no data change.
- **D-11-18:** **Seed the four presets with a starter alias set.** Each canonical field in `presets/*.yaml` gains a handful of real-world header spellings (`IC50 (uM)`, `IC50_uM`, `ic50 um`, `Cmpd ID`, …). **Data only, no logic** — consistent with the standing rule that presets are editable data, never compiled-in tool knowledge. D-11-17 alone only rescues *tidy* files; real CRO files never write `compound_id`, and this is what makes the feature live on the first messy file.
- **D-11-19:** **Claude is the third stage of the scorer, not its first.** When *both* deterministic stages return zero coverage across *every* Schema, the sheet's **headers** (never its values) go to Claude, which ranks the Schemas. This is **not** a departure from "Python before LLM" — it is exactly D-10-03's Python → Claude → human ladder applied to the Schema choice: the cheap deterministic pass always runs first and an LLM call is only ever spent on what it could not resolve. **D-11-06 is unchanged**: Claude still only *proposes*, the human still confirms every sheet, and nothing is auto-applied. `headers_only` remains honoured — Claude sees headers in both modes, which is all it ever sees here.
- **D-11-06:** **Always pre-fill, never auto-apply.** For a multi-sheet workbook the sheet-selection screen is **always** shown; the best-matching Schema is pre-selected with its coverage displayed, and a human always confirms. **No coverage threshold, no confidence margin, no silent auto-apply** — deliberately *unlike* `rank_sheets`'s `_CONFIDENCE_MARGIN = 0.1` (`sheets.py:28`). There is no threshold to tune and therefore no threshold to get wrong. This is "Claude proposes, human disposes" applied to the sheet/Schema choice itself. A sheet with **zero coverage** is pre-selected as **skip**, never force-mapped onto the least-bad Schema. A **tie** is shown as a tie — the tool does not break it.

### No merge (supersedes SHEET-02)

- **D-11-07:** **Sheets are never merged into one dataset. The capability is not built.** The builder was unambiguous: *"Без мёрджа. Его не должно быть вообще."* SHEET-02 (propose-the-safe-merge, name-the-divergence) is **struck from the requirements**, not parked as a deferred idea for a later phase.
- **D-11-08:** N selected sheets produce **N independent datasets**: each sheet gets its own Schema, its own mapping, its own amber/confirm gate, and its own export. Nothing is combined at any point.
- **D-11-09 (consequence — and it simplifies SHEET-04):** because each sheet is an independent dataset, a date-order or decimal-locale disagreement *between* sheets is **no longer a contradiction to surface**. Each sheet resolves its own column's date order for itself. SHEET-04's "where two sheets resolve the same column differently, surface the disagreement" clause is **moot under D-11-08** and should not be built. What survives of SHEET-04 is the real requirement: **each selected sheet passes the structural gates independently** (header row, table shape, decimal locale, date order), and a sheet that fails a gate raises its own question rather than being dropped.

### N datasets through Review and export (SHEET-01)

- **D-11-10:** **All N at once, one Review with tabs** — not a sequential queue. The human sees every selected sheet's dataset, confirms each on its own gate, and exports with one action (an archive of N result sets). Chosen over the queue explicitly, knowing the cost.
- **D-11-11 (the cost, accepted knowingly):** this is the expensive decision of the phase, and the planner must not underestimate it. `UploadEntry.table` is a **single** `RawTable` (`state.py:75-155`); `service.export` (`service.py:561-589`), `canonical.assemble` (`canonical.py:130`), the confirm gate, and `GET /api/export/{run_id}/{fmt}` (`export.py:46-59`) are **all single-table**. A **run group** — one upload, N member runs — must be introduced through every one of those paths, and the export route must learn to serve a group. `_is_review_ready` / the `pending_uploads` write-through (`state.py:240-285`) must keep working per member.

### Row provenance (SHEET-03)

- **D-11-12:** `source_sheet` is a **reserved meta column in the export**, *not* a `Field` in the `FieldSet`. `CanonicalTable` gains an explicit provenance field (e.g. `record_sources: list[str]`, parallel to `records`), and the writers append a reserved trailing column (e.g. `__source_sheet`).
- **D-11-13 (why not a real Field — this is the load-bearing reason):** adding `source_sheet` to the `FieldSet` would change `FieldSet.signature`, and **every previously learned profile would silently stop matching** — the learning loop, which is the product's differentiator, would quietly break. It would also make the validator and the mapper treat a bookkeeping column as a *target* field to map and validate. The meta column keeps the Schema clean, the signature stable, and the mapper blind to it.
- **D-11-14 (the writers constraint that forces this to be explicit):** an extra key in `CanonicalTable.records` that is absent from `field_names` is **silently dropped** by `write_xlsx` (`record.get(name)`, `writers.py:50-58`) and **raises** in `write_csv` (`csv.DictWriter` rejects extra keys, `writers.py:40-47`). The provenance column must therefore be threaded through the writers deliberately — it cannot be smuggled into `records` and left to work by accident. `write_json` (`writers.py:62`) dumps `records` verbatim and needs its own handling.
- **D-11-15:** Provenance is written on **every** ingest, including a single-sheet one — a row from a one-sheet file records that sheet too. A traceability column that only sometimes exists is not a traceability column. (`RawTable.sheet_name` is currently set *only* when the workbook has >1 sheet — `table.py:328` — so this needs care for CSV/single-sheet sources.)

### Decided by research (post-discussion, evidence-backed)

- **D-11-20 (run group = a group id over N ordinary tokens):** research enumerated both shapes of D-11-11 against every affected function. **Option A wins decisively.** A group id owning N *ordinary* `upload_token`s changes **zero** of `service.confirm`, `service.export`, `_is_review_ready`, the `pending_uploads` round-trip, `GET /api/export/{run_id}/{fmt}`, `MappingResponse`, or `date_format.py`. Widening `UploadEntry` to hold N tables breaks all eight (`entry.table` is read at `confirm.py:83,145,196` and `date_format.py:62,71,98,112,126`) plus `Review.tsx`'s props. **The phase is therefore substantially cheaper than D-11-11 feared** — that warning stands as a caution, but Option A defuses it.
- **D-11-21 (the manifest sits ABOVE `parse()`):** `parse()` already short-circuits sheet ranking when handed an explicit `sheet=` (`table.py:359-367`). So: build the sheet manifest and ask the question *before* `parse()`, then call `parse(path, sheet=X)` once per selected sheet. Consequences — `parse()`, `_resolve_sheet`, `rank_sheets` and `SheetRanking` are **not touched at all**, every existing parsing test stays green, and **SHEET-04 comes for free**: each per-sheet `parse()` already runs the full header / shape / decimal-locale / date-order chain on its own sheet.
- **D-11-22 (fix `structural_hint.py:56` — in scope, not optional):** the structural-hint resolve route calls `service.resolve_or_map` **without** `schema=`, `sheet=` or `strictness=`, and **never checks `result.date_question`** — re-creating the exact Confirm dead-end that quick task `260712-qgc` fixed. It also loses the Python-first prefill, the escalation line, and the vendor pre-fill that `/api/confirm` then *requires*. Every sheet-group member re-enters this route, so the bug stops being latent and becomes load-bearing. It must be fixed in this phase.
- **D-11-23 (tombstones are safe here — verified, not assumed):** D-10-15 warned that "a single missed filter silently resurrects a deleted field", and the Schema scorer is a new read path. Research verified the filter is **structural**, at `postgres_schema_store._entity_to_schema:311` and `_aliases_for_field:336`, through which both `get_schema` and `list_schemas` pass. The scorer needs no filter of its own. **The one rule to test:** it must source Schemas *only* via `SchemaStore`, never by another route.

### Decided during execution (2026-07-13)

- **D-11-24 (the "almost-empty sheet" default — no threshold, and none is coming).** Execution of 11-04 disproved a premise of this CONTEXT: meridian's `LEGEND` sheet does **not** score zero. It carries a `CMP` column, and `CMP` is a seeded starter alias of `compound_id` (11-02), so LEGEND honestly scores **1/7**. The "zero coverage → propose skip" rule therefore does **not** fire for it, and LEGEND arrives at the sheet screen **ticked**.
  **The builder's ruling: leave it.** The untick rule stays literal — *exactly* zero coverage, nothing else. No coverage threshold is introduced, then or ever (D-11-06 holds). The `CMP` alias is kept.
  **Consequence, and it is the point:** the *coverage number is now the only thing the human has to go on* when deciding whether a sheet is a data sheet. "1/7" beside "6/7" is what tells them LEGEND is a legend. So the coverage must be large, adjacent to the checkbox, and impossible to miss — it is not decoration, it is the control. Plan 11-09 must render it that way.
  **The safety net below it:** if a human ingests LEGEND anyway, 6 of 7 fields map to nothing, every one goes amber, and the confirm gate blocks the export. Nothing bad ships — it merely wastes a click. That is fail-closed working as designed, and it is why the tool does not need to guess here.

### Claude's Discretion

- Whether the per-sheet header extraction reuses `rank_sheets`'s already-materialized `rows_by_sheet` (`sheets.py:75`, which computes every sheet's grid and then discards all but the winner's name) or re-reads via `grid`; and whether `SheetRanking` is widened or a new dataclass carries `(name, score, headers, row_count, signature)`.
- Whether `_prefill_coverage` / `_vendor_agnostic_alias_index` / `field_set_from_schema` are imported as-is (they are `_`-private, `service.py:1451`/`:1572`) or promoted behind a small public scorer API. A headers-only stub `RawTable` is sufficient input — `_prefill_coverage` reads `.headers` and nothing else.
- The concrete shape of the run group (a group id owning N `upload_token`s vs. an `UploadEntry` holding N tables) — provided `confirm` stays per-dataset and the amber gate is never weakened across members.
- The exact reserved-column name and how the three writers each surface it; whether the archive is zip or tar.
- The visual layout of the sheet-selection screen, within D-11-06 (coverage must be *visible*, not just a Schema name).
- Whether the existing `sheet: str | None = Form(None)` param on `/api/upload` (`upload.py:86`) is reused for the resolve call or superseded.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The response contract being extended (a 5th `kind`)
- `src/assayingest/api/wire.py` §`MappingResponse` (:108), §`StructuralQuestionResponse` (:349), §`ReconcileQuestionResponse` (:393), §`DateFormatQuestionResponse` (:461) — the four existing arms. The new `sheet_question` arm joins these.
- `frontend/src/lib/types.ts:205` §`UploadResponse` and `frontend/src/state/upload.ts:124` (`assertNever`) — the client union; a 5th kind is a compile-time error until handled. This is a feature, not an obstacle.
- `src/assayingest/api/routes/date_format.py` + `frontend/src/components/DateFormatQuestionPanel.tsx` — **the pattern to copy**: own wire model, own resolve route, own panel, own retention shape. Not `StructuralHintPanel` (single-select, cannot express this question).

### Token retention across an ask
- `src/assayingest/api/state.py` §`UploadEntry` (:75-155), §`UploadRegistry` (:171-235), `_is_review_ready` (:272-285), `_entry_to_json` (:300) — the three existing retention shapes (structural question keeps `tmp_path`; date question keeps the parsed `table`+`proposal`; happy path keeps `table`). The sheet question needs a fourth. Note `sheet_name` **already round-trips** through the `pending_uploads` persistence (:321).

### The Schema scorer (SHEET-05) — everything needed already exists
- `src/assayingest/service.py` §`_prefill_coverage` (:1572) — **returns exactly what SHEET-05 needs**: which canonical fields matched, and which header matched each, plus the uncovered remainder. Reads `table.headers` only (:1581-1583) — headers-only-safe.
- `src/assayingest/service.py` §`_vendor_agnostic_alias_index` (:1451) — normalised alias → canonical field; `None` marks a cross-vendor collision (never guess).
- `src/assayingest/service.py` §`field_set_from_schema` (:1431), §`recall_vendor` (:1497), §`Escalation` (:1560).
- `src/assayingest/learning/signature.py` §`column_signature` (:30), §`_normalise_header` (:44) — pure functions over a header list.
- `src/assayingest/learning/store.py` §`ProfileStore.find` (:30) and `learning/postgres_store.py:75` — **exact-match only**, no fuzzy capability. All coverage scoring lives in `_prefill_coverage`.
- `src/assayingest/learning/schema_store.py` §`list_schemas` (:49) — how to enumerate every governed Schema to score against.

### Sheet ranking (SHEET-01) — what must be widened
- `src/assayingest/parsing/structure/sheets.py` §`rank_sheets` (:67), §`SheetRanking` (:42), `_score_sheet` (:87), `_CONFIDENCE_MARGIN` (:28). **`rows_by_sheet` (:75) already materializes every sheet's full grid and then throws away everything but the winner's name.**
- `src/assayingest/parsing/table.py` §`_resolve_sheet` (:349), §`_sheet_ambiguous_question` (:377), §`_parse_excel_structurally` (:289), §`RawTable` (:18, note `sheet_name` at :32 and `label` at :44).
- `src/assayingest/parsing/structure/header.py` §`detect_header` — already run per-sheet at `table.py:314`.

### Provenance + export (SHEET-03) — the constraint that forces D-11-12
- `src/assayingest/canonical.py` §`assemble` (:130), §`CanonicalTable` (:112), §`_assemble_record` (:178, iterates `field_names` **only**), §`_inferred_constants` (:198 — the existing "constant per table" precedent).
- `src/assayingest/export/writers.py` §`write_csv` (:40, `DictWriter` **raises** on extra keys), §`write_xlsx` (:50, **silently drops** them), §`write_json` (:62), §`build_manifest` (:70).
- `src/assayingest/service.py` §`export` (:561) and `src/assayingest/api/routes/export.py` (:27 format allowlist, :46 download route) — all single-run today; D-11-10 makes them serve a group.

### Prior decisions that constrain this phase
- `.planning/phases/10-frictionless-correct-ingest/10-CONTEXT.md` — D-10-03 (Python → Claude → human escalation), D-10-05 (`headers_only` restricts Claude, not the server), D-10-07 (fail-closed, ask once per column), D-10-13 (sign-in required), D-10-15 (soft-delete tombstones — **every read path must filter them, and the Schema scorer is a new read path**).

### Fixtures that ARE the acceptance tests
- `data/synthetic/zephyr_bio_ZB-2025.xlsx` — 3 data sheets (Week 1-3), header not on row 1. The N-independent-datasets case.
- `data/synthetic/delta_screening_per_target.xlsx` — one sheet per target, **different header spellings per sheet**. The per-sheet-Schema-proposal case: the crosswalk must resolve differently-spelled headers to the same canonical fields.
- `data/synthetic/orion_pk_report.xlsx` — Summary / Raw timepoints / Notes; the deliberately ambiguous ranking (`tests/test_structure_sheets.py` pins it as the must-hesitate reference).
- `data/synthetic/meridian_cro_codes.xlsx` — DATA + LEGEND; the must-be-confident reference, and the "one sheet is not data at all" case (zero coverage → propose skip).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_prefill_coverage` + `field_set_from_schema` + `SchemaStore.list_schemas()`** — together **already sufficient** for the pure-Python "which Schema fits this sheet" scorer. The only missing primitive is per-sheet header extraction, which `rank_sheets`'s `rows_by_sheet` + `detect_header` already effectively compute and discard.
- **`column_signature(headers)`** — pure, order-independent, duplicate-preserving; the key both the learned-profile lookup and the sheet manifest need.
- **The `date_question` triad** (wire model → resolve route → panel → retention shape) — a complete, working template for adding a new question kind.
- **`_inferred_constants`** (`canonical.py:198`) — the existing precedent for "a fact about the file, not about any one row" written as a constant across every record. The nearest thing to the provenance column.
- **`RawTable.sheet_name`** — already exists and already persists through `pending_uploads`; it simply never reaches `CanonicalTable.records` or the exports.

### Established Patterns
- **Claude proposes, human disposes** — extended here to the sheet and Schema choice themselves (D-11-06). Nothing is auto-applied.
- **Fail-closed on ambiguity** — a tie is shown as a tie; zero coverage proposes *skip*, not a least-bad guess.
- **Pure-Python before any LLM spend** (D-10-03) — the Schema scorer is a first-layer, zero-cost pass.
- **Headers-only privacy** — the scorer reads headers, never values; `headers_only` is unaffected.
- **Wire ↔ domain boundary** — frozen domain dataclasses, Pydantic wire models never leak inward.

### Integration Points
- `api/routes/upload.py::_resolve_field_set` (:358) — currently 422s without a Schema. Must instead branch: multi-sheet + no Schema → `sheet_question`.
- `frontend/src/state/upload.ts` — the `UploadState` union and `fromResponse()` (:111) gain a `sheetQuestion` phase and its paired `resolvingSheets`.
- `frontend/src/screens/Review.tsx` — becomes tabbed over N member datasets (D-11-10).
- **`structural_hint.py:56` is a latent bug the planner will meet:** the structural-hint resolve path calls `service.resolve_or_map` **without** `schema=`, losing the Schema/escalation/vendor context that `upload.py:125` passes. A sheet question that can precede *or follow* a structural question must not inherit that hole.

</code_context>

<specifics>
## Specific Ideas

- The builder's framing of the whole problem, and the reason this phase exists: *"я пытаюсь загрузить многолистный файл, но откуда мне как пользователю знать для какого листа какая схема должна подойти?"* — the user should not have to know. The tool should propose.
- The builder on merging, unprompted and unambiguous: *"Без мёрджа. Его не должно быть вообще."* This is a product decision, not a scheduling one — do not resurrect it as a "later" idea.
- The coverage must be **visible**, not implied: the proposal shows *"6/7 canonical fields matched"*, not just a Schema name. The human is being asked to check the tool's reasoning, and cannot check what is not shown.

</specifics>

<deferred>
## Deferred Ideas

- **SHEET-02 (merging sheets into one dataset) — STRUCK, not deferred.** The builder ruled the capability out of the product entirely, not out of this phase. It moves to **Out of Scope** in `.planning/REQUIREMENTS.md`, not to Future Requirements. Anything downstream that assumes a merge exists (the ROADMAP's old criterion 2, the old SHEET-04 cross-sheet-disagreement clause) is obsolete and must not be planned.

### Reviewed Todos (not folded)
- `parser-encoding-detection.md`, `parser-excel-hazards.md`, `parser-legacy-xls.md`, `parser-ragged-and-preamble.md` — matched this phase only on the shared `area: parsing` tag. All four are parser-hardening concerns (non-UTF-8 CSVs, `#REF!` / hidden rows / multi-row headers, legacy binary `.xls`, ragged/preamble/multi-table CSVs). **None** touches sheet selection, Schema proposal, or row provenance. Not folded; they belong to a parser-hardening phase.

</deferred>

---

*Phase: 11-multi-sheet-ingest*
*Context gathered: 2026-07-13*
