---
phase: 11-multi-sheet-ingest
plan: "07"
subsystem: api
tags: [fastapi, sheet-question, run-group, multi-sheet, wire-arms, tdd, fail-closed, no-merge]
status: complete

# Dependency graph
requires:
  - phase: 11-04
    provides: "describe_workbook(path, schemas, *, store, client, rank_fn) -> the whole manifest, above parse(); SheetManifestEntry + SchemaProposal"
  - phase: 11-05
    provides: "Stage 3 (Claude ranks the Schemas) behind the client/rank_fn seam — neutralized in this plan's test harness so no test can dial out"
  - phase: 11-06
    provides: "UploadEntry.sheet + the full-context structural-hint resolve — every group member re-enters that route with an explicit retained sheet"
  - phase: 10-frictionless-correct-ingest
    provides: "The 4 existing response arms; require_user (D-10-13); the date question (D-10-07); recall_vendor; the pending_uploads write-through"
provides:
  - "wire.py: SheetSchemaProposalOut, SheetOut, SheetQuestionResponse (+ from_manifest), SheetSelectionIn, SheetResolveRequest, SheetMemberOut, SheetGroupResponse — the 5th and 6th response arms"
  - "state.py: UploadGroup + GroupRegistry (memory-only) + module singleton `groups`; UploadEntry.sheet_manifest (the 4th retention shape) and UploadEntry.group_id"
  - "POST /api/upload: the multi-sheet branch — >1 real worksheet AND no explicit sheet= => kind:'sheet_question', regardless of whether a Schema was chosen (D-11-16). schema_name is now optional for a multi-sheet workbook."
  - "POST /api/sheets/resolve: N selected sheets => N INDEPENDENT datasets, each an ordinary upload_token with its own arm, its own amber gate, its own confirm"
affects:
  - "11-08 (records each member's run_id into the group at confirm — see Handoff below, which names a two-line change it MUST make)"
  - "11-09 (the SheetQuestionPanel renders SheetOut: coverage, tie, skip, status badges)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "The run group as a group id over N ORDINARY tokens (Option A): the feature costs the rest of the codebase literally nothing — service.confirm, service.export, _is_review_ready, the pending_uploads round-trip, GET /api/export/{run_id}/{fmt}, MappingResponse and date_format.py are all byte-for-byte untouched"
    - "The recursive member arm: SheetMemberOut.response is one of the four EXISTING arms, so a member that still has a question reuses its existing panel verbatim — the only shape honest about a member that is not done"
    - "Validate-before-filesystem, all-or-nothing: every untrusted selection is checked against the SERVER-RETAINED manifest before a single byte is copied, so a client sheet_name can never reach parse() and surface as a 500"
    - "Per-member temp copy: each question-bearing member owns its own file, so every existing unlink (structural_hint's, the registry's eviction) stays correct with ZERO changes — refcounting a shared path was rejected for adding a second lifecycle owner"
    - "Deferred-refusal: the ONE 422 D-11-16 makes conditional is deferred until the file is on disk; every other 422/404 keeps its exact position and status"

key-files:
  created:
    - src/assayingest/api/routes/sheets.py
    - tests/api/test_sheets_route.py
  modified:
    - src/assayingest/api/wire.py
    - src/assayingest/api/state.py
    - src/assayingest/api/routes/upload.py
    - src/assayingest/api/app.py
    - tests/api/test_state.py

