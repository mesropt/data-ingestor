---
phase: quick-260712-sat
plan: 01
subsystem: api
tags: [fastapi, confirm-gate, validator, review-ui, typescript]

requires:
  - phase: quick-260712-qgc
    provides: Confirm gate re-flagging (applyGateRejection) already resolvable for date-order rejections
provides:
  - "422 body from the confirm P1 gate now carries unclear_details (field, reason, source_column) alongside the unchanged unclear_fields name list"
  - "GateRejected client model carries unclearDetails, parsed defensively (falls back to reason:null per name on an older/malformed body)"
  - "Review screen's rejection alert lists every unresolved field by name with the validator's own reason text"
affects: [review-screen, confirm-gate, validator]

tech-stack:
  added: []
  patterns:
    - "Additive 422 detail key: unclear_details is a parallel, reason-carrying view of the SAME NotReadyError.unclear_fields list -- the legacy unclear_fields key is never touched, so applyGateRejection's re-flagging keeps working byte-identically."
    - "Boundary parsing with a names-derived fallback: an absent/malformed unclear_details never throws -- it degrades to one {reason: null} detail per already-known field name."

key-files:
  created: []
  modified:
    - src/assayingest/api/routes/confirm.py
    - tests/api/test_confirm_gate.py
    - frontend/src/lib/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/state/review.ts
    - frontend/src/state/review.test.ts
    - frontend/src/screens/Review.tsx

key-decisions:
  - "unclear_details is additive-only: unclear_fields (the legacy name-only key applyGateRejection reads) is left byte-identical; no existing consumer needed to change."
  - "reason is the no-LLM validator's own validator_note passed through unmodified -- never re-worded or synthesised when absent (null in, null out)."
  - "A null-reason field is still named in both the parsed client model and the rendered alert -- never silently dropped."

patterns-established:
  - "422 detail widening pattern: add a parallel *_details key built from the same exception data, never mutate the existing compatibility key."

requirements-completed: []

coverage:
  - id: D1
    description: "The confirm 422 body carries unclear_details with the validator's exact reason text, alongside the byte-identical legacy unclear_fields key"
    verification:
      - kind: unit
        ref: "tests/api/test_confirm_gate.py#test_confirm_rejects_a_tampered_ready_claim_over_a_real_constraint_violation"
        status: pass
    human_judgment: false
  - id: D2
    description: "The client parses unclear_details defensively: real reasons pass through, an older body without the key falls back to reason:null per name, and a malformed unclear_details (non-array, or entries missing field) never throws"
    verification:
      - kind: unit
        ref: "frontend/src/state/review.test.ts#api.confirm -- /api/confirm"
        status: pass
    human_judgment: false
  - id: D3
    description: "gateRejection() shapes a rejection's fields into {name, reason} pairs, preserving order and never dropping a null-reason field"
    verification:
      - kind: unit
        ref: "frontend/src/state/review.test.ts#gateRejection (shapes a rejection's fields for the Review alert)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The Review screen's rejection alert renders each unresolved field by name with its reason, keeps applyGateRejection's re-flagging untouched, and never unlocks export from the rejection branch"
    verification: []
    human_judgment: true
    rationale: "Rendering correctness (list layout, styling, visual clarity of the 'field — reason' lines) requires a human to look at the actual Review screen; the frontend test environment has no jsdom/@testing-library/react to assert DOM output."

duration: 20min
completed: 2026-07-12
status: complete
---

# Quick Task 260712-sat: Make the Confirm Rejection Name the Unresolved Field, With Its Reason Summary

**The server's confirm 422 body now carries a per-field validator reason (`unclear_details`), parsed defensively on the client and rendered as a `field — reason` list in the Review screen's rejection alert, instead of a single generic "some field wasn't resolved" message.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3 completed
- **Files modified:** 7

## Accomplishments

