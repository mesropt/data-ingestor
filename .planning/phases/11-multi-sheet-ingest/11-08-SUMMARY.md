---
phase: 11-multi-sheet-ingest
plan: "08"
subsystem: api
tags: [fastapi, export, zip, run-group, zip-slip, tdd, fail-closed]
status: complete

# Dependency graph
requires:
  - phase: 11-07
    provides: "UploadGroup.runs + GroupRegistry.record_run + UploadEntry.group_id/.sheet — and the explicit handoff naming the four re-puts that lose them (closed here)"
  - phase: 11-03
    provides: "__source_sheet row provenance (SHEET-03) that the archive's per-member export.csv files prove end to end"
  - phase: 10-frictionless-correct-ingest
    provides: "require_user (D-10-13); the confirm gate and service.export this plan looks up but never touches"
provides:
  - "export/archive.py: build_group_archive(run_dirs_by_sheet, out_path) — stdlib zipfile, allowlist-sanitized entry names, sheet_<index> fallback, collision suffixing"
  - "confirm.py: groups.record_run(entry.group_id, entry.sheet, run_id) after the export dir is written — the ONLY change there"
  - "export.py: GET /api/export/group/{group_id}/archive — uuid4-validated before any filesystem access, require_user-gated, 409 naming how many datasets are still unconfirmed"
  - "structural_hint.py + date_format.py: all four question-hop re-puts now carry group_id/sheet forward (the 11-07 handoff, closed)"
affects:
  - "11-09/11-10 (the Review group tabs' Download All bar calls this route)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Allowlist-sanitized archive entry names ([A-Za-z0-9._ -], dot-run collapse, edge strip) — export.py's validate-before-filesystem discipline extended from run_id to worksheet titles"
    - "The archive as a LOOKUP over per-member verdicts, never a gate: a run_id exists only because service.confirm's NotReadyError gate passed, so 'every member has a run' is the gates' own verdict read back — no readiness re-derived, none aggregated"
    - "Per-request temp zip served via FileResponse with a BackgroundTask unlink — no download accumulates server state"

key-files:
  created:
    - src/assayingest/export/archive.py
    - tests/test_export_archive.py
    - tests/api/test_group_export.py
  modified:
    - src/assayingest/api/routes/confirm.py
    - src/assayingest/api/routes/export.py
    - src/assayingest/api/routes/structural_hint.py
    - src/assayingest/api/routes/date_format.py

key-decisions:
  - "409 (not 404) for a partially-confirmed group: the group exists and the request is well-formed — the state conflicts. The detail names HOW MANY datasets are still unconfirmed, so the human can see what is missing and why."
  - "A member confirmed WITHOUT export has no recorded run and blocks the archive exactly like an unconfirmed one — the archive zips export directories, and a run directory exists only when export ran."
  - "The Content-Disposition filename gets the same allowlist treatment as an entry name — a filename in a response header is every bit as client-influenced as a path inside the zip."

requirements-completed: [SHEET-01]

