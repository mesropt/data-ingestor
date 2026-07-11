---
phase: 04-api-review-ui
reviewed: 2026-07-11T09:21:20Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - src/assayingest/service.py
  - src/assayingest/api/app.py
  - src/assayingest/api/deps.py
  - src/assayingest/api/state.py
  - src/assayingest/api/wire.py
  - src/assayingest/api/routes/upload.py
  - src/assayingest/api/routes/confirm.py
  - src/assayingest/api/routes/export.py
  - src/assayingest/api/routes/field_sets.py
  - src/assayingest/api/routes/structural_hint.py
  - src/assayingest/learning/field_set_store.py
  - src/assayingest/learning/sqlite_field_set_store.py
  - src/assayingest/cli.py
  - src/assayingest/fields/loader.py
  - frontend/src/state/review.ts
  - frontend/src/state/upload.ts
  - frontend/src/state/fieldSet.ts
  - frontend/src/lib/api.ts
findings:
  critical: 3
  warning: 4
  info: 2
  total: 9
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-07-11T09:21:20Z
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

The API/review-UI phase is well-documented and, in most respects, faithfully mirrors the
CLI's decide-vs-render split into `service.py`. The parameterized SQL discipline in
`sqlite_field_set_store.py` is correct (all `?` placeholders, `from_dict` round-trip guard),
YAML `safe_load` is the only loader in `fields/loader.py`, the export-download route validates
`run_id` against a strict UUID regex before touching the filesystem, and the frontend gate
(`review.ts` / `api.ts`) correctly treats a 422 as `GateRejected` and never unlocks export on
server rejection. The `app.frontend()` call in `app.py` is valid for the pinned FastAPI
0.139.0 (verified by import).

**However, the single most important surface — the server-side P1 confirm gate — has two
independent bypasses, and a third finding leaks medical cell values to disk.** The gate does
NOT use the server-retained `FieldSet`; it re-parses the client's `body.field_set` and
validates against it, directly contradicting `api/state.py`'s own documented contract. A
tampering client can therefore weaken the constraints the gate checks, or simply omit an
unresolved field entirely, and drive a yellow/unsafe mapping to a persisted, exported record.
These are exactly the fail-open paths the phase brief asked to be hunted down.

## Critical Issues

### CR-01: Confirm gate validates against the CLIENT-supplied field set, not the retained one — constraint-weakening bypass

**File:** `src/assayingest/api/routes/confirm.py:51` (and `:59`, `:72`)
**Issue:**
`api/state.py`'s module docstring states the `UploadEntry` retains *"the FieldSet the upload was
resolved against"* precisely so a later `/api/confirm` can *"re-find [it] without trusting
anything the client sends back."* `wire.py::ConfirmRequest` repeats the same intent. But
`confirm.py` ignores `entry.field_set` and instead rebuilds the field set from the request body:

```python
field_set = from_dict(body.field_set)          # <-- CLIENT-controlled, not entry.field_set
...
result = service.confirm(entry.table, edited_mappings, field_set, ...)
service.export(EXPORT_BASE_DIR / run_id, entry.table, field_set, ...)
```

The entire gate's safety rests on `validate(table, proposal, field_set)` re-flagging any value
that violates a declared constraint (`validation/validator.py`). That check only ever inspects
constraints carried by the *passed* field set. So a client that uploaded against
`Field(name="value", min=100)` (yielding a yellow field for value `12.5`) can confirm with a
body whose `field_set` drops the `min` (`Field(name="value")`). Then:

- `_has_constraints()` returns `False` → `_validate_mapping` emits the "no declared constraints"
  note and leaves `needs_confirmation` untouched.
- The client already sent `needs_confirmation=False` → `proposal.is_ready` is `True`.
- `service.confirm` returns success; `canonical.assemble` also runs against the weakened field
  set, and the out-of-range value is exported.

`tests/api/test_confirm_gate.py` never exercises this: every test sends the *same* field set it
seeded. The signature-tampering test (`test_confirm_ignores_a_client_sent_field_set_signature`)
is closed only because `from_dict` recomputes the signature — but the *constraints* are trusted
verbatim. This is a P1 fail-closed violation ("lives at stake").

**Fix:** Use the retained field set as the sole authority; never the client's copy for
validation/assembly. Guard the (always-present on the happy path) retained value:

```python
entry = registry.get(body.upload_token)
if entry is None or entry.table is None or entry.field_set is None:
    raise HTTPException(status_code=404, detail=f"no pending upload for token '{body.upload_token}'")
field_set = entry.field_set   # authoritative; body.field_set is not trusted for the gate
```

