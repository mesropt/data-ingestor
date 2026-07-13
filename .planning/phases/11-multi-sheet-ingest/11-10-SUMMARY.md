---
phase: 11-multi-sheet-ingest
plan: "10"
subsystem: ui
tags: [react, typescript, vitest, jsdom, tabs, base-ui, forcemount, state-loss, tdd]
status: complete

# Dependency graph
requires:
  - phase: 11-09
    provides: "The seam this plan fills: the `sheetGroup` reducer phase carrying `response` + `groupId`, the SheetGroupResponse/SheetMember/SheetMemberResponse client types, and Upload.tsx's deliberate `sheet_group` no-op"
  - phase: 11-08
    provides: "GET /api/export/group/{group_id}/archive — the route the Download All bar calls, and its 409-naming-the-count refusal while any member is unconfirmed"
  - phase: 10-frictionless-correct-ingest
    provides: "The Review screen (its local amber-resolution state IS the hazard this plan closes), ConfirmGate, ExportBar, StructuralHintPanel/DateFormatQuestionPanel reused verbatim inside a member tab"
provides:
  - "components/ReviewGroupTabs.tsx (NEW): member tab strip + kept-mounted panes + the group Download All bar; N=1 renders neither"
  - "state/review.ts: memberStatus, groupExportBlockedReason, showTabStrip, memberPaneKey, provenanceLine — every tab/group decision as a tested pure function"
  - "screens/Review.tsx: the mono 'sheet {name}' provenance line (EVERY ingest, D-11-15) + optional onMappingsChange/onConfirmed reporting for a group parent"
  - "components/ExportBar.tsx: the reserved __source_sheet note"
  - "lib/api.ts: downloadGroupArchive(groupId)"
  - "App.tsx: the sheetGroup phase routes to ReviewGroupTabs, keyed by group_id"
affects:
  - "Phase 11 is complete — this was the last plan. The multi-sheet flow is end-to-end."

# Tech tracking
tech-stack:
  added:
    - "jsdom (devDependency, test-only) — the ONE install; see Deviations. No runtime dependency added, no shipped bytes changed."
  patterns:
    - "The installed primitive is @base-ui/react, whose Tabs.Panel spells Radix's `forceMount` as `keepMounted` (it renders the inactive pane with `hidden` + `inert` itself). The UI-SPEC's `forceMount` requirement is satisfied by `keepMounted` — same guarantee, different spelling in this registry."
    - "Child-owns-state, parent-mirrors: Review remains the SOLE owner of its resolution state and REPORTS it up (onMappingsChange/onConfirmed). The parent never controls it — lifting the state would re-create the very remount/reset hazard the tabs exist to close."
    - "A mount-lifecycle claim cannot be pinned by a pure function: exactly one jsdom file (ReviewGroupTabs.test.tsx) renders for real and drives the actual hazard; every other derivation stays a node-env pure-function test."

key-files:
  created:
    - frontend/src/components/ReviewGroupTabs.tsx
    - frontend/src/components/ReviewGroupTabs.test.tsx
    - .planning/phases/11-multi-sheet-ingest/deferred-items.md
  modified:
    - frontend/src/state/review.ts
    - frontend/src/state/review.test.ts
    - frontend/src/screens/Review.tsx
    - frontend/src/screens/Upload.tsx
    - frontend/src/components/ExportBar.tsx
    - frontend/src/lib/api.ts
    - frontend/src/App.tsx
    - frontend/package.json

key-decisions:
  - "The tab-switch state-loss hazard (T-11-37) is pinned by a REAL DOM test, not asserted by grep. A grep for `forceMount` proves a string is present; it does not prove a curator's work survives. The test was verified to FAIL (`expected '1 of 2 resolved' to match /2 of 2/`) with keepMounted removed — that failing message IS the curator's work being destroyed. This required installing jsdom (one dev-only package), a deliberate deviation from the plan's zero-install claim."
  - "Review REPORTS its state upward (onMappingsChange/onConfirmed) rather than having it lifted into ReviewGroupTabs. Lifting would have made the parent the owner and re-introduced the reset risk from above; reporting keeps the child the single owner while giving the tab badges and the group bar a live read."
  - "The group bar is an <a download> when unblocked and a disabled <Button> when blocked — never an enabled link with a client-side guard. There is no DOM path to the archive URL until every member is confirmed, and the server refuses it independently anyway (409)."
  - "`groupExportBlockedReason` appends the outstanding count once confirmations diverge from the total ('— 1 still unconfirmed'), mirroring the server's own 409 detail. The bare UI-SPEC sentence is used while nothing is confirmed, where a count would be redundant with the total."