coverage:
  - deliverable: "build_group_archive: one zip, one directory per sheet, four files each — and a worksheet title can never escape it (T-11-28)"
    verification:
      - kind: unit
        ref: "tests/test_export_archive.py#test_a_hostile_sheet_title_cannot_escape_the_archive_root"
        status: pass
      - kind: unit
        ref: "tests/test_export_archive.py#test_two_titles_that_sanitize_identically_do_not_overwrite_each_other"
        status: pass
      - kind: unit
        ref: "tests/test_export_archive.py#test_the_archive_holds_one_directory_per_sheet_with_all_four_files"
        status: pass
    human_judgment: false
  - deliverable: "One action downloads every confirmed member's result set, each export.csv carrying its OWN __source_sheet (SHEET-01's last clause + SHEET-03 across a group)"
    verification:
      - kind: integration
        ref: "tests/api/test_group_export.py#test_a_confirmed_group_downloads_as_one_zip_with_each_sheets_own_provenance"
        status: pass
    human_judgment: false
  - deliverable: "The archive is served only when EVERY member has a recorded run; an unconfirmed member is refused loudly (409 naming the count), never silently omitted — and no member's gate was touched (T-11-31)"
    verification:
      - kind: integration
        ref: "tests/api/test_group_export.py#test_the_archive_refuses_while_any_member_is_unconfirmed"
        status: pass
      - kind: integration
        ref: "tests/api/test_group_export.py#test_a_member_with_an_unresolved_amber_field_still_422s_at_confirm"
        status: pass
      - kind: command
        ref: "git diff -U0 src/assayingest/api/routes/confirm.py | grep -cE 'NotReadyError|is_ready|unclear' -> 0"
        status: pass
    human_judgment: false
  - deliverable: "The boundary holds: 401 anonymous (T-11-30), non-uuid4 group_id 404 BEFORE any filesystem access (T-11-29), unknown group 404 naming the consequence"
    verification:
      - kind: integration
        ref: "tests/api/test_group_export.py#test_an_anonymous_archive_request_is_401"
        status: pass
      - kind: integration
        ref: "tests/api/test_group_export.py#test_a_group_id_that_is_not_a_uuid4_is_404_before_any_filesystem_access"
        status: pass
      - kind: integration
        ref: "tests/api/test_group_export.py#test_an_unknown_group_is_404_naming_the_consequence"
        status: pass
    human_judgment: false
  - deliverable: "Group membership survives every question hop (the 11-07 handoff, closed): all four re-puts carry group_id/sheet, so the members that needed a question still appear in the archive"
    verification:
      - kind: integration
        ref: "tests/api/test_group_export.py#test_a_member_that_answered_a_date_question_still_appears_in_the_archive"
        status: pass
      - kind: integration
        ref: "tests/api/test_group_export.py#test_group_membership_survives_a_still_ambiguous_hint_re_put"
        status: pass
      - kind: integration
        ref: "tests/api/test_group_export.py#test_group_membership_survives_a_hint_resolved_to_a_mapping"
        status: pass
      - kind: integration
        ref: "tests/api/test_group_export.py#test_group_membership_survives_a_hint_resolved_to_a_date_question"
        status: pass
    human_judgment: false

# Metrics
duration: 17min
completed: 2026-07-13
tasks: 2
files: 7
commits: 4
---

# Phase 11 Plan 08: Group Export — One Archive, N Confirmed Datasets Summary

**A confirmed group now downloads as ONE zip — one allowlist-sanitized directory per sheet, four files each, every member's rows carrying their own `__source_sheet` — served only when every member's own gate has already passed, and the 11-07 handoff defect (membership lost on a question hop) is closed and pinned by four tests.**

## Performance

- **Duration:** 17 min (08:55 → 09:12 UTC)
- **Tasks:** 2 (both TDD, RED then GREEN)
- **Files:** 7 (3 created, 4 modified)
- **Suite:** 1121 passed, 4 skipped (was 1102 after 11-07; **+19 tests, zero existing test files modified** — verified by `git diff --name-only b69d0c0..HEAD -- tests/`, which lists only the two new files)

## Accomplishments

- **SHEET-01's last clause is closed.** N selected sheets already produced N independent datasets (11-07); the human can now "export with one action" (D-11-10): `GET /api/export/group/{group_id}/archive` zips each member's `EXPORT_BASE_DIR/{run_id}/` directory into one download, in workbook order, named after the curator's own file (`zephyr_bio_ZB-2025.zip`).

- **The archive is a convenience over the per-member gates, never a bypass (T-11-31, critical).** It adds NO readiness logic: `confirm.py` records `run_id` into the group only after the existing gate passed and the export was written, and the route merely checks every member of `group.members` has an entry in `group.runs`. With 2 of 3 confirmed it refuses with a 409 naming *how many* datasets are still unconfirmed — the human sees what is missing and why — while each confirmed member's own per-run download keeps working. The grep criterion proves the gate untouched: `git diff` on `confirm.py` contains zero hits for `NotReadyError|is_ready|unclear`.

