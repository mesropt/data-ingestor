---
phase: quick-260712-qgc
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/assayingest/parsing/structure/date_order.py
  - src/assayingest/service.py
  - tests/test_date_order.py
  - tests/test_date_escalation.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "An AMBIGUOUS date column whose field declares a date_format that CANNOT parse its values raises the date-order question (conflicts non-empty) and puts NO format into DateResolution.formats."
    - "That same refuted-and-unanswered column records contradictions[field] = one refuting raw value, so the amber note is the honest _contradiction_objection_note (names the declared format and an example value), not the generic conversion note."
    - "When the human answers the order for a refuted column, service.confirm(date_answers={...}) PASSES the gate (no NotReadyError / no 422) and the assembled cell is ISO-8601 -- '03/11/2025' answered DAY_FIRST becomes '2025-11-03'."
    - "The human's answer overrides the stale declaration for THIS run only -- nothing is written back to the Schema/Field."
    - "An AMBIGUOUS column whose declared date_format DOES parse every non-blank value is still trusted, raises no question, records no contradiction, and confirms clean (the trust is now earned, not assumed)."
    - "date_order exposes the all-values-parse check under a public name (parses_all); no second strptime loop is hand-rolled in service.py."
    - "Every other row of the resolve_date_formats decision table (EXCEL_SERIAL, INVALID/NON_DATE, DAY_FIRST/MONTH_FIRST/ISO agrees-or-contradicts) behaves exactly as before."
    - "Backend suite is green with no test deleted or weakened: >= 824 passed, 4 skipped."
  artifacts:
    - src/assayingest/parsing/structure/date_order.py
    - src/assayingest/service.py
    - tests/test_date_escalation.py
    - tests/test_date_order.py
  key_links:
    - "date_order.parses_all(values, declared) gates the AMBIGUOUS+declared branch of service._resolve_one_column -> refuted declarations fall through to the existing answer/conflict path -> DateFormatConflict reaches DateFormatQuestion -> the existing UI DateFormatQuestion panel asks the order."
    - "contradictions[name] (unanswered branch ONLY) -> validate(date_contradictions=...) -> validator._contradiction_objection_note -> the amber note names the declared format + a refuting value."
    - "confirm(date_answers={field: DateOrder.DAY_FIRST}) -> resolve_date_formats(answers=...) -> date_order.format_for_order(column, answer) -> formats -> BOTH validate() (gate passes) AND canonical.assemble() (cell is ISO-8601)."
---

<objective>
Close the Confirm dead-end: an AMBIGUOUS date column whose field declares an unparseable `date_format` is currently trusted blindly, so no question is asked, `canonical.assemble()` strptime-fails on every row, the field is amber forever with an uninformative note, and Confirm 422s with no way out from Review.

Purpose: this violates the phase's own locked rule (D-10-06 / INGEST-04) — "a declared `date_format` is a human claim, CHECKED AGAINST THE DATA, not blindly trusted" — and it is a permanent dead end a real user hit in manual UAT. Fail-closed means ASK, not silently trust.

Output: a public `date_order.parses_all` predicate; a corrected `AMBIGUOUS + declared` branch in `service._resolve_one_column` (try the declaration → trust it only if it parses, else ask the human); the decision-table docstring updated to document the new truth; and tests-first coverage of the dead-end reproduction, the human-answer escape hatch, the still-good trusted case, and the untouched decision-table rows.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/10-frictionless-correct-ingest/10-CONTEXT.md

@src/assayingest/service.py
@src/assayingest/parsing/structure/date_order.py
@src/assayingest/validation/validator.py
@tests/test_date_escalation.py
@tests/test_date_order.py