requirements-completed: [SHEET-01, SHEET-03]

coverage:
  - id: D1
    description: "Member status, the group-export gate, the N=1 predicate, the tab-blind pane key, and the provenance line — all pure, all tested, no DOM"
    requirement: SHEET-01
    verification:
      - kind: unit
        ref: "frontend/src/state/review.test.ts — memberStatus (all four states), groupExportBlockedReason (both outcomes + 'confirming one member never unblocks the group'), showTabStrip (N=1 false), memberPaneKey, provenanceLine (17 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "T-11-37 (critical): an amber resolution made on member A survives switching to member B and back — the hazard closed structurally and PINNED"
    requirement: SHEET-01
    verification:
      - kind: unit
        ref: "frontend/src/components/ReviewGroupTabs.test.tsx#keeps an amber resolution made on Week 1 after switching to Week 2 and back"
        status: pass
      - kind: unit
        ref: "frontend/src/components/ReviewGroupTabs.test.tsx#keeps every member's pane mounted while inactive (3 panes in the DOM, inactive ones hidden not unmounted)"
        status: pass
      - kind: other
        ref: "Negative control: with `keepMounted` removed, 4 tests fail — 'expected 1 of 2 resolved to match /2 of 2/'. The test provably catches the hazard."
        status: pass
    human_judgment: false
  - id: D3
    description: "The confirm gate is per member and NEVER aggregated; Download All enables only when every member is confirmed, and names how many remain until then"
    requirement: SHEET-01
    verification:
      - kind: unit
        ref: "frontend/src/components/ReviewGroupTabs.test.tsx#resolving one member never resolves another / blocks Download All while no member is confirmed / blocks even after an amber field is resolved (resolved is not confirmed)"
        status: pass
      - kind: integration
        ref: "Walkthrough step 3 (live API): Week 1 confirms 200; the archive STILL 409s naming '2 of 3 datasets still unconfirmed'; Week 2 STILL 422s on its own unresolved amber field"
        status: pass
    human_judgment: false
  - id: D4
    description: "Provenance is visible on EVERY ingest (D-11-15) and is header metadata, never a ReviewTable row (UI-SPEC Discretion §3)"
    requirement: SHEET-03
    verification:
      - kind: unit
        ref: "frontend/src/components/ReviewGroupTabs.test.tsx#shows each member's own source sheet in its own tab / ExportBar tells the curator the export carries the reserved __source_sheet column"
        status: pass
      - kind: command
        ref: "grep -c 'source_sheet\\|sheet {' frontend/src/components/ReviewTable.tsx -> 0"
        status: pass
      - kind: integration
        ref: "Walkthrough step 7 (live API): the CSV path's export.csv carries __source_sheet='novascreen_batch01.csv' on every row; Review renders 'sheet novascreen_batch01.csv'"
        status: pass
    human_judgment: false
  - id: D5
    description: "N=1 renders with no tab strip and no group bar (SHEET-01's no-regression clause), and the CSV/single-sheet path never enters the group flow at all"
    requirement: SHEET-01
    verification:
      - kind: unit
        ref: "frontend/src/components/ReviewGroupTabs.test.tsx#renders a single-member group with no tab strip and no group bar"
        status: pass
      - kind: integration
        ref: "Walkthrough step 7: a CSV upload returns kind='mapping' (not sheet_question) — no sheet panel, straight to Review"
        status: pass
    human_judgment: false
  - id: D6
    description: "Rendering adequacy — tab labels mono, status glyphs carry aria-labels, TabsList wraps, group bar is in-flow, zero new hex/type roles"
    verification:
      - kind: other
        ref: "grep: forceMount/keepMounted >=1 (2), aria-label 3, hex 0, groupExportBlockedReason 2, <Review 1, downloadGroupArchive 2; npm run build + lint + 248 tests green"
        status: pass
    human_judgment: true
    rationale: "Visual adequacy (the amber/success discipline, the 32px tab target, the wrap) is checker-validated per the project's established rule; the logic beneath every one of those renders is D1-D5's tested surface."

# Metrics
duration: 24min
completed: 2026-07-13
tasks: 3
files: 11
commits: 4
---

# Phase 11 Plan 10: The N-Dataset Review Summary

