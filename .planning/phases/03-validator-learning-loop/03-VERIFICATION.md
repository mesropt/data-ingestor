---
phase: 03-validator-learning-loop
verified: 2026-07-10T22:40:00Z
gap_resolved: 2026-07-10T00:00:00Z
status: verified
score: 10/10 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "A Phase-1 structural hint is saved with its profile and replays automatically, so the same odd layout parses automatically next time without re-asking (LEARN-06, ROADMAP SC5)."
    status: resolved
    reason: >
      The hint IS persisted correctly (StructuralHint round-trips through SqliteProfileStore --
      tests/test_profile_store.py::test_structural_hint_round_trips passes), but it is NEVER
      read back and applied to parsing on a later run. `run()`'s `hint` parameter is populated
      exclusively from the CLI's `--hint key=value` flags (`_hint_from_args(args.hint)` in
      `main()`); no code path looks up a saved profile's `structural_hint` and feeds it into
      `resolve_or_ask()`/`parse()` before or during structure resolution. Live reproduction:
      parsed `data/synthetic/verity_reagents_stock.xlsx` with `--hint header-row=2`, saved a
      profile; re-running the SAME file with NO `--hint` flag reproduces the identical
      `StructureQuestion` ("which row is the real header") and exits 4 (BLOCKED) -- exactly the
      re-asking LEARN-06/SC5 says must not happen. No test in the suite exercises "second run,
      no --hint, saved profile with a structural_hint resolves automatically" -- every
      `_map_one`/`run()` test in `tests/test_learning_loop_cli.py` either passes
      `structural_hint=None` or never sets up an ambiguous-structure fixture at all; the only
      hint round-trip coverage is at the store layer (`test_profile_store.py`), not through
      `run()`/`parse()`.
    artifacts:
      - path: "src/assayingest/cli.py"
        issue: "run()/resolve_or_ask()/_resolve_proposal() never call store.find()/list_for_field_set() to retrieve a saved structural_hint before parsing; `hint` is CLI-arg-only end to end (lines 161-236, 402-433)."
      - path: "src/assayingest/learning/reconstruct.py"
        issue: "reconstruct_proposal() reconstructs the MAPPING from a profile, but nothing in the learning package or cli.py reconstructs/applies the profile's structural_hint at parse time."
    missing:
      - "A lookup path in run()/resolve_or_ask() that, when no --hint was given, checks whether any saved profile for the current field_set carries a structural_hint that would resolve the file's current StructureQuestion, and retries parse() with it before surfacing the question to the human."
      - "An end-to-end test proving a second run of a same-layout file with NO --hint flag and a previously-saved profile (from a first run that used --hint) does not re-ask the structural question."
    resolution: >
      Fixed by test commit b871042 (`test(03): add failing test for structural-hint replay
      (LEARN-06/SC5)`, tests/test_hint_replay_cli.py, TDD RED) and fix commit d6c6ff9
      (`fix(03): replay a saved profile's structural hint automatically (LEARN-06/SC5)`,
      src/assayingest/cli.py). `run()` now calls a new `_try_replay_saved_hint()` whenever
      parsing returns a `StructureQuestion` and no explicit `--hint` was given: it iterates
      `store.list_for_field_set(field_set.signature)`, re-parses with each candidate profile's
      `structural_hint`, and accepts the FIRST candidate whose re-parsed table's
      `column_signature` exactly equals that profile's own stored `column_signature` (the same
      exact-signature guarantee LEARN-03/04 already require for mapping auto-apply, applied here
      to the hint itself -- fail-closed: a hint that resolves a structurally-similar but
      genuinely different file is rejected because its signature differs, never silently
      applied). A successful replay reuses the existing auto-apply path unchanged, so it also
      maps at confidence 1.0 with no Claude call, and prints a transparency line ("replayed
      saved structural hint from profile <id>") before the existing "applied saved profile ...
      (no Claude call)" line. An explicit `--hint` always takes precedence and is never routed
      through replay. Live-reproduced fixed: the exact repro this gap documented (parse
      `data/synthetic/verity_reagents_stock.xlsx` with `--hint header-row=2`, save a profile;
      re-run the SAME file with NO `--hint` and NO credentials) now exits 0, prints the replay
      transparency line, auto-applies the saved mapping, and never calls `propose_mapping`.
      New tests (tests/test_hint_replay_cli.py, 3 tests): replay succeeds and auto-applies with
      no Claude call; an explicit `--hint` still wins over a saved replay; a DIFFERENT
      odd-layout file whose hinted reparse resolves structurally but yields a different column
      signature still surfaces the `StructureQuestion` (fail-closed control). Full suite: 394
      passed, 4 skipped (live-API tests, unchanged) -- up from 391 passed/4 skipped pre-fix.
deferred: []
---

# Phase 3: Validator + Learning Loop Verification Report

**Phase Goal:** Each field Claude proposes — including every ranked alternative, not only the top pick — is checked in pure Python against the constraints the user declared for that field (no built-in vocabulary, zero LLM calls), and any objection forces the field back to needs-confirmation regardless of Claude's reported confidence; a curator can confirm a fully-clear mapping and save it as a profile keyed by (field set, column signature) so a repeat file from the same source auto-maps at confidence 1.0 — safely across a vendor's format drift, remembering any Phase 1 structural hint; and from the CLI a curator can export the confirmed data as CSV, Excel, and JSON, each with a provenance manifest.

**Verified:** 2026-07-10T22:40:00Z (initial) / 2026-07-10 (gap-resolution re-check)
**Status:** verified
**Re-verification:** Yes — the LEARN-06/SC5 gap below was closed by commits b871042 (test) and
d6c6ff9 (fix); see the `resolution` field on the gap entry in the frontmatter and the "Gap
Resolution" section at the end of this report. The gap's own repro was re-run live and now
passes.

## Goal Achievement

### Observable Truths (mapped to the 6 ROADMAP Success Criteria + binding principles)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 (SC1) | A field with a user-declared allowed-value/type/unit constraint is flagged when a mapped value violates it, with NO LLM call. | ✓ VERIFIED | `validation/validator.py` has zero anthropic/network imports (only `math`, `dataclasses.replace`, `canonical`, domain/fields/parsing modules). Live repro: a mapping pointing every field at the same source column produced `assay_type`/`unit` allowed_values violations and forced exit 5. `tests/test_validator.py::test_allowed_values_flags_a_value_not_in_the_declared_set`, `test_min_flags_a_value_below_the_declared_minimum`, `test_max_flags_a_value_above_the_declared_maximum` all pass. |
| 2 (SC2) | The validator's objection overrides Claude's confidence, and EVERY ranked alternative is checked, not only the top pick. | ✓ VERIFIED | `_apply_objection` (validator.py:258-269) is additive-only (`needs_confirmation=mapping.needs_confirmation or objects` — can only OR True in). `tests/test_validator.py::test_validator_overrides_a_confidence_1_0_clear_field` and `test_every_alternative_is_validated_not_only_the_chosen_column` pass. |
| 3 (SC3) | A field with no declared constraints is never silently trusted; the validator's objection (or its absence) is shown alongside Claude's reasoning. | ✓ VERIFIED | `_NO_CONSTRAINTS_NOTE` path leaves `needs_confirmation` as Claude set it but always sets `validator_note`; `cli.py::_render_field`/`_with_validator_note` render the note for both yellow and clear fields (confirmed live: every field in the smoke test printed a `validator_note:` line). `tests/test_validator.py::test_no_constraints_field_gets_an_explicit_absence_note_and_keeps_claudes_gate` passes. |
| 4 (SC4) | Two files whose headers differ only in order/case/whitespace produce an identical signature; a fully-clear mapping saves as a profile keyed by (field set, signature); a matching-signature repeat file auto-applies at 1.0 with NO Claude call; a mismatch (incl. drift) never auto-applies and falls back to Claude. | ✓ VERIFIED | Live repro of the full money shot: `column_signature(['Compound ID',...]) == column_signature(['  compound   id ',...])` is True; a real `run()` call on `novascreen_batch01.csv` saved a profile, and a second `run()` on `novascreen_batch02.csv` with credentials unset and `propose_mapping` monkeypatched to raise printed `"applied saved profile <id> (no Claude call)"`, exited 0, confidence 1.0, zero yellow, and the raise-if-called function was never invoked. `tests/test_learning_loop_cli.py` (10 tests, incl. `test_money_shot_auto_applies_offline_zero_yellow_no_claude_call`, `test_a_seeded_profile_for_a_different_signature_never_auto_applies`) all pass. |
| 5 (SC5) | A Phase-1 structural hint is saved with its profile and replays automatically, so the same odd layout parses automatically next time without re-asking. | ✓ VERIFIED (gap closed) | Was **FAILED** at initial verification — see "Gap Resolution" below. `cli.py::_try_replay_saved_hint` now retries every saved profile's `structural_hint` before asking, accepting only when the re-parsed table's `column_signature` exactly matches that profile's own stored signature (fail-closed). Live re-repro on `data/synthetic/verity_reagents_stock.xlsx`: save with `--hint header-row=2`, then a second run with NO `--hint` and NO credentials now exits 0, prints `replayed saved structural hint from profile <id>` then `applied saved profile <id> (no Claude call)`, and never calls `propose_mapping`. `tests/test_hint_replay_cli.py` (3 tests) pass, incl. a fail-closed control against a different odd-layout file whose hinted reparse yields a different signature. |
| 6 (SC6) | A curator can export CSV, Excel, and JSON, all derived from the one canonical form, each with a JSON manifest (field set, signature, field→source mapping, inferred/confirmed flags, per-field confidence). | ✓ VERIFIED | Live repro: a clean mapping run with `--export`/`output_dir` wrote exactly `export.csv`, `export.xlsx`, `export.json`, `manifest.json`; manifest contained `field_set_signature`, `column_signature`, per-field `source_column_normalised`/`confidence`/`confirmed`, `provenance: "fresh-claude"`, `strictness: "strict"`, `exported_at`. A yellow (not-ready) mapping wrote nothing and stayed exit 5. `tests/test_export_writers.py`, `tests/test_export_cli.py` (13 tests) pass. |
| 7 (P1 fail-closed) | Exact-signature match only; auto-apply builds no client, checks no credentials; validator additive-only; validator runs on both fresh-Claude and auto-applied-1.0 paths and every alternative. | ✓ VERIFIED | `_resolve_proposal` (cli.py:402-433): profile-hit branch never calls `_has_credentials()` or constructs a client; miss branch checks credentials only then. `_map_one` (cli.py:448-505) calls `validate(...)` unconditionally after `_resolve_proposal` returns, before any print — same call site for both branches. Confirmed live in the SC4 auto-apply repro (no credentials, no client, validator still ran and reported `no constraint violation found` on the auto-applied fields). |
| 8 (P2 confidentiality) | `--headers-only` sends headers only, no cell values, on ALL paths, including structure-assist. | ✓ VERIFIED | CR-01 fix confirmed in code: `_ask_and_report(question, *, headers_only=False)` (cli.py:258-280) skips `_enrich_question` entirely when `headers_only=True`, closing the leak the code review found (evidence_rows previously reached Claude via the structure-assist path even under `--headers-only`). `tests/test_headers_only.py::test_ask_and_report_skips_enrichment_entirely_under_headers_only` passes; mapper's `_render_table` skips the sample-rows block on the fresh-Claude branch (`tests/test_headers_only.py`, 8 tests, all pass). |
| 9 (Code-review fixes) | CR-01, WR-01, WR-02, WR-03, IN-01 are real in the code, not just claimed in 03-REVIEW.md. | ✓ VERIFIED | All 5 fix commits (`b00012c`, `fc013a5`, `6acbad7`, `952ac06`, `d40613e`) present in `git log` and their diffs inspected directly: CR-01 (headers_only threaded into `_ask_and_report`), WR-01 (`reconstruct.py`'s `Counter`-based ambiguous-duplicate fail-closed path), WR-02 (`math.isfinite` guard in `_check_value`), WR-03 (explicit `ValueError` when `field_set is None` with credentials), IN-01 (`_to_domain_field` grep returns no match — removed). |
| 10 (Repository seam) | `sqlite3` is imported by exactly one module (`learning/sqlite_store.py`); domain never imports it. | ✓ VERIFIED | `grep -rlE '^\s*(import\|from)\s+sqlite3' src/assayingest` returns only `src/assayingest/learning/sqlite_store.py`. |

**Score:** 10/10 truths verified (LEARN-06/SC5 gap closed — see "Gap Resolution" below)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/assayingest/learning/signature.py` | Order-independent, normalised, duplicate/blank-preserving column signature | ✓ VERIFIED | `column_signature()` sorts a normalised LIST (never a set); NFC+casefold+whitespace-collapse; live-tested order/case/ws invariance and column-count sensitivity. |
| `src/assayingest/learning/profile.py` | `LearnedProfile`/`StoredFieldMapping` domain model | ✓ VERIFIED | Frozen dataclasses, `to_dict()` recursion for nested `StructuralHint`, imports nothing infra. |
| `src/assayingest/learning/store.py` | `ProfileStore` ABC repository seam | ✓ VERIFIED | Zero sqlite3 import; abstractmethods `save`/`find`/`list_for_field_set`. |
| `src/assayingest/learning/sqlite_store.py` | SQLite-backed implementation, sole sqlite3 importer | ✓ VERIFIED | `contextlib.closing`, parameterised `?` queries, `ON CONFLICT ... DO UPDATE` upsert, confirmed by grep isolation check. |
| `src/assayingest/learning/reconstruct.py` | Auto-apply reconstruction, normalised-lookup (not exact `headers.index()`) | ✓ VERIFIED, with the WR-01 fail-closed extension for ambiguous duplicate/blank headers. |
| `src/assayingest/validation/validator.py` | No-LLM constraint validator, additive-only | ✓ VERIFIED | See truths 1-3, 7 above. |
| `src/assayingest/domain/models.py` | `FieldMapping.validator_note` optional field | ✓ VERIFIED | Present, additive, non-frozen dataclass unaffected elsewhere. |
| `src/assayingest/export/writers.py` | CSV/xlsx/JSON writers + `build_manifest` | ✓ VERIFIED | See truth 6 above; `ensure_ascii=False` throughout (grepped, present in `write_json`/manifest). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `learning/signature.py::column_signature` | `cli.py::_resolve_proposal` / `_save_profile_if_ready` | save-time and lookup-time both call the same function | ✓ WIRED | Confirmed by the SC4 live money-shot repro (save on batch01, lookup hit on batch02). |
| `learning/reconstruct.py::reconstruct_proposal` | `cli.py::_resolve_proposal` | profile-hit branch | ✓ WIRED | `reconstruct_proposal(profile, table.headers)` called directly, no Anthropic import in the module. |
| `validation/validator.py::validate` | `cli.py::_map_one` | called unconditionally on BOTH branches before any print | ✓ WIRED | Single call site at cli.py:479-482, confirmed by code read and by the auto-apply-still-validates live/test evidence. |
| `export/writers.py::build_manifest` | `learning/reconstruct.py::stored_mapping_from` + `learning/signature.py::column_signature` | manifest reuses save-time functions, not a re-derivation | ✓ WIRED | Confirmed by reading `writers.py` imports and by the live manifest output matching the expected shape. |
| `cli.py::_resolve_proposal` provenance return | `export/writers.py::build_manifest`'s `provenance` param | threaded value, never re-detected | ✓ WIRED | Live manifest showed `"provenance": "fresh-claude"` / `"auto-applied-from-profile"` correctly in both scenarios tested. |
| **`learning` store's saved `structural_hint`** | **`cli.py::resolve_or_ask`/`parse()` on a later run** | **automatic replay via `_try_replay_saved_hint`** | ✓ **WIRED (gap closed)** | Was NOT WIRED at initial verification. `cli.py::run()` now calls `_try_replay_saved_hint()` on a `StructureQuestion` with no explicit `--hint`; it re-parses with each saved profile's `structural_hint` and accepts the first exact-signature match. Live-reconfirmed, see "Gap Resolution" below. |

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| VAL-01 | 03-02 | ✓ SATISFIED | Truth 1, live repro, tests pass. |
| VAL-02 | 03-02 | ✓ SATISFIED | Truth 2, live repro, tests pass. |
| VAL-03 | 03-02 | ✓ SATISFIED | Truth 3, live repro, tests pass. |
| LEARN-01 | 03-01 | ✓ SATISFIED | Truth 4 (signature half), live repro. |
| LEARN-02 | 03-01 | ✓ SATISFIED | Truth 4 (save-gated-on-clear), live repro + `tests/test_learning_loop_cli.py::test_save_profile_flag_refuses_to_save_a_blocked_mapping`. |
| LEARN-03 | 03-01 | ✓ SATISFIED | Truth 4 (auto-apply at 1.0, no Claude call), live repro. |
| LEARN-04 | 03-01 | ✓ SATISFIED | Truth 4 (mismatch falls back), `test_a_seeded_profile_for_a_different_signature_never_auto_applies`. |
| LEARN-05 | 03-01 | ✓ SATISFIED | `test_one_field_set_may_hold_several_profiles` — one field set, two signatures, both retrievable. |
| **LEARN-06** | 03-01 | **✓ SATISFIED (gap closed)** | Was BLOCKED at initial verification (persisted but never replayed). Fixed by commits b871042/d6c6ff9; `_try_replay_saved_hint()` now retries a saved `structural_hint` and only accepts an exact `column_signature` match. Live re-repro passes; `tests/test_hint_replay_cli.py` (3 tests) pass. REQUIREMENTS.md's "Complete" status is now accurate. |
| EXPORT-02 | 03-03 | ✓ SATISFIED | Truth 6, live repro (CSV + xlsx written and re-openable). |
| EXPORT-03 | 03-03 | ✓ SATISFIED | Truth 6, live repro (JSON array of records, unicode-safe). |
| EXPORT-04 | 03-03 | ✓ SATISFIED | Truth 6, live repro (manifest shape matches D-09). |

No orphaned requirements: all 12 phase-declared requirement IDs (VAL-01..03, LEARN-01..06, EXPORT-02..04) appear in exactly one plan's frontmatter and are cross-referenced in REQUIREMENTS.md's Phase 3 traceability table.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/assayingest/validation/validator.py` | 165-172 (`_check_column`) | IN-02 (from 03-REVIEW.md, not fixed): blank cell `""` in an `allowed_values`-constrained column is flagged as a violation rather than skipped. | ℹ️ Info | Fail-closed (safe) direction, not a correctness defect — explicitly deferred to a builder product decision per 03-REVIEW.md's resolution note. Flagging here only because it can perpetually block the "zero yellow" money-shot demo if a chosen preset/file combination has sparse allowed_values cells; not a phase-goal blocker. |

No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers found in any file modified by this phase (`learning/`, `validation/`, `export/`, `cli.py`, `domain/models.py`, `mapping/mapper.py`).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Column signature order/case/ws invariance | live Python: `column_signature(...)` equality check | `True` | ✓ PASS |
| Full test suite | `.venv/bin/pytest -q` | 391 passed, 4 skipped (live-API-key tests, expected) | ✓ PASS |
| Named Phase-3 test files | `pytest tests/test_signature.py tests/test_profile_store.py tests/test_learning_loop_cli.py tests/test_validator.py tests/test_validator_strictness.py tests/test_validator_cli.py tests/test_export_writers.py tests/test_export_cli.py tests/test_headers_only.py` | 77 passed | ✓ PASS |
| Validator flags a violating value and blocks export | live `cli.run()` with a deliberately-violating fake mapping | exit 5, no files written | ✓ PASS |
| Money-shot: save profile, auto-apply zero-yellow no Claude call | live `cli.run()` twice (batch01 save, batch02 auto-apply with `propose_mapping` raising if called) | exit 0 both times, provenance `auto-applied-from-profile`, confidence 1.0, `propose_mapping` never invoked | ✓ PASS |
| Clean export writes CSV/xlsx/JSON/manifest | live `cli.run(..., export=True, output_dir=...)` on a fully-clear fake mapping | exit 0, exactly 4 files written with correct manifest shape | ✓ PASS |
| **LEARN-06 hint replay** | live `cli.run()` on `verity_reagents_stock.xlsx` with `--hint header-row=2` (parses OK), then a second `cli.run()` on the same file with no hint | Initial: reproduced the identical `StructureQuestion`, exit 4 (BLOCKED). **Re-checked post-fix: second run exits 0, prints "replayed saved structural hint from profile ...", auto-applies at confidence 1.0, never calls `propose_mapping`.** | ✓ **PASS (gap closed)** |
| Full test suite (post-fix) | `.venv/bin/pytest -q` | 394 passed, 4 skipped (live-API-key tests, expected) | ✓ PASS |

### Human Verification Required

None — the LEARN-06 gap was a concretely reproduced, programmatically-verifiable failure (not a judgment call), and its closure was verified the same way: a live repro re-run plus a new automated test suite.

### Gap Resolution

**LEARN-06/SC5 — resolved.** The roadmap's SC5 and REQUIREMENTS.md's own wording both require that
a structural hint saved with a profile causes "the same odd layout [to] parse... automatically next
time without re-asking." At initial verification the implementation only persisted the hint (a
real, tested round-trip through SQLite) — it never retrieved and reapplied a stored hint to resolve
a subsequent file's `StructureQuestion`.

Fixed by two commits, test-first:

- `b871042` — `test(03): add failing test for structural-hint replay (LEARN-06/SC5)` —
  `tests/test_hint_replay_cli.py`, confirmed RED against pre-fix `cli.py` (second run returned
  exit 4, not 0).
- `d6c6ff9` — `fix(03): replay a saved profile's structural hint automatically (LEARN-06/SC5)` —
  `src/assayingest/cli.py`. `run()` now calls a new `_try_replay_saved_hint()` whenever parsing
  returns a `StructureQuestion` and no explicit `--hint` was given: it iterates
  `store.list_for_field_set(field_set.signature)`, re-parses with each candidate profile's
  `structural_hint` via the new `_reparse_with_hint()` helper (which fails closed to `None` — never
  crashes — on `FileNotFoundError`/`ValueError`/`IndexError`, since a stale or unrelated-file hint
  is now reachable automatically rather than only via a deliberate human `--hint`), and accepts the
  FIRST candidate whose re-parsed table's `column_signature` exactly equals that profile's own
  stored `column_signature` — the same exact-signature guarantee LEARN-03/04 already require for
  mapping auto-apply, applied here to the hint itself (fail-closed: a hint that resolves a
  structurally-similar but genuinely different file's structure is rejected because its signature
  differs, never silently applied). A successful replay reuses the existing auto-apply path
  unchanged (via `_map_and_report` → `_resolve_proposal` → `store.find`), so it also maps at
  confidence 1.0 with no Claude call, and prints a transparency line ("replayed saved structural
  hint from profile `<id>`") before the existing "applied saved profile ... (no Claude call)" line
  (D-08). An explicit `--hint` always takes precedence and is never routed through replay.

Verification of the fix:

- Live repro re-run: the exact scenario this gap documented (parse
  `data/synthetic/verity_reagents_stock.xlsx` with `--hint header-row=2`, save a profile; re-run
  the SAME file with NO `--hint` and NO credentials) now exits 0, prints the replay transparency
  line, auto-applies the saved mapping at confidence 1.0, and `propose_mapping` is never called
  (asserted via a raising monkeypatch).
- New tests, `tests/test_hint_replay_cli.py` (3 tests, all pass):
  `test_second_run_with_no_hint_replays_saved_hint_and_auto_applies` (the money-shot repro above),
  `test_explicit_hint_always_wins_over_replay` (a human's own `--hint` is never second-guessed by
  replay), `test_mismatched_file_with_replayed_hint_still_asks_the_human` (fail-closed control: a
  different odd-layout `.xlsx` fixture, structurally similar enough to also be ambiguous on its own
  and to reparse successfully under verity's saved `header-row=2` hint, but whose resulting
  `column_signature` differs from the saved profile's — the tool still surfaces the
  `StructureQuestion`, exit 4, and never prints a replay line).
- Full suite: `.venv/bin/pytest -q` → 394 passed, 4 skipped (live-API-key tests, unchanged) — up
  from 391 passed / 4 skipped at initial verification, +3 for the new hint-replay tests.
- REQUIREMENTS.md's LEARN-06 "Complete" checkbox and traceability-table status, which this
  verification's first pass found to be inaccurate against the code, are now genuinely accurate.

Phase 3 delivers its full scope correctly and demonstrably: the no-LLM validator (VAL-01/02/03) is
real, additive-only, and runs identically on both the fresh-Claude and auto-applied paths; the
learning-loop signature/profile/store/reconstruction machinery (LEARN-01..06) is correct,
live-verified end-to-end including the exact money-shot scenario (second same-lab file auto-maps at
confidence 1.0 with zero Claude calls) and the structural-hint replay scenario closed above; the
export writers and provenance manifest (EXPORT-02..04) are correct and live-verified; and all five
03-REVIEW.md findings (CR-01 privacy leak, WR-01 duplicate/blank fail-closed, WR-02 NaN fail-open,
WR-03 crash, IN-01 dead code) are genuinely fixed in the code, not merely claimed fixed.

---

_Verified: 2026-07-10T22:40:00Z (initial verification, gap found)_
_Gap resolved: 2026-07-10 (commits b871042, d6c6ff9)_
_Verifier: Claude (gsd-verifier / gsd-execute-phase)_
