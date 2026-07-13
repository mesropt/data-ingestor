---
phase: quick-260712-qgc
verified: 2026-07-12T00:00:00Z
status: passed
score: 8/8 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Quick Task 260712-qgc: Fix the Confirm Dead-End — Verification Report

**Task Goal:** Fix the Confirm dead-end — an ambiguous date column whose field declares a `date_format` that cannot parse the data was trusted blindly, so the field stayed amber forever and Confirm returned 422 with no way out from the Review screen.

**Verified:** 2026-07-12
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from PLAN.md frontmatter `must_haves.truths`)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | AMBIGUOUS column whose declared `date_format` CANNOT parse its values raises the conflict, puts NO format into `formats` | VERIFIED | `service.py:1313-1337`; `test_ambiguous_declared_format_refuted_by_the_data_is_not_trusted_and_raises_a_conflict` passes; independently reproduced against the real `helixbio_export.csv` + `presets/assay-potency.yaml` in a throwaway python session — `formats: {}`, `has_conflicts: True` |
| 2 | Refuted-and-unanswered column records `contradictions[field]` = one refuting raw value → honest `_contradiction_objection_note`, not the generic note | VERIFIED | `service.py:1321-1326` sets `contradictions[name]` only when `declared is not None` and control reaches past the `answer is not None` early-return; `test_ambiguous_refuted_declaration_amber_note_is_honest_not_generic` asserts `"%Y-%m-%d"`, `"03/11/2025"`, `"Schemas page"` all present in the note |
| 3 | Human answers the order for a refuted column → `confirm(date_answers=...)` PASSES the gate (no 422), cell is ISO-8601 | VERIFIED | `test_answered_refuted_column_passes_confirm_and_assembles_iso`; independently reproduced — `result.tidy.records[0]["assay_date"] == "2025-11-03"` |
| 4 | Human's answer overrides the stale declaration for THIS run only — nothing written back to Schema/Field | VERIFIED | `formats`/`resolved_answers` are local dicts built fresh per call in `resolve_date_formats`; `target_field`/`field_set` are never mutated (frozen `Field`/`FieldSet`, no `replace()` call on them anywhere in `service.py`'s date path); confirmed by code inspection of `_resolve_one_column` and `resolve_date_formats` |
| 5 | AMBIGUOUS column whose declared `date_format` DOES parse every value is still trusted, raises no question, records no contradiction, confirms clean | VERIFIED | `test_ambiguous_with_a_declared_format_trusts_the_declaration_and_raises_no_question` (unchanged assertions, docstring extended) + new companion `..._confirm_gate` test, both pass |
| 6 | `date_order` exposes the all-values-parse check under the public name `parses_all`; no second strptime loop hand-rolled in `service.py` | VERIFIED | `date_order.py:177` defines public `parses_all`; `grep -rn "_all_parse"` returns nothing repo-wide; `grep -n "strptime" src/assayingest/service.py` returns only a docstring comment, no executable loop |
| 7 | Every other decision-table row (EXCEL_SERIAL, INVALID/NON_DATE, DAY_FIRST/MONTH_FIRST/ISO agrees-or-contradicts) behaves exactly as before | VERIFIED | Their existing tests in `test_date_escalation.py` (`test_excel_serial_column_resolves_to_the_marker_regardless_of_declaration`, `test_non_date_column_mapped_to_a_date_field_yields_no_resolution...`, `test_unambiguous_evidence_contradicting_a_declared_format_yields_a_contradiction_not_an_override`, etc.) all still pass unmodified; full suite green |
| 8 | Backend suite green, no test deleted/weakened: >= 824 passed, 4 skipped | VERIFIED | `uv run pytest -q` → **832 passed, 4 skipped** (824 baseline + 8 new tests, confirmed via `git diff ... | grep -c "^+def test_"` = 8, and `grep "^-def test_"` = 0 deletions) |