key-decisions:
  - "A TIE IS NEVER BROKEN BY THE UPLOAD DROPDOWN EITHER. The plan's pre-selection precedence (scorer's proposal -> the human's Upload pick -> None) is implemented with the tie as a HARD short-circuit above the middle rung. A default carried over from a dropdown the human set before the file was even parsed is not evidence, and letting it settle a genuine tie would be precisely the silent guess D-11-06 exists to forbid. The tie pre-fills nothing and the human chooses."
  - "`proposals == []` IS the propose-skip signal, never `proposed_schema is None`. The two are deliberately separated: an empty proposal list means the scorer has no opinion (the sheet arrives unticked, D-11-06), while `proposed_schema` only pre-fills the Select — so the human's own Upload pick can fill the dropdown on a skip-proposed sheet WITHOUT the tool ticking it for them. One signal for 'should this be ingested', a different one for 'with what'."
  - "_is_tie compares (is_profile, score), not score alone. A learned-profile hit outranks every crosswalk match whatever its raw coverage (D-11-05), so a profile hit at 4/7 above a crosswalk hit at 4/7 is a WINNER, not a tie. Comparing scores alone would have reported the phase's own learning loop as an ambiguity."
  - "`group_id` and `sheet` ride on the member ENTRY, not only in the group's token map. A member that answers a structural or date question is re-put under a FRESH token, so the group's original map goes stale while the entry's own membership survives the hop. (The re-put itself does not yet carry them forward — see Handoff to 11-08.)"
  - "The sheet manifest is retained but NOT persisted. It is derived, purely and cheaply, from a per-process temp path that is meaningless to any other process — so an entry holding one was never persistable anyway (_is_review_ready). There is nothing a restart could honestly restore and nothing it would destroy: the curator has not reviewed anything yet."
  - "`_asks_which_sheets` counts `list_worksheets`, never `wb.sheetnames`: a chartsheet is excluded by construction (D-17), so a workbook of one data sheet plus a chart stays a SINGLE-sheet workbook here — exactly as it is to parse(). Counting sheetnames would ask the human to choose between a table and a picture."

patterns-established:
  - "Structural no-outbound-call guard: the harness DI-overrides get_anthropic_client to None AND autouse-explodes service.propose_schema_ranking, so 'this file makes zero outbound calls' is enforced by the suite rather than promised in prose — and holds whatever ANTHROPIC_API_KEY says and whatever the merge order of 11-05 and 11-07 was"
  - "Exploding-mapper proof, extended to the route: a fully-covered member resolving through an exploding propose_mapping IS the proof that the crosswalk carried it and Claude was called zero times"

requirements-completed: [SHEET-01, SHEET-04, SHEET-05]

coverage:
  - deliverable: "A multi-sheet workbook ALWAYS returns kind:'sheet_question' — regardless of whether a Schema was chosen — with every worksheet, its headers, rows, signature, status and ranked proposals with visible coverage"
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_zephyr_with_a_schema_chosen_still_asks_which_sheets"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_the_question_fires_even_though_rank_sheets_is_confident_here"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_a_multi_sheet_workbook_with_no_schema_at_all_asks_instead_of_422"
        status: pass
      - kind: unit
        ref: "tests/api/test_sheets_route.py#test_a_proposal_shows_which_field_matched_which_header"
        status: pass
    human_judgment: false
  - deliverable: "meridian's LEGEND — silently discarded by parse() today — appears in the manifest, marked and scored"
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_meridian_shows_the_legend_sheet_parse_silently_discards_today"
        status: pass
      - kind: command
        ref: "describe_workbook(meridian) -> DATA status=ok 7/7; LEGEND status=header_uncertain 1/7 (both present)"
        status: pass
    human_judgment: false
  - deliverable: "The single-sheet path is untouched: a CSV, a one-sheet workbook, or any upload with an explicit sheet= returns exactly what it returns today"
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_a_csv_upload_still_returns_a_mapping"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_an_explicit_sheet_bypasses_the_question_entirely"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_a_csv_with_no_target_still_422s_exactly_as_today"
        status: pass
      - kind: command
        ref: "git diff --name-only -- tests/api/test_upload.py tests/api/test_money_shot.py tests/api/test_upload_schema_target.py -> EMPTY (all pass unmodified)"
        status: pass
    human_judgment: false
  - deliverable: "N selected sheets => N INDEPENDENT datasets, each with its own arm, its own amber gate, its own confirm. Nothing merged, ever."
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_selecting_every_sheet_yields_n_independent_datasets"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_each_member_confirms_on_its_own_gate_and_mints_its_own_run"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_confirming_one_member_leaves_the_others_pending"
        status: pass
      - kind: unit
        ref: "tests/api/test_sheets_route.py#test_the_group_response_has_no_merged_table_and_no_group_level_gate"
        status: pass
      - kind: command
        ref: "git diff --name-only -- src/assayingest/service.py api/routes/confirm.py api/routes/date_format.py api/routes/export.py -> EMPTY (Option A changes none of them)"
        status: pass
    human_judgment: false
  - deliverable: "The amber gate is never weakened by group membership — there is no group-level bypass, because there is no group-level gate"
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_a_member_with_an_amber_field_still_422s_at_confirm"
        status: pass
    human_judgment: false
  - deliverable: "A selected sheet that fails a structural gate raises ITS OWN question inside its member — never dropped (SHEET-04)"
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_a_gate_failing_sheet_raises_its_own_question_inside_its_member"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_one_group_carries_members_on_different_arms_at_once"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_a_members_genuinely_ambiguous_date_raises_the_date_question_for_it_alone"
        status: pass
    human_judgment: false
  - deliverable: "Different sheets may legitimately use different Schemas (SHEET-05)"
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_different_sheets_may_use_different_schemas"
        status: pass
    human_judgment: false
  - deliverable: "Each question-bearing member owns its own temp file, so resolving one member's hint cannot delete another member's file (T-11-24)"
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_two_question_bearing_members_own_distinct_temp_files"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_resolving_one_members_hint_leaves_the_other_members_file_intact"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_the_original_workbook_leaves_disk_once_every_member_is_parsed"
        status: pass
    human_judgment: false
  - deliverable: "Untrusted input fails closed: an unknown sheet_name is 422 (never a 500), an unknown schema_name 404, an empty selection 422, an anonymous resolve 401"
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_a_sheet_name_not_in_the_manifest_is_422_naming_the_consequence"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_an_unknown_schema_name_is_404"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_an_empty_selections_list_is_422_fail_closed"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_an_anonymous_sheets_resolve_is_401"
        status: pass
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_a_rejected_selection_never_touches_the_filesystem"
        status: pass
    human_judgment: false
  - deliverable: "Headers are NOT redacted under headers_only — a header is not a cell value (D-10-05)"
    verification:
      - kind: integration
        ref: "tests/api/test_sheets_route.py#test_headers_still_cross_the_wire_under_headers_only"
        status: pass
    human_judgment: false

