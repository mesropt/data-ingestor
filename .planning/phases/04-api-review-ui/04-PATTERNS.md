# Phase 4: API & Review UI - Pattern Map

**Mapped:** 2026-07-10
**Files analyzed:** ~24 (service layer 1, api/ ~9, learning field-set store 2, frontend ~15+ net-new, tests ~3)
**Analogs found:** 9 / 9 backend-side file groups (React frontend has no in-repo analog — see below)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/assayingest/service.py` | service | request-response | `src/assayingest/cli.py` (`_resolve_proposal`, `_map_one`, `run()`) | exact (extraction, not analog-by-similarity) |
| `src/assayingest/cli.py` (modified) | controller (CLI adapter) | request-response | itself, post-refactor | exact |
| `src/assayingest/api/app.py` | config/wire-up | request-response | none in-repo (net-new: FastAPI app object) | none — follow RESEARCH.md Pattern 3 |
| `src/assayingest/api/deps.py` | config (DI seam) | request-response | `cli.py::_resolve_store` (store construction) | partial |
| `src/assayingest/api/wire.py` | model (wire) | request-response | `src/assayingest/mapping/schema.py` (Claude wire models) + `cli.py::proposal_to_dict`/`_field_to_dict` | role-match (HTTP wire, not Claude wire, but same wire↔domain boundary discipline) |
| `src/assayingest/api/routes/upload.py` | route/controller | request-response, file-I/O | `cli.py::run()`/`_map_and_report` + `parsing/table.py::parse_file` | role-match |
| `src/assayingest/api/routes/structural_hint.py` | route/controller | request-response | `cli.py::_ask_and_report`/`_try_replay_saved_hint` | role-match |
| `src/assayingest/api/routes/confirm.py` | route/controller | request-response | `cli.py::_map_one` (validate+gate) + `learning/reconstruct.py` (build-then-validate shape) | exact (gate logic) |
| `src/assayingest/api/routes/field_sets.py` | route/controller, CRUD | CRUD | `learning/sqlite_store.py` (repository CRUD) via `learning/field_set_store.py` | role-match |
| `src/assayingest/api/routes/export.py` | route/controller, file-I/O | file-I/O | `cli.py::_export_if_ready` + `export/writers.py` | exact |
| `src/assayingest/learning/field_set_store.py` | model/interface (ABC) | CRUD | `src/assayingest/learning/store.py` (`ProfileStore` ABC) | exact |
| `src/assayingest/learning/sqlite_field_set_store.py` | service (repository impl) | CRUD | `src/assayingest/learning/sqlite_store.py` (`SqliteProfileStore`) | exact |
| `frontend/src/**/*.tsx` (all components) | component | request-response, event-driven | none in-repo | none — net-new, governed by `04-UI-SPEC.md` |
| `tests/test_api_*.py` | test | request-response | `tests/test_cli_run.py` + `tests/test_learning_loop_cli.py` | role-match (monkeypatch idiom identical; TestClient replaces subprocess/direct-call) |

## Pattern Assignments

### `src/assayingest/service.py` (service, request-response) — THE KEY REFACTOR

**Analog:** `src/assayingest/cli.py` lines 490-657 (`_resolve_proposal`, `_map_one`, `_save_profile_if_ready`, `_export_if_ready`)

**What to extract verbatim (decision logic, strip every `print`):**

`_resolve_proposal` (`cli.py:490-533`) — the auto-apply/fresh-Claude branch. This is already print-light (one `print` at line 516 on auto-apply hit) and already returns `(proposal, provenance)`. **Copy this almost unchanged into `service.py`**, just delete the one `print` (line 516) and let the caller (both `cli.py` and the API route) render the "no Claude call" fact themselves from the returned `provenance` string. Signature to preserve exactly:

```python
def _resolve_proposal(
    table: RawTable, field_set: FieldSet | None, store: ProfileStore | None,
    *, headers_only: bool = False,
) -> tuple[MappingProposal | None, str]:
```

The `field_set is None` → `raise ValueError("Cannot map: no field set was provided...")` at `cli.py:521-531` is the exact "error message names the consequence" pattern (CLAUDE.md convention) to keep verbatim in the service layer — do not soften it into an `Optional` return.

**The gate-recompute sequence in `_map_one` (`cli.py:536-592`)** is the template for `service.confirm()`. Strip everything from `print(...)` (lines 575, 580-583) — keep only:
1. `_resolve_proposal(...)` call + its two exception handlers (`AuthenticationError`, `APIError`/`ValueError`) — **but** as return values/raised exceptions, not `print`+return-int. The API needs these same three outcomes (success, bad-credentials, mapping-error) surfaced as distinct types the route layer turns into HTTP status codes (401/500/422), not exit codes 1/3.
2. `validate(table, proposal, field_set, strictness=strictness)` at line 573 — copy verbatim, this line is identical for CLI and API.
3. `canonical.assemble(table, proposal, field_set)` at line 579 — copy verbatim (EXPORT-01 tidy table both adapters need).
4. The `save_profile`/`export_dir` gate calls (`_save_profile_if_ready` line 585, `_export_if_ready` line 590) become service functions returning data (a saved `profile.profile_id` or a `NotReadyError`), not printing "not saved"/"not exported" strings — the API route or CLI wrapper renders that message itself.

**`_save_profile_if_ready` (`cli.py:595-624`)** — copy the gate check (`if not proposal.is_ready: ...`) and the `LearnedProfile(...)` construction verbatim (lines 613-622) into a service function; replace the two `print()` calls (608, 611, 624) with either a raised `NotReadyError`/`NoStoreError` or a returned `profile.profile_id`.

**`_export_if_ready` (`cli.py:627-656`)** — copy the `write_csv`/`write_xlsx`/`write_json`/`build_manifest` sequence (lines 647-655) verbatim into a service function; the `export_dir.mkdir(parents=True, exist_ok=True)` line and the four writer calls are exactly what the API's `/api/export` flow needs (RESEARCH.md's "server-side temp/output dir" note).

**What stays CLI-only (do NOT move to service.py):** `render_report`, `_render_field`, `_render_gate`, `_render_question`, `_ask_and_report`'s printing, `_hint_from_args`, `main()`'s `argparse` setup, and every literal `print(...)` call. `proposal_to_dict`/`_field_to_dict` (`cli.py:50-72`) are the one exception — already public, print-free, pure-data — reuse these directly from `api/wire.py` rather than re-deriving the same dict shape (RESEARCH.md Pattern 4 says this explicitly).

**Server-side gate (`api/routes/confirm.py`'s `service.confirm()`) — exact recomputation order to copy from `cli._map_one` (lines 567-591):**
```python
# cli.py:567-591 order, mirrored 1:1 in service.confirm():
proposal = validate(table, proposal, field_set, strictness=strictness)   # line 573
tidy = canonical.assemble(table, proposal, field_set)                     # line 579
if save_profile: _save_profile_if_ready(...)                              # line 585 (gate: proposal.is_ready)
if export_dir is not None: _export_if_ready(...)                          # line 590 (gate: proposal.is_ready)
return 0 if proposal.is_ready else 5                                      # line 592 — becomes 422 in the API
```

---

### `src/assayingest/api/wire.py` (model, request-response)

**Analog 1 (Claude-facing wire, same discipline different direction):** `src/assayingest/mapping/schema.py` — module docstring lines 1-18 states the exact principle to copy: *"These Pydantic models live at the infrastructure boundary... the mapper validates Claude's output against them and then maps them onto the domain `MappingProposal`."* Do the same in reverse — `api/wire.py`'s Pydantic models are what the domain gets serialized TO for the browser, never mixed into `domain/models.py`. `WireCandidate` (schema.py:27-31) is the exact shape to mirror for the HTTP-facing `AlternativeOut`:
```python
class WireCandidate(BaseModel):
    source_column: str = Field(description="A source header that could match.")
    confidence: float = Field(description="0.0-1.0 confidence for this option.")