**N selected sheets now arrive as N tabs in one Review — each holding the whole existing screen on its OWN 4-tier gate, each confirming alone, none able to lose a curator's work to a tab switch — and one "Download All" appears only once every member has confirmed. The state-loss hazard the phase named as critical is closed structurally AND pinned by a test proven to catch it.**

## Performance

- **Duration:** 24 min (09:43 → 10:07 UTC)
- **Tasks:** 3 (Task 1 TDD: RED then GREEN)
- **Files:** 11 (3 created, 8 modified)
- **Suites:** frontend **248 passed** (was 240; +8), `npm run build` (tsc -b) and `npm run lint` green; backend **1121 passed, 4 skipped** — byte-unchanged, this plan touches no Python

## Accomplishments

- **The hazard is closed structurally, and — more importantly — it is PINNED.** `Review` holds amber resolutions in local `useState`, so a remounting tab silently destroys a curator's work. Every pane is now kept mounted (hidden + `inert` when inactive) and each member's `Review` is keyed by its own upload token via `memberPaneKey`, a pure function that *cannot see* the active tab and therefore cannot be changed by a switch. A grep for `forceMount` would only have proved a string exists; instead `ReviewGroupTabs.test.tsx` renders for real (jsdom), resolves the amber `unit` field on Week 1, switches to Week 2, switches back, and asserts the resolution is still there. **Negative control run:** with `keepMounted` removed, that test fails with `expected '1 of 2 resolved' to match /2 of 2/` — which is precisely the curator's work vanishing. The test catches the thing it claims to catch.

- **The gate is per dataset and is never aggregated — proven on the live API, not just in units.** Confirming Week 1 returned 200; the archive *still* refused with `409 — 2 of 3 datasets in this group are still unconfirmed`; and Week 2 *still* returned 422 on its own unresolved amber field. One member's success neither confirms nor unblocks another. There is no group-level `ready`, no group confirm, and no aggregate anywhere in the component.

- **"Download All" is a lookup over the per-member verdicts, never a bypass.** While blocked it is a **disabled `<Button>`** and there is no `<a href>` to the archive URL in the DOM at all — not a live link with a client-side guard in front of it. The reason names how many datasets remain (`Confirm all 3 datasets to download the archive — 1 still unconfirmed.`), mirroring the server's own 409 copy. The server refuses independently regardless (T-11-38).

- **The money shot works end to end.** zephyr's 3 sheets → 3 independent datasets → 3 separate confirms → one zip: **three directories, four files each, each `export.csv` carrying its own `__source_sheet`** (`Week 1` rows say `Week 1`, never a sibling's name), served as `application/zip` named `zephyr_bio_ZB-2025.zip`.

- **Provenance is on every ingest, including the CSV.** D-11-15 is honoured literally: a CSV's Review shows `sheet novascreen_batch01.csv` and its export carries `__source_sheet=novascreen_batch01.csv` on all 12 rows. It renders as **header metadata, never a `ReviewTable` row** (UI-SPEC Discretion §3 — a bookkeeping constant must not be dressed up as something Claude proposed and the human must check); `grep` over `ReviewTable.tsx` returns 0.

- **N=1 does not regress.** A single-member group renders with no tab strip and no group bar, and the single-sheet/CSV path never enters the group flow at all (a CSV upload returns `kind: "mapping"`, not `sheet_question`). Per the UI-SPEC's explicit instruction, no test pins byte-identity — D-11-15's provenance line is locked and wins.

- **Per-sheet Schemas are genuinely independent.** orion resolved with `Summary → assay-potency` (7 fields) and `Raw timepoints → pk-parameters` (8 fields): two members, two different field sets, two independent amber sets, with `Notes` left unticked and excluded. SHEET-05's whole point, working.

## Task Commits

1. **Task 1: pure member/group derivations + the provenance line** — RED: `24b669a` (test) · GREEN: `30894e3` (feat)
2. **Task 2: ReviewGroupTabs — tabs that never remount, gates that never merge** — `f82b485` (feat)
3. **Task 3: the walkthrough, and the hazard pinned by a real DOM render** — `8da7020` (test)

## Walkthrough

Driven end to end against the running app (API on :8000, frontend on :5173, signed in as a verified user). Every step's OBSERVED outcome, recorded for the end-of-phase human verification.

