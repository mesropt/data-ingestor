# Phase 11: Multi-Sheet Ingest - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-13
**Phase:** 11-multi-sheet-ingest
**Areas discussed:** Upload order (when the Schema is chosen), Merge semantics, Row provenance, Schema-proposal threshold, N-datasets flow

**Origin:** the phase was reopened by the builder's question — *"я пытаюсь загрузить многолистный файл, но откуда мне как пользователю знать для какого листа какая схема должна подойти?"* Phase 11 as originally written covered sheet selection but assumed a single Schema chosen upfront for the whole workbook. SHEET-05 was added to the roadmap before this discussion.

---

## Upload order — when the Schema is chosen

| Option | Description | Selected |
|--------|-------------|----------|
| Schema optional everywhere | Every file (incl. CSV / single-sheet) parses first, then the server proposes a Schema. Uniform, but rewrites the whole happy path and its tests. | |
| Ask only on multi-sheet workbooks | Schema stays optional on input; a multi-sheet workbook without a Schema returns a new `sheet_question` arm. Single-sheet + Schema keeps the existing path, no regression. | ✓ |
| Separate `/api/inspect` endpoint | Upload → manifest → second call to `/api/upload` with chosen sheets. Conceptually clean, but doubles the upload or needs a second retention mechanism beside `upload_token`. | |

**User's choice:** Ask only on multi-sheet workbooks.
**Notes:** Keeps the parse-first inversion scoped to the case where the ambiguity actually exists. `tests/api/test_upload.py` and `test_money_shot.py` pin the current single-sheet contract; this avoids invalidating them.

---

## Merge semantics (SHEET-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Merge within one Schema, by canonical fields | Only sheets resolving to the same Schema may merge; the crosswalk absorbs header-spelling differences. | |
| Strictly identical column signature | Byte-for-byte matching signatures only — refuses exactly the case the crosswalk was built for. | |
| Allow merging across different Schemas | Union of fields, blanks where absent. Produces a dataset belonging to no governed Schema. | |
| **Free text: "Без мёрджа. Его не должно быть вообще."** | No merge at all — the capability should not exist. | ✓ |

**User's choice:** No merge, anywhere. The capability is struck from the product.
**Notes:** This was volunteered against all three offered options. Consequences taken immediately: **SHEET-02 struck** from REQUIREMENTS.md (moved to Out of Scope, not Future Requirements — it is not a "later" idea), removed from the Phase 11 goal and success criteria in ROADMAP.md, and coverage recounted 28 → 27. SHEET-04's cross-sheet-disagreement clause became moot as a direct consequence and was struck with it: if every sheet is its own dataset, two sheets resolving the same column to different date orders is not a contradiction.

---

## Scope follow-up — what "multi-sheet ingest" means without a merge

| Option | Description | Selected |
|--------|-------------|----------|
| N sheets = N independent datasets | Human ticks N sheets, each with its own Schema, mapping, confirm gate and export. One upload → N runs. | ✓ |
| Strictly one sheet per upload | Informed picker, but to get three sheets you upload the file three times. | |
| One sheet now, a queue later | Ship the informed single-sheet choice; defer multi-ingest to a future phase. | |

**User's choice:** N sheets = N independent datasets.
**Notes:** Asked because "no merge" left SHEET-01 ("one sheet or several merged") undefined. This is the expensive answer — `UploadEntry.table`, `canonical.assemble`, `confirm` and `export` are all single-table today — and it was chosen with that cost stated.

---

## Row provenance (SHEET-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Reserved meta column in the export | `CanonicalTable` gains an explicit provenance field; writers append a reserved trailing column. Schema stays clean; validator and mapper never see it. | ✓ |
| A real `Field` in the `FieldSet` | Flows through existing paths untouched — but changes `FieldSet.signature`, silently invalidating every learned profile. | |
| Manifest only, not in rows | Cheap, but does not satisfy SHEET-03: the exported row stays anonymous. | |

**User's choice:** Reserved meta column.
**Notes:** The decisive argument is the signature: a new `Field` would change `FieldSet.signature` and every previously learned profile would quietly stop matching — breaking the learning loop, which is the product's differentiator. Constraint discovered while scouting: `write_csv`'s `DictWriter` **raises** on extra keys and `write_xlsx` **silently drops** them, so the column must be threaded through the writers deliberately, not smuggled into `records`.

---

## Schema-proposal threshold (SHEET-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Always pre-fill, never auto-apply | Sheet screen always shown for a multi-sheet workbook; best Schema pre-selected with coverage displayed; a human always confirms. No threshold to tune. | ✓ |
| Auto-apply on an exact learned-profile hit | Stronger demo (a repeat file flies straight through), but reintroduces a silent tool decision about what to ingest. | |
| Numeric coverage threshold | e.g. ≥ 80% + margin over runner-up → apply silently. Fewer clicks, but the threshold needs justifying and its failure is silent. | |

**User's choice:** Always pre-fill, never auto-apply.
**Notes:** Consistent with the project's first principle. Deliberately unlike `rank_sheets`'s existing `_CONFIDENCE_MARGIN = 0.1` — no threshold means no threshold to get wrong. Zero coverage → propose *skip*; a tie is shown as a tie, not broken by the tool.

---

## N datasets through Review and export

| Option | Description | Selected |
|--------|-------------|----------|
| Sequential queue | N tokens, Review opens them one at a time ("Sheet 2 of 3"). Backend stays single-table — all new complexity on the frontend. | |
| All at once, one Review with tabs | Every dataset visible, each confirmed on its own gate, exported in one action (archive of N). Better product; requires a run-group concept in the backend and an export-route rewrite. | ✓ |

**User's choice:** All at once, tabbed Review.
**Notes:** Chosen over the cheaper queue with the cost stated explicitly (D-11-11). This is the largest single engineering item in the phase.

---

## Claude's Discretion

- Whether per-sheet header extraction reuses `rank_sheets`'s already-materialized `rows_by_sheet` or re-reads via `grid`; whether `SheetRanking` widens or a new dataclass carries `(name, score, headers, row_count, signature)`.
- Whether `_prefill_coverage` / `_vendor_agnostic_alias_index` / `field_set_from_schema` are imported as-is or promoted behind a public scorer API.
- The concrete shape of the run group (group id owning N tokens vs. one entry holding N tables).
- The reserved column's name, how each of the three writers surfaces it, and whether the archive is zip or tar.
- The sheet-selection screen's layout, within the constraint that coverage must be visible.

## Deferred Ideas

- **None deferred to a later phase.** The one capability raised and rejected — merging sheets (SHEET-02) — was struck from the product outright, not postponed. It must not be resurrected as future work.
- Four pending parser todos (`parser-encoding-detection`, `parser-excel-hazards`, `parser-legacy-xls`, `parser-ragged-and-preamble`) matched this phase on the shared `area: parsing` tag alone. Reviewed, none folded — all are parser-hardening concerns untouched by sheet selection, Schema proposal, or row provenance.
