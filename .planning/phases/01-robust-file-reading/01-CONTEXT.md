# Phase 1: Robust File Reading - Context

**Gathered:** 2026-07-10
**Status:** Ready for planning

<domain>
## Phase Boundary

The parser resolves a messy CSV/Excel file's **structure** — which row is the header, which delimiter and decimal locale is used, which sheet holds the data, and whether the table shape is even a supported row-per-record table — by detecting structure rather than by hardcoding per-vendor rules. When structure cannot be resolved confidently, the tool never crashes and never guesses silently: it asks the human for a structural hint, optionally pre-filled by a Claude proposal, and proceeds once the human confirms.

Covers PARSE-01..06. Delivers a structurally-clean `RawTable` (or a structural question) that Phase 2's mapper consumes. Does **not** interpret column meaning — that is the mapper's job.

</domain>

<decisions>
## Implementation Decisions

### Structure engine — three layers, human always last

- **D-01:** Structure resolution runs in three ordered layers: (1) deterministic Python heuristics, (2) a Claude structural proposal when the heuristics are not confident, (3) human confirmation. All three ship in Phase 1.
- **D-02:** **Claude never applies a structural answer itself.** Its proposal — value, plain-English reason, confidence, ranked alternatives — pre-fills the question shown to the human, who confirms or corrects. This is the same "propose / dispose" pattern the mapper already uses, applied one layer earlier. Rationale: a wrong structure does not *look* wrong. Shift the header row by one and you get a perfectly clean table with units sitting in the `compound_id` column; the mapper then maps that garbage confidently, every field goes green, the "no yellow fields" export gate has nothing to catch, and the curator exports corruption. Structural error is the one class of error the downstream gates cannot see, so it is the one place where silent auto-apply is least acceptable.
- **D-03:** The deterministic layer must be able to say "I am not confident" as a first-class outcome, not fall back to a best guess. Heuristics that cannot express uncertainty are not acceptable.
- **D-04:** The deterministic layer is pure — no network, no `input()`, no side effects. It must be testable without mocks or an API key. The Claude layer is a separate module so the deterministic tests never touch the SDK.

### Hint contract (PARSE-06)

- **D-05:** The parser signals uncertainty by **returning a result object, not by raising**. Exceptions are for broken files (missing path, unreadable workbook), not for "I need to ask you something". `parse` returns either a resolved table or a structural question; both are ordinary values.
- **D-06:** `StructuralHint` is a plain, JSON-serialisable frozen dataclass — the fields a human can pin down: sheet name, header row index (0-based, in the raw grid), delimiter, decimal separator, data region, table shape. It must survive a round-trip through JSON because the same object is persisted with a learned profile (LEARN-06, Phase 3) and travels over HTTP to the browser (UI-02, Phase 4). No `input()` inside the parser, no CLI-only representation.
- **D-07:** `StructureQuestion` carries what the tool is unsure about, a plain-English reason, the pre-filled proposal (from heuristics or from Claude), a confidence score, ranked alternatives, and enough raw-grid evidence (the first N rows as read) for a human to answer without opening the file. Error/question messages describe the consequence, not the symptom — per project conventions.
- **D-08:** Asking the human is the responsibility of the **caller**, not the parser. The CLI prompts on a terminal; the API returns the question as JSON. One question object, two presentations.

### Not-one-table: sheet selection and shape (PARSE-04, PARSE-05)

- **D-09:** Sheet selection produces **ranked candidates**, never a silent single pick. One clear winner → use it. Several equally data-like sheets → a structural question. This is required by the corpus, not theoretical: `orion_pk_report.xlsx` has one real data sheet (`Summary`) plus `Raw timepoints` and `Notes`, where the wrong sheet is also a tidy table; `delta_screening_per_target.xlsx` has genuine data on *every* sheet (one per target), so "pick the data sheet" is simply the wrong question there. v1 targets one chosen table per file (PROJECT.md Out of Scope), so the human picks.
- **D-10:** Table shape is classified into `row_per_record | wide_matrix | transposed | multiple_tables | unknown`. Anything other than `row_per_record` **does not produce a `RawTable`** — it produces a structural question explaining the detected shape and why it is unsupported in v1.
- **D-11:** No "parse anyway with a warning" path. A silently-wrong table that carries a warning nobody reads is exactly the failure mode PARSE-05 exists to prevent. Un-pivoting wide/transposed layouts stays deferred (PARSE-V2-01).

### Decimal comma: detect in Phase 1, convert in Phase 2 (PARSE-03)