Key facts already established (do not re-derive):
- `service._resolve_one_column` (service.py ~1292) has the bug in its `DateOrder.AMBIGUOUS` branch: `if declared is not None: formats[name] = declared; return` — accepted without trying it against a single value.
- `date_order._all_parse(values, date_format)` (date_order.py:314) is exactly the missing check. It has 3 internal call sites (`_classify_iso`, `_resolved_dm_result`).
- `validation/validator.py::_contradiction_objection_note` already produces the correct amber copy once `contradictions[name]` is populated. It is CORRECT and must NOT be touched.
- `service.confirm()` (service.py:360) already threads `date_answers` → `resolve_date_formats(answers=...)` → BOTH `validate()` and `canonical.assemble()`. The plumbing is right; only the resolver's verdict is wrong.
- Existing test `test_ambiguous_with_a_declared_format_trusts_the_declaration_and_raises_no_question` (tests/test_date_escalation.py:101) declares `%d/%m/%Y` against `03/11/2025` — which PARSES — so it is the still-good case and must keep passing unchanged in behavior.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1 (RED): failing tests pinning the dead-end, the escape hatch, and the earned-trust case</name>
  <files>tests/test_date_escalation.py, tests/test_date_order.py</files>
  <behavior>
    In tests/test_date_escalation.py (the natural home — it already owns one test per decision-table row; do NOT create a parallel file):
    - Test A (the dead-end reproduction, resolver level): a helixbio-shaped table `["Compound ID", "Experiment Date"]` with ambiguous dd/mm values (`03/11/2025`, `04/11/2025` — both components <= 12), a FieldSet whose `assay_date` field is `type="date", date_format="%Y-%m-%d"` (the stale preset declaration, which cannot parse those values). `resolve_date_formats(table, proposal, field_set)` MUST: (1) leave `"assay_date"` OUT of `resolution.formats`; (2) return `resolution.question.has_conflicts is True` with a conflict naming `source_column="Experiment Date"` and both candidate formats `%d/%m/%Y` / `%m/%d/%Y`; (3) set `resolution.contradictions["assay_date"]` to one refuting RAW value from the column (e.g. `"03/11/2025"`).
    - Test B (the amber note is honest, fail-closed): run `validate(table, proposal, field_set, date_formats=resolution.formats, date_contradictions=resolution.contradictions)` on Test A's unanswered resolution. The `assay_date` mapping MUST have `needs_confirmation is True` and its note MUST contain `"%Y-%m-%d"` and `"03/11/2025"` (the `_contradiction_objection_note` copy), and MUST NOT be the generic `"type/date/unit conversion check objected"` note.
    - Test C (the escape hatch, end-to-end through confirm): same table + field set, `service.confirm(table, edited_mappings, field_set, date_answers={"assay_date": DateOrder.DAY_FIRST})` MUST NOT raise `NotReadyError`, and `result.tidy.records[0]["assay_date"] == "2025-11-03"` (03/11/2025 read day-first). `edited_mappings` must cover exactly `field_set.field_names` (confirm's FieldCoverageError gate) — keep the field set to 2 fields.
    - Test D (answered ⇒ NO contradiction — the assertion that proves the dead end is actually gone): `resolve_date_formats(..., answers={"assay_date": DateOrder.DAY_FIRST})` on the refuted column MUST return `formats["assay_date"] == "%d/%m/%Y"` AND `contradictions == {}` AND raise nothing.
    - Test E (earned trust, still-good case — unbroken): extend the EXISTING `test_ambiguous_with_a_declared_format_trusts_the_declaration_and_raises_no_question` docstring to state that the trust is now EARNED (the declared `%d/%m/%Y` parses every value, so the data cannot refute the claim); its assertions stay exactly as they are. Do not delete or weaken it. Add a companion assertion in the same test (or a sibling test) that `service.confirm(...)` with NO `date_answers` still passes the gate for this column.
    - Test F (regression guard on the untouched rows): assert the EXCEL_SERIAL, INVALID/NON_DATE, and DAY_FIRST-order-contradicts rows still behave as their existing tests assert — verify by running the existing file, do not duplicate those tests.
    In tests/test_date_order.py:
    - Test G: `date_order.parses_all(["03/11/2025"], "%Y-%m-%d") is False` and `date_order.parses_all(["03/11/2025", "04/11/2025"], "%d/%m/%Y") is True` — pins the promoted public name that service.py depends on.
  </behavior>
  <action>Write the tests above using the file's existing `_table` / `_mapping` / `_proposal` helpers and the same import style. Every date value used must be a real ambiguous dd/mm shape consistent with `data/synthetic/helixbio_export.csv`'s "Experiment Date" column (`03/11/2025`) — do not invent exotic values. Run pytest on the two files and confirm each new test fails for the RIGHT reason: Test A/B/D fail because today's resolver puts the unparseable `%Y-%m-%d` into `formats` and records no conflict/contradiction; Test C fails with `NotReadyError` (the exact 422 dead end); Test G fails with `AttributeError: module has no attribute 'parses_all'`. Do NOT touch src/ in this task. Commit the RED tests.</action>
  <verify>
    <automated>uv run pytest tests/test_date_escalation.py tests/test_date_order.py 2>&1 | tail -30 — new tests FAIL (A/B/D on wrong formats/empty conflicts, C on NotReadyError, G on missing parses_all); every pre-existing test in both files still PASSES</automated>
  </verify>
  <done>The new tests exist, fail for the documented reasons (not on import errors or fixture typos), and no existing test in either file was deleted, skipped, or had an assertion removed.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2 (GREEN): promote parses_all, then check the declaration against the data before trusting it</name>
  <files>src/assayingest/parsing/structure/date_order.py, src/assayingest/service.py</files>
  <behavior>
    All of Task 1's tests go green with no test edited.
  </behavior>
  <action>
Step 1 — `src/assayingest/parsing/structure/date_order.py`: rename the private `_all_parse(values, date_format) -> bool` to the public `parses_all(values, date_format) -> bool` and update its 3 internal call sites (`_classify_iso`, `_resolved_dm_result`) so they keep working. Move it up beside the other public functions and give it a docstring stating that a successful parse of every value is the ONLY evidence that can (fail to) refute a declared format — it does not prove the format is CORRECT (the module docstring's own `03/04/2025` warning still stands), it only proves the data cannot refute it. Blank values are ignored (strip-and-drop), mirroring `classify_column`'s own cleaning rule, so a column with blank cells is not falsely refuted. Do not hand-roll a second strptime loop anywhere.

Step 2 — `src/assayingest/service.py::_resolve_one_column`, the `DateOrder.AMBIGUOUS` branch ONLY. Replace the blind `if declared is not None: formats[name] = declared; return` with: if `declared is not None` AND `date_order.parses_all(values, declared)` → `formats[name] = declared; return` (earned trust — the data cannot refute the human's claim; this is the genuine `%d/%m/%Y` vs `03/11/2025` tiebreak case). Otherwise the declaration is either absent or REFUTED by the data, and Python cannot pick an order on its own, so fall through to the EXISTING answer/conflict path unchanged: an `answers[name]` resolves via `date_order.format_for_order(column, answer)` (the human's explicit answer overrides the stale declaration, for THIS run only, never written back to the Schema); no answer appends the existing `DateFormatConflict`.

Step 3 — the contradiction signal, on the UNANSWERED branch ONLY. When the declaration was refuted AND no answer is present, additionally record `contradictions[name] = <one refuting raw value>` alongside the appended `DateFormatConflict`, so `validate()` renders `_contradiction_objection_note` instead of the uninformative generic conversion note. Pick the refuting value from the column's own non-blank values (the first value the declared format fails to parse is the most honest choice; `column.example_values[0]` is an acceptable fallback, matching the existing DAY_FIRST/MONTH_FIRST contradiction row's idiom). CRITICAL: record it ONLY when there is no answer — if the human answered and a contradiction were still recorded, `validate()` would re-flag the field amber and the dead end would survive the fix, which is the entire bug. Do NOT record a contradiction on the earned-trust branch either.

Step 4 — the `resolve_date_formats` docstring decision table currently documents the WRONG behavior as intended. Replace the single row `| AMBIGUOUS | present | -- | trust the declaration (no evidence to contradict it) |` with exactly two rows: one for a declared format that PARSES every value (trust it — earned, the data cannot refute the claim) and one for a declared format the data REFUTES (contradiction + conflict; ask the human, whose answer overrides the declaration for this run). Leave every other row byte-identical. Keep the existing "a fact about THIS upload's column, never written back to the stored Schema/Field" paragraph.

Scope fence (hard): do NOT modify `validation/validator.py`, `canonical.py`, `presets/assay-potency.yaml`, or ANY file under `frontend/`. The client contract stays `order: "day_first" | "month_first"` — the server re-derives the format; never accept a format string from a client. Backend-only: no `npm run build`, no `frontend/dist` rebuild.
  </action>
  <verify>
    <automated>uv run pytest tests/test_date_escalation.py tests/test_date_order.py tests/test_canonical_dates.py tests/api/test_confirm_dates.py tests/api/test_date_format_route.py -q</automated>
  </verify>
  <done>All Task 1 tests pass with zero test-file edits in this task. `grep -rn "strptime" src/assayingest/service.py` returns nothing (no hand-rolled second loop). `git diff --name-only` touches only `src/assayingest/parsing/structure/date_order.py` and `src/assayingest/service.py` — no validator.py, no canonical.py, no presets/, no frontend/.</done>
</task>

<task type="auto">
  <name>Task 3: full-suite regression and the real-fixture dead-end sanity check</name>
  <files>tests/</files>
  <action>Run the full backend suite. Baseline to protect: 824 passed / 4 skipped — the count may only GO UP (by Task 1's new tests); no test may be deleted, skipped, or weakened. If any pre-existing test now fails, it is a genuine regression from Task 2's branch change — fix `src/`, never the test, unless the test literally encoded the bug (only `test_ambiguous_with_a_declared_format_trusts_the_declaration_and_raises_no_question` is a candidate, and it must still PASS because its declared `%d/%m/%Y` parses `03/11/2025`; if it fails, the earned-trust branch is wrong). Then, as a final sanity check, run the real dead-end input through the resolver in a throwaway python -c (no new file, no Claude call): parse `data/synthetic/helixbio_export.csv`, build a proposal mapping `assay_date -> "Experiment Date"` against the `presets/assay-potency.yaml` field set, call `service.resolve_date_formats`, and confirm the output is now `formats` WITHOUT `assay_date`, `conflicts` NON-EMPTY, and `contradictions={'assay_date': '03/11/2025'}` — the exact inverse of the reported bug. Record the before/after in the SUMMARY.</action>
  <verify>
    <automated>uv run pytest -q 2>&1 | tail -5 — >= 824 passed, 4 skipped, 0 failed</automated>
  </verify>
  <done>Full suite green at or above baseline; the real helixbio + assay-potency preset input now raises the date-order question instead of silently trusting the unparseable `%Y-%m-%d`; SUMMARY records the observed before/after resolver output.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| client → /api/date-format/resolve → confirm | The human's date-order answer crosses here. It must remain an ORDER enum, never a strptime format string. |
| declared Schema/Field.date_format → resolver | A human claim from the Schemas page, applied to a DIFFERENT vendor's file. Untrusted input with respect to THIS upload's data. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-qgc-01 | Tampering | `service._resolve_one_column` AMBIGUOUS branch | high | mitigate | A declared `date_format` is checked against the column's own values via `date_order.parses_all` before it is trusted; a refuted declaration cannot silently produce a wrong-order date (lives-at-stake bar: fail closed and ask, never guess). |
| T-qgc-02 | Spoofing | client-supplied date format | high | mitigate | Unchanged existing contract: the client may only send `order: day_first \| month_first`; the server re-derives the concrete strptime format from the column's own shape via `format_for_order`. This plan adds no new client-supplied-format path. |
| T-qgc-03 | Information disclosure | contradiction example value under `headers_only` | low | accept | The contradiction value is the same class of raw value the existing DAY_FIRST/MONTH_FIRST contradiction row already records and the existing wire layer already redacts under `headers_only` (D-10-05); no new leak surface. |
| T-qgc-04 | Elevation of privilege | human answer overriding a declaration | medium | mitigate | The answer overrides the stale declaration for THIS run only — `formats` is a per-run override threaded into `validate()`/`assemble()`; nothing is written back to the stored `Schema`/`Field`. |
</threat_model>

<verification>
- `uv run pytest -q` — full backend suite, >= 824 passed / 4 skipped / 0 failed.
- The resolver's verdict on the real reported input (helixbio "Experiment Date" + assay-potency `%Y-%m-%d`) is now: no format resolved, question raised, contradiction recorded.
- `service.confirm(date_answers={"assay_date": DateOrder.DAY_FIRST})` on that input passes the gate and yields ISO-8601 `2025-11-03` — the Review screen has a way out.
- `git diff --name-only` for src/: exactly `date_order.py` + `service.py`. No frontend, no validator, no canonical, no presets.
</verification>

<success_criteria>
- The AMBIGUOUS + declared-format branch tries the declaration against the data before trusting it (D-10-06 honored: a human claim is checked, not trusted).
- A refuted declaration asks the human (question raised) and, while unanswered, carries the honest contradiction note — fail-closed, never a silent guess.
- An answered refuted column confirms clean with an ISO-8601 cell and records NO contradiction — the dead end is gone, not merely relabeled.
- A declaration the data cannot refute is still trusted with no question — the curator is not nagged on a file they already declared correctly.
- No test deleted or weakened; suite green at or above 824/4.
</success_criteria>

<output>
Create `.planning/quick/260712-qgc-fix-the-confirm-dead-end-an-ambiguous-da/260712-qgc-SUMMARY.md` when done.
</output>