| # | Step | Expected | **Observed** | Verdict |
|---|------|----------|--------------|---------|
| 1 | Upload `zephyr_bio_ZB-2025.xlsx` | Sheet panel: Week 1/2/3, REAL header row (not the banner), row counts, `{n}/{total}` coverage with matched pairs | `kind=sheet_question`. Three sheets, each `rows=8`, `status=ok`, headers `['Compound ID','Assay','Result','Units','Protein Target','Replicates','Run Date']` — the real header row, not `ZEPHYR BIOSCIENCES`. Each carries `assay-potency 7/7 (crosswalk)` with all 7 matched pairs visible. | **PASS** |
| 2 | Resolve an amber field on Week 2, switch to Week 3, switch back | The resolution must still be there | Pinned as a test (jsdom): resolve on Week 1 → `2 of 2 resolved`; switch away and back → **still `2 of 2`**. All 3 panes stay in the DOM; the inactive ones are `hidden`, never unmounted. **Negative control: removing `keepMounted` makes this test fail** (`'1 of 2 resolved'`) — the hazard is real and the test catches it. | **PASS** |
| 3 | Confirm each tab on its own; Week 1 must not confirm/unblock Week 2; Download All blocked with the reason until all three | Per-member gates, never aggregated | Week 1 confirm → **200**. Archive → **409: "2 of 3 datasets in this group are still unconfirmed"**. Week 2 with its amber field unresolved → **still 422**. Download All is a disabled `<Button>` with the reason shown; no archive `<a href>` exists in the DOM while blocked. | **PASS** |
| 4 | Confirm all three, Download All: 3 dirs, 4 files each, `__source_sheet` per row | One zip, per-member provenance | **200, `application/zip`, `zephyr_bio_ZB-2025.zip`, 18,705 bytes.** Three directories (`Week 1/`, `Week 2/`, `Week 3/`), **four files each** (`export.csv`, `export.json`, `export.xlsx`, `manifest.json`). Each `export.csv`: 8 rows, `__source_sheet` = its OWN week, never a sibling's. | **PASS** |
| 5 | Upload `meridian_cro_codes.xlsx`: LEGEND appears, unticked | LEGEND present, not silently discarded | LEGEND **appears** (today's code would have discarded it), `rows=6`, `status=header_uncertain`, **unticked via the GATE rule**, carrying its honest **1/7** coverage (`compound_id ← 'CMP'`). DATA: `7/7`, ticked. **NOTE:** the plan's "proposed: skip this sheet" claim for LEGEND is STALE against **D-11-24** — 4th recurrence, already flagged by 11-04/11-07/11-09. The genuine skip line fires where it is genuinely true: orion's `Notes` (zero proposals). | **PASS** (per D-11-24, not per the plan's stale line) |
| 6 | Upload `orion_pk_report.xlsx`: Notes marked "header unclear", still tickable; Summary/Raw may take different Schemas | Different Schemas per sheet | `Notes`: `status=header_uncertain`, zero proposals → the skip line, still tickable. Resolved with **two different Schemas**: `Summary → assay-potency` (7 fields, amber `unit`/`assay_date`) and `Raw timepoints → pk-parameters` (8 fields, its own amber set). Two members, two field sets, fully independent. | **PASS** |
| 7 | Upload `novascreen_batch01.csv`: no sheet panel, straight to Review, plus provenance + ExportBar note | No regression | `kind=mapping` — **not** `sheet_question`: no sheet panel, straight to Review. Provenance line renders `sheet novascreen_batch01.csv`. Confirm → 200; `export.csv` carries `__source_sheet='novascreen_batch01.csv'` on all **12** rows. ExportBar shows the reserved-column note. | **PASS** |

**Steps 2 and 3 — the two that could not be waived — both pass.**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Correctness requirement] One dev-only package installed (`jsdom`), against the plan's "zero packages installed"**

