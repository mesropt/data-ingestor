---
phase: quick-260712-sat
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/assayingest/api/routes/confirm.py
  - tests/api/test_confirm_gate.py
  - frontend/src/lib/types.ts
  - frontend/src/lib/api.ts
  - frontend/src/state/review.ts
  - frontend/src/state/review.test.ts
  - frontend/src/screens/Review.tsx
autonomous: true
requirements: []

must_haves:
  truths:
    - "A confirm rejected by the server-side P1 gate names EVERY unresolved field in the Review screen's alert."
    - "When the no-LLM validator produced a `validator_note` for a rejected field, that exact reason is shown next to the field's name."
    - "A rejected field whose reason is null is still NAMED (never silently dropped from the list)."
    - "An old/short 422 body without `unclear_details` still parses, still names the fields, and never throws."
    - "The 422 body's existing `unclear_fields: [str]` key is byte-identical to before (no existing consumer breaks)."
  artifacts:
    - src/assayingest/api/routes/confirm.py
    - frontend/src/lib/api.ts
    - frontend/src/state/review.ts
    - frontend/src/screens/Review.tsx
    - frontend/dist
  key_links:
    - "service.NotReadyError.unclear_fields (list[FieldMapping], each carrying validator_note) -> confirm.py 422 detail.unclear_details -> api.ts GateRejected.unclearDetails -> state/review.ts gateRejection() -> Review.tsx <AlertDescription>."
    - "GateRejected.unclearFields (names only, UNCHANGED) -> applyGateRejection() -> mappings re-flagged amber. This link must survive untouched."
---

<objective>
The server-side confirm gate already knows exactly which field it rejected AND why (`service.NotReadyError.unclear_fields` is a `list[FieldMapping]`, each carrying the no-LLM validator's honest `validator_note`), but `api/routes/confirm.py` throws the reason away (`detail={"unclear_fields": [m.target_field ...]}`) and `Review.tsx` renders a generic "The server found an uncertain field that wasn't resolved." The human is left guessing — which is the one thing this product refuses to do.

Purpose: make the rejection name the field and state the reason, end to end.
Output: a widened (backward-compatible) 422 body, a defensively-parsed client model, and a Review alert that lists `field — reason` per rejected field.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.claude/CLAUDE.md
@src/assayingest/api/routes/confirm.py
@src/assayingest/service.py
@src/assayingest/domain/models.py
@frontend/src/lib/api.ts
@frontend/src/state/review.ts
@frontend/src/screens/Review.tsx
@tests/api/test_confirm_gate.py
@frontend/src/state/review.test.ts

Key facts already established by reading the code:
- `FieldMapping` (domain/models.py:38) fields: `target_field: str`, `source_column: str | None`, `validator_note: str | None` (None until `validate()` runs).
- The 422 detail body is a plain dict passed to `HTTPException` in `api/routes/confirm.py` — it is NOT a Pydantic model in `api/wire.py`. So **no `api/wire.py` change is needed**; do not invent one.
- `api.ts` already has the defensive `stringArrayField(detail, key)` idiom (api.ts:325) and `unclearFieldsFrom(detail)` (api.ts:339) which unions `unclear_fields` + `missing_fields`. Reuse that posture; do not invent a second one.
- The `FieldCoverageError` 422 branch (`{missing_fields, unknown_fields}`) is OUT OF SCOPE — its shape does not change.
- Frontend vitest runs with `environment: 'node'` (frontend/vite.config.ts:26). There is NO jsdom and NO @testing-library/react. Test pure logic only; never render a component.
- The api.ts confirm/GateRejected tests already live in `frontend/src/state/review.test.ts` (see its `unclear_fields` 422 test at ~line 379) — that is the natural home, not a new file.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: The 422 detail carries the validator's reason, not just the name</name>
  <files>src/assayingest/api/routes/confirm.py, tests/api/test_confirm_gate.py</files>
  <behavior>
    - A confirm that trips the P1 gate on a real constraint violation (declared `min=100`, mapped value `12.5`) still returns 422 with `detail["unclear_fields"] == ["value"]` — byte-identical to today.
    - The SAME body additionally carries `detail["unclear_details"] == [{"field": "value", "reason": <the validator's actual note>, "source_column": "potency"}]`, where the reason is the real note text the no-LLM validator produced (it names the column, the offending value, and the declared minimum), NOT a placeholder and NOT merely a non-empty string.
    - Nothing is persisted (the existing `store.find(...) is None` assertion still holds).
  </behavior>
  <action>
Extend ONLY the `except service.NotReadyError` branch in `src/assayingest/api/routes/confirm.py` (currently lines 123-127).

KEEP `"unclear_fields": [m.target_field for m in exc.unclear_fields]` exactly as it is — it is the backward-compatibility contract that existing tests and the existing frontend depend on. ADD a parallel key built from the same `exc.unclear_fields` list:

`"unclear_details"` — a list of dicts, one per unclear `FieldMapping`, in the same order, each with keys `field` (the `target_field`), `reason` (the mapping's `validator_note`, passed through as-is, `None` when the validator produced none), and `source_column` (the mapping's `source_column`, `None` when no column matched).

Build it via a small module-private helper (e.g. `_unclear_detail(mapping: FieldMapping) -> dict`) so the route body stays at a single level of abstraction, per CLAUDE.md. Give the helper a docstring pinning the intent: the two keys are parallel views of the SAME `NotReadyError.unclear_fields` — the names key is the legacy/compatible one the client re-flags amber from, the details key adds the honest reason so the human is never left guessing. Note in the docstring (or an inline comment on the branch) that `reason` is passed through unmodified: it is the deterministic validator's own verdict, never re-worded, never synthesised here when absent.

Do NOT change the status code (still 422). Do NOT touch the `FieldCoverageError` branch or the `UnresolvedDateColumnsError` branch. Do NOT add a Pydantic model to `api/wire.py` — the detail body is a plain dict by design here.

Then extend the EXISTING test `test_confirm_rejects_a_tampered_ready_claim_over_a_real_constraint_violation` in `tests/api/test_confirm_gate.py` (its current 422 assertion is at line ~157). Keep the existing `unclear_fields == ["value"]` assertion untouched (it IS the backward-compat guard) and add assertions on `detail["unclear_details"]`: it is a one-element list, its `field` is `"value"`, its `source_column` is `"potency"`, and its `reason` is the validator's ACTUAL note text. Assert the real string — run the test once to read the note the validator emits for this fixture (it is built from `validator.py`'s `f"column '{label}': {violation}"` + `f"{value} is below the declared minimum {target_field.min}"`) and assert equality against that exact text. Do not settle for `is not None` / `!= ""` / a bare `in` on one word — the whole point of this change is that the reason is real and complete. Give the test a name/docstring making clear it guards BOTH the unchanged legacy key and the new reason-carrying one.