```

**Analog 2 (the dict shape to match field-for-field):** `src/assayingest/cli.py:50-72` (`proposal_to_dict`, `_field_to_dict`) — already the exact JSON shape API-01's response needs (`ready`, `source_columns`, `field_mappings[]` with `target_field`/`source_column`/`confidence`/`reasoning`/`needs_confirmation`/`inferred_value`/`alternatives[]`). Per RESEARCH.md Pattern 4: define `api/wire.py`'s `MappingResponse`/`FieldMappingOut` Pydantic models with field names identical to this dict's keys, populated FROM `cli.proposal_to_dict(proposal, provenance)`'s output — never hand-derive a second, drifting shape. Note the dict does not currently include `validator_note` (it's on the domain `FieldMapping` per `validation/validator.py` but `_field_to_dict` at `cli.py:60-72` omits it) — the API wire model MUST add it (UI-SPEC requires it distinctly from `reasoning`), so this is one place `api/wire.py` extends rather than mirrors byte-for-byte.

---

### `src/assayingest/learning/field_set_store.py` (model/interface, CRUD)

**Analog:** `src/assayingest/learning/store.py` (the entire file, 37 lines) — copy structure exactly:
- Same `ABC`/`@abstractmethod` shape.
- Same docstring convention: state which future implementation this seam allows to swap in (`store.py:15-21` — "the seam a Postgres-backed store... implements identically").
- Same method-count discipline: `store.py` has exactly `save`/`find`/`list_for_field_set` — for field-set templates, RESEARCH.md's sketch (`save`/`get`/`list`) is the right analog size — do not add more methods than the UI actually calls (UI-01: list templates, save one, load one by id).

```python
# store.py:15-21 — copy this docstring pattern verbatim, adjust nouns:
class ProfileStore(ABC):
    """The seam a Postgres-backed store (Phase 4+) implements identically.
    A local SQLite file is v1's only implementation (`sqlite_store.py`), but
    nothing in the domain or the CLI's auto-apply path may depend on that
    fact -- only on the three methods declared here."""
