---
phase: 03-validator-learning-loop
reviewed: 2026-07-10T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - src/assayingest/cli.py
  - src/assayingest/domain/models.py
  - src/assayingest/export/__init__.py
  - src/assayingest/export/writers.py
  - src/assayingest/learning/__init__.py
  - src/assayingest/learning/profile.py
  - src/assayingest/learning/reconstruct.py
  - src/assayingest/learning/signature.py
  - src/assayingest/learning/sqlite_store.py
  - src/assayingest/learning/store.py
  - src/assayingest/mapping/mapper.py
  - src/assayingest/validation/__init__.py
  - src/assayingest/validation/validator.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: resolved
resolution: >
  CR-01, WR-01, WR-02, WR-03 fixed test-first (commits b00012c, fc013a5,
  6acbad7, 952ac06); IN-01 dead code removed (d40613e). IN-02 (allowed_values
  blank-cell flagging) resolved test-first (commits e6110b5, 7b4ea03): a
  blank cell is flagged only when the field is required (the Field default);
  an explicitly optional field (required=False) skips the blank without
  flagging to avoid alert fatigue, while a non-blank out-of-set value is
  always flagged regardless of required. Full suite green.
---

# Phase 3: Code Review Report

**Reviewed:** 2026-07-10
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

The learning-loop and validator wiring largely honor the two binding principles.
The auto-apply path (`_resolve_proposal`) correctly builds no Anthropic client and
checks no credentials on a profile hit; `find()` is an exact-signature SQL match
so a mismatch falls back to fresh Claude; the validator runs on both paths and is
additive-only (`_apply_objection` only ORs `True`); SQL is fully parameterized;
SQLite connections are all wrapped in `closing()`; `column_signature` is a sorted
list + sha256 + NFC/casefold with no builtin `hash()`; export is gated on
`proposal.is_ready`; and the domain/repository seam keeps `sqlite3` out of the
domain. Good.

However, the review found one confidentiality defect that breaks the absolute
`--headers-only` guarantee, plus a P1 correctness hazard in column reconstruction
for duplicate/blank headers, a fail-open in the numeric bounds check, and a
latent uncaught crash. Details below.

## Critical Issues

### CR-01: `--headers-only` leaks raw cell values via the structure-assist path

**File:** `src/assayingest/cli.py:226`, `src/assayingest/cli.py:267-303`
**Issue:** The `--headers-only` flag advertises an absolute privacy guarantee — the
CLI help (cli.py:660-667) states "send Claude the column headers only -- zero data
values" and "no cell value leaves the machine." But `headers_only` is only threaded
to the *mapping* path. When a file's structure is ambiguous, `run()` takes the
`_ask_and_report(outcome)` branch (line 226) — which never receives `headers_only`
— and `_enrich_question` calls `propose_structure(_render_question_evidence(question))`.
`_render_question_evidence` (line 296-303) embeds `question.evidence_rows`, which are
**raw source cell values** (e.g. `rows[:8]` from `_ambiguous_locale_question`,
`_shape_unsupported_question`, etc.). Enrichment fires whenever credentials exist
(line 285), which is exactly the case for a `--headers-only` user who still wants
Claude to map. So a privacy-mode user whose file trips any structural question has
real research-IP cell values sent to the Anthropic API, silently contradicting the
guarantee shown to them (and highlighted to judges). This is a P2 confidentiality
breach.
**Fix:** Thread `headers_only` into `_ask_and_report`/`_enrich_question` and suppress
`evidence_rows` before they reach Claude when it is set (send headers/derived shape
signals only), or skip Claude enrichment entirely under `--headers-only`:
```python
def _ask_and_report(question: StructureQuestion, *, headers_only: bool = False) -> int:
    if not headers_only:
        question = _enrich_question(question)
    ...
# and in run():
if isinstance(outcome, StructureQuestion):
    return _ask_and_report(outcome, headers_only=headers_only)
```
Alternatively, strip values inside `_render_question_evidence` under the flag. Until
then, either the help text's "no cell value leaves the machine" claim must be
narrowed, or (preferred) the leak closed.

## Warnings

### WR-01: Duplicate / blank headers can be misrouted at confidence 1.0 on auto-apply

**File:** `src/assayingest/learning/reconstruct.py:60-76`, `src/assayingest/learning/signature.py:30-41`
**Issue:** `column_signature` is deliberately order-independent (sorted multiset),
while `_resolve_new_header` disambiguates same-normalized headers by left-to-right
**occurrence rank**. For files with *distinct* headers this is sound under reorder.
But when a file has duplicate or blank headers (both normalize to the same string,
including `""`), occurrence rank is order-dependent while the signature is not. Two
files can share an identical signature yet carry the duplicated/blank columns in a
different physical order — so a stored mapping resolved by `(normalised="", rank=0)`
binds to a *different* data column in the new file. The reconstructed field is built
at `confidence=1.0, needs_confirmation=False`, and the validator only catches it if
the misrouted data happens to violate a declared constraint. In a safety-critical
context this is a silent wrong-data path (P1). Concretely: profile saved on headers
`["", ""]` (col0→value, col1→unit); a later same-signature file with those two blank
columns swapped auto-applies value←unit-column silently.
**Fix:** Auto-apply should fail closed when the signature match relies on
indistinguishable (duplicate/blank normalized) headers whose count > 1 — fall back to
fresh Claude, or flag those specific fields `needs_confirmation=True` instead of 1.0.
For example, in `reconstruct_proposal`, detect duplicated normalized headers and mark
fields resolving to them as needing confirmation rather than clearing them.

