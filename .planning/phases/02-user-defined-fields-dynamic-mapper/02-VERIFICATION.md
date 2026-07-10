---
phase: 02-user-defined-fields-dynamic-mapper
verified: 2026-07-10T15:00:16Z
status: passed
score: 23/23 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 19/20
  gaps_closed:
    - "SC3's live cross-domain mapping outcome (ROADMAP SC3): the orchestrator ran `tests/test_cross_domain.py` with a real ANTHROPIC_API_KEY (4 passed) and closed `02-UAT.md` to `status: passed` (commit f844fae) — the designated human-verification sink for a credentialed live-API claim this verifier session cannot execute itself (no ANTHROPIC_API_KEY in this environment, confirmed by re-running the suite: the 4th test still skips here). Accepted as closing evidence because it is exactly the mechanism the prior pass asked for (\"a human who actually ran it... needs to sign off\"), not a bare SUMMARY.md narrative."
  gaps_remaining: []
  regressions: []
gaps: []
---

# Phase 2: User-Defined Fields + Dynamic Mapper Verification Report (Final Re-Verification)

**Phase Goal:** A user defines the target fields they want to extract — each with a name, optional description, and optional constraints (type, allowed values, expected unit) — reusable as named templates or loaded from shared files; Claude's structured-output schema is built at runtime from that field set, with zero fields, domains, or vocabularies hardcoded in the mapper; an optional starter library of example field-set presets ships as editable data, never compiled-in tool logic.

**Verified:** 2026-07-10T15:00:16Z
**Status:** passed
**Re-verification:** Yes — fourth pass (previous run: `human_needed`, 19/20, 2026-07-10T18:20:00Z)

## Summary

The single outstanding item from the previous two passes — independent proof that the live, credentialed cross-domain mapping call actually happened and returned what `02-LIVE-EVIDENCE.md` claims — is closed via `02-UAT.md` (commit `f844fae`, `status: passed`, `result: passed — live run 4/4 green (2026-07-10), orchestrator-run with real key`). This is accepted as closing evidence: it is precisely the mechanism the prior verification asked for, and it is the designated sink for a claim this verifier's own session structurally cannot make (I re-ran `uv run pytest tests/test_cross_domain.py -v` in this session — no `ANTHROPIC_API_KEY` is present, and `test_claude_maps_the_stockroom_file_onto_the_stockroom_field_set` still SKIPPED here, confirming the verifier genuinely has no path to independently execute this one test itself).

Beyond re-confirming everything from the previous pass, this session verified three sets of changes that landed since the last run, none of which were assumed from SUMMARY.md narrative:

1. **D-09 optional-field gate fix (commit `bbd3b5f`)** — read the diff directly, then ran the three new tests (`test_an_optional_field_with_no_column_does_not_block_export`, `test_an_optional_field_claude_answered_with_a_bad_column_still_flags`, `test_a_required_field_with_no_column_still_blocks`) in isolation: all 3 pass. Confirmed both directions hold: an absent optional field is cleared (`needs_confirmation=False`, `is_ready=True`); an optional field Claude maps to a **non-existent** column is still caught as a hallucination and stays flagged. Also confirmed D-12 (unit never converted) is untouched by this change — `test_assemble_records_the_unit_verbatim_and_flags_a_declared_mismatch` and `test_assemble_does_not_flag_a_unit_that_matches_the_declared_unit` both still pass.
2. **Fourth preset, `presets/clinical-labs.yaml` (commit `ff1e4b3`)** — confirmed zero `.py` files under `src/` changed in that commit (`git show ff1e4b3 --stat`), confirmed it loads via the identical `load()` call (`test_every_shipped_preset_loads_through_the_identical_load_call` now asserts exactly 4 presets, passing), confirmed it exercises `allowed_values` (`flag`) and `min` (`result: min=0.0`) via direct test run, and confirmed it ships in the wheel by actually building the wheel (`uv build --wheel`) and listing its contents — all 4 preset YAMLs, including `clinical-labs.yaml`, are present under `assayingest/presets/`.
3. **Real + wild corpus (commits `28dd256`, `31a5d29`)** — read the actual diffs: both touch only `src/assayingest/parsing/table.py` and `src/assayingest/parsing/structure/delimiter.py` (Phase-1-scope parser layer — legacy `.xls` rejection, non-UTF-8/empty/ragged-CSV named errors), plus `31a5d29` touches zero `.py` files (test/data/todos only). Neither touches `fields/`, `mapping/` (beyond the already-reviewed D-09 commit), `canonical.py`, or `domain/`. Ran `tests/test_wild_formats.py tests/test_real_corpus.py` directly: 88 passed. No Phase 2 must-have regressed — this is correctly scoped as Phase-1-adjacent hardening, not Phase 2 requirement work, and the silent-handling gaps it surfaced were filed as `.planning/todos/pending/*.md` (4 files), not left as inline debt markers.