```

### `src/assayingest/learning/sqlite_field_set_store.py` (service/repository, CRUD)

**Analog:** `src/assayingest/learning/sqlite_store.py` (the entire file, 113 lines) — copy line-for-line pattern:
- Module docstring's non-negotiable rule to keep: *"the ONLY module in this project allowed to `import sqlite3`"* (`sqlite_store.py:1-11`) — extend that sentence's set to name the field-set store module too, or place both in one file per RESEARCH.md's "same file" recommendation (D-03).
- `_DEFAULT_DB_PATH = ".assayingest/profiles.db"` (`sqlite_store.py:26`) — RESEARCH.md's schema sketch recommends reusing this exact same file/constant with a second `CREATE TABLE IF NOT EXISTS` statement appended to `_SCHEMA` (`sqlite_store.py:28-40`), not a second `.db` file.
- `closing(sqlite3.connect(...))` + `conn.row_factory = sqlite3.Row` idiom (`sqlite_store.py:46-50, 79-80, 89-90`) — copy verbatim for every query.
- Parameterized `?` placeholders ONLY — `sqlite_store.py:8-11` docstring states why (untrusted header content) — the same reasoning applies even more directly to field-set names, which are raw user text from the browser.
- `save()`'s `ON CONFLICT(...) DO UPDATE SET` upsert idiom (`sqlite_store.py:57-76`) — reuse for `UNIQUE(name)` from RESEARCH.md's schema sketch.
- `_row_to_profile(row)` (`sqlite_store.py:98-112`) is explicitly self-documented as "the wire (SQLite row) -> domain... boundary translator -- the analog of `mapping/mapper.py::_to_domain`" — write `_row_to_field_set_template(row)` following the identical shape and comment convention.

---

### `src/assayingest/api/routes/confirm.py` (route/controller, the server-side gate)

**Analog 1 (recompute-then-gate order):** `cli.py:536-592` (`_map_one`) — see service.py section above; the route handler's own job is thin: deserialize JSON → call `service.confirm(...)` → map its return/exception to an HTTP status.

**Analog 2 ("build proposal from external input then validate" shape):** `src/assayingest/learning/reconstruct.py::reconstruct_proposal` (lines 51-68) — this is RESEARCH.md's own cited analog for "rebuild domain object from external data, then hand to `validate()`, never trust the source's own claims about readiness." The specific transferable idiom:
```python
# reconstruct.py:63-68 — the shape to mirror in service.confirm():
# 1. build fresh domain object(s) from external input (stored profile / HTTP body)
# 2. do NOT copy across any "already validated" flag from that external input
# 3. return the freshly-built object; caller (here: confirm()) still calls validate()
mappings = [_reconstruct_field(stored, new_headers, occurrence_counts) for stored in profile.field_mappings]
return MappingProposal(source_columns=list(new_headers), field_mappings=mappings)
```
`reconstruct.py`'s module docstring (lines 1-21) is worth reading verbatim before writing `confirm.py` — it names the exact P1 failure mode ("exactly the kind of wrong-or-missing-field-with-no-error P1 forbids") that a naive `if request_body.ready: save()` would reintroduce at the HTTP layer.

**Never-trust-client fields:** see RESEARCH.md's "Server-Side Gate" table (already phase-specific and authoritative — do not re-derive) — `needs_confirmation`, `validator_note`, `is_ready`/`ready` are always recomputed server-side by calling `validate()` fresh, matching `_apply_objection`'s additive-only OR discipline documented in `validation/validator.py:18-26`.

---

### `src/assayingest/api/routes/upload.py` (route/controller, file-I/O)

**Analog:** `src/assayingest/parsing/table.py::parse_file(path: str | Path, sheet: str | None = None)` (line 95) and `sheet_names(path)` (line 73) — both take a filesystem path, never bytes/file-like. RESEARCH.md's File Upload Handling section (already phase-specific) covers the `UploadFile → tempfile.NamedTemporaryFile → parse_file(tmp_path)` translation — copy that pattern; do not change `parse_file`'s signature (CONTEXT.md phase boundary: "never reimplement... parsing").

**Analog for the `run()`-shaped orchestration the route replicates:** `cli.py:179-252` (`run()`) — specifically the `resolve_or_ask` → `StructureQuestion` branch check (`cli.py:228-244`) → `_map_and_report` (`cli.py:249-252`) sequence is exactly the flow `service.resolve_or_map()` (RESEARCH.md Pattern 1's example) reimplements as data-returning. Reuse `resolve_or_ask` (`cli.py:160-176`) UNCHANGED — it is already public and print-free.

---

### `src/assayingest/api/routes/structural_hint.py` (route/controller, request-response)

**Analog:** `cli.py:346-369` (`_ask_and_report`) for the shape of what data a structural question carries, and `cli.py:372-391` (`_enrich_question`) for the `headers_only` gate that must be honored on this path too (P2, CR-01 — RESEARCH.md flags this explicitly). The route must reuse `StructureQuestion.to_dict()` (already referenced at `cli.py:366`) verbatim rather than re-deriving fields.

```python
# cli.py:364-366 — the exact P2 guard to replicate in the API route:
if not headers_only:
    question = _enrich_question(question)