Do not create a new test file; do not weaken or delete any existing assertion.
  </action>
  <verify>
    <automated>uv run pytest tests/api/test_confirm_gate.py tests/api/test_confirm_dates.py -q</automated>
  </verify>
  <done>The gate's 422 body carries both `unclear_fields` (unchanged) and `unclear_details` with the validator's real note; the extended test asserts the exact note text and passes; the two confirm test modules are green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: The client parses the reason defensively and shapes a nameable message</name>
  <files>frontend/src/lib/types.ts, frontend/src/lib/api.ts, frontend/src/state/review.ts, frontend/src/state/review.test.ts</files>
  <behavior>
    - A 422 body carrying `unclear_details` yields a `GateRejected` whose `unclearDetails` is `[{field, reason, sourceColumn}, ...]` with the reason preserved verbatim, AND whose `unclearFields` is still the plain name list (unchanged).
    - A 422 body carrying ONLY `unclear_fields` (no `unclear_details` — an older/shorter server body) does NOT throw: it yields `unclearDetails` derived from the names, each with `reason: null`.
    - A 422 body whose `unclear_details` is garbage (not an array; or an array holding non-objects / entries missing `field`) does NOT throw: unparseable entries are dropped, and the fallback still names every field from `unclear_fields`.
    - A `FieldCoverageError` 422 (`{missing_fields, unknown_fields}`) still yields a `GateRejected` naming those fields (existing test must keep passing), with `reason: null` details.
    - The pure shaping function turns a details list into `{fields: [{name, reason}, ...]}` — a field whose reason is null is STILL present in `fields`, with `reason: null`. It is never omitted.
  </behavior>
  <action>