# Metrics
duration: 25min
completed: 2026-07-13
tasks: 3
files: 7
commits: 5
---

# Phase 11 Plan 07: The Sheet Question and the Run Group Summary

**A multi-sheet workbook now asks WHICH SHEETS — always, with the coverage behind every Schema proposal shown — and the human's answer becomes N INDEPENDENT datasets, each with its own Schema, its own question, its own amber gate and its own confirm. Nothing is merged, anywhere.**

## Performance

- **Duration:** 25 min (12:21 → 12:46)
- **Tasks:** 3 (all TDD, RED then GREEN)
- **Files:** 7 (2 created, 5 modified)
- **Suite:** 1102 passed, 4 skipped (was 1020 before this plan; **+82 tests, zero existing assertions weakened, zero existing test files modified**)

## Accomplishments

- **The two silent guesses are dead.** `_resolve_sheet` used to rank the worksheets, take the winner, and discard every other sheet without a word — and the human had to pick a Schema from a dropdown *before* upload, with the file unparsed and no header yet seen. Now the file is described first, every sheet is shown with its evidence, and the human confirms. The manual check makes it concrete:

  | meridian sheet | before | now |
  |---|---|---|
  | `DATA` | parsed (the ranked winner) | shown, `ok`, proposal **assay-potency 7/7** |
  | `LEGEND` | **silently discarded** | shown, `header_uncertain`, proposal **assay-potency 1/7** |

  D-11-24 in action: LEGEND is *not* suppressed and *not* unticked by a threshold that does not exist. The **coverage number is the control** — "1/7" beside "7/7" is what tells the curator it is a legend.

- **The trigger is D-11-16, and that was the whole ballgame.** `>1 worksheet` AND no explicit `sheet=` — **regardless of whether a Schema was chosen**. The browser *always* sends `schema_name`, so gating on "no Schema" (the original D-11-01 wording) would have shipped the feature dead: unreachable from the UI. `schema_name` is now genuinely optional for a multi-sheet workbook, and a Schema picked in the dropdown only *pre-selects*.

- **N sheets, N independent datasets — and the rest of the codebase paid nothing for it.** The run group is a group id owning N **ordinary** `upload_token`s (D-11-20, Option A). `service.confirm`, `service.export`, `_is_review_ready`, the `pending_uploads` round-trip, `GET /api/export/{run_id}/{fmt}`, `MappingResponse`, `date_format.py`, `structural_hint.py` and `confirm.py` are **byte-for-byte untouched** — verified by `git diff --name-only`, which is empty for every one of them.