print(json.dumps(question.to_dict(), indent=2, ensure_ascii=False))
```
Replace the `print` with a JSON response; keep the `if not headers_only: ... enrich` guard identical — this is the CR-01 privacy fix and must not regress at the new HTTP call site.

---

### `src/assayingest/api/routes/field_sets.py` (route/controller, CRUD)

**Analog:** `src/assayingest/learning/sqlite_store.py` used through `learning/field_set_store.py`'s ABC (see above) — the route itself is a thin CRUD wrapper: `GET` → `store.list()`, `POST` → `store.save(name, field_set)`, `GET /{id}` → `store.get(id)`. No new business logic; `FieldSet.to_dict()`/loader shape already exists in `src/assayingest/fields/models.py` and `fields/loader.py` for the JSON (de)serialization the route needs — reuse those, don't hand-roll a parallel `FieldSet` JSON encoder.

---

### `src/assayingest/api/routes/export.py` (route/controller, file-I/O)

**Analog:** `cli.py:627-656` (`_export_if_ready`) + `src/assayingest/export/writers.py` (`write_csv`, `write_xlsx`, `write_json`, `build_manifest`). Copy the gate check (`if not proposal.is_ready: ...` at `cli.py:643-645`) and the four-writer sequence (`cli.py:647-655`) into `service.export(...)`; the route itself only needs `FileResponse` with the right `Content-Type` for each of the four `fmt` values — no new writer logic (RESEARCH.md's "Don't Hand-Roll" table already forbids reimplementing this).

---

## Shared Patterns

### Public API / no-underscore-import discipline
**Source:** `.claude/CLAUDE.md` — "Public API is everything not prefixed with `_`"
**Apply to:** every file in `api/` — none may import a `cli._foo` name; every decision-making function `api/` needs must first be lifted to `service.py` as a public, non-underscore function. This is the single governing rule for this whole phase's structure.

### Wire↔domain boundary mapping
**Source:** `src/assayingest/mapping/schema.py` (module docstring, lines 1-18) + `src/assayingest/mapping/mapper.py::_to_domain` (line 195) + `src/assayingest/learning/sqlite_store.py::_row_to_profile` (lines 98-112, explicitly self-labeled as `_to_domain`'s analog)
**Apply to:** `api/wire.py` (HTTP request/response models), `learning/sqlite_field_set_store.py` (`_row_to_field_set_template`)
```python
# sqlite_store.py:98-101 — the naming/comment convention to replicate for every new boundary translator
def _row_to_profile(row: sqlite3.Row) -> LearnedProfile:
    """The wire (SQLite row) -> domain (`LearnedProfile`) boundary
    translator -- the `sqlite3.Row -> LearnedProfile` analog of
    `mapping/mapper.py::_to_domain`."""