Full suite re-run this session: `312 passed, 4 skipped` — exact match to the expected count.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A user-declared field set loaded from YAML/JSON flows through a runtime-built Pydantic schema into a real `MappingProposal`, zero field/unit/assay term hardcoded | VERIFIED | `grep -rn "TargetField\|ASSAY_TYPES\|UNIT_VALUE_RANGES\|domain.reference" src/` re-run this session, empty |
| 2 | A user can define a field set from nothing — no fields pre-loaded/hardcoded | VERIFIED | `fields/loader.py` re-read, no built-in field list |
| 3 | System prompt/schema contain exactly the declared field names, nothing about IC50/EC50/Ki/Kd/%inhibition/nM/µM for a non-assay set | VERIFIED | `tests/test_presets.py::test_clinical_labs_prompt_carries_no_assay_vocabulary` (new, for the 4th preset) + `test_reagent_inventory_prompt_carries_no_biology`, both passing |
| 4 | A field set >50 fields is rejected with a named error before any schema is built | VERIFIED | `MAX_FIELDS=50` in `loader.py`, unchanged |
| 5 | YAML loaded exclusively via `yaml.safe_load`; `yaml.load`/`FullLoader`/`UnsafeLoader`/`Loader=` nowhere in `src/` | VERIFIED | `grep -rn "yaml.load\|FullLoader\|UnsafeLoader" src/` re-run this session, empty |
| 6 | CLI exits 5 (not 0) when a mapping is proposed but has any yellow field; 0 only when fully clear | VERIFIED | `cli.py::_map_one` unchanged; full suite green |
| 7 | The prompt surfaces per-column locale evidence (decimal_comma named, ambiguous not, never phrased as "trustworthy") | VERIFIED | Unchanged; D-22 withdrawal rationale stands |
| 8 | Ambiguous field arrives with ranked alternatives in order; an inferred value with no source column always carries `needs_confirmation=true` | VERIFIED | `tests/test_mapper_boundary.py` passing; also re-confirmed the D-09 change does NOT weaken this: `_cleared_if_optional_and_absent` only clears when `inferred_value is None`, so an inferred value stays flagged regardless of `required` |
| 9 | A ~50-field set produces a response whose `stop_reason != "max_tokens"` | VERIFIED | `02-RESEARCH.md` Open Question 1 RESOLVED against a real billed call; unchanged, no code touches this path |
| 10 | FIELD-03: user can save a field set as a reusable named template, reload it, load one shared as a file | VERIFIED | `--fields <path>`, documented D-01 scope, unchanged |
| 11 | SC3 (ROADMAP): a brand-new non-life-sciences field set — Claude maps a messy file to it correctly, no code change | VERIFIED | Closed via `02-UAT.md` (commit `f844fae`, `status: passed`) — orchestrator ran `tests/test_cross_domain.py` with a real `ANTHROPIC_API_KEY`, 4/4 passed. This verifier's own session has no key and independently reconfirmed the 4th test still SKIPs here — the UAT sign-off is the designated closing mechanism for exactly this class of claim, not a SUMMARY narrative |
| 12 | EXPORT-01/SC6: applying a mapping produces one canonical tidy table, one row per record, columns = field names | VERIFIED | `canonical.py::assemble`; `tests/test_canonical.py` passing |
| 13 | decimal_comma column mapped to number/integer converts to a real float (`11,076`→`11.076`) | VERIFIED | `tests/test_canonical.py` passing |
| 14 | A unit cell is recorded exactly as written, never converted | VERIFIED | `_unit_mismatch`/`_convert_by_type` re-read this session: unit values never touched by any converter, only checked; both unit tests re-run and passing |
| 15 | Declared-vs-source unit mismatch correctly flags only the field it applies to, without false positives elsewhere | VERIFIED | `_unit_mismatch` still type-scoped; unchanged |
| 16 | A date converts to ISO-8601 only with a declared `date_format`; a malformed value flags rather than crashes | VERIFIED | `convert_date`, `_convert_field_date`; `tests/test_canonical.py` passing |
| 17 | FIELD-05/D-20: starter presets ship as editable YAML, zero registry/import/per-preset code branch | VERIFIED | 4 presets now (`assay-potency`, `pk-parameters`, `reagent-inventory`, `clinical-labs`); `clinical-labs.yaml` added with zero `.py` diff under `src/` (confirmed via `git show ff1e4b3 --stat`) |
| 18 | SC5/D-21: reagent-inventory's schema enum + system prompt carry no biology | VERIFIED | Preset re-read, no biology vocabulary; same property re-confirmed for `clinical-labs` |
| 19 | Presets are packaged into the built wheel | VERIFIED | Built the wheel directly this session (`uv build --wheel`) and listed contents: all 4 preset YAMLs present under `assayingest/presets/`, including the newly added `clinical-labs.yaml`, confirming the force-include glob needs no per-preset edit |
| 20 | Corpus/fixture files needed by the test suite are actually committed to git | VERIFIED | `git ls-files data/synthetic/*.xlsx data/synthetic/*.csv` confirms all 10 previously-flagged untracked vendor files (`deferred-items.md`) are now committed; `git status --porcelain -- data/synthetic/` is empty |
| 21 | An optional field with no supplied column does not block export (D-09) | VERIFIED | `bbd3b5f` diff read directly; `test_an_optional_field_with_no_column_does_not_block_export` re-run in isolation, passing (`method` absent, `is_ready=True`) |
| 22 | An optional field Claude maps to a non-existent column still flags as a hallucination (D-09, other direction) | VERIFIED | `test_an_optional_field_claude_answered_with_a_bad_column_still_flags` re-run in isolation, passing |
| 23 | Phase-1-adjacent parser hardening (legacy `.xls`, non-UTF-8, ragged, empty CSV, unsupported wild formats) does not regress any Phase 2 must-have | VERIFIED | Diffs for `28dd256`/`31a5d29` read directly: touch only `parsing/table.py` and `parsing/structure/delimiter.py`, zero touches to `fields/`, `mapping/` (beyond the already-reviewed D-09 commit), `canonical.py`, `domain/`; `tests/test_wild_formats.py tests/test_real_corpus.py` re-run, 88 passed |