- `api/routes/confirm.py`'s `NotReadyError` 422 branch now returns both the unchanged `unclear_fields` name list and a new `unclear_details` list of `{field, reason, source_column}`, where `reason` is the no-LLM validator's own `validator_note` passed through verbatim.
- `frontend/src/lib/api.ts`'s `GateRejected` gained `unclearDetails`, parsed at the trust boundary: real reasons pass through, an older/shorter body without `unclear_details` falls back to `reason: null` per already-known field name, and a malformed `unclear_details` (non-array, or entries missing a string `field`) degrades to the same fallback rather than throwing.
- `frontend/src/state/review.ts` added the pure `gateRejection(details)` shaper (`{fields: [{name, reason}]}`) and the `ConfirmError` union, so the Review screen's rejection message is testable without a DOM.
- `Review.tsx`'s rejection alert now renders "Confirm rejected — nothing was saved.", a bulleted list of every unresolved field (`name — reason` when a reason exists, bare `name` when it doesn't), and the existing "Resolve the highlighted field(s) below and confirm again." close line -- inside the same `<Alert>`/`<AlertTitle>`/`<AlertDescription>` structure, no new component.
- `applyGateRejection` and the export-never-unlocks-from-rejection invariant (T-04-18) are both untouched -- this task changed only what the rejection SAYS, never what the gate DECIDES.

## Task Commits

Each task was committed atomically (TDD RED -> GREEN per task):

1. **Task 1: The 422 detail carries the validator's reason, not just the name**
   - `37f35a8` (test) - failing test asserting `unclear_details`'s exact reason text
   - `63737a0` (feat) - `confirm.py` adds `unclear_details` via `_unclear_detail()`
2. **Task 2: The client parses the reason defensively and shapes a nameable message**
   - `423f250` (test) - failing tests for `GateRejected.unclearDetails` parsing + `gateRejection()`
   - `5a3eba5` (feat) - `types.ts`/`api.ts`/`review.ts` implement the parsing + shaping
3. **Task 3: The Review alert names the field and states the reason; rebuild dist**
   - `2c6a7d1` (feat) - `Review.tsx` renders the structured rejection; full suites + `npm run build` run clean

_Note: this quick task's docs/state commit (SUMMARY.md, STATE.md) is made separately by the orchestrator, per the execution constraints._

## Files Created/Modified

- `src/assayingest/api/routes/confirm.py` - `NotReadyError` 422 branch adds `unclear_details` via a new `_unclear_detail()` helper; `unclear_fields` left byte-identical
- `tests/api/test_confirm_gate.py` - extended the tampered-ready test to assert the exact `unclear_details` reason text
- `frontend/src/lib/types.ts` - added `UnclearDetail` (client-side view of one 422 detail entry)
- `frontend/src/lib/api.ts` - `GateRejected` gains `unclearDetails`; added `parseUnclearDetail`/`unclearDetailsFrom` boundary parsers
- `frontend/src/state/review.ts` - added `GateRejectionField`, `ConfirmError`, and the pure `gateRejection()` shaper
- `frontend/src/state/review.test.ts` - added tests for real-reason parsing, the older-body fallback, malformed-body handling, and `gateRejection()` itself
- `frontend/src/screens/Review.tsx` - widened `confirmError` state to `ConfirmError | null`; rejection alert renders the field-by-field list

## Decisions Made

- `unclear_details` is purely additive: the legacy `unclear_fields` key (what `applyGateRejection` reads to re-flag amber fields) is never touched, so no existing consumer had to change.
- `reason` is the validator's own `validator_note`, passed through unmodified everywhere in the chain -- the route never rewords it, the client never re-synthesizes one when absent.
- A field with a `null` reason is still named at every layer (server detail, parsed client model, `gateRejection()` output, rendered `<li>`) -- never silently dropped, matching the plan's explicit invariant.

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

- `uv run pytest tests/api/test_confirm_gate.py tests/api/test_confirm_dates.py -q` -> 14 passed (Task 1 gate)
- `uv run pytest -q` (full suite) -> 843 passed, 4 skipped (baseline held)
- `cd frontend && npx vitest run` (full suite) -> 191 passed (baseline 186 + 5 new tests)
- `cd frontend && npm run build` -> `tsc -b && vite build` succeeded (type-checks the widened `ConfirmError` union); `frontend/dist` rebuilt, gitignored, not force-added

## Self-Check: PASSED

All 8 claimed files found on disk; all 5 claimed commit hashes found in `git log --oneline --all`.