```

### Repository seam (ABC + SQLite impl, parameterized queries only)
**Source:** `src/assayingest/learning/store.py` + `src/assayingest/learning/sqlite_store.py`
**Apply to:** `src/assayingest/learning/field_set_store.py` + `src/assayingest/learning/sqlite_field_set_store.py` (D-03 exact mirror)

### Error handling / exit-code-to-HTTP-status mapping
**Source:** `cli.py:551-566` (`_map_one`'s exception handling: `AuthenticationError` → exit 3, `APIError`/`ValueError` → exit 1, missing-credentials sentinel → exit 3) + `.claude/CLAUDE.md` "Log-or-raise, never both"
**Apply to:** every `api/routes/*.py` — the SAME three failure modes exist at the HTTP layer, just mapped to status codes instead of exit codes (e.g. `AuthenticationError`→401, mapping `ValueError`/`APIError`→500, `NotReadyError` from the gate→422). `service.py` should raise typed exceptions (not print+return-int) so each adapter (CLI, API) maps them to its own vocabulary (exit code vs. HTTP status) without duplicating the `try/except` logic itself.

### Optional-client seam (auto-apply constructs no Anthropic client)
**Source:** `cli.py:512-517` (`_resolve_proposal`'s profile-hit branch returns before any credential check) + `learning/reconstruct.py` module docstring lines 16-20 ("constructs no `anthropic.Anthropic` client at all... this module has no Anthropic SDK import")
**Apply to:** `api/routes/upload.py`'s auto-apply branch (API-03) — must reach `reconstruct_proposal` without ever touching `_has_credentials()`/constructing a client, exactly as `_resolve_proposal` does today.

### Never-trust-client gate (P1 fail-closed)
**Source:** `validation/validator.py` module docstring lines 1-27 (esp. "A violation forces `needs_confirmation=True` no matter how confident Claude reported the field... the caller is responsible for calling `validate()` on both paths") + `learning/reconstruct.py` module docstring lines 9-15
**Apply to:** `api/routes/confirm.py` / `service.confirm()` exclusively — the one place in the whole phase where "trust nothing the client asserts about readiness" is load-bearing.

### Test idiom: monkeypatch the same seams, offline
**Source:** `tests/test_cli_run.py` lines 65-88 (`monkeypatch.setattr(cli, "propose_mapping", lambda ...)`) + `tests/test_learning_loop_cli.py` lines 28-95 (fixture builders `_ready_field_mappings()`/`_blocked_field_mappings()`, `SqliteProfileStore` against a tmp path, `novascreen_batch01/02` same-signature corpus files)
**Apply to:** `tests/test_api_*.py` — use `fastapi.testclient.TestClient` + `monkeypatch.setattr(<module under test>, "propose_mapping", ...)` at whatever module now owns the import (service.py, not cli.py, once the propose_mapping import moves) — same fixture files (`data/synthetic/novascreen_batch01.csv`/`novascreen_batch02.csv`), same `_ready_field_mappings()`/`_blocked_field_mappings()` builder idiom, same "money shot" structure (upload → yellow → confirm+save → re-upload same signature → zero yellow, spy asserts `propose_mapping` was called exactly once across both uploads).

```python
# test_cli_run.py:65-72 — the exact idiom to port to API tests (swap direct call for TestClient.post)
monkeypatch.setattr(
    cli, "propose_mapping", lambda table, field_set, client=None, **kwargs: _blocked_proposal()
)
monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `frontend/**` (entire React app: `AppShell`, `FieldEditorRow`, `UploadDropzone`, `StructuralHintPanel`, `ReviewTable`, `FieldRow`, `ConfidenceChip`, `ConfirmGate`, `ExportBar`, `ProfileAppliedBanner`, all Vite/shadcn config) | component / hook / provider | event-driven, request-response | No JS/TS/frontend code exists anywhere in this repo (Python-only project to date, confirmed by `find` across `src/`). This is a first-of-kind for the whole codebase. **The authoritative reference is `04-UI-SPEC.md`** (Design System, Color, Typography, Screens & States, Component Inventory sections) — treat every component listed there as net-new with no code to copy from, only the design contract to implement against. |
| `src/assayingest/api/app.py` | config (FastAPI app object, `app.frontend()` mount, router includes) | request-response | No FastAPI/ASGI code exists in this repo yet. Follow `04-RESEARCH.md` Pattern 2 (sync `def` endpoints) and Pattern 3 (`app.frontend()`) verbatim — those are the reference, not an in-repo file. |

## Metadata

**Analog search scope:** `src/assayingest/` (all 30 `.py` files), `tests/` (all 35 test files), `.claude/CLAUDE.md`/`CLAUDE.md` conventions
**Files scanned:** `cli.py`, `learning/store.py`, `learning/sqlite_store.py`, `learning/reconstruct.py`, `mapping/schema.py`, `mapping/mapper.py`, `parsing/table.py`, `validation/validator.py`, `tests/test_cli_run.py`, `tests/test_learning_loop_cli.py`
**Pattern extraction date:** 2026-07-10