### WR-02: Numeric bounds check fails open on `nan`

**File:** `src/assayingest/validation/validator.py:187-212`
**Issue:** `_numeric_value` coerces cells with `float(raw.strip())`. `float("nan")`
succeeds, and every comparison against NaN (`value < min`, `value > max`) is `False`,
so a literal `nan`/`NaN` cell in a bounded field passes the min/max check unflagged.
On a `number`-typed `decimal_point` column, `canonical._convert_numeric` also
`float()`s it successfully and does **not** flag, so the field can reach the export
gate green despite carrying a non-value. This is a fail-open in the "runs on every
value" safety net (P1). (`inf`/`-inf` are correctly caught by max/min.)
**Fix:** Reject non-finite parses in the bounds path:
```python
import math
value = _numeric_value(raw, locale)
if value is not None and not math.isfinite(value):
    return f"'{raw}' is not a finite number"
```
Or filter in `_numeric_value` (`return None if not math.isfinite(v) else v`) plus an
explicit objection so the flag is not merely skipped.

### WR-03: `run()` crashes with an uncaught `AttributeError` when `field_set is None` and credentials exist

**File:** `src/assayingest/cli.py:414-424`, `src/assayingest/mapping/mapper.py:45-51`
**Issue:** `run()`/`_resolve_proposal` accept `field_set=None` (documented for
early-exit callers). If a caller passes `field_set=None` while credentials are set,
`_resolve_proposal` skips the profile branch, passes the credential check, and calls
`propose_mapping(table, None, ...)`. Inside, `_render_system_prompt(field_set)`
dereferences `field_set.fields` → `AttributeError: 'NoneType'`. `_map_one` only
catches `AuthenticationError`, `APIError`, and `ValueError`, so the CLI crashes with
a bare traceback instead of a consequence-naming error. The `--fields`-required CLI
guard masks this today, but `run()` is a public API exercised directly by tests.
**Fix:** Guard the fresh-Claude branch explicitly before the SDK call:
```python
if not _has_credentials():
    return None, _MISSING_CREDENTIALS
if field_set is None:
    raise ValueError(
        "Cannot map: no field set was provided, so no target fields can be resolved."
    )
proposal = propose_mapping(table, field_set, headers_only=headers_only)
```
(`ValueError` is already handled by `_map_one`, yielding a clean exit 1.)

## Info

### IN-01: Dead code — `structure_assist._to_domain_field` is never called

**File:** `src/assayingest/parsing/structure_assist.py:90-99`
**Issue:** `_to_domain_field` (mapping a `WireStructureCandidate` to a `StructuralHint`)
has no callers; `propose_structure` returns only the main proposal and never surfaces
ranked alternatives. It is documented as "available for a caller that also wants
alternatives," but no such caller exists, so it is untested dead code.
**Fix:** Remove it until a caller needs it, or wire alternatives through
`propose_structure` so the function is exercised.

### IN-02: `allowed_values` validation flags legitimately blank cells — RESOLVED

**Status:** resolved (commits e6110b5, 7b4ea03)
**File:** `src/assayingest/validation/validator.py:180-186`, `_check_column:165-172`
**Issue:** `_check_column` skips only `raw is None` (column shorter than row); an empty
string cell `""` is passed to `_check_value`, where `"".casefold()` is not in the
allowed set and returns a violation. A field with sparse/blank rows in an
`allowed_values` column therefore always flags. This is fail-closed (safe direction),
so not a correctness defect, but it will make otherwise-clean files perpetually yellow
and can prevent a repeat-file profile from demonstrating the "zero yellow" money shot.
**Resolution:** Fail-closed-by-default blank-cell policy, scoped to the
`allowed_values` check only. A blank cell (`None`, empty, or whitespace-only) is
flagged when the field is `required` (the `Field` default — required unless
explicitly opted out), and skipped without flagging when the field is explicitly
`required=False`. A non-blank out-of-set value is always flagged regardless of
`required`, unchanged. This keeps the safety-critical default (missing required
result must surface to a human) while avoiding alert fatigue from false yellows
on legitimately-optional missing data. `min`/`max`/`type`/`unit` checks are
untouched; the validator remains additive-only.

---

_Reviewed: 2026-07-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