- **Found during:** Task 3.
- **Issue:** The plan's threat register accepts T-11-SC on the basis that zero packages are installed, and its acceptance criteria propose to verify the critical T-11-37 hazard by `grep -c 'forceMount'`. **A grep proves a string is present; it does not prove a curator's work survives a tab switch.** The orchestrator's binding constraint is explicit: *"Pin it with a test: resolving an amber field on member A, switching to member B and back, must NOT lose A's resolution."* That is a claim about React's **mount lifecycle** — no pure function can express it, and the repo had **no DOM test environment at all** (`environment: 'node'`, no jsdom/happy-dom/@testing-library).
- **Fix:** Installed `jsdom` as a **devDependency** (test-only; no runtime dependency, no shipped byte changes) and wrote exactly ONE jsdom file, which renders `ReviewGroupTabs` for real via `react-dom/client` + React 19's `act` — no testing-library, no second install. Every other derivation stays a pure node-env test. The per-file `// @vitest-environment jsdom` docblock leaves the existing 240 node-env tests untouched.
- **Supply chain:** `jsdom` is the standard vitest DOM environment (npmjs.com/package/jsdom); `npm install` reported **0 vulnerabilities**. One package, dev-only, verified — not a substitute for a failed install.
- **Verification:** the test was proven to FAIL with `keepMounted` removed (4 failures, incl. `expected '1 of 2 resolved' to match /2 of 2/`) and to pass with it restored. **The grep criteria still pass too** (`forceMount|keepMounted` ≥1, `aria-label` 3, hex 0).
- **Committed in:** `8da7020`

**2. [Rule 3 — Blocking] `forceMount` does not exist in this registry; the installed primitive spells it `keepMounted`**

- **Found during:** Task 2.
- **Issue:** The UI-SPEC and the plan require `forceMount` on every `TabsContent` (a Radix idiom). The project's installed primitive is **`@base-ui/react`**, whose `Tabs.Panel` has no `forceMount` prop — passing one would be an ignored no-op, silently leaving the hazard WIDE OPEN while the grep criterion passed.
- **Fix:** Used base-ui's `keepMounted`, which provides the identical guarantee (verified in `node_modules/@base-ui/react/tabs/panel/TabsPanel.js`: `shouldRender = keepMounted || mounted`, and the inactive panel renders with `hidden` + `inert`). Documented at the call site so the spelling difference is not mistaken for a deviation from the design contract.
- **Verification:** the jsdom test proves the panes actually stay mounted — which is exactly why deviation 1 was worth taking: **a grep for `forceMount` would have "passed" on a no-op prop.**
- **Committed in:** `f82b485` / `8da7020`

**3. [Rule 2 — Design contract] `Review` REPORTS its state upward; it is not lifted**

- **Found during:** Task 2.
- **Issue:** The tab badges ("{n} to resolve") and the group bar need each member's live amber count and confirm status. The obvious move — lift `mappings` into `ReviewGroupTabs` — would make the parent the owner of the state and re-introduce the reset hazard from above, defeating the component's entire purpose.
- **Fix:** `Review` stays the SOLE owner and gained two optional callbacks (`onMappingsChange`, `onConfirmed`); the parent keeps read-only mirrors. Both props are optional, so the single-dataset path passes neither and is behaviourally unchanged.
- **Committed in:** `f82b485`