- **SHEET-04 came for free, exactly as D-11-21 predicted.** Each selected sheet is re-parsed with an explicit `sheet=`, which short-circuits ranking and runs *that sheet's* own full gate chain. A gate-failing sheet the human insists on raises its **own** question in its **own** member. One group now genuinely carries members on different arms at once: meridian's `DATA` maps while `LEGEND` asks a structural question.

- **The confirm gate is per dataset, and it bites.** Zephyr proved it with no contrivance at all: its `Units` column holds `uM` (an ASCII u), which is not one of the Schema's allowed values (`µM`, `nM`, `%`). Six of seven fields map cleanly, the seventh goes amber, and Confirm **422s**. There is no group-level gate for anything to bypass — `SheetGroupResponse` has no aggregate `ready` field at all, and a test pins its exact field set so nobody can add one by accident.

- **No test in this file can ever dial out.** Plan 11-05 makes a zero-coverage sheet escalate to Claude whenever a client exists, and this harness sets `ANTHROPIC_API_KEY=test-key`. Two structural guards close that: `get_anthropic_client` is DI-overridden to `None`, and an autouse fixture **explodes** on `service.propose_schema_ranking`. Offline and deterministic regardless of the merge order of 11-05 and 11-07.

## Task Commits

Each task committed atomically (TDD: test then feat).

1. **Task 1: the two new wire arms + the run-group registry**
   - RED: `0b5a0e3` · GREEN: `f9b3da8`
2. **Task 2: /api/upload asks the sheet question, always**
   - GREEN: `f8cef75` (its RED rode in `0b5a0e3` — one test module, one RED commit)
3. **Task 3: POST /api/sheets/resolve — N independent datasets**
   - RED: `6bde180` · GREEN: `4256677`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] The plan's meridian LEGEND assertion was stale, and writing it would have pinned a falsehood**

- **Found during:** Task 2
- **Issue:** The plan orders a test asserting LEGEND arrives with `proposed_schema is None` (propose skip), "never force-mapped". It does not, and must not: **D-11-24 — a decision locked during execution of 11-04, *after* this plan was written — establishes that LEGEND honestly scores 1/7**, because its `CMP` column is a real seeded starter alias of `compound_id`. The builder's ruling was explicit: *leave it*; the untick rule stays literal (**exactly** zero coverage), and no threshold is introduced then or ever. Coding the plan's assertion would have required either pinning a falsehood or inventing the suppression rule the locked decision forbids.
- **Fix:** LEGEND is tested **honestly** — present, `header_uncertain`, proposal `assay-potency` at **1/7**, with the matched pair (`compound_id ← 'CMP'`) shown so the human can see *why* it is only 1/7. The genuine propose-skip contract is pinned where it is genuinely true: orion's `Notes`, which resolves no headers at all and therefore yields no proposal.
- **Files:** `tests/api/test_sheets_route.py`
- **Verification:** `test_meridian_shows_the_legend_sheet_parse_silently_discards_today`, `test_orion_notes_is_described_and_marked_never_dropped`, `test_zero_coverage_proposes_skip_and_names_no_schema`
- **Commit:** `0b5a0e3`

**2. [Rule 1 — Bug] meridian's DATA does not raise a date question — a declared format leaves nothing to ask about**

- **Found during:** Task 3
- **Issue:** The plan's Task-3 behaviour implies the date-question member arm is exercised by the in-tree fixtures. It is not, and the reason is a *correct* one worth recording: meridian's `DATA` dates are `01-01-2025`-style (genuinely order-ambiguous *as raw values*), but the `assay-potency` Schema **declares** `date_format: "%Y-%m-%d"`. A declared format covers the column, so there is no *ambiguity* left to ask about — the non-conforming values are a **violation**, and the field goes amber (fail-closed) rather than being coerced into whichever reading happens to parse. Asserting `date_question` here would have pinned behaviour the tool must not have.
- **Fix:** Pinned what is actually true (`test_a_declared_date_format_is_enforced_per_member_not_silently_coerced` — the field goes amber, the member is not ready), **and** built a purpose-made fixture to exercise the date-question member arm honestly: a governed Schema whose date field declares **no** format, over a synthetic two-sheet workbook whose date column is genuinely ambiguous. Both members then raise their own date question, and answering one completes that member alone — which is D-11-09's "each sheet resolves its own order for itself" proved rather than asserted.
- **Files:** `tests/api/test_sheets_route.py`
- **Verification:** `test_a_members_genuinely_ambiguous_date_raises_the_date_question_for_it_alone`, `test_answering_one_members_date_question_completes_that_member_only`
- **Commit:** `6bde180`, `4256677`

