---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: — Canonical Schemas, Crosswalk & Governance
current_phase: 11
current_phase_name: multi-sheet-ingest
status: executing
stopped_at: Completed 12-05-PLAN.md (Wave 4 of 7) — the verdict reaches parse time
last_updated: "2026-07-13T17:11:41.560Z"
last_activity: 2026-07-13
last_activity_desc: Phase 11 execution started
progress:
  total_phases: 12
  completed_phases: 9
  total_plans: 57
  completed_plans: 54
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-09)

**Core value:** Claude proposes a mapping of a messy file onto whatever fields the user asked for, with honest per-field confidence; a human disposes; nothing is trusted or saved until every uncertain field is cleared. Zero hardcoded domain.
**Current focus:** Phase 11 — multi-sheet-ingest

## Current Position

Phase: 11 (multi-sheet-ingest) — EXECUTING
Plan: 7 of 10
Status: Ready to execute
Last activity: 2026-07-13 — Phase 11 execution started

## Performance Metrics

**Velocity:**

- Total plans completed: 24
- Average duration: - min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 02 | 3 | - | - |
| 03 | 3 | - | - |
| 04 | 6 | - | - |
| 6 | 3 | - | - |
| 7 | 4 | - | - |
| 8 | 3 | - | - |
| 9 | 2 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 8 | 3 tasks | 10 files |
| Phase 01 P02 | 4min | 3 tasks | 6 files |
| Phase 01-robust-file-reading P03 | 10min | 3 tasks | 14 files |
| Phase 01 P04 | 3min | 2 tasks | 4 files |
| Phase 01 P05 | 7min | 2 tasks | 4 files |
| Phase 02 P01 | 13min | 5 tasks | 19 files |
| Phase 02 P02 | 6min | 2 tasks | 3 files |
| Phase 02 P03 | 12min | 2 tasks | 8 files |
| Phase 03 P01 | 17min | 3 tasks | 13 files |
| Phase 03 P02 | 15min | 3 tasks | 8 files |
| Phase 03 P03 | 11min | 3 tasks | 11 files |
| Phase 04 P01 | 25min | 3 tasks | 7 files |
| Phase 04 P02 | 20min | 3 tasks | 9 files |
| Phase 04 P03 | 24min | 3 tasks | 13 files |
| Phase 04 P04 | 50min | 3 tasks | 42 files |
| Phase 04-api-review-ui P05 | ~2h | 3 tasks | 9 files |
| Phase 04 P06 | 14min | 4 tasks | 12 files |
| Phase quick-260712-sat P01 | 20min | 3 tasks | 7 files |
| Phase 12 P01 | 15min | 3 tasks | 8 files |
| Phase 12 P03 | 25min | 2 tasks | 2 files |
| Phase 12 P04 | 76min | 4 tasks | 8 files |
| Phase 12 P05 | 68min | 3 tasks | 9 files |
| Phase 12 P06 | 27min | 3 tasks | 6 files |

## Accumulated Context

### Roadmap Evolution