If the request must still carry `field_set` for shape reasons, verify equivalence and reject on
mismatch: `if from_dict(body.field_set).signature != entry.field_set.signature: raise
HTTPException(422, "field set does not match the uploaded file")`. Note that `structural_hint.py`
already does the right thing (it passes `entry.field_set`), which makes `confirm.py`'s deviation
a clear inconsistency, not a design choice.

### CR-02: Confirm gate is fail-open on omitted fields — dropping an unresolved mapping unlocks export

**File:** `src/assayingest/api/routes/confirm.py:55` → `src/assayingest/service.py:254-259`
**Issue:**
`service.confirm` rebuilds the proposal purely from whatever `field_mappings` the client sends:

```python
proposal = MappingProposal(source_columns=list(table.headers), field_mappings=list(edited_mappings))
proposal = validate(table, proposal, field_set, strictness=strictness)
if not proposal.is_ready:
    raise NotReadyError(proposal.unclear_fields)
```

`MappingProposal.is_ready` (`domain/models.py:79`) is `bool(field_mappings) and all(m.is_clear
for m in field_mappings)` — it is computed **only over the mappings the client chose to send**.
Nothing cross-checks that `field_mappings` covers every field in `field_set.fields`. A tampering
client can therefore drop any still-yellow (e.g. required) field from the confirm body: the
remaining mappings are all clear, `is_ready` is `True`, and the gate passes. `canonical.assemble`
then iterates `field_set.field_names`, finds no column for the dropped field, and silently emits
`None` for it (`canonical.py:104-110`, `_cell(None)` → `None`, no flag). The result: a required
field is exported as empty data with no confirmation and no block — a silent fail-open on the P1
gate.

**Fix:** Before reading `is_ready`, assert the submitted mappings cover exactly the retained
field set's fields (server-side, against `entry.field_set`):

```python
expected = {f.name for f in field_set.fields}
got = {m.target_field for m in edited_mappings}
if got != expected:
    raise HTTPException(status_code=422, detail={"missing_fields": sorted(expected - got),
                                                 "unknown_fields": sorted(got - expected)})
```

Placing this in `service.confirm` (so the CLI path is covered too) is preferable.

### CR-03: `/api/structural-hint/resolve` leaks the retained temp file on every error path (P2)

**File:** `src/assayingest/api/routes/structural_hint.py:37,52,54,58`
**Issue:**
The route pops the entry up front, then re-parses:

```python
entry = registry.pop(body.upload_token)     # entry (and its tmp_path) removed from registry
...
try:
    result = service.resolve_or_map(entry.tmp_path, entry.field_set, ...)
except service.MissingCredentialsError as exc:
    raise HTTPException(status_code=503, ...)     # entry.tmp_path never unlinked
except anthropic.AuthenticationError as exc:
    raise HTTPException(status_code=401, ...)     # leaked
except (anthropic.APIError, ValueError) as exc:
    raise HTTPException(status_code=500, ...)     # leaked
```