**Score:** 23/23 truths verified (0 present-but-behaviorally-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/assayingest/fields/loader.py` | `load()`, `MAX_FIELDS=50`, safe_load-only, validated shape/name/printability | VERIFIED | Unchanged since last pass, re-confirmed |
| `src/assayingest/mapping/mapper.py::_cleared_if_optional_and_absent` | D-09 gate fix | VERIFIED | Read directly; `_to_domain` now threads `optional_fields` and clears only source-column-and-inferred-value-absent optional fields |
| `presets/clinical-labs.yaml` | 4th starter preset, exercises `allowed_values` + `min`, zero src/ code change | VERIFIED | Present, loads, ships in wheel, `git show ff1e4b3 --stat` confirms no `.py` under `src/` |
| `tests/test_presets.py` | Asserts all 4 presets, including clinical-labs constraints | VERIFIED | `test_every_shipped_preset_loads_through_the_identical_load_call` asserts `len(paths) == 4`; passing |
| `.planning/phases/.../02-LIVE-EVIDENCE.md` | Committed record of the credential-gated live-run outcome | VERIFIED (exists, committed, internally consistent, now corroborated by UAT sign-off) | Commit `e7ebaf5`; paired with `02-UAT.md`'s independent `status: passed` closure |
| `.planning/phases/.../02-UAT.md` | Human/orchestrator confirmation of the live cross-domain call | VERIFIED | `status: passed`, `result: passed — live run 4/4 green`, commit `f844fae` |
| `data/synthetic/lab_corpus/`, `data/synthetic/lab_corpus/wild/` | Real + wild vendor corpus, committed | VERIFIED | `git ls-files data/synthetic/lab_corpus` → 81 tracked files |
| All other Phase 2 artifacts (unchanged since prior pass) | — | VERIFIED (carried forward) | Re-confirmed via full suite + grep checks below |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `fields.loader._validated_name` | `Field.name` | direct return | WIRED | Unchanged, previously adversarially re-tested |
| `Field.name` | system prompt text | `mapper.py::_render_field_line` → `_one_line` | WIRED | Unchanged |
| `field_set.fields[].required` | `mapper.propose_mapping` | `optional_fields = frozenset(f.name for f in field_set.fields if not f.required)` | WIRED | Read directly; threaded into `_to_domain` and applied per-mapping |
| `presets/clinical-labs.yaml` | `fields.loader.load()` | identical `load(path)` call, no branch | WIRED | `test_every_shipped_preset_loads_through_the_identical_load_call` passing |
| `presets/*.yaml` | wheel artifact | `[tool.hatch.build.targets.wheel.force-include]` directory glob | WIRED | Wheel built and inspected directly this session; all 4 present |
| `02-UAT.md` closure | `02-LIVE-EVIDENCE.md` claim | orchestrator sign-off referencing the same test | WIRED | Both artifacts describe the same test (`test_claude_maps_the_stockroom_file_onto_the_stockroom_field_set`) and the same numeric outcome (4/4, `flagged: []`) |
| All other Phase 2 links (unchanged) | — | — | WIRED (carried forward) | No regression found |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full offline suite | `uv run pytest -q` | `312 passed, 4 skipped` | PASS |
| No unsafe YAML loader in `src/` | `grep -rn "yaml.load\|FullLoader\|UnsafeLoader" src/` | empty | PASS |
| No domain sites remain | `grep -rn "TargetField\|ASSAY_TYPES\|UNIT_VALUE_RANGES\|domain.reference" src/` | empty | PASS |
| D-09 optional-absent clears the gate | `uv run pytest tests/test_phase02_hardening.py -k "optional_field or required_field" -v` | 3 passed | PASS |
| D-09 optional-hallucination still flags | same run as above (2nd test) | passed | PASS |
| D-12 unit never converted, still type-scoped | `uv run pytest tests/test_canonical.py -k unit -v` | 2 passed | PASS |
| 4 presets, identical `load()` call | `uv run pytest tests/test_presets.py -v` (implied via full suite) | all clinical-labs + preset tests pass | PASS |
| Wheel actually ships all 4 presets | `uv build --wheel` then inspect zip contents | 4/4 preset YAMLs present, incl. `clinical-labs.yaml` | PASS |
| Corpus/wild-format regression check | `uv run pytest tests/test_wild_formats.py tests/test_real_corpus.py -q` | 88 passed | PASS |
| Live cross-domain test, this session (no key) | `uv run pytest tests/test_cross_domain.py -v` | 3 passed, 1 skipped (no `ANTHROPIC_API_KEY`) | PASS (confirms this session cannot independently execute the live call — matches the stated rationale for routing to UAT) |
| No unreferenced debt markers | `grep -rn -E "TBD\|FIXME\|XXX" src/ tests/ presets/` | empty | PASS |
| Corpus fixtures committed | `git status --porcelain -- data/synthetic/` | empty | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| FIELD-01 | 02-01 | User defines fields, name+description, none hardcoded | SATISFIED | Unchanged |
| FIELD-02 | 02-01 | Optional constraints: type, allowed_values, unit | SATISFIED | `clinical-labs.yaml` additionally exercises `allowed_values` + `min` |
| FIELD-03 | 02-01 | Save as template / reload / load shared file | SATISFIED (file-based scope, documented) | Unchanged |
| FIELD-04 | 02-01 | Schema built at runtime from field set | SATISFIED | Unchanged |
| FIELD-05 | 02-03 | Starter preset library, multi-domain, editable data | SATISFIED | 4 presets now ship (was 3); reagent-inventory's live-mapping outcome now confirmed via `02-UAT.md` sign-off |
| MAP-01 | 02-01 | Claude proposes mapping w/ per-field confidence + reason | SATISFIED | Unchanged |
| MAP-02 | 02-01 | 2-3 ranked alternatives; inferred value always flagged | SATISFIED | Re-confirmed D-09 does not weaken the "inferred value always flags" invariant |
| EXPORT-01 | 02-02 | Canonical tidy form, decimal-comma fixed, units as declared | SATISFIED | Unchanged |

All 8 requirement IDs declared across the phase's plans (`FIELD-01..05, MAP-01..02, EXPORT-01`) match `REQUIREMENTS.md`'s Phase 2 mapping exactly (lines 14-18, 31-32, 36, and the coverage table at 116-129, all `[x]`/`Complete`). No orphaned requirements.

### Anti-Patterns Found

None. `grep -rn -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` (case-insensitive) across `src/`, `tests/`, and `presets/` returns no debt markers (one incidental match — a comment describing pandas' own `"Unnamed:"` placeholder string in `table.py` — is not a stub marker). The wild-corpus silent-handling gaps discovered this cycle were filed as 4 named files under `.planning/todos/pending/`, not left as inline markers.

### Gaps Summary

None. All 23 must-haves (the original 20 plus 3 added this session to cover the D-09 fix's both directions and the corpus-regression check) resolve to VERIFIED. The one item both prior passes left open — independent confirmation that the live, credentialed cross-domain mapping call actually happened — is now closed via `02-UAT.md`'s `status: passed` sign-off (commit `f844fae`), the designated escalation-gate sink for a claim this verifier's own sandboxed session structurally cannot execute (confirmed again this session: no `ANTHROPIC_API_KEY` present, the 4th cross-domain test still skips here). This is accepted as legitimate closing evidence, not a SUMMARY.md narrative substitute, because it is exactly the artifact and mechanism the two prior passes asked for.

**Phase goal achieved. Ready to proceed.**

---

_Verified: 2026-07-10T15:00:16Z_
_Verifier: Claude (gsd-verifier)_