- **D-12:** **The parser does not rewrite cell values.** `RawTable` keeps every value as a string exactly as written. This preserves the existing documented invariant in `parsing/table.py` ("Values are kept as strings so the mapper sees them exactly as written … without pandas coercing types and hiding the ambiguity the curator needs to resolve"), and it keeps a single conversion site.
- **D-13:** The parser attaches a **column-level numeric-locale annotation**: `decimal_comma | decimal_point | ambiguous | non_numeric`, inferred per column across all rows — not per cell. A per-cell guess cannot see the pattern that disambiguates the column.
- **D-14:** Ambiguity rule. Varying digit counts after the comma prove a decimal separator: `446,2` next to `11,076` and `654,85` cannot be thousands grouping, so the column is confidently `decimal_comma` (this is `pinnacle_labs_export.csv`, and it must resolve without asking). A column where *every* comma is followed by exactly three digits (`1,234`), or which mixes both patterns, is `ambiguous` → flagged for confirmation, never guessed. This satisfies PARSE-03's "normalises without corrupting by 1000×, flagging when genuinely ambiguous."
- **D-15:** Actual string→number conversion happens once, at mapping-apply time, in EXPORT-01's canonical tidy form (Phase 2), driven by the parser's locale annotation. Three documents previously implied three different conversion sites (PARSE-03 "normalises", `RawTable` "strings only", EXPORT-01 "values normalised"); this decision resolves that in favour of *detect in Phase 1, convert in Phase 2*.

### Drawings: charts, chartsheets, and images (verified empirically 2026-07-10)

A source workbook may contain charts and images. Three distinct cases, three different behaviours — established by probing the installed `openpyxl` / `pandas`, not assumed:

- **D-16: A chart embedded in a data sheet must not disqualify that sheet.** A `BarChart` anchored at `E2` on a 2-column table leaves `pd.read_excel` returning `shape=(5, 2)` — floating drawings create no cells and do not extend `max_column`. The shape classifier (D-10) must therefore ignore `ws._charts` / `ws._images` entirely when deciding `row_per_record`. Rejecting a perfectly ordinary report because it has a graph next to the table would be a worse failure than the one PARSE-05 guards against.
- **D-17: Iterate `wb.worksheets`, never `wb.sheetnames`.** A dedicated chart sheet appears in `openpyxl`'s `wb.sheetnames` but is a `Chartsheet` object with no cells and no `iter_rows` — touching it as a worksheet crashes. `pandas` silently omits chartsheets from `pd.ExcelFile.sheet_names` (probe: openpyxl reported `['Data','DataWithChart','ChartOnly','Empty']`, pandas reported the same list minus `ChartOnly`), which is why today's `sheet_names()` is accidentally safe. Phase 1 will read the raw grid through `openpyxl` in order to locate a header row below banner rows, and that is precisely where the crash appears. Chartsheets are "obvious non-data sheets" under PARSE-04 — drop them from sheet ranking, and drop `openpyxl.chartsheet.Chartsheet` explicitly rather than relying on a duck-typed `AttributeError`.
- **D-18: An image-only sheet gets a structural question, not "no data rows".** `Pillow` is not a dependency, and `openpyxl`'s reader handles that deliberately (`reader/drawings.py`: `if not PILImage: # Pillow not installed, drop images`) — the workbook loads, images are dropped, nothing raises. So a sheet holding only a scanned/pasted table reads as `shape=(0, 0)`, and `cli.py` currently answers `(skipped: sheet has no data rows)`. That is false: the sheet has data we cannot read. Detect "zero cells but at least one drawing anchored on the sheet" and raise it as a `StructureQuestion` explaining exactly that. Never silently skip.
- **D-20: A chart is a *view* of cells, never a source of truth — do not read values out of it.** Probed: an embedded `BarChart` stores no numbers, only references — `series[0].val.numRef.f == "'DataWithChart'!$B$2:$B$6"`, title `"'DataWithChart'!B1"`. Following that reference lands on cells the parser already reads, so "parsing the chart" is a non-goal. The one case where a chart *does* carry numbers is a broken link: Excel persists the last-rendered values in `numCache` (our probe showed `None` only because openpyxl wrote the fixture and openpyxl does not emit the cache; Excel does). Those cached numbers have no column names and no freshness guarantee — a snapshot of whatever was on screen at last save. For a tool whose motto is "trust the numbers", that is the worst possible source: plausible-looking and unverifiable. If a chart is the only carrier of a value, raise a `StructureQuestion`; never read the cache silently.
- **D-21: Chart references are a legitimate structural *signal*, but stay off the critical path.** `'Summary'!$B$2:$B$6` names the real sheet, the data region, and (by exclusion) the header row — precisely what PARSE-01/04/05 compute the hard way. On `orion_pk_report.xlsx`, where `Summary` and `Raw timepoints` are indistinguishable by shape, a chart anchored on `Summary` would settle the ranking instantly. Treat this as an optional heuristic input to sheet ranking and region detection: adopt it if research finds it cheap, drop it otherwise. It cannot be load-bearing — it fires only when a chart exists, and no file in the current corpus has one.
- **D-19: Do not add `Pillow`, and do not attempt OCR.** Reading pixels is out of scope for v1. Detecting that pixels are all a sheet contains, and saying so plainly, is in scope. Note that `openpyxl` needs `Pillow` merely to *construct* an `Image` object — a fixture generator that plants an image in a test workbook will need it as a dev-only dependency, while the parser itself must keep working without it.