On the success branches the temp file is either unlinked (`:80`) or re-retained under a new token
(`:63-68`). But on **every** error branch the entry has already been popped and the temp file is
never unlinked — it is orphaned on disk with no remaining reference, permanently (until OS temp
cleanup). Because this is the re-parse endpoint, a `ValueError` from a still-broken parse is its
*normal* failure mode, not an edge case. The temp file holds the uploaded assay/patient cell
values, so this directly violates P2 ("temp-file handling must not leak values to disk longer than
needed"). `upload.py` handles this correctly (it unlinks on every error branch); this route does
not.

**Fix:** Unlink `entry.tmp_path` on the error paths, e.g. wrap the resolve in try/except that
cleans up before re-raising, or pop only after success:

```python
try:
    result = service.resolve_or_map(entry.tmp_path, entry.field_set, store=store,
                                    hint=hint, headers_only=entry.headers_only, client=client)
except service.MissingCredentialsError as exc:
    os.unlink(entry.tmp_path)
    raise HTTPException(status_code=503, detail=str(exc)) from exc
except anthropic.AuthenticationError as exc:
    os.unlink(entry.tmp_path)
    raise HTTPException(status_code=401, detail="Anthropic rejected the credentials.") from exc
except (anthropic.APIError, ValueError) as exc:
    os.unlink(entry.tmp_path)
    raise HTTPException(status_code=500, detail=str(exc)) from exc
```

## Warnings

### WR-01: Registry eviction drops entries without unlinking their temp files (P2, resource)

**File:** `src/assayingest/api/state.py:71-73`
**Issue:**
`_evict_oldest_if_over_capacity` calls `self._entries.popitem(last=False)` to drop the oldest
entry when over `_MAX_ENTRIES`. Structural-question entries carry a live `tmp_path`; eviction
removes the last reference without unlinking the file, leaking the uploaded bytes (cell values)
to disk. Each `registry.put` in `upload.py`/`structural_hint.py` can trigger this. Bounded (needs
>200 accumulated uploads), but it is the same P2 confidentiality class as CR-03.
**Fix:** Make eviction cleanup-aware — before dropping an entry, `if evicted.tmp_path:
os.unlink(evicted.tmp_path)` (guarded against a missing file). Centralizing temp-file lifecycle in
the registry (rather than in each route) would remove this whole class of leak.

### WR-02: `.xls` is allow-listed on upload but rejected by the parser → client error surfaces as HTTP 500

**File:** `src/assayingest/api/routes/upload.py:41` (and `:92-94`)
**Issue:**
`_ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}` but `parsing/table.py` explicitly refuses `.xls`
with a `ValueError` ("the old binary .xls format is not supported…", verified at
`table.py:62-69`). So an `.xls` upload passes the allowlist, is written to a temp file, and then
`service.resolve_or_map` raises `ValueError`, caught by `except (anthropic.APIError, ValueError)`
and returned as **HTTP 500**. A malformed-input (client) error is thus reported as a server error,
and the allowlist's own comment ("the upload allowlist matches that exact set so a genuinely
unsupported extension is rejected here, before any bytes reach `parse()`") is inaccurate — `.xls`
is precisely such an unsupported extension yet it is admitted.
**Fix:** Drop `.xls` from `_ALLOWED_EXTENSIONS` so it is rejected at `_validated_extension` with a
400 and the actionable "re-save as .xlsx" message, matching the stated intent.

### WR-03: `list_field_sets` can NPE if a template disappears between `list()` and `get()`

**File:** `src/assayingest/api/routes/field_sets.py:22-26`
**Issue:**
```python
return [FieldSetOut(id=template_id, name=name, field_set=store.get(template_id).to_dict())
        for template_id, name in store.list()]
```
`FieldSetTemplateStore.get` is contractually allowed to return `None` on any miss
(`field_set_store.py:33`). If a row is deleted (or the DB mutated) between `list()` and the
per-id `get()`, `store.get(...)` returns `None` and `.to_dict()` raises `AttributeError` → HTTP
500. Low likelihood in a single-user demo, but it is an unguarded None-dereference on a public
route.
**Fix:** Skip/guard `None` results, e.g. build from a fetched value and `continue` when `None`, or
add a store method that returns full rows in one query so there is no list/get gap.

### WR-04: Confirm records a client-controlled `provenance` into the manifest and export (audit integrity)

**File:** `src/assayingest/api/routes/confirm.py:60,73` → `src/assayingest/service.py:263,329`
**Issue:**
`ConfirmRequest.provenance` is a free-form client string (default `"fresh-claude"`) that flows
straight into `build_manifest(..., provenance=provenance)` and the written `manifest.json`. The
server does not retain the *actual* provenance from upload (the `UploadEntry` has no provenance
field), so it cannot verify it. In a "trust the numbers" lives-at-stake tool the manifest is the
audit record; a client can label a fresh-Claude mapping as `"auto-applied-from-profile"` (or any
string), corrupting the provenance trail. `wire.py` acknowledges it "plays no role in the gate" —
true for readiness, but it still pollutes the persisted audit artifact.
**Fix:** Retain the real provenance in `UploadEntry` at upload/resolve time and use
`entry.provenance` for the manifest, ignoring `body.provenance` (or constrain it to the known
enum and cross-check against the retained value).

## Info

### IN-01: Frontend still sends `field_set` in the confirm body — vestigial once CR-01 is fixed

**File:** `frontend/src/state/review.ts:119-133`
**Issue:**
`toConfirmPayload` includes `field_set: fieldSet` from client state. Once CR-01 is fixed to use
the server-retained field set, this becomes redundant (and, if left trusted, is the attack
surface CR-01 describes). Harmless to send, but the client should not be the source of truth.
**Fix:** After CR-01, either drop `field_set` from `ConfirmRequest`/the payload, or keep it only
as a signature the server verifies against `entry.field_set` and rejects on mismatch.

### IN-02: `_MAX_ENTRIES` eviction can silently drop the wrong upload under concurrent tokens

**File:** `src/assayingest/api/state.py:57-63,71-73`
**Issue:**
`put` evicts strictly by insertion order (oldest first). `get` (used by `confirm.py`) does not
refresh recency, so a long-lived upload a curator is still reviewing can be evicted by a burst of
newer uploads even though it was accessed more recently than they were created. Single-user demo
scope makes this benign, but the docstring's claim that "the upload I'm mid-review on is the last
thing ever evicted" does not hold under `get`-without-touch.
**Fix:** If recency matters, `move_to_end(token)` on `get`, or document that eviction is
creation-ordered, not access-ordered.

---

_Reviewed: 2026-07-11T09:21:20Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
