---
phase: 11-multi-sheet-ingest
verified: 2026-07-13T14:25:00Z
status: gaps_found
score: 3/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Every ingested row records the sheet it came from — on every ingest, single-sheet included — as a reserved export column, not a target field. (SHEET-03, SC-2)"
    status: partial
    reason: >-
      The API path is fully satisfied and tested (a single-sheet CSV confirmed through
      /api/confirm carries __source_sheet in all three export formats). The CLI export
      path writes NO provenance: cli.py calls canonical.assemble() with no source_sheet=,
      so record_sources stays empty and export/writers.py::_export_columns returns the bare
      field names — the exported CSV/XLSX/JSON have no __source_sheet column at all. The
      roadmap SC and D-11-15 are unqualified ("every ingest"), and D-11-15's own rationale
      is the exact failure this produces: "a traceability column that only sometimes exists
      is not a traceability column."
    artifacts:
      - path: "src/assayingest/cli.py"
        issue: "Line 598 — `canonical.assemble(table, proposal, field_set)` omits `source_sheet=`; the CLI's --export output therefore carries no provenance column."
      - path: "src/assayingest/export/writers.py"
        issue: "Lines 52/61 — `_export_columns`/`_rows_with_sources` correctly no-op on empty `record_sources`; the omission is upstream in cli.py, not here. Behaviour is by design, but it makes the CLI ingest surface provenance-free."
      - path: "tests/test_export_cli.py"
        issue: "No test asserts a __source_sheet column on the CLI export path (grep for source_sheet returns nothing) — the gap is untested, not merely unimplemented."
    missing:
      - "Pass `source_sheet=table.origin_sheet or path.name` at cli.py:598 (the SUMMARY itself calls this a one-line change), OR"
      - "Record an explicit override accepting that the CLI is not a product ingest surface, so SC-2 reads 'every API ingest'."
      - "A CLI-path test asserting the reserved column is present, mirroring tests/api/test_provenance_export.py."
deferred: []
human_verification:
  - test: "Upload data/synthetic/zephyr_bio_ZB-2025.xlsx through the browser, select a sheet, and try to confirm."
    expected: "Decide what the curator should be able to do when the validator correctly refuses `uM` against the `µM`-only allowed set. Today the 422 is right and fail-closed, but FieldRow has no control that expresses 'clear the column, use the inferred constant' — the curator is stuck."
    why_human: "Pre-existing (proved by a control experiment on the untouched single-sheet path; see deferred-items.md D-1). Not caused by Phase 11 and it fails no Phase 11 criterion, but it blocks the demo fixture end-to-end. Needs a product decision, not a code check."
  - test: "Review the export writers' handling of a leading =, +, -, or @ in a cell value."
    expected: "A decision on whether CSV/XLSX formula injection is accepted risk for this product."
    why_human: "Pre-existing since Phase 2 and not widened by Phase 11 (the reserved __source_sheet column is server-minted, never client text). Security posture call."
---

# Phase 11: Multi-Sheet Ingest — Verification Report