**Score:** 8/8 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/assayingest/parsing/structure/date_order.py` | Public `parses_all` predicate | VERIFIED | Present at line 177, documented, 3 internal call sites (`_classify_iso`, `_resolved_dm_result` x2) updated to use it; blank-handling confirmed by `test_parses_all_ignores_blank_values_like_classify_column_does` |
| `src/assayingest/service.py` | Corrected AMBIGUOUS+declared branch in `_resolve_one_column`; docstring decision table updated | VERIFIED | Lines 1251-1255 (docstring) and 1313-1337 (implementation) match exactly |
| `tests/test_date_escalation.py` | New RED→GREEN tests for dead-end, escape hatch, earned-trust confirm-gate | VERIFIED | 7 new test functions present and passing, existing tests untouched except one docstring extension |
| `tests/test_date_order.py` | New tests pinning `parses_all` | VERIFIED | 3 new tests (`test_parses_all_is_false...`, `test_parses_all_is_true...`, `test_parses_all_ignores_blank_values...`) present and passing |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `date_order.parses_all(values, declared)` | AMBIGUOUS+declared branch of `_resolve_one_column` | direct call, line 1314 | WIRED | Gates trust; refuted declarations fall through to the existing answer/conflict path (verified by code read + test D/A) |
| refuted+unanswered `contradictions[name]` | `validate(date_contradictions=...)` → `_contradiction_objection_note` | `service.py` → `validator.py:_validate_mapping` line 128-129 | WIRED | Confirmed the note is additive with `canonical.assemble()`'s own unrelated generic flag (see deviation analysis below) but the honest note is always present |
| `confirm(date_answers={...})` | `resolve_date_formats(answers=...)` → `format_for_order` → `formats` → both `validate()` and `canonical.assemble()` | `service.py:confirm()` (unchanged plumbing, line 360+) | WIRED | End-to-end test + independent python repro both confirm ISO-8601 output and gate passing |

### Focus Area 1 — The Load-Bearing Correctness Property

**Claim to verify:** a contradiction must be recorded ONLY on the unanswered branch of `_resolve_one_column`. If it were also recorded when the human HAS answered, `validate()` would re-flag the field amber and the dead end would survive.

**Verified directly in source** (`src/assayingest/service.py:1313-1337`):

```python
if column.order == DateOrder.AMBIGUOUS:
    if declared is not None and date_order.parses_all(values, declared):
        formats[name] = declared
        return
    answer = answers.get(name)
    if answer is not None:
        formats[name] = date_order.format_for_order(column, answer)
        return                                    # <-- returns BEFORE the contradictions line
    if declared is not None:
        contradictions[name] = column.example_values[0] if column.example_values else ""
    conflicts.append(...)
    return