- **A worksheet title cannot escape the archive (T-11-28).** `_safe_entry_name` is an ALLOWLIST (`[A-Za-z0-9._ -]`) with a dot-run collapse (so `../../evil` → `evil`), an edge strip, a `sheet_<index>` fallback for a title the allowlist empties, and an index suffix when two titles sanitize identically (`Data/2025` vs `Data\2025` — both survive, distinctly named, neither overwritten). Stdlib `zipfile`, zero packages installed. `group_id` gets `_RUN_ID_PATTERN`'s validate-before-filesystem treatment verbatim (T-11-29), proved by an exploding-builder test.

- **The 11-07 handoff defect is closed — and it was exactly as bad as advertised.** All four question-hop re-puts (`structural_hint.py` × 3, `date_format.py` × 1) now carry `group_id`/`sheet` onto the fresh entry. Without this, a member that answered a structural or date question reached Confirm with `group_id is None` and silently vanished from "Download All" — precisely the members that needed a question. Pinned four ways, including end-to-end: a two-member group whose BOTH members answer a date question downloads as a complete archive, the defect's consequence proved in the zip's own bytes.

- **SHEET-03 is proved across a group.** Each member's `export.csv` inside the archive carries its OWN `__source_sheet` value (`Week 1` rows say `Week 1`, never a sibling's name) — the plan's manual verification, automated end to end through `TestClient`.

## Task Commits

Each task committed atomically (TDD: test then feat).

1. **Task 1: build_group_archive — a zip a worksheet title cannot escape**
   - RED: `21d54aa` · GREEN: `8abf18a`
2. **Task 2: confirm records the run into the group; the archive route serves it**
   - RED: `78a579b` · GREEN: `5abadc5`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug, mandated handoff] `structural_hint.py` and `date_format.py` modified beyond the plan's `files_modified` list**