**Phase Goal:** On a multi-sheet workbook the human decides which sheets to ingest and which Schema applies to which sheet; the tool makes those decisions informed, never silent.
**Verified:** 2026-07-13T14:25:00Z
**Status:** gaps_found (3/4)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (ROADMAP Success Criteria) | Status | Evidence |
|---|---|---|---|
| 1 | Human is shown every sheet and chooses; N sheets → N **independent** datasets, never merged; single-sheet path does not regress. (SHEET-01) | ✓ VERIFIED | `upload.py:148` `_asks_which_sheets` fires on `>1 worksheet AND no explicit sheet=` (D-11-16, not gated on Schema). `sheets.py::resolve_sheets` mints one `UploadGroup` whose `members` map `sheet_name → an ORDINARY upload token` — N independent entries, each with its own field_set/gate/export. No merge/concat path exists anywhere in `src/` (grep: only docstrings *stating* SHEET-02 is struck, at `wire.py:765`, `routes/sheets.py:5`). Single-sheet regression pinned by `test_an_explicit_sheet_bypasses_the_question_entirely`, `test_a_csv_upload_still_returns_a_mapping`, `test_a_csv_with_no_target_still_422s_exactly_as_today`. Merge-absence pinned by `test_the_group_response_has_no_merged_table_and_no_group_level_gate`. |
| 2 | Every ingested row records its source sheet — **on every ingest, single-sheet included** — as a reserved export column, not a target field. (SHEET-03) | ✗ FAILED (partial) | **Column shape is right; one ingest surface is missing it.** `canonical.py:72` `SOURCE_SHEET_COLUMN = "__source_sheet"` rides `record_sources` (a list *parallel* to `records`), never a `Field` — `FieldSet.signature` (`fields/models.py:66-78`) hashes only `self.fields`, so **no learned profile is invalidated** (D-11-12/13 held). API path verified: `service.py:489` `source_sheet = table.origin_sheet or source_label`, `confirm.py` passes the client's real filename, and `tests/api/test_provenance_export.py::test_a_confirmed_csv_export_carries_source_sheet_in_all_three_formats` proves a **single-sheet CSV** gets the column. **But `cli.py:598` calls `canonical.assemble(table, proposal, field_set)` with no `source_sheet=`** → `record_sources == []` → `writers.py:52` returns the bare field names → **a CLI export has no provenance column.** See Gaps. |
| 3 | Each selected sheet passes the structural gates **independently**; a gate-failed sheet is surfaced with its own question, never dropped. (SHEET-04) | ✓ VERIFIED | Each member is parsed with an explicit `sheet=`, which short-circuits ranking and runs that sheet's own full header/shape/locale/date chain (`describe_workbook` docstring; `_resolve_one_sheet` re-derives `/api/upload`'s exact choreography: structural question → date question → mapping). `structural_hint.py:71-76,109-110,134,154` threads `schema`/`sheet`/`strictness`/`group_id` through the re-parse, so a member's own question resolves back **into its group** (11-06's fix — pinned by `test_group_membership_survives_a_still_ambiguous_hint_re_put` / `..._resolved_to_a_mapping` / `..._resolved_to_a_date_question`). Never dropped: `state/sheets.ts::_isPreTicked` leaves a gate-failed sheet **unticked but still tickable** (not disabled, not hidden); `test_orion_notes_is_described_and_marked_never_dropped`. |
| 4 | Best-matching Schema proposed per sheet with the **coverage visible**; always pre-filled, **never auto-applied**; zero coverage → skip; a tie is shown as a tie. (SHEET-05) | ✓ VERIFIED | `service.py:1828 propose_schemas_for_sheet` — profile hit → crosswalk coverage → (only on zero coverage everywhere) Claude ranker. **No threshold:** `grep -E 'MARGIN\|THRESHOLD' src/assayingest/service.py` → **nothing**, and `test_there_is_no_threshold_or_confidence_margin_in_the_scorer` greps the module to keep it that way (D-11-06). **Coverage visible:** `SheetQuestionPanel.tsx:136-156` renders `coverageLine()` ("6/7 canonical fields matched · crosswalk"), the matched field←header pairs, and the uncovered list, always — never behind a disclosure. **Never auto-applied:** the panel pre-selects, the human submits. **Zero coverage → skip:** `proposals: []` is the signal; panel renders "No canonical fields matched any Schema — proposed: skip this sheet" and `_isPreTicked` returns false. **A tie is a tie:** both returned with equal scores; `_preSelectedSchema` hard short-circuits to an **empty** Select on `tie`, and `submitBlockedReason` refuses submit with "ties aren't broken automatically" — the Upload dropdown's stale default is not allowed to settle it either. |

**Score:** 3/4 truths verified (0 present, behavior-unverified)

### Explicitly Requested Constraint Checks

| Constraint (from CONTEXT / the verification brief) | Result | Evidence |
|---|---|---|
| No coverage threshold smuggled into the scorer (D-11-06) | ✓ PASS | `grep -rE 'MARGIN\|THRESHOLD' src/assayingest/service.py` → empty. The only `_CONFIDENCE_MARGIN`s in `src/` are pre-existing, in `parsing/structure/{header,sheets}.py`, on paths this phase deliberately does not touch. A test pins the absence. |
| No merging/combining path anywhere (SHEET-02 struck) | ✓ PASS | No `merge`/`combine`/`concat` function in `src/`. The only SHEET-02 strings are docstrings asserting it is struck from the product. |
| `FieldSet.signature` unchanged — `source_sheet` is NOT a Field | ✓ PASS | `fields/models.py:66-78` hashes `self.fields` only. Provenance lives in `CanonicalTable.record_sources` + the reserved `__source_sheet` export column (`canonical.py:72,144`). Learned profiles still match. |
| Confirm gate per dataset, never aggregated | ✓ PASS | `confirm.py` operates on ONE upload token; its only group awareness is `groups.record_run(...)` bookkeeping (`confirm.py:215-216`). The archive route independently refuses while any member is unrecorded (`export.py:122-130`). Pinned by `test_confirming_one_member_leaves_the_others_pending`, `test_each_member_confirms_on_its_own_gate_and_mints_its_own_run`, and the UI test "resolving one member never resolves another (the gate is per dataset, never aggregated)". |
| Scorer sources Schemas only via `SchemaStore` (D-11-23) | ✓ PASS | `propose_schemas_for_sheet` takes `Schema` **objects** — it holds no store, opens no session, issues no query. Its two callers use the store and nothing else: `upload.py:306 schema_store.list_schemas()`, `sheets.py:155 schema_store.get_schema(...)`. Pinned by `test_the_scorer_cannot_reach_a_schema_except_through_the_store` + two tombstone tests. |
| Tabs use `keepMounted` (@base-ui), NOT `forceMount` (Radix no-op) | ✓ PASS | `ReviewGroupTabs.tsx:285` → `<TabsContent … keepMounted>`. `forceMount` appears only inside the explanatory comment at :278-280. The behavioural consequence is tested: "keeps an amber resolution made on Week 1 after switching to Week 2 and back". |