```

The `answer is not None` branch always `return`s before control can reach the `contradictions[name] = ...` line. There is no code path where both an answer is supplied AND a contradiction is recorded. This is confirmed by `test_answered_refuted_column_resolves_with_no_lingering_contradiction`, which independently asserts `resolution.contradictions == {}` after answering, and is not merely inferred from the "happy path" `confirm()` test. **Property holds — VERIFIED, not merely present.**

### Focus Area 2 — The Executor's Documented Deviation

**Claim:** the loosened assertion (dropping "no generic conversion note at all") is legitimate because `canonical.assemble()`'s own D-13 fallback (unchanged, out of scope) additively appends its own generic note alongside the contradiction note, per `validator.py`'s pre-existing additive-only design.

**Verified by tracing the actual code path**, not taking the SUMMARY's word for it:

1. `validator.py:_validate_mapping` (lines 119-136) builds `notes: list[str]`, appends `_contradiction_objection_note(...)` when `date_contradiction is not None`, appends `_conversion_objection_note(...)` when `mapping.target_field in canonical_flagged` — both conditions independently checked, joined with `"; "` — **additive by construction**, confirming the design claim.
2. `canonical.py:_convert_field_date` (lines 244-269): for the refuted-and-unanswered `assay_date` column, `resolved_format` is `None` (not in `resolution.formats`, per Focus Area 1), so control falls to `declared_format is None` (false, `%Y-%m-%d` is declared) → calls `convert_date(raw, "%Y-%m-%d")` on `"03/11/2025"`, which fails to parse and returns `needs_confirmation=True`. This independently confirms `canonical.assemble()` DOES flag `assay_date` in `tidy.flagged` on exactly this path, which is what feeds `canonical_flagged` in `_validate_mapping` and triggers the additive generic note.
3. This mechanism is genuinely pre-existing and out of the plan's declared scope fence (`validator.py`/`canonical.py` untouched, confirmed by `git diff --name-only` below) — not a new defect introduced by this fix, and not something this plan's scope permitted fixing.

**Judgment: the loosening is legitimate.** `_apply_objection` is a pure additive join of independently-triggered note fragments; the executor did not touch validator.py or canonical.py (respecting the scope fence), and weakening the test to tolerate an orthogonal, pre-existing, unrelated additive note — while still requiring the new honest note's specific content (declared format, refuting value, "Schemas page") and requiring the combined string differ from the generic-only text — is the correct call. Suppressing the generic note would have required editing `validator.py`, which was explicitly out of scope. This is not "papering over a real defect" — it is the additive design working exactly as documented in `validator.py`'s own module docstring ("additive-only: `_apply_objection` may only ever OR a True in, never clear one").

### Focus Area 3 — No Regression, No Weakened Tests

| Check | Result |
|-------|--------|
| Full backend suite | `832 passed, 4 skipped` (independently re-run, matches SUMMARY exactly) |
| New tests added | 8 (`git diff <baseline>..HEAD -- tests/test_date_escalation.py tests/test_date_order.py \| grep -c "^+def test_"` = 8) |
| Tests deleted | 0 (`grep "^-def test_"` on the same diff = empty) |
| Assertions weakened besides the one documented deviation | 0 — the only `-` line in the diff (excluding `+`/context) is a docstring sentence that was extended, not an assertion |
| Scope fence — `src/` changed files | `git diff --name-only <baseline>..HEAD -- src/` → exactly `src/assayingest/parsing/structure/date_order.py`, `src/assayingest/service.py`. No `validator.py`, `canonical.py`, `presets/`, or `frontend/` |
| Debt markers (TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER) in modified files | none found |

### Real-Fixture Sanity Check — Independently Reproduced

Ran the exact scenario from `data/synthetic/helixbio_export.csv` (`Experiment Date` = `03/11/2025`, ambiguous dd/mm) against `presets/assay-potency.yaml`'s `assay_date` field (declares stale `%Y-%m-%d`) in a fresh python session, not trusting the SUMMARY's transcript:

```
formats: {}
has_conflicts: True
contradictions: {'assay_date': '03/11/2025'}
confirm assay_date[0]: 2025-11-03
```

Matches the SUMMARY's claimed before/after exactly — this is the precise inverse of the reported bug.

### Anti-Patterns Found

None. No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers, no empty-return stubs, no hardcoded-empty-data patterns in any of the four modified files.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Targeted test files pass | `uv run pytest tests/test_date_escalation.py tests/test_date_order.py -q` | 52 passed | PASS |
| Full suite regression | `uv run pytest -q` | 832 passed, 4 skipped | PASS |
| Real-fixture dead-end reproduction (resolver level) | throwaway `python -c` against real fixture + preset | `formats: {}`, `has_conflicts: True`, `contradictions: {'assay_date': '03/11/2025'}` | PASS |
| Real-fixture escape hatch (confirm level) | same session, `confirm(date_answers={"assay_date": DateOrder.DAY_FIRST})` | `2025-11-03` | PASS |

### Requirements Coverage

No formal `requirements` IDs were declared in this quick task's PLAN frontmatter (`requirements: []`) — this is a quick-task fix, not a formal roadmap phase, and no REQUIREMENTS.md entries map to it. Not applicable.

### Human Verification Required

None. This is a pure backend/domain-logic fix fully exercised by unit tests plus an independent code-path trace and an independent live repro against the real fixture + preset. No frontend, UI, or external-service behavior was touched or needs eyeballing.

### Gaps Summary

No gaps. All 8 must-have truths verified against the actual source (not the SUMMARY's narrative), the load-bearing correctness property (contradiction recorded only on the unanswered branch) is confirmed directly in `_resolve_one_column`, the documented test-assertion deviation is judged legitimate after independently tracing `canonical.py`'s D-13 fallback and `validator.py`'s additive-note join, and the full suite is green at 832/4 (above the 824/4 baseline) with zero deleted or weakened tests and the scope fence intact.

---

_Verified: 2026-07-12_
_Verifier: Claude (gsd-verifier)_