- **Found during:** Task 2 (ordered by the 11-07 SUMMARY's "Handoff to 11-08 — READ THIS" and the orchestrator's inherited-defect instruction)
- **Issue:** The four re-puts in the two question-resolve routes drop `group_id` (and, on three of them, `sheet`), so a group member that answers a question arrives at Confirm with `group_id is None` and `groups.record_run` never fires for it — "Download All" would silently lose exactly the members that needed a question. 11-07 could not fix it (its own acceptance criteria required those files' diffs to be empty, as Option A's proof).
- **Fix:** `sheet=entry.sheet, group_id=entry.group_id` added to all four re-put `UploadEntry(...)` constructions. Nothing else in either route changed.
- **Files:** `src/assayingest/api/routes/structural_hint.py`, `src/assayingest/api/routes/date_format.py`
- **Verification:** `test_a_member_that_answered_a_date_question_still_appears_in_the_archive` (end-to-end, through the archive's bytes), plus one registry-level pin per structural-hint re-put (still-ambiguous, resolved-to-mapping, resolved-to-date-question).
- **Commit:** `5abadc5`

**2. [Rule 1 — Bug in the plan's fixture assumption] The two-question workbook's hint never resolves to a mapping**

- **Found during:** Task 2 (RED test `test_group_membership_survives_a_hint_resolved_to_a_mapping` failed for the wrong reason after the fix)
- **Issue:** The prose workbook (`Alpha`/`Beta`, one prose row) with `header_row_index: 0` still returns `structural_question` — a header hint leaves a one-row prose sheet shapeless. The existing 11-07 test that posts this exact hint never asserts the response `kind`, so nothing had ever established it resolves. The resolved-mapping hop could not be pinned through that fixture.
- **Fix:** The pin was rewritten to the deterministic `test_hint_and_export.py` idiom: an ambiguous-decimal CSV seeded directly at the registry with `group_id`/`sheet`, whose `decimal_separator` hint DETERMINISTICALLY resolves to a mapping. The fresh entry provably carries membership forward.
- **Files:** `tests/api/test_group_export.py`
- **Verification:** `test_group_membership_survives_a_hint_resolved_to_a_mapping` (passes; the fixture's limitation is documented in its docstring)
- **Commit:** `5abadc5`

**Total deviations:** 2 auto-fixed (both bugs; the first explicitly mandated by the 11-07 handoff). **Impact:** correctness-only — the first IS the plan's purpose being made whole; the second swaps a fixture that could not exercise the branch under test for one that can.

## Threat Flags

None new. All five `mitigate` dispositions from the plan's threat register are applied:

| Threat | Applied |
|---|---|
| T-11-28 (zip-slip via a worksheet title) | Allowlist `[A-Za-z0-9._ -]` + dot-run collapse + `sheet_<index>` fallback + collision suffixing; pinned by the `../../evil` test |
| T-11-29 (traversal via `group_id`) | uuid4 regex BEFORE any lookup/path join/build, `_RUN_ID_PATTERN`'s discipline verbatim; exploding-builder test proves the filesystem is never reached |
| T-11-30 (unauthenticated archive download) | `Depends(require_user)` with D-10-13's comment; 401 pinned |
| T-11-31 (the archive bypassing a member's gate) | Lookup-only over recorded runs; grep-asserted zero gate lines changed in `confirm.py`; 409 + still-422 tests |
| T-11-SC (package installs) | Zero packages installed (`zipfile`, `tempfile` are stdlib) |

T-11-32 (an archive served for someone else's group) stays **accepted** as the plan disposes: group ids are unguessable server-minted uuid4s and the route requires a verified user — the same posture the per-run export route takes. **Noted for a future phase:** per-user ownership of exports would be a phase-wide change to `GET /api/export/{run_id}/{fmt}` too (which today carries no auth gate at all), not something to widen here.

## Known Stubs

None. No placeholder values, no unwired data path, no TODO.

## Issues Encountered

None beyond the two deviations above.

## User Setup Required

None.

## Verification

- `uv run pytest tests/ -q` → **1121 passed, 4 skipped** (+19; every existing confirm/export test unmodified — `git diff --name-only b69d0c0..HEAD -- tests/` lists only the two new files).
- `uv run pytest tests/api/test_group_export.py tests/api/test_hint_and_export.py tests/api/test_confirm_gate.py tests/api/test_confirm_vendor_required.py -q` → 32 passed.
- `grep -c zipfile src/assayingest/export/archive.py` → 3; no third-party archive dependency (`pyproject.toml`/`uv.lock` untouched).
- `grep -c require_user src/assayingest/api/routes/export.py` → 3 (the new route is gated).
- `git diff -U0 src/assayingest/api/routes/confirm.py | grep -cE 'NotReadyError|is_ready|unclear'` → **0** (the gate is untouched).
- **The plan's manual check, automated:** zephyr's 3 sheets ingested, each confirmed on its own gate, the archive downloaded — it opens with three directories, four files each, and each `export.csv` names its own sheet in `__source_sheet` (`test_a_confirmed_group_downloads_as_one_zip_with_each_sheets_own_provenance`).

## TDD Gate Compliance

- **RED gates:** `21d54aa` (Task 1 — failed at collection: `assayingest.export.archive` did not exist), `78a579b` (Task 2 — all 10 tests failed: no route, no `record_run` call, membership lost on hops).
- **GREEN gates:** `8abf18a`, `5abadc5` — each after its RED.
- **REFACTOR:** not needed.

## Next Phase Readiness

- **11-09/11-10** (the Review group tabs): the "Download All" bar has its contract — `GET /api/export/group/{group_id}/archive` returns `application/zip` when every member has confirmed-with-export, 409 with a human-readable count otherwise, 401 signed out. `SheetGroupResponse.group_id` is the handle the frontend already receives.
- A member confirmed with `export: false` blocks the archive like an unconfirmed one (no run directory exists to zip) — the group UI should confirm members with `export: true`, as the existing single-dataset flow already does.

---
*Phase: 11-multi-sheet-ingest*
*Completed: 2026-07-13*

## Self-Check: PASSED

- All 3 created files and 4 modified files exist on disk, plus this SUMMARY.
- All 4 task commits present in `git log`: `21d54aa`, `78a579b` (RED), `8abf18a`, `5abadc5` (GREEN).
- No file deletions in any of this plan's commits (`git diff --diff-filter=D` over the range is empty).
- Every acceptance criterion from both tasks re-run and passes (zip-slip, collision, `zipfile` grep, `require_user` grep, the zero-hit confirm-gate grep, the plan's four-file verify command).
- Full suite green: 1121 passed, 4 skipped, with every pre-existing test file unmodified.