**4. [Rule 1 — Bug in the plan's fixture assumption] The plan's step 5 LEGEND claim is stale (4th recurrence)**

- See Walkthrough step 5 and `deferred-items.md` §D-2. LEGEND honestly scores 1/7 and arrives unticked via the `header_uncertain` GATE, not via a zero-coverage skip line. Behaviour is correct per **D-11-24**; the plan's sentence is not. No code changed.

---

**Total deviations:** 4 auto-fixed (1 correctness-driven install, 1 blocking API mismatch, 1 design-contract, 1 stale plan claim). **Impact:** correctness-only, no scope creep. Deviation 2 is the load-bearing one — without it the hazard would have shipped open behind a passing grep.

## Deferred Issues

Logged to `.planning/phases/11-multi-sheet-ingest/deferred-items.md`:

- **D-1 (medium, PRE-EXISTING — proven by control experiment):** a validator-rejected *value* is a UI dead end. zephyr's `Units` column holds `uM` (ASCII u); `assay-potency`'s `unit` allows `['µM','nM','%']`, so confirm correctly 422s. But `FieldRow`'s three controls (chip / Accept / dropdown) all resolve a field to a **column** — none can express "clear the column, use the inferred constant `µM`", which is the resolution the codebase's own tests treat as the curator's answer (`test_group_export.py::_resolved_unit`). **Control experiment proving this is not 11-10's:** the SINGLE-SHEET path (`sheet=Week 1`, never entering the group flow) produces the identical 422. Out of scope per the scope boundary; the smallest honest fix is a "use this value for every row" affordance on an amber `FieldRow` — the domain already has the wire shape (`inferred_value`, MAP-02).
- **D-2 (informational):** the stale LEGEND claim, for planners.

## Known Stubs

None. No placeholder values, no unwired data path, no TODO. The one stub 11-09 declared (`Upload.tsx`'s `sheet_group` no-op) is **closed**: the resolve handler now routes the group to `onSheetGroup` → `App.tsx` → `ReviewGroupTabs`.

## Threat Flags

None new. All four `mitigate` dispositions applied:

| Threat | Applied |
|---|---|
| T-11-36 (XSS via a worksheet title in a tab label) | Sheet names, headers and vendor text render as text children only — no `dangerouslySetInnerHTML`, no `innerHTML` anywhere in the new component |
| T-11-37 (a curator's resolutions destroyed by a tab switch) — **critical** | Every pane `keepMounted` (base-ui's `forceMount`), each member's Review keyed by `memberPaneKey` (pure, tab-blind). **Pinned by a DOM test proven to fail without it** — not merely grep-asserted |
| T-11-38 (the group download bypassing a member's gate) — **critical** | The bar is enabled only when every member is confirmed; while blocked it is a disabled Button with NO archive href in the DOM. Server refuses independently (409, verified live) |
| T-11-39 (a hidden member silently forgotten) | `TabsList` has `flex-wrap` + `h-auto` — it WRAPS, never scrolls; every member stays visible |
| T-11-SC (package installs) | **One** dev-only package (`jsdom`), taken deliberately to close T-11-37 with a real test rather than a grep. 0 vulnerabilities; no runtime dependency; see Deviation 1 |

## Issues Encountered

- The `key_links` frontmatter expects `ReviewGroupTabs → Review` via `<Review`; the import is `@/screens/Review` (the project's established alias convention). The link holds exactly as specified: one `Review` per member, keyed by its own `upload_token`, never re-keyed on a tab switch.

## User Setup Required

None. (The walkthrough used a throwaway verified account against the local dev DB; no project state was modified.)

## Verification

- `cd frontend && npm run build && npm run lint && npm test -- --run` → **248 passed**, build (tsc -b) and lint green (lint's 3 warnings are pre-existing in shadcn `ui/` files).
- `uv run pytest tests/ -q` → **1121 passed, 4 skipped** — identical to 11-08's baseline; this plan changes no Python.
- Task 1 ACs: `review.test.ts` passes with all four member statuses and both group-gate outcomes; `grep -c 'source_sheet\|sheet {' ReviewTable.tsx` → **0**; build green.
- Task 2 ACs: `forceMount|keepMounted` → **2** (≥1); `aria-label` → **3** (≥2); hex → **0**; `groupExportBlockedReason` → **2** (≥1); build + lint + full suite green.
- Task 3 ACs: all seven walkthrough steps recorded above; **steps 2 and 3 pass**; a group member's `export.csv` carries `__source_sheet` on every row; the CSV path is unchanged apart from the provenance line and the ExportBar note.

## TDD Gate Compliance

- **RED gate:** `24b669a` — verified failing first (17 failures across the five new derivations).
- **GREEN gate:** `30894e3` — 55/55 in `review.test.ts`, build green.
- **REFACTOR:** not needed.
- **Task 3's DOM test** was additionally verified as a *negative control*: deliberately removing `keepMounted` produced 4 failures, restoring it produced 8 passes. A test that cannot fail proves nothing; this one can.

## Next Phase Readiness

- **Phase 11 is complete.** The multi-sheet flow runs end to end: upload → sheet manifest with visible coverage → N independent datasets → N tabs, N gates → one archive. SHEET-01, SHEET-03, SHEET-04 and SHEET-05 are all delivered; SHEET-02 (merge) remains struck from the product by D-11-07.
- **One pre-existing gap is now documented and worth a decision** (`deferred-items.md` §D-1): a curator cannot resolve a validator-rejected *value* through the UI. It blocks confirming zephyr through the browser without a Schema edit — worth knowing before the demo is recorded, since zephyr is the phase's showcase file.

---
*Phase: 11-multi-sheet-ingest*
*Completed: 2026-07-13*

## Self-Check: PASSED

- All 3 created files exist on disk, plus this SUMMARY.
- All 4 task commits present in `git log`: `24b669a` (RED), `30894e3` (GREEN), `f82b485`, `8da7020`.
- No file deletions in any of this plan's commits (`git diff --diff-filter=D` over the range is empty).
- Every acceptance criterion from all three tasks re-run and passes.
- Full suites green: frontend 248 passed; backend 1121 passed / 4 skipped.