**3. [Rule 3 — Blocking] The "no target" 422 had to be DEFERRED, not branched**

- **Found during:** Task 2
- **Issue:** The plan says `_resolve_field_set` "gains ONE branch: a missing `schema_name` on a multi-sheet workbook must NOT 422". It cannot: `_resolve_field_set` runs at the very top of the route, **before the upload's bytes are anywhere** — so at that moment nothing can know whether this file *is* a multi-sheet workbook. The branch the plan asks for has no information to branch on.
- **Fix:** The refusal is **deferred** rather than branched (`require_target=False` returns `None` instead of raising), and re-raised — identical status, identical message — the moment the route learns the upload is *not* a multi-sheet workbook. Every **other** refusal keeps its exact position and status: an unknown Schema name is still a 404 before anything is written, malformed `field_set` JSON still a 422, the map-file path's own no-target 422 still fires before the extension check. A target that was *supplied and is wrong* is always an error, whatever the file turns out to be.
- **Files:** `src/assayingest/api/routes/upload.py`
- **Verification:** `test_a_csv_with_no_target_still_422s_exactly_as_today`; and `tests/api/test_upload.py`, `test_money_shot.py`, `test_upload_schema_target.py` all pass **unmodified** (the 400/413/422 ordering tests each supply a target, so no ordering they pin is disturbed).
- **Commit:** `f8cef75`

**4. [Rule 2 — Missing critical] A rejected selection must not leak the retained workbook**

- **Found during:** Task 3
- **Issue:** The plan orders validate-before-filesystem (T-11-22) but does not say what becomes of the **retained** temp file when validation rejects the request. The entry has already been `pop`ped by then, so the rejection path holds the **last remaining reference** to a file full of uploaded cell values — returning the 422 and walking away would leak it to disk with nothing left to clean it up (the exact WR-01 hazard the registry's own eviction-unlink exists to prevent).
- **Fix:** Every rejection branch unlinks the retained workbook before raising, mirroring `structural_hint.py`'s unlink-on-every-error-branch discipline. Validation is also **all-or-nothing**: one bad selection refuses the whole request, because a partially-honoured resolve would ingest some sheets and silently swallow the rest — which is the very "discard without a word" behaviour this phase exists to kill.
- **Files:** `src/assayingest/api/routes/sheets.py`
- **Verification:** `test_a_rejected_selection_never_touches_the_filesystem`
- **Commit:** `4256677`

**Total deviations:** 4 auto-fixed (2 bugs, 1 blocking, 1 missing-critical). **Impact:** correctness-only, no scope creep. Two are the plan's own fixture claims corrected against reality — one of them against a decision (D-11-24) that was *locked after the plan was written*, which is worth flagging to the planner as a recurring pattern: 11-04's summary reported the identical stale-LEGEND claim.

## Threat Flags

None new. All five `mitigate` dispositions from the plan's threat register are applied:

| Threat | Applied |
|---|---|
| T-11-22 (client `sheet_name` → `parse()`) | Every selection validated against the server-retained manifest **before** any filesystem access; 422 naming the consequence, never a `ValueError` → 500 |
| T-11-23 (unauthenticated drive-to-completion) | `Depends(require_user)` on `/api/sheets/resolve`, with D-10-13's comment verbatim |
| T-11-24 (one member's unlink kills another's file) | Per-member `shutil.copyfile`; distinct paths pinned by test |
| T-11-25 (client-supplied token/group id) | `group_id` and every member token are server-minted `uuid4` |
| T-11-SC (package installs) | Zero packages installed (`shutil`, `tempfile` are stdlib) |

## Known Stubs / Handoff to 11-08 — READ THIS

**`group_id` does not yet survive a member's question-resolve, and 11-08 must close it.**

A member's membership rides on its `UploadEntry` (`group_id` + `sheet`), deliberately — because a member that answers a structural or date question is **re-put under a fresh token**, so the group's original `members` map goes stale at that moment. But the re-puts themselves, in `structural_hint.py` and `date_format.py`, do **not** carry `group_id`/`sheet` forward: they were written before this field existed. A member that goes through a question therefore arrives at Confirm with `group_id is None`, and 11-08's `groups.record_run(...)` hook would silently not fire for it.

This is **not** fixed here, on purpose: this plan's acceptance criteria require `git diff` on `date_format.py` to be **empty** (it is Option A's proof), and `structural_hint.py` is outside `files_modified`. The fix belongs with the plan that consumes it.

