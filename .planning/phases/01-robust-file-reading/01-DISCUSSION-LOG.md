# Phase 1: Robust File Reading — Discussion Log

**Date:** 2026-07-10
**Mode:** default (interactive)

> Human reference only. Downstream agents read `01-CONTEXT.md`, not this file.

## Gray areas presented

All four were selected for discussion:

1. Structure engine — deterministic Python or Claude
2. Hint contract (PARSE-06)
3. What to return when the file is not one clean table (PARSE-04/05)
4. Decimal comma — where the fix happens (PARSE-03)

Alongside the selection, the builder noted a preference for FastAPI (currently learning it) and asked whether the product should be a website or something else.

## Area 1 — Structure engine

**Q (first attempt):** Who decides the file's structure — deterministic Python or Claude?
Options: pure deterministic / Python + Claude fallback / Claude first / you decide.
→ Builder asked to clarify rather than answer.

**Q (second attempt, reframed):** When the rules fail, who do we ask?
Options: human immediately (recommended) / Claude first, then human / hand structure to Claude entirely.
→ Builder asked to clarify again: *"не понимаю, поясни проще"*.

**Clarification given in plain language,** then the builder asked the sharp question:
*"если в парсере нет ни одного вызова Claude, то будет ли этот код прекрасно понимать структуру файла?"*

**Answer: no.** Rules see *form*, not *meaning*. Walked the corpus concretely: rules handle `zephyr` (banner rows), `pinnacle` (delimiter + comment lines), `helix_genomics` (comma decimals), `bionexus` (transposed). Rules break on `orion` (`Summary` vs `Raw timepoints` differ by meaning, not shape), `delta` (data on every sheet — "pick the data sheet" is the wrong question), `apex` (unit lives in the sheet *name*). Claude would also err — less often, but confidently and silently, which is worse. The requirements already concede this: PARSE-05 says *detect and flag*, PARSE-06 says *ask the human*, PARSE-V2-01 defers un-pivot entirely.

**Builder's counter-proposal:** *"а что если сначала работает код, если остаются неуверенности, то подключается Claude, и только потом спрашивают человека?"*

Accepted, with one constraint attached. The trap in the middle layer is auto-apply: a wrong structure does not look wrong. Shift the header row by one and the mapper confidently maps garbage, every field goes green, the export gate has nothing to catch. So Claude may **propose** a structure with a reason and a confidence, pre-filling the question — it may never **apply** one.

**Q:** Does Claude apply its structural answer or show it for confirmation?
→ **"Предлагает, человек подтверждает"** → D-02.

**Q:** Build the Claude layer immediately, or after "rules + human" works? (~3 days left, 4 phases to go.)
→ **"Сразу все три слоя"** → D-01.

## Areas 2, 3, 4

Builder: *"ладно, делай как считаешь нужным"* — remaining gray areas resolved as Claude's discretion, recorded as D-05..D-15 in CONTEXT.md.

- **Hint contract:** result object, not an exception; `StructuralHint` and `StructureQuestion` as JSON-serialisable frozen dataclasses; the *caller* asks the human, never the parser (CLI prompts, API returns JSON). Driven by LEARN-06 (persist the hint) and UI-02 (render it in the browser).
- **Not-one-table:** ranked sheet candidates rather than a silent pick; shape classified into five kinds; anything but `row_per_record` yields a question, never a warned-but-wrong table.
- **Decimal comma:** parser detects and annotates a per-column locale, never rewrites values; conversion happens once, at EXPORT-01 apply time in Phase 2. Resolves the three-way contradiction between PARSE-03, `RawTable`'s strings-only docstring, and EXPORT-01.

## Late addition — drawings in source files

**Builder:** *"учти, что в файле могут быть картинки и графики."*

Probed the installed `openpyxl` / `pandas` rather than assuming. Three distinct behaviours, recorded as D-16..D-19:

| Case | Behaviour | Consequence |
|---|---|---|
| Chart embedded in a data sheet | `pd.read_excel` → `shape=(5, 2)`; no phantom cells, `max_column` unaffected | Must **not** disqualify the sheet (D-16) |
| Dedicated chartsheet | In `openpyxl` `wb.sheetnames` but not in `pd.ExcelFile.sheet_names`; it is a `Chartsheet` with no `iter_rows` | Iterate `wb.worksheets`; a raw-grid reader over `wb.sheetnames` would crash (D-17) |
| Image-only sheet | `Pillow` absent → `reader/drawings.py` drops images, no exception; sheet reads as `shape=(0, 0)` | Today's `cli.py` says "no data rows" — a lie. Must raise a structural question (D-18) |

**Follow-up:** *"а если понадобится спарсить или считать график?"*

Probed `openpyxl`'s chart object. A chart stores references, not numbers: `series[0].val.numRef.f == "'DataWithChart'!$B$2:$B$6"`, title `"'DataWithChart'!B1"`. So reading a chart means following the reference back to cells the parser already reads — a non-goal (D-20). Three sub-cases:

- **Broken link** → Excel persists last-rendered values in `numCache`. Unnamed, stale, unverifiable. Structural question, never a silent read (D-20). Deferred permanently.
- **Chart pasted as a PNG** → pixels only. Claude's vision could read it, and D-02's propose→confirm layer is the right shape for that, but it needs its own prompt/schema and produces numbers with nothing to check against. Deferred to v2.
- **Chart references as a structural signal** → `'Summary'!$B$2:$B$6` names the sheet, the region, and by exclusion the header row. Would settle `orion_pk_report.xlsx` instantly. Recorded as an optional heuristic (D-21), explicitly off the critical path: it fires only when a chart exists, and the corpus has none.

Also decided: no `Pillow` in runtime deps, no OCR (D-19). And noted that the synthetic corpus has zero drawings, so three fixtures must be added to `scripts/gen_synthetic_pk.py` before D-16..D-18 are testable.

## Scope handling

**Raised:** "желательно написать проект на FastAPI… и подумать, это должен быть сайт или что-то другое."

**Not scope creep, already decided.** PROJECT.md and ROADMAP Phase 4 lock the stack: FastAPI backend + Vite/React review screen. It is a browser app. Phase 4 is where FastAPI gets built, and API-02 (server independently re-checks the export gate) is the requirement that exercises it. Phase 1 stays a pure library layer. Recorded in CONTEXT.md `<deferred>` so it is not re-litigated.

## Configuration changed during this session

- `workflow.tdd_mode` → `true` (was `false`), per the builder's standing preference for strict tests-first.

## Not committed

Per the builder's instruction earlier in the session ("не надо коммитить"), `01-CONTEXT.md`, this log, and the `STATE.md` update are written to the working tree but left uncommitted, alongside the other pending `.planning/` changes.