**`frontend/src/lib/types.ts`** — add one exported interface for the new 422 detail entry, e.g. `UnclearDetail { field: string; reason: string | null; sourceColumn: string | null }` (camelCase on the client side, per the file's own client-model convention — the snake_case wire keys are read at the boundary in `api.ts`). Docstring it as the client-side view of the confirm gate's `unclear_details` 422 entry.

**`frontend/src/lib/api.ts`** — 
1. `GateRejected` gains a second readonly member `unclearDetails: UnclearDetail[]`, set from a second constructor parameter. `unclearFields` stays exactly as it is (the names list) — `applyGateRejection` reads it and MUST keep working unchanged.
2. Add a boundary parser alongside the existing `stringArrayField`/`unclearFieldsFrom` helpers, in the same "never trust the body's shape" posture: read `detail.unclear_details`, accept it only when it is an array, and keep only entries that are non-null objects with a string `field`; map each to `{field, reason: typeof reason === "string" ? reason : null, sourceColumn: typeof source_column === "string" ? source_column : null}`. When the key is absent or yields zero usable entries, FALL BACK to the names already computed by `unclearFieldsFrom(detail)` — one detail per name with `reason: null`, `sourceColumn: null` — so an older body still names its fields and never throws.
3. In `confirm()`'s 422 catch, construct `new GateRejected(names, details)` from the same `err.detail`. Do not change the thrown type, the status check, or anything about the non-422 path.

**`frontend/src/state/review.ts`** — add the PURE message-shaping function (this is what makes the render testable under `environment: 'node'`; no React, no DOM). Export:
- a small shape for a rejection line, e.g. `GateRejectionField { name: string; reason: string | null }`;
- a `ConfirmError` union the screen's state holds, e.g. `type ConfirmError = string | { fields: GateRejectionField[] }` — a plain string for every non-gate failure, the structured shape for a gate rejection (never a newline-concatenated string);
- `gateRejection(details: UnclearDetail[]): ConfirmError` returning `{fields: [...]}` mapping each detail to `{name: d.field, reason: d.reason}`, PRESERVING order and NEVER dropping a null-reason entry.
Docstring it against the invariant: a field the server named is always named back to the human, reason or no reason.

Leave `applyGateRejection` completely untouched — it still takes the plain name list and re-flags exactly those fields amber. That behaviour is the reason the rejection is resolvable at all.

**`frontend/src/state/review.test.ts`** — extend the existing suite (do not create a new file). Keep every existing test as-is. Add:
- a 422-with-`unclear_details` test driving `confirm()` through the existing `globalThis.fetch` mock idiom, asserting `unclearDetails` carries the real reason text AND `unclearFields` is still the plain name array;
- a 422-WITHOUT-`unclear_details` test (old body) asserting `confirm()` rejects with `GateRejected` (does not throw a TypeError) and `unclearDetails` is `[{field: <name>, reason: null, sourceColumn: null}, ...]` derived from the names;
- a malformed-`unclear_details` test (e.g. `unclear_details: "nope"`, and/or an array holding `[null, {reason: "x"}]`) asserting it still does not throw and still names the fields from `unclear_fields`;
- direct unit tests of `gateRejection(...)`: a mixed list where one detail has a real reason and one has `reason: null` — assert BOTH appear in `fields`, in order, the null one named with `reason: null`.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/state/review.test.ts</automated>
  </verify>
  <done>`GateRejected` carries `unclearDetails`; an old body without `unclear_details` and a malformed one both parse without throwing and still name every field; `gateRejection()` never omits a null-reason field; the full `review.test.ts` suite (existing + new) is green.</done>
</task>

<task type="auto">
  <name>Task 3: The Review alert names the field and states the reason; rebuild dist</name>
  <files>frontend/src/screens/Review.tsx</files>
  <action>
In `frontend/src/screens/Review.tsx`:

1. Widen the `confirmError` state from `string | null` to `ConfirmError | null` (the union added in `state/review.ts`) — import it alongside the existing `state/review` imports. Every existing non-gate `setConfirmError("...")` call site (the `!fieldSet` "Still loading this Schema's fields" guard, the `ApiError` branch, the catch-all branch) keeps passing a plain string and needs no change; the union accepts it.

2. In the `err instanceof GateRejected` branch (currently lines 163-175): KEEP `setMappings((current) => applyGateRejection(current, err.unclearFields))` EXACTLY as it is — that is the invariant that makes the rejection resolvable, and it still reads the plain name list. Replace ONLY the generic `setConfirmError("The server found an uncertain field...")` string with `setConfirmError(gateRejection(err.unclearDetails))`. Export must never unlock from this branch — do not touch `setConfirmed`.

3. In the render, keep the EXISTING `<Alert variant="destructive">` / `<AlertTriangle />` / `<AlertTitle>` / `<AlertDescription>` block (line ~218). Do NOT add a new component, a new design token, or a new shadcn primitive. Inside `<AlertDescription>`, branch on the union: a `string` renders as today; the structured shape renders "Confirm rejected — nothing was saved.", then a `<ul>` with one `<li>` per field (keyed by field name) reading `{name}` when there is no reason and `{name} — {reason}` when there is, then the closing line "Resolve the highlighted field(s) below and confirm again." A null-reason field must still render its name. Style the list with existing Tailwind utilities already used in this codebase (e.g. a `list-disc`/`pl-*`/`space-y-*` combination) — no new token, no new CSS file. Keep the `<AlertTitle>` as "Confirm rejected".

Keep the change additive and small: no new files, no new dependencies.

4. Run the FULL suites and rebuild the bundle uvicorn serves:
   - `uv run pytest -q` from the repo root — must stay at the 843 passed / 4 skipped baseline (plus the assertions Task 1 added); no test deleted or weakened.
   - `cd frontend && npx vitest run` — must stay at the 186-passing baseline (plus Task 2's new tests).
   - `cd frontend && npm run build` — this is `tsc -b && vite build`, so it also type-checks the widened union. This MUST be the last step so the fix actually reaches the site uvicorn serves on :8000.
   - NEVER `git add -f dist`. `frontend/dist` is a build artifact; leave it gitignored.
  </action>
  <verify>
    <automated>uv run pytest -q && cd frontend && npx vitest run && npm run build</automated>
  </verify>
  <done>The rejection alert lists each unresolved field by name with the validator's reason (null-reason fields still named); `applyGateRejection` still re-flags exactly the server-named fields amber; export never unlocks from the rejection branch; backend >= 843 passed / 4 skipped and frontend >= 186 passed with nothing deleted or weakened; `frontend/dist` rebuilt and not force-added to git.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| server -> browser (422 body) | The client must not assume the error body's shape; a short or malformed body must degrade, never throw. |
| browser -> server (confirm) | Unchanged. The server remains the sole gate; this task only changes what the rejection SAYS. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-QK-01 | Denial of Service | `api.ts` 422 parsing | medium | mitigate | Parse `unclear_details` defensively (array check + per-entry `typeof` guards, unparseable entries dropped, fallback to names). A malformed body must never throw and strand the Review screen with no way forward. Explicitly tested (Task 2). |
| T-QK-02 | Elevation of Privilege | Review confirm branch | high | mitigate | The rejection branch never sets `confirmed`/unlocks export (P1, T-04-18). Task 3 touches only `setConfirmError`; `applyGateRejection(err.unclearFields)` is left byte-identical. |
| T-QK-03 | Information Disclosure | `unclear_details.reason` | low | accept | `validator_note` is the tool's own deterministic verdict about the file the authenticated curator just uploaded themselves (it may quote one of their own cell values, e.g. `'03/11/2025'`). It is returned only to the `require_verified_user` who submitted the confirm — no new data crosses a boundary it did not already cross via the mapping response. |
| T-QK-04 | Tampering | 422 body contract | low | accept | The added key is additive and read-only; the client's re-flagging still derives from `unclear_fields`, which the server computes. No client-supplied value gains authority. |
</threat_model>

<verification>
- 422 body carries BOTH `unclear_fields` (byte-identical) and `unclear_details` with the validator's real note text (asserted exactly, not merely present).
- An older 422 body without `unclear_details`, and a malformed one, both parse without throwing and still name every field.
- `applyGateRejection` still re-flags exactly the server-named fields to amber (existing tests unchanged and green).
- Export never unlocks from the rejection branch.
- A rejected field with a null reason is still named in the alert.
- Backend >= 843 passed / 4 skipped; frontend >= 186 passed. Nothing deleted or weakened.
- `frontend/dist` rebuilt via `npm run build`; not force-added to git.
</verification>

<success_criteria>
The builder clicks Confirm, the server rejects, and the Review screen tells him exactly which field is unresolved and exactly why the no-LLM validator objected — in the validator's own words — with every named field re-flagged amber and resolvable. No generic "some field wasn't resolved" message remains.
</success_criteria>

<output>
Create `.planning/quick/260712-sat-make-the-confirm-rejection-name-the-unre/260712-sat-SUMMARY.md` when done.
</output>