### Claude's Discretion

- Module layout inside `src/assayingest/parsing/` (heuristics, hint/question types, Claude assist) — planner's call, subject to the pure/impure split in D-04.
- Whether the existing `parse_file()` signature is kept as a thin wrapper for the 32 existing green tests, or migrated — planner's call. Backward compatibility is not a requirement; a clean boundary is.
- The specific scoring heuristic for header-row detection and sheet ranking, and its confidence threshold. Research should ground these rather than invent them.
- Whether the Claude structural proposal is one call covering all structural questions or one call per question.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` §"Phase 1: Robust File Reading" — goal, 5 success criteria
- `.planning/REQUIREMENTS.md` §Parsing — PARSE-01..06, the six requirements this phase owns
- `.planning/REQUIREMENTS.md` §v2 / §"Out of Scope" — PARSE-V2-01 (no un-pivot), PARSE-V2-02 (no multi-table extraction), "no hardcoded field list / domain"

### Project direction (supersedes the original brief)
- `.planning/PROJECT.md` — the domain-independent pivot; the direction note at the top explicitly supersedes `CLAUDE.md`'s fixed 7-field assay framing
- `.planning/STATE.md` §Blockers/Concerns — flags PARSE-06's human-assisted hint as one of two mechanisms with no Day-1 precedent, to de-risk early; and warns that every safety mechanism must be enforced structurally, never as a UI-only nicety

### Code and conventions
- `src/assayingest/parsing/table.py` — the parser being hardened; `RawTable`'s strings-only invariant is documented in its docstring (see D-12)
- `.planning/codebase/CONVENTIONS.md` — naming, error handling, dataclass and type-hint conventions
- `.planning/codebase/CONCERNS.md` §"Fragile Areas" — `_clean_header()` depends on pandas' `"Unnamed: N"` placeholder; §"Test Coverage Gaps" — no tests for files with no headers, corrupted Excel, or unicode edge cases
- `CLAUDE.md` §"Coding conventions" — Clean Architecture, single level of abstraction, log-or-raise never both, error messages describe the consequence

### Test corpus (the hazards this phase must survive)
- `data/synthetic/README.md` — per-file table of the structural mess each vendor file demonstrates
- `data/synthetic/zephyr_bio_ZB-2025.xlsx` — 4 metadata rows above the real header, 3 sheets (PARSE-01)
- `data/synthetic/pinnacle_labs_export.csv` — semicolon-delimited, comment lines above the header, comma decimals (PARSE-02, PARSE-03)
- `data/synthetic/helix_genomics_DE.xlsx` — German headers, comma decimals `14,771`, `DD.MM.YYYY` (PARSE-03)
- `data/synthetic/orion_pk_report.xlsx` — `Summary` / `Raw timepoints` / `Notes`; the wrong sheet is also a tidy table (PARSE-04)
- `data/synthetic/delta_screening_per_target.xlsx` — real data on every sheet; "pick the data sheet" is the wrong question (PARSE-04)
- `data/synthetic/apex_labs_wide_matrix.xlsx` — wide matrix, unit hidden in the sheet name (PARSE-05)
- `data/synthetic/bionexus_transposed.xlsx` — transposed layout (PARSE-05)
- `scripts/gen_synthetic_pk.py` — deterministic regeneration of the extended vendor set

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `RawTable` (frozen dataclass, `parsing/table.py`): headers + rows as strings, `row_count`, `label`, `sample(limit)`. Keep it as the parser's success output; extend with structural provenance rather than replacing it.
- `sheet_names(path)`: already lists workbook sheets and raises the project's standard `FileNotFoundError` / `ValueError`. Sheet ranking builds on it.
- `_clean_header()`: already normalises pandas' `"Unnamed: N"` placeholder to `""`, treating a blank header as signal rather than noise — exactly the posture this phase generalises.
- The mapper's proposal shape (`FieldMapping`: source column, confidence 0.0–1.0, human-readable reasoning, `needs_confirmation` gate) is the model to imitate for `StructureQuestion` (D-02, D-07).

### Established Patterns
- Wire models (Pydantic, API shape) map to domain models (frozen dataclasses, stdlib-only) at the layer boundary. A Claude structural proposal is a *wire* model; `StructuralHint` is a *domain* model.
- Parsing currently has zero dependencies on mapping or domain, and no network calls. D-04 preserves that for the deterministic layer and isolates the Claude assist behind its own module.
- `str | None` unions, keyword-only optional args after `*`, `@property` for computed values, `_private` helpers for low-level detail.

### Integration Points
- `cli.py:run()` currently loops every sheet of a workbook and calls the mapper per sheet. D-09 changes this: sheet selection happens in the parser, and the CLI becomes the thing that *asks* when the parser returns a question (D-08).
- Phase 3 (LEARN-06) persists `StructuralHint` alongside a learned profile; Phase 4 (UI-02) renders `StructureQuestion` inline in the browser. Both consume the exact objects defined here — hence D-06's JSON round-trip requirement.
- Phase 2 (EXPORT-01) performs the numeric conversion the parser only annotates (D-15).

</code_context>

<specifics>
## Specific Ideas

- The three-layer design (rules → Claude proposes → human confirms) came from the builder, replacing an initial two-layer "rules → human" recommendation. The decisive argument for keeping Claude in the loop: the human then *agrees with a pre-filled proposal* rather than diagnosing the file themselves — one click instead of an investigation, and a better demo beat for DEMO-03, without weakening the gate.
- `pinnacle_labs_export.csv` is the reference case for D-14: it must parse **without** asking the human, because `446,2` / `11,076` / `654,85` disambiguate themselves. If the implementation asks about this file, the ambiguity rule is too eager.
- `orion_pk_report.xlsx` is the reference case for D-09: `Summary` vs `Raw timepoints` differ by *meaning*, not by *shape*, so a purely structural heuristic should be expected to hesitate here — and that hesitation is correct behaviour, not a bug.
- TDD is enabled for this phase (`workflow.tdd_mode: true`). Each hazard in the corpus is a failing test on a concrete synthetic file first, then the code.
- **The corpus has no drawings.** None of the ten synthetic files contains a chart, a chartsheet, or an image, so D-16..D-18 are currently untestable. Phase 1 must extend `scripts/gen_synthetic_pk.py` with three fixtures: a data sheet carrying an embedded chart (must parse normally), a workbook containing a chartsheet alongside its data sheet (chartsheet must be dropped from ranking, no crash), and a sheet holding only an image (must yield a structural question, not "no data rows"). This also feeds DEMO-02, whose hazard list does not yet mention drawings — worth adding there.

</specifics>

<deferred>
## Deferred Ideas

- **Un-pivot of wide/transposed layouts** — the Claude structural layer built here could later propose the un-pivot too. Stays v2 (PARSE-V2-01); v1 detects and asks.
- **Extraction of several tables from one sheet** — v2 (PARSE-V2-02); v1 targets one chosen table per file.
- **Fuzzy matching of a remembered hint to a near-miss layout** — adjacent to MATCH-01, already deferred to v2. A hint matches its profile exactly or not at all.
- **Reading values out of a chart image via Claude's vision** — a chart pasted as a PNG carries neither references nor cache, only pixels. Claude can see it, and the D-02 layer (propose → human confirms) is exactly the right shape for surfacing what it read. Deferred to v2: it needs its own prompt and schema, and it yields numbers with nothing to check them against. v1 detects the image and asks (D-18).
- **Recovering a broken chart's `numCache` values** — technically reachable via `ser.val.numRef.numCache.pt`. Deferred, and probably permanently: cached values are unnamed and stale by construction (D-20).
- **Delivery form ("сайт или что-то другое")** — raised during discussion; already decided at project level, not a Phase 1 question. It is a browser app: FastAPI backend + Vite/React review screen (PROJECT.md §Context, ROADMAP Phase 4). The builder wants FastAPI for learning purposes; Phase 4 is where that happens, and API-02 (the server re-checks the export gate rather than trusting the client) is the requirement that exercises it. Phase 1 stays a pure library layer that FastAPI later calls. ROADMAP keeps a CLI-only demo as the fallback if UI time runs short.

</deferred>

---

*Phase: 1-robust-file-reading*
*Context gathered: 2026-07-10*