- Phase 10 added (2026-07-12): Frictionless & Correct Ingest — INGEST-01..04. Two halves: stop asking for what the tool can derive (field set from the Schema; else proposed by Claude from headers), and stop guessing what it cannot (merged `Age / Sex` column split proposed-not-automatic; ambiguous date order asked once per column before ISO 8601 normalization). Prompted by the user asking why Define Fields and the field-set picker are mandatory at all.
- Phase 11 edited: edited fields: goal, requirements (+SHEET-05), success_criteria (+criterion 5 — per-sheet Schema proposal)
- Phase 12 added: Claude judges sheet shape; Python classifier removed; key-value sheets actually read (lifts PARSE-V2-01)

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Pivot: the product is domain-independent — the user defines target fields at runtime (name, optional description, optional constraints); zero fields/domains/vocabularies are hardcoded anywhere in the tool. The original fixed 7-field assay brief in CLAUDE.md is superseded.
- Pre-pivot, still true: validator + reference checking are plain Python, no LLM — but the "reference" is now the constraints the *user* declares per field, not a built-in vocabulary.
- Pre-pivot, still true: learning loop via SQLite profiles, no fuzzy matching — the differentiator, must be demonstrable on video — now keyed by (field set, column signature), not just (lab, signature).
- Roadmap revision (pivot): parser hardening remains structure-driven (header position, delimiter, decimal locale, sheet selection, table shape); PARSE-06 adds a human-assisted fallback — an unfamiliar structure asks the user for a hint instead of crashing — kept as Phase 1 ahead of fields/mapping/validation so downstream phases operate on a structurally-clean table.
- Roadmap revision (pivot): fields and the mapper's structured-output schema are generalized into their own phase (Phase 2) ahead of validation/learning — FIELD-01..05 (user-defined fields, constraints, templates, dynamic schema, optional presets) plus MAP-01..02 (dynamic Claude mapping) — since validation and learning both depend on a user-declared field set existing first.
- Roadmap revision (pivot): a source's file format can change over time, so the learning store is keyed by (field set, column signature) and one source may hold several profiles, one per format version; a changed layout yields a new signature that never matches an old profile — it falls back to Claude and can be learned as an additional profile, while old-format files keep matching their original profile (LEARN-05, in Phase 3). A structural hint from Phase 1 is persisted with its profile (LEARN-06) so odd layouts stop requiring a repeated hint.
- [Phase ?]: The D-14 decimal-locale ambiguity predicate (variance in comma-digit-count proves decimal_comma; uniform 3-digit groups are ambiguous) implemented exactly per 01-RESEARCH.md Pattern 3, including the single-value-column edge case (Pitfall 7).
- [Phase ?]: parse() dispatches CSV through the new structural detector (structure/delimiter.py + structure/locale.py); Excel and parse_file() are untouched in this plan -- Excel structural detection is deferred to plans 02-04 of Phase 1.
- [Phase 01-02]: _CONFIDENCE_MARGIN set to 0.05 (not RESEARCH.md's tentative 0.1) so zephyr's real 0.086 header margin resolves confidently — RESEARCH.md flagged the threshold as unvalidated and asked it to be tuned during execution; 0.1 would have wrongly flagged the plan's own reference fixture as not-confident
- [Phase 01-02]: HeaderDetection.index is always the top-scoring row, even when confident=False — Lets parse() pre-fill StructureQuestion.proposal.header_row_index with a real best guess (D-02 propose-never-auto-apply pattern) instead of re-deriving one from raw scores
- [Phase 01-02]: cli.py left untouched — Excel still routes through the legacy parse_file() path, not parse()'s new header detection — Out of this plan's files_modified scope; sheet selection is a later wave's job per the plan's own constraint, and cli.py's docstring already documents the deferral
- [Phase ?]: [Phase 01-03] Sheet-ranking score uses saturating (min(x/threshold,1.0)) signals, not linear, so orion's Summary/Raw timepoints tie honestly (D-09) while meridian's DATA beats LEGEND confidently -- _CONFIDENCE_MARGIN=0.1
- [Phase ?]: [Phase 01-03] resolve_or_ask() now routes both CSV and Excel through parse() unconditionally -- CLI never loops every sheet of a multi-sheet workbook anymore, matching PROJECT.md's one-chosen-table-per-file v1 scope; resolve_tables()/parse_file() remain public/tested but are no longer wired into run()'s live path
- [Phase ?]: [Phase 01-03][Rule 1 bug] header.py's _type_consistency treated int/float as distinct types, causing a false not-confident on meridian_cro_codes.xlsx's real header row (openpyxl reads a decimal-less numeric cell back as int); added _type_class() to normalize int/float into one numeric class
- [Phase ?]: shape.py's homogeneity formula is a from-scratch, documented majority-type-fraction metric verified against the whole corpus, not a literal reproduction of RESEARCH.md's quoted float values (no probe code was published to reproduce them exactly)
- [Phase ?]: Shape gate in parse() runs before the header-confidence check and covers the explicit hint.header_row_index override path too, not just auto-detection -- required by D-11's 'no code path attaches a shape warning to a RawTable' invariant
- [Phase ?]: wide_matrix's 'no distinguishing category/unit column' signal is satisfied implicitly by the numeric-cluster-size gate rather than a separate column-label heuristic, since a real category/unit column never produces a 3+-column overlapping-range numeric cluster in the corpus
- [Phase ?]: Phase 01-05: Claude structural-assist enrichment lives in cli.py's ask-path (_enrich_question), not parsing/table.py::parse() -- keeps the deterministic parse() network-free and its test suite untouched (D-04/D-08 discretion call).
- [Phase ?]: Phase 01-05: structure_assist.py mirrors mapping/mapper.py exactly (optional client injection, _to_domain/_to_domain_field split); Claude's structural proposal only ever pre-fills StructureQuestion.proposal and is never auto-applied (D-02).
- [Phase ?]: D-16/D-17 implemented via pydantic.create_model + Literal[tuple(field_names)]; field names never sanitised
- [Phase ?]: D-22 solved as a decimal_comma-only evidence line in the mapper prompt, verified against pinnacle_labs_export.csv
- [Phase ?]: D-10's per-field min/max collapses UNIT_VALUE_RANGES' three per-unit ranges into one 0.0-1000.0 range for assay-potency's value field (documented granularity loss)
- [Phase ?]: 02-RESEARCH.md Open Question 1 left NOT YET RESOLVED (no ANTHROPIC_API_KEY in this environment) rather than fabricating an observed stop_reason
- [Phase ?]: D-12 unit-mismatch detection is field-scoped: fires only when a field declares Field.unit and its own mapped source cell differs -- no cross-field lookup, no prefix arithmetic
- [Phase ?]: Per the plan's literal action text, decimal-point/ambiguous-locale numeric columns pass through unconverted -- only decimal_comma converts (D-14 scope)
- [Phase ?]: A malformed date's canonical cell falls back to the raw string (not None) when strptime fails, so the flagged record still carries the human-readable original
- [Phase 02]: D-20/D-21 completed: pk-parameters and reagent-inventory presets ship as pure YAML data, zero .py files touched (verified via git diff --stat); reagent-inventory's schema enum and system prompt carry no assay vocabulary (SC5).
- [Phase 02]: Presets are packaged into the built wheel via [tool.hatch.build.targets.wheel.force-include] mapping presets/ -> assayingest/presets/; verified by building the wheel and listing its exact contents (only the 3 preset YAMLs, no stray files).
- [Phase 02]: Both new corpus-gap fixtures (European thousands+decimal, Excel-native datetime cell) were added as brand-new files rather than edits to existing tracked fixtures, to avoid any risk of invalidating tests that assert against those fixtures' exact current shapes.
- [Phase ?]: column_signature sorts a LIST of normalised headers, never a set -- preserves duplicate/blank counts per D-02 (LEARN-01)
- [Phase ?]: StoredFieldMapping persists the NORMALISED source column + occurrence rank; reconstruction resolves via normalised equality, never canonical._column_index's exact headers.index() (Pitfall 2, LEARN-03)
- [Phase ?]: Credential check relocated from run()'s unconditional gate into _map_one's no-profile branch only -- a profile hit builds no Anthropic client and checks no credentials (Pitfall 3, D-10/P2)
- [Phase ?]: validate() runs on both fresh-Claude and auto-applied-profile paths (D-03) immediately after proposal resolution, before any output is printed
- [Phase ?]: Validator is additive-only (_apply_objection ORs a True in, never clears one) and reuses canonical.assemble().flagged as its type/date/unit engine (Pattern 1); only allowed_values and min/max are new checks
- [Phase ?]: presets/assay-potency.yaml's assay_date field was missing date_format -- added %Y-%m-%d (Rule 2 fix) since canonical's D-13 rule always flags a dateless-format field, which would have permanently blocked the money-shot once .flagged was wired into the gate
- [Phase ?]: build_manifest(field_set, headers, proposal, *, provenance, strictness) mirrors learning.reconstruct.stored_mapping_from's signature -- keeps export/writers.py decoupled from RawTable
- [Phase ?]: Export filenames are fixed (export.csv/export.xlsx/export.json/manifest.json) -- a multi-sheet export into one DIR would overwrite across sheets, an accepted v1 scope boundary
- [Phase ?]: headers_only only ever reaches propose_mapping on the fresh-Claude miss branch -- a structural consequence of the auto-apply path never calling propose_mapping at all, not a separate check
- [Phase ?]: CLI export flag is store_true; a separate output-dir flag supplies the optional path (default: beside the source file), avoiding argparse nargs ambiguity with a bare flag pair
- [Phase 04]: Extracted cli.py's print-coupled orchestration into public service.py (resolve_or_map/resolve_table_mapping/confirm/save_profile_if_ready/export + typed exceptions); cli.py now delegates and passes its own monkeypatchable propose_mapping reference through to preserve existing test seams
- [Phase 04]: Deferred requirements.mark-complete for API-01/02/03 -- these IDs also cover 04-02/04-03's HTTP route work; this plan only delivers the backend-logic seam, not a user-facing upload/confirm capability yet
- [Phase ?]: Task 1 built a minimal routes/upload.py; Task 2 extended the same file to full robustness (extension/size guards, structural-question branch, cleanup, exception mapping) -- kept genuine RED->GREEN per task despite the plan's Task-1 file list omitting routes/upload.py
- [Phase ?]: P2 headers_only privacy test exercises the REAL propose_mapping/_render_table chain via a fake Anthropic client injected through the get_anthropic_client DI seam, not a monkeypatched propose_mapping -- proves no cell value reaches the actual outbound Claude request at the HTTP boundary
- [Phase ?]: [Phase 04] Server-side confirm gate (API-02) shipped by wire-model omission: ConfirmRequest/ConfirmFieldMappingIn carry no headers/signature/ready field at all -- confirm.py is a pure deserialize-then-delegate adapter over 04-01's already-P1-tested service.confirm, never a second gate implementation
- [Phase ?]: [Phase 04] structural_hint.py calls only service.resolve_or_map, never cli._enrich_question/propose_structure -- the API has zero Claude structural-enrichment call sites by construction (W1), eliminating the evidence-row leak vector rather than guarding it
- [Phase ?]: [Phase 04] export.py validates run_id against the exact uuid4() shape confirm.py mints before any filesystem access (T-04-13) instead of path-resolve-and-compare containment
- [Phase ?]: [Phase 04] shadcn init -d resolved to style base-nova (not the plan's literal New York) on shadcn@4.13.0 -- the upstream registry's default style set changed; the plan's binding requirement (D-01 token substance, verified via zinc/slate grep) was met regardless of the base style name
- [Phase ?]: [Phase 04] Dark theme selector is [data-theme="dark"] (matches 04-UI-SPEC.md literally), not shadcn's default .dark class -- ThemeToggle sets the data attribute directly and persists to localStorage, independent of any theme-provider library
- [Phase ?]: [Phase 04] Self-hosted Inter Variable + JetBrains Mono woff2 files were extracted once from @fontsource packages into frontend/public/fonts/, then those npm packages were uninstalled -- only the static font files remain committed, no CDN dependency and no permanent font-distribution package
- [Phase ?]: resolveStructuralHint renamed to resolveHint (matches plan naming, zero prior callers)
- [Phase ?]: StructuralHintPanel split across Task 2 (minimal placeholder, app compiles) and Task 3 (full implementation) commits to keep every task commit buildable, mirroring 04-02's precedent for mutually-dependent files
- [Phase ?]: Upload's dropzone gets a 5th 'locked' state (beyond UI-SPEC's 4) while a structural-hint resolve is in flight or a question is showing, so the dropzone never offers a conflicting second Upload CTA
- [Phase ?]: The Review screen's Source Columns pane renders column names only, not sample values -- MappingResponse's wire contract carries no cell values on any upload path; a documented gap versus 04-UI-SPEC.md's literal description, not a fabrication.
- [Phase ?]: resolveByChip adopts the selected candidate's own confidence and resolveByDropdown sets confidence to 1.0 (a human explicitly chose); resolveByAccept leaves confidence untouched (accepting Claude's proposal as-is).
- [Phase ?]: Every /api/confirm call from the Review screen sends save_profile: true and export: true -- Confirm & Save Mapping always saves the learned profile, which is what makes a same-signature re-upload return provenance auto-applied-from-profile with zero amber rows (UI-06).
- [Phase ?]: uploadErrorTitle maps only 503/413/400 (single unambiguous causes); 401/500/non-ApiError fall through to a neutral title, never guessing a cause the server didn't report
- [Phase ?]: .env is loaded at api/app.py's module import time (uvicorn has no main()) but only inside cli.py::main() (never in run(), so the test suite's direct run() calls keep today's env semantics); override=False always lets a real env var win
- [Phase ?]: Converted 4 live-Claude-API skipif(ANTHROPIC_API_KEY) tests to an explicit ASSAYINGEST_LIVE_TESTS=1 opt-in after confirming the auto-loaded .env made them fire for real, billed calls during this task's own regression sweep
- [Phase ?]: 260712-fuf: Collapsed App.tsx path+activeTab into one pathname state with activeTab derived (D-1), eliminating a de-sync bug now that tabs and /verify share one URL axis
- [Phase ?]: 260712-fuf: FastAPI docs/redoc/openapi relocated to /api/* so the SPA catch-all can own /docs for the app's own Docs tab
- [Phase ?]: 260712-r8b: fixed silent CSV header truncation at a mid-line '#' via an explicit quote-aware whole-line comment pre-filter (delimiter.py), replacing pandas' comment= kwarg; D-01 fails closed with a named ValueError when a dropped '#'-line matches the table's own column count
- [Phase ?]: 260712-sat: confirm 422's unclear_details is purely additive -- the legacy unclear_fields key is never touched, so no existing consumer (applyGateRejection) had to change
- [Phase ?]: 260712-sat: unclear_details' reason is the no-LLM validator's own validator_note, passed through unmodified everywhere in the chain -- never reworded or synthesised when absent
- [Phase 12]: 12-01: Un-pivot skips a block row only when label AND all value cells are blank — reconciles block spans with the golden header counts (Summary 10, Patient Info 17)
- [Phase 12]: 12-01: _jsonable gained a tuple branch (tuple→list, recursive) and StructuralHint/SheetLayout gained from_dict — the profile store loads layouts as frozen types; old rows without a layout key load as layout=None
- [Phase 12]: 12-03: parse() dispatches on hint.layout BEFORE the heuristic flow via _table_from_layout; the classify_shape gate is byte-for-byte unmoved and the verdict-less path is unchanged
- [Phase 12]: 12-03: verdict indices are untrusted at parse time — out-of-grid block/row indices fail closed to the answerable _shape_unknown_question, never IndexError (T-12-08 inner closure)
- [Phase 12]: 12-03: layout.confidence is not consulted in parse() — a verdict arriving on a hint IS the confirmation; asking about low-confidence verdicts is service's job (plan 12-05)
- [Phase 12]: 12-04: SheetOut.status wire Literal gained layout_unknown in Wave B (Rule 3); semantic wire/frontend treatment stays with 12-05/12-06
- [Phase 12]: 12-04: upload route forwards headers_only into describe_workbook so the privacy toggle reaches the judge's evidence rendering (Rule 2, D-12-11)
- [Phase 12]: 12-04: verdict-less classifier fallback kept byte-for-byte behind layouts=None with fallback-pin tests, fenced for Wave C deletion
- [Phase 12]: 12-06: isUnreadableShape re-keyed on layout.kind — never key_value, never unknown; a null layout is never unreadable
- [Phase 12]: 12-06: the sheet Select is suppressed on a layout question; the sheet name still rides the answer payload
- [Phase 12]: 12-06: no disagree action on the unknown line — that sheet already routes to the layout question

### Pending Todos

None yet.

### Blockers/Concerns

- Research (pre-pivot, still largely applicable) flags the column-signature exact-match design (normalize, sort, hash) as having no single canonical external source — validate empirically against the actual synthetic files in Phase 3, including the format-drift case and the new (field set, signature) compound key.
- Every safety mechanism (parser shape/hint detection, validator, signature match, export gate, edit re-validation) must be enforced server-side/structurally, never as a UI-only nicety or a per-domain hack — the confirm endpoint in Phase 4 must independently re-check the gate.
- The dynamic mapper schema (Phase 2) and the human-assisted parsing hint (Phase 1/PARSE-06, LEARN-06) are the two genuinely new mechanisms introduced by the pivot with no direct Day-1 precedent — de-risk both early with focused tests before building the validator/learning loop on top of them.
- Live Claude API calls during demo recording risk latency/nondeterminism/failure — rehearse end-to-end, pin model version, keep a backup file/cached response for Phase 5.
- 10 extended-vendor corpus files (data/synthetic/*.xlsx and pinnacle_labs_export.csv) were never committed to git by a prior plan; still uncommitted on disk (see phase 02 deferred-items.md) -- not blocking (tests pass regardless) but should be committed by a future plan.
- Claude Code's `isolation="worktree"` forks new worktrees from `main`, which on this repo is only the first two commits (8c57475) -- every isolated agent landed in a near-empty tree with no `src/assayingest/api/`. `workflow.use_worktrees` is now `false` in `.planning/config.json` so GSD executors run on the active branch. Re-enable only if `main` is ever fast-forwarded to the feature branch.

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 260712-c47 | Mint the email verification token before persisting the new user in signup, so a token failure cannot strand a half-created unverifiable account | 2026-07-12 | fb7ac30 |  | [260712-c47-create-the-email-verification-token-befo](./quick/260712-c47-create-the-email-verification-token-befo/) |
| 260712-e0e | Seed the 4 shipped presets into the web field-set store at startup and auto-select a field set on Upload, so the picker is never blank and "Upload & Map" is never a silent no-op | 2026-07-12 | d2d40b4 |  | [260712-e0e-seed-the-4-presets-into-the-web-field-se](./quick/260712-e0e-seed-the-4-presets-into-the-web-field-se/) |
| 260712-ekj | Fix the upload error alert's hardcoded parse-failure title (a 503 now says "the mapper isn't available") and load `.env` at both real entrypoints (FastAPI import, CLI `main()`) so the README's own Quickstart command works with no `--env-file`; gated 4 live-Claude tests behind an explicit `ASSAYINGEST_LIVE_TESTS=1` opt-in after the auto-loaded `.env` made them fire for real | 2026-07-12 | 200b7db |  | [260712-ekj-fix-misleading-upload-error-alert-title-](./quick/260712-ekj-fix-misleading-upload-error-alert-title-/) |
| 260712-fiv | Sync `activeTab` with `location.hash` via plain `hashchange` (no router dependency) -- adds a pure, unit-tested `state/routing.ts` and thin `App.tsx` wiring so all five tabs are linkable, refresh-stable (F5 on `#registry` reopens Registry), and reachable via browser Back/Forward; garbage/empty hash always falls back to the default tab | 2026-07-12 | d9dbdab |  | [260712-fiv-add-hash-based-routing-so-browser-back-f](./quick/260712-fiv-add-hash-based-routing-so-browser-back-f/) |
| 260712-fuf | Replace hash routing with clean History-API path routing (`/upload`, `/review`, `/registry`, `/docs`, one `pathname` state with derived `activeTab`) and relocate FastAPI's Swagger/ReDoc/OpenAPI to `/api/*` so the SPA's Docs tab can own `/docs` | 2026-07-12 | 216919d |  | [260712-fuf-switch-to-clean-path-routing-and-move-sw](./quick/260712-fuf-switch-to-clean-path-routing-and-move-sw/) |
| 260712-qgc | Fix the Confirm dead-end: an ambiguous date column whose field declares a `date_format` that cannot parse the data was trusted blindly, so no date-order question was asked, the field stayed amber forever, and Confirm 422'd with no way out from Review. The declaration is now checked against the column's values before it is trusted (D-10-06); a refuted one asks the human, whose answer overrides it for that run only | 2026-07-12 | d7d3ede | Verified | [260712-qgc-fix-the-confirm-dead-end-an-ambiguous-da](./quick/260712-qgc-fix-the-confirm-dead-end-an-ambiguous-da/) |
| 260712-r8b | Fix silent data loss in the CSV parser: pandas' `comment="#"` truncated ANY line at a mid-line `#`, so the `# Reps` header column destroyed a column, shifted every row one left, and deleted the compound ID from every record on the live `parse()` path. Replaced with an explicit quote-aware whole-line comment pre-filter; a dropped `#`-line that matches the table's own column count now fails closed with a named ValueError instead of silently corrupting the table | 2026-07-12 | 9a4ef34 | Verified | [260712-r8b-fix-silent-data-loss-in-the-csv-parser-p](./quick/260712-r8b-fix-silent-data-loss-in-the-csv-parser-p/) |
| 260712-sat | Make the Confirm rejection name the unresolved field and say why: the 422 body now carries `unclear_details` (field + the no-LLM validator's own note + source column) alongside the unchanged `unclear_fields`, and the Review alert lists each rejected field with its reason instead of a generic "some field wasn't resolved" | 2026-07-12 | 2c6a7d1 |  | [260712-sat-make-the-confirm-rejection-name-the-unre](./quick/260712-sat-make-the-confirm-rejection-name-the-unre/) |
| 260712-r8b | Fix silent data loss in the live CSV parse path: `pd.read_csv`'s `comment="#"` kwarg truncated ANY line at the first mid-line `#`, destroying `helixbio_export.csv`'s `# Reps` header column and shifting `HLX-100` and every compound ID out of the table. Replaced with an explicit, quote-aware whole-line comment pre-filter; a `#`-prefixed line structurally matching the table's own column count now fails closed with a named `ValueError` (D-01) instead of being silently dropped or guessed | 2026-07-12 | 9a4ef34 |  | [260712-r8b-fix-silent-data-loss-in-the-csv-parser-p](./quick/260712-r8b-fix-silent-data-loss-in-the-csv-parser-p/) |
| 260712-sat | Make the confirm rejection name the unresolved field: the server's P1 gate 422 now carries `unclear_details` (field, reason, source_column) alongside the unchanged `unclear_fields` name list, with the reason being the no-LLM validator's real `validator_note`. The client parses it defensively (an older/malformed body falls back to `reason: null` per name, never throws) and the Review screen's rejection alert lists every unresolved field by name with its reason instead of one generic message | 2026-07-12 | 2c6a7d1 |  | [260712-sat-make-the-confirm-rejection-name-the-unre](./quick/260712-sat-make-the-confirm-rejection-name-the-unre/) |

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | DEPLOY-01/02/03 (accounts, hosted deployment, ingest history) | Deferred to v2 | Requirements definition |
| v2 | MATCH-01 (fuzzy signature matching with confirmation) | Deferred to v2 | Requirements definition |
| v2 | PARSE-V2-01 (correct un-pivot ingestion of wide/transposed layouts — v1 only detects and flags, PARSE-05) | Deferred to v2 | Requirements definition |
| v2 | PARSE-V2-02 (automatic extraction of multiple tables from a single report sheet — v1 targets one chosen table) | Deferred to v2 | Requirements definition |

## Session Continuity

Last session: 2026-07-13T17:10:39.190Z
Stopped at: Completed 12-05-PLAN.md (Wave 4 of 7) — the verdict reaches parse time
Resume file: 
None