**11-08 must add `group_id=entry.group_id, sheet=entry.sheet` to the re-put `UploadEntry(...)` in:**
- `src/assayingest/api/routes/structural_hint.py` — the still-ambiguous re-put, the date-question re-put, **and** the resolved-mapping re-put (all three)
- `src/assayingest/api/routes/date_format.py` — the resolved-mapping re-put

Without it, the "Download All" archive would be missing exactly those members that needed a question — which is the least forgivable set to lose.

Nothing else is stubbed: no placeholder values, no unwired data path, no TODO.

## Issues Encountered

None beyond the four deviations above.

## User Setup Required

None.

## Verification

- `uv run pytest tests/ -q` → **1102 passed, 4 skipped** (was 1020; +82 tests).
- `git diff --name-only -- src/assayingest/service.py api/routes/confirm.py api/routes/date_format.py api/routes/structural_hint.py api/routes/export.py` → **EMPTY**. Option A changes none of them, which is the whole point of D-11-20.
- `git diff --name-only -- tests/api/test_upload.py test_money_shot.py test_upload_schema_target.py` → **EMPTY**. The no-regression suite passes **unmodified**.
- `grep -c require_user src/assayingest/api/routes/sheets.py` → 3. `grep -c copyfile` → 1.
- `grep -c 'class GroupRegistry' src/assayingest/api/state.py` → 1; the `_is_review_ready` **body** has zero changed lines (its only diff hits are prose in new docstrings).
- No merge path exists anywhere in the new or changed source — grepped for `merge`/`combin`/`concat`/`aggregate`; the sole hit is pre-existing prose about `OrderedDict` in `state.py`'s module docstring.
- **Manual (plan's own check):** `describe_workbook(meridian_cro_codes.xlsx)` → `DATA status=ok 7/7` **and** `LEGEND status=header_uncertain 1/7`. Today `parse()` discards LEGEND silently.

## TDD Gate Compliance

- **RED gates:** `0b5a0e3` (Tasks 1+2 — one test module), `6bde180` (Task 3). Each verified failing before implementation: `0b5a0e3` failed at **collection** (the wire arms and `GroupRegistry` did not exist), then 7 behavioural failures against the real route; `6bde180` produced 17 failures (the resolve route did not exist).
- **GREEN gates:** `f9b3da8`, `f8cef75`, `4256677` — each after its RED.
- **REFACTOR:** not needed.

## Next Phase Readiness

- **11-09** (the `SheetQuestionPanel`) has its complete contract: `SheetOut` carries `sheet_name`, `row_count`, `headers`, `column_signature`, `status` (a 4-value `Literal`), `proposals` (ranked, each with `matched` field←header pairs, `uncovered`, `matched_count`, `total_fields`, `source`, `reason`), `proposed_schema` and `tie`. Per D-11-24, the panel must render the **coverage count large and adjacent to the checkbox** — it is the control, not decoration.
- **11-08** (group export) has `GroupRegistry.record_run` and `UploadEntry.group_id`/`.sheet` waiting — **and the two-line handoff above that it must not skip.**

---
*Phase: 11-multi-sheet-ingest*
*Completed: 2026-07-13*

## Self-Check: PASSED

- All 7 key files exist on disk, plus this SUMMARY.
- All 5 task commits present in `git log`: `0b5a0e3`, `f9b3da8`, `f8cef75`, `6bde180`, `4256677`.
- No file deletions in any of this plan's commits.
- Every acceptance criterion from all three tasks re-run and passes.
- Full suite green: 1102 passed, 4 skipped, with the no-regression suite unmodified.