### Test Suites (run by the verifier, not quoted from SUMMARY)

| Suite | Command | Result |
|---|---|---|
| Backend | `uv run pytest -q` | **1121 passed, 4 skipped**, 1 warning — 188.48s |
| Frontend | `npm test -- --run` (vitest) | **248 passed** (14 files) — 5.92s |
| Frontend typecheck | `npx tsc --noEmit` | **exit 0**, no errors |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|---|---|---|---|
| SHEET-01 | Human chooses which sheets; N sheets → N independent datasets; never merged | ✓ SATISFIED | Truth 1 |
| SHEET-02 | *(STRUCK 2026-07-13)* | ✓ CORRECTLY ABSENT | No merge path in `src/` or `frontend/src/`; only docstrings recording the strike |
| SHEET-03 | Every ingested row records its source sheet, on every ingest | ✗ PARTIAL | API path satisfied and tested; **CLI export path writes no provenance** — see Gaps |
| SHEET-04 | Each sheet passes the structural gates independently; failures surfaced, never dropped | ✓ SATISFIED | Truth 3 |
| SHEET-05 | Tool proposes the best Schema per sheet, coverage visible, never auto-applied | ✓ SATISFIED | Truth 4 |

No orphaned requirements: REQUIREMENTS.md maps exactly SHEET-01/03/04/05 to Phase 11, and all four are claimed by plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| — | — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` in any file this phase touched | — | Clean |
| `SheetQuestionPanel.tsx` | 170 | `placeholder="Choose a Schema…"` | ℹ️ Info | A legitimate `<SelectValue>` prop, not a stub marker |

### Assessment of the Known Open Items

1. **CLI writes no provenance** → this **is** the gap. `cli.py:598` omits `source_sheet=`, so a CLI `--export` produces CSV/XLSX/JSON with no `__source_sheet` column. Plan 11-03 scoped this out on the reasoning that "the API path… is the product surface", but SC-2, SHEET-03, and D-11-15 are all unqualified ("every ingest, single-sheet included"), and D-11-15's stated rationale — *a traceability column that only sometimes exists is not a traceability column* — describes precisely this outcome. The CLI is a live, tested entry point that emits the same three export formats. **Criterion 2 is not met as written.** It is a one-line fix or a one-entry override; either closes it.
2. **zephyr `uM` vs `µM` confirm dead-end** → **not a Phase 11 gap.** Proved pre-existing by the control experiment on the untouched single-sheet path (deferred-items D-1). The validator's 422 is correct and must stay; the gap is that `FieldRow` has no control expressing "clear the column, use the inferred constant". It fails no Phase 11 criterion, but it blocks a demo fixture end-to-end → routed to human decision.
3. **Formula injection in the export writers** → **not a Phase 11 gap.** Pre-existing since Phase 2 and not widened here: the one column this phase adds is server-minted (a worksheet title or the server-retained filename), never free client text. Security-posture call → routed to human decision.

### Gaps Summary

Three of the four success criteria are achieved in the shipped code, and the achievement is structural rather than incidental: the scorer has no threshold to tune (and a grep-test that keeps it that way), the group has no aggregated gate to bypass (each member is an ordinary upload token), and the provenance column is a reserved meta column rather than a `Field`, so `FieldSet.signature` — and therefore every learned profile — is untouched. The `keepMounted` correction landed.

The single gap is criterion 2, and it is narrow but literal: provenance is written on **every API ingest** but on **no CLI ingest**. The roadmap's own wording ("on every ingest, single-sheet included") and D-11-15's own rationale both reject a sometimes-column. This is one line in `cli.py` plus a mirroring test — or an explicit override recording that the CLI is not a product ingest surface.

**This gap may be intentional.** To accept the deviation instead of closing it, add to this file's frontmatter:

```yaml
overrides:
  - must_have: "Every ingested row records the sheet it came from — on every ingest, single-sheet included"
    reason: "The CLI is a developer entry point, not a product ingest surface; SC-2 is scoped to the API path, which is fully covered."
    accepted_by: "Mesrop Tarkhanyan"
    accepted_at: "2026-07-13T00:00:00Z"
```

---

_Verified: 2026-07-13T14:25:00Z_
_Verifier: Claude (gsd-verifier)_
