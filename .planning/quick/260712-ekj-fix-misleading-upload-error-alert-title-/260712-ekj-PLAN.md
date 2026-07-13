---
phase: quick-260712-ekj
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - frontend/src/state/upload.ts
  - frontend/src/state/upload.test.ts
  - frontend/src/screens/Upload.tsx
  - frontend/src/components/UploadDropzone.tsx
  - pyproject.toml
  - uv.lock
  - src/assayingest/env.py
  - src/assayingest/api/app.py
  - src/assayingest/cli.py
  - README.md
  - tests/test_cli_run.py
  - tests/test_cross_domain.py
  - tests/test_max_tokens_live.py
  - tests/api/test_google_oauth_flag.py
autonomous: true
requirements: [UI-02, API-01]

must_haves:
  truths:
    - "An upload error alert never asserts a cause the server did not report: a 503 (no Anthropic credentials) shows a mapper-availability title, not a parse-failure title."
    - "An error whose cause is unknown to the client shows a neutral title; the server's own consequence-shaped detail always remains visible in the alert description."
    - "The README's documented command `uv run uvicorn assayingest.api.app:app --port 8000` starts a server whose mapper works, with no --env-file flag."
    - "`assayingest <file> --fields ...` picks up ANTHROPIC_API_KEY from the repo-root .env with no extra flag."
    - "A real environment variable always beats the .env file: an exported/injected ANTHROPIC_API_KEY is never overwritten by a .env value."
    - "The full backend pytest suite and the frontend vitest suite are green, and pytest makes no live Claude API calls unless explicitly opted in."
    - ".env stays untracked; no secret value is printed, logged, or committed."
  artifacts:
    - "src/assayingest/env.py — load_project_env(), the single composition-root .env loader (override=False)"
    - "frontend/src/state/upload.ts — uploadErrorTitle(), a pure status->title map; error state carries a title"
    - "frontend/src/state/upload.test.ts — vitest coverage proving a 503 does not get a parse-failure title"
    - "pyproject.toml — python-dotenv declared as a direct dependency"
    - "README.md — Quickstart documents the .env path and the env-var-wins rule"
  key_links:
    - "api/app.py imports load_project_env() and calls it at module import, BEFORE the module-level os.environ.get(ASSAYINGEST_DEV_CORS / DATA_INGESTOR_GOOGLE_OAUTH) reads and before FastAPI() is constructed — uvicorn imports this module, there is no main()"
    - "cli.py calls load_project_env() as the first statement of main() only — never at import, never in run(), so the pytest suite's direct run() calls keep today's env semantics"
    - "service.has_credentials() reads os.environ at CALL time, so a startup-time load is enough — no signature or domain change anywhere"
    - "Upload.tsx's three catch sites (UPLOAD_ERROR / HINT_ERROR / RECONCILE_ERROR) pass uploadErrorTitle(err) alongside consequenceMessage(err, ...) — one helper, three call sites, no drift"
---

<objective>
Fix the two demo-day footguns found in live browser UAT:

1. The upload error alert hardcodes a parse-failure title for EVERY error, so a
   missing-API-key 503 was reported to the curator as "this file can't be read" —
   actively misleading, and the exact thing the product's own "never guess silently"
   principle forbids. Make the title tell the truth, or say nothing more than "Upload failed".
2. The backend never loads `.env`, so the README's own Quickstart command starts a
   server whose mapper ALWAYS fails. Load `.env` at the composition root of both real
   entrypoints (FastAPI app, CLI `main()`), without ever overriding a real environment
   variable — and fix the README.

Purpose: a judge copy-pasting the README must get a working demo, and any failure they
do hit must be described accurately.
Output: an accurate error title (pure, vitest-covered), a `.env` loader at the
composition root, a corrected README, and both test suites green with no accidental
live Claude calls.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.claude/CLAUDE.md
@.planning/STATE.md
@frontend/src/components/UploadDropzone.tsx
@frontend/src/state/upload.ts
@frontend/src/screens/Upload.tsx
@frontend/src/lib/api.ts
@src/assayingest/api/app.py
@src/assayingest/service.py
@src/assayingest/cli.py
@README.md
@pyproject.toml

Interface facts already established (do NOT re-derive):
- `ApiError` (frontend/src/lib/api.ts) carries `status: number` and `detail: unknown`;
  every non-2xx from `fetch` is thrown as one. Any other thrown value is a network/JS error.
- `Upload.tsx` already has a local `consequenceMessage(error, fallback)` (line ~58) that
  renders the server's own `detail` when present, falling back to a consequence-shaped
  string. The alert DESCRIPTION is already correct — only the TITLE lies.
- `UploadState`'s error arm is `{ phase: "error"; file: File; message: string }`; the three
  error actions (`UPLOAD_ERROR`, `HINT_ERROR`, `RECONCILE_ERROR`) each carry `message: string`.
  `state/upload.ts` is pure (no React import) and is already covered by `state/upload.test.ts`.
- Server status codes actually emitted by `api/routes/upload.py`: 503 = MissingCredentialsError,
  413 = over the size limit, 400 = rejected file extension, 401/403 = auth/verification gates
  (reconcile) OR Anthropic rejecting credentials, 404 = unknown upload token, 422 = bad field set /
  reconcile inputs, 500 = parse ValueError OR anthropic.APIError. 401 and 500 are each used for
  two unrelated causes — so those MUST fall through to the neutral title, never a guessed one.
- `service.has_credentials()` reads `os.environ` at call time (service.py:78-86), so loading
  `.env` once at startup is sufficient; no service/domain change is needed.
- `python-dotenv` is ALREADY in `uv.lock` (transitively, via `uvicorn[standard]`), so declaring
  it as a direct dependency adds zero new download — it just makes the reliance explicit.
- `.gitignore` already ignores `.env` (and keeps `!.env.example`). `.env.example` exists.
- Existing "no credentials" tests already `monkeypatch.delenv(...)` explicitly (test_service.py,
  test_cli_run.py, test_validator_cli.py, ...) — they are safe under an auto-loaded `.env`.
  The two fragile spots are named in Task 3.

HARD RULE: never open, print, echo, cat, or otherwise surface the contents of `.env`.
Its API key must not appear in any command output, test, artifact, or commit.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Derive the upload error alert title from the error, never assert a cause we don't know</name>
  <files>frontend/src/state/upload.ts, frontend/src/state/upload.test.ts, frontend/src/screens/Upload.tsx, frontend/src/components/UploadDropzone.tsx</files>
  <behavior>
    New pure helper `uploadErrorTitle(error: unknown): string` in `state/upload.ts`:
    - Test 1: an `ApiError` with status 503 returns "The mapper isn't available" (NOT any parse-related title) — the exact UAT defect.
    - Test 2: an `ApiError` with status 413 returns "This file is too large".
    - Test 3: an `ApiError` with status 400 returns "This file type can't be ingested".
    - Test 4: an `ApiError` with status 500 returns the neutral "Upload failed" (500 is emitted for BOTH a parse failure and an Anthropic API error — the client cannot tell them apart, so it must not guess).
    - Test 5: an `ApiError` with status 401 returns the neutral "Upload failed" (401 is emitted for both a sign-in gate and rejected Anthropic credentials).
    - Test 6: a plain `Error` (network failure, no status) returns the neutral "Upload failed".
    Reducer:
    - Test 7: `UPLOAD_ERROR` from `uploading` produces `{ phase: "error", file, message, title }` carrying BOTH the message and the title it was dispatched with.
    - Test 8: `HINT_ERROR` from `resolving` and `RECONCILE_ERROR` from `resolvingReconcile` likewise carry their title through.
    Write these tests FIRST in `frontend/src/state/upload.test.ts` and watch them fail (RED) before touching `upload.ts`.
  </behavior>
  <action>
    RED: extend `frontend/src/state/upload.test.ts` with the behaviours above. Import `ApiError`
    from `../lib/api` to build the error objects.

    GREEN, in `frontend/src/state/upload.ts`:
    - Export `uploadErrorTitle(error: unknown): string`. Implement it as a small explicit
      `status -> title` lookup applied only when `error instanceof ApiError`, returning a
      module-level neutral default for every other status and for any non-ApiError value.
      Map ONLY the three statuses the server emits for a single unambiguous cause: 503
      (mapper/credentials unavailable), 413 (over the size limit), 400 (rejected extension).
      Every other status — notably 401 and 500, each of which the server emits for two
      unrelated causes — falls through to the neutral default. Document that rule in the
      function's docstring comment: a title that names a cause the server did not report is
      the defect being fixed here, and principle 2 ("never guess silently") applies to our own
      error copy, not just to Claude's mappings.
    - Add `title: string` to the `error` arm of `UploadState` and to the `UPLOAD_ERROR`,
      `HINT_ERROR` and `RECONCILE_ERROR` actions; carry it through the three reducer arms
      alongside `message`.

    In `frontend/src/screens/Upload.tsx`: at each of the three catch sites (~lines 176, 195, 214)
    add `title: uploadErrorTitle(err)` to the dispatched action, leaving the existing
    `consequenceMessage(err, ...)` fallbacks exactly as they are. Derive
    `dropzoneErrorTitle = state.phase === "error" ? state.title : null` next to the existing
    `dropzoneErrorMessage` (~line 228) and pass it to `<UploadDropzone errorTitle={...} />`.

    In `frontend/src/components/UploadDropzone.tsx`: add an `errorTitle?: string | null` prop
    and render it inside `<AlertTitle>` in place of the hardcoded string, falling back to the
    neutral default when it is null/undefined. Keep the `<AlertDescription>{errorMessage}</AlertDescription>`
    line untouched — the description was already correct. Update the component docstring's
    description of the `error` state so it no longer claims the alert reports a parse failure.

    Import direction stays clean: `state/upload.ts` may import from `lib/api` (types + ApiError);
    nothing in `lib/` imports `state/`.
  </action>
  <verify>
    <automated>cd frontend && npm run test -- --run && npm run build && test "$(grep -c 'read as a table' src/components/UploadDropzone.tsx)" = "0" && test "$(grep -c 'errorTitle' src/components/UploadDropzone.tsx)" -ge 2 && grep -q 'uploadErrorTitle' src/screens/Upload.tsx</automated>
  </verify>
  <done>
    `uploadErrorTitle` is exported, pure, and covered by vitest for 503/413/400/500/401/non-ApiError;
    the reducer carries a title on all three error paths; `UploadDropzone` renders the passed title
    with a neutral fallback and no longer hardcodes a cause; `npm run build` (tsc -b) and
    `npm run test -- --run` are both green.
  </done>
</task>

<task type="auto">
  <name>Task 2: Load .env at the composition root of both entrypoints, without ever overriding a real env var</name>
  <files>pyproject.toml, uv.lock, src/assayingest/env.py, src/assayingest/api/app.py, src/assayingest/cli.py, README.md</files>
  <action>
    Declare the dependency: add `"python-dotenv>=1.0"` to `[project].dependencies` in `pyproject.toml`.
    It is already resolved in `uv.lock` transitively via `uvicorn[standard]`, so this adds no new
    download — it makes an implicit reliance explicit rather than depending on another package's extra.
    Refresh the lock with `uv sync` (do NOT hand-edit `uv.lock`).

    Create `src/assayingest/env.py` — a new infrastructure module at the composition root, NOT in
    the domain (per the Clean Architecture convention: the domain never reads the process
    environment or the filesystem). Module docstring: explains that this is the one place the
    project reads a `.env` file, that it exists so the README's documented `uvicorn ...` and
    `assayingest ...` commands work with no extra flags, and that a real environment variable
    always wins.

    Implement one public function, `load_project_env() -> bool`, returning whether a file was
    actually loaded:
    - Resolve the file with `find_dotenv(usecwd=True)` so the search walks UP from the process
      working directory (the README runs both commands from the repo root). This never depends on
      where the package happens to be installed.
    - PITFALL — guard on the empty result: `find_dotenv` returns `""` when nothing is found, and
      `load_dotenv("")` does NOT no-op — an empty path is falsy, so python-dotenv silently falls
      back to its own frame-based search. Return `False` early when the resolved path is empty, and
      only call `load_dotenv(path, override=False)` when it is non-empty. Say why in a comment.
    - Pass `override=False`. This is the non-negotiable rule: a credential already present in the
      process environment (a CI secret, a deployment's injected env, an `export` in the operator's
      shell) MUST beat a `.env` file on disk, never the other way round. State that in the docstring.
    - The function never logs, prints, or returns any variable VALUE — only the boolean.

    Wire it into `src/assayingest/api/app.py`: import `load_project_env` from `..env` and call it at
    module import, immediately after the imports and BEFORE `_configure_console_logging()` /
    `app = FastAPI(...)` / the module-level `os.environ.get("ASSAYINGEST_DEV_CORS")` and
    `os.environ.get("DATA_INGESTOR_GOOGLE_OAUTH")` reads. Ordering is load-bearing: `uvicorn
    assayingest.api.app:app` imports this module and never calls a `main()`, and the two
    conditional-middleware blocks read the environment at import time, so a `.env` value must be in
    place before them or it has no effect. Add a short comment saying exactly that.

    Wire it into `src/assayingest/cli.py`: call `load_project_env()` as the FIRST statement of
    `main()` (line ~686). Deliberately NOT at module import and NOT inside `run()` — the pytest suite
    calls `run()` directly, so keeping the load in `main()` leaves every existing CLI test's
    environment semantics exactly as they are today. Note that reasoning in a comment.

    Update `README.md`'s Quickstart (~lines 19-29): replace the bare `export ANTHROPIC_API_KEY=…`
    line with both options — export it, OR `cp .env.example .env` and put the key in `.env` at the
    repo root, which the server and the CLI both load automatically at startup. State the precedence
    rule explicitly (a real environment variable always wins over `.env`) and that `.env` is
    gitignored and must never be committed. Leave the `uv run uvicorn assayingest.api.app:app
    --port 8000` command exactly as written — making that unchanged command work is the point of
    this task.

    Do NOT read, print, or commit `.env`. Confirm it stays ignored (`git check-ignore .env`) and that
    `git status --short` shows no `.env` before committing.
  </action>
  <verify>
    <automated>uv sync && git check-ignore -q .env && test -z "$(git status --porcelain -- .env)" && uv run python -c "
import os, pathlib
from assayingest.env import load_project_env
os.environ['ANTHROPIC_API_KEY'] = 'sentinel-real-env-wins'
load_project_env()
assert os.environ['ANTHROPIC_API_KEY'] == 'sentinel-real-env-wins', 'override=False violated: .env clobbered a real env var'
import subprocess
out = subprocess.run(['git','grep','-n','load_project_env','--','src/assayingest/api/app.py','src/assayingest/cli.py'], capture_output=True, text=True).stdout
assert 'api/app.py' in out and 'cli.py' in out, 'load_project_env is not wired into both entrypoints'
print('ok')
" && grep -q 'python-dotenv' pyproject.toml && grep -q '.env' README.md</automated>
    <human-check>Run `uv run uvicorn assayingest.api.app:app --port 8000` (no --env-file), upload a file in the browser, and confirm the mapper runs instead of surfacing the mapper-unavailable error.</human-check>
  </verify>
  <done>
    `src/assayingest/env.py` exists with `load_project_env()` (find_dotenv(usecwd=True), empty-path
    guard, `override=False`); it is called at import in `api/app.py` above the env-flag reads and as
    the first statement of `cli.main()`; `python-dotenv` is a declared dependency with `uv.lock`
    refreshed; the README documents the `.env` path and the env-var-wins precedence; `.env` remains
    untracked and its contents never leave the file.
  </done>
</task>

<task type="auto">
  <name>Task 3: Regression sweep — full suites green, and no accidental live Claude calls</name>
  <files>tests/test_cli_run.py, tests/test_cross_domain.py, tests/test_max_tokens_live.py, tests/api/test_google_oauth_flag.py</files>
  <action>
    Auto-loading `.env` changes ambient process state during a pytest run, which has two known
    consequences. Fix both properly — NEVER by weakening or deleting a product assertion (the
    credential guard and the no-SessionMiddleware guarantee are real product behaviours).

    (a) Live-API tests would start firing for real. `tests/test_cli_run.py` (skipif at ~lines 121 and
    140), `tests/test_cross_domain.py` (~line 78) and `tests/test_max_tokens_live.py` (~line 45) each
    skip themselves via `skipif(not os.environ.get("ANTHROPIC_API_KEY"))`. pytest collects `tests/api/*`
    first, which imports `assayingest.api.app`, which now loads `.env` — so by the time those skipif
    expressions are evaluated a key IS present and the tests would make real, billable, non-deterministic
    Claude calls on every plain `pytest` run, one day before the deadline. Convert each of those four
    skipif conditions to an EXPLICIT opt-in: skip unless `os.environ.get("ASSAYINGEST_LIVE_TESTS") == "1"`,
    with a reason naming the flag. Every assertion inside those tests stays exactly as it is — this
    changes only WHEN they run, and they already do not run without a key today, so no coverage is lost.
    It also removes the collection-order dependency, which is the real bug here. Mention the flag in the
    README's test line if one exists.

    (b) `tests/api/test_google_oauth_flag.py:46-57` asserts the MODULE-LEVEL `app` object has no
    SessionMiddleware, but that object is built at import time from
    `os.environ.get("DATA_INGESTOR_GOOGLE_OAUTH")` — which a developer's `.env` may now set. Run the
    suite first: if the test passes, leave it alone. If it fails, make it deterministic instead of
    ambient-dependent — inside the test, `monkeypatch.delenv("DATA_INGESTOR_GOOGLE_OAUTH", raising=False)`,
    then `importlib.reload(assayingest.api.app)` and assert on the RELOADED module's `app`, restoring
    the module afterwards so no other test sees a swapped app object. Keep the assertion itself intact.

    Then run BOTH suites in full and fix any other fallout the same way — by making the test explicit
    about the environment it needs (`monkeypatch.delenv` / `monkeypatch.setenv`), never by softening
    what it asserts. Do NOT read the developer's `.env` to find out what is in it: infer only from the
    test failures.

    Backend: `uv run pytest -q`  (must be green with no network calls)
    Frontend: `cd frontend && npm run test -- --run`
  </action>
  <verify>
    <automated>uv run pytest -q && cd frontend && npm run test -- --run</automated>
  </verify>
  <done>
    `uv run pytest -q` is green and performs zero live Claude calls without `ASSAYINGEST_LIVE_TESTS=1`;
    the frontend vitest suite is green; every credential/middleware assertion that existed before this
    task still exists, unchanged, and now depends on an explicitly-set environment rather than an
    ambient one.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| disk (`.env`) -> process environment | A file on disk injects credentials into the process |
| process environment -> git / logs / test output | Where a secret could leak out |
| server error -> browser alert copy | Server-side failure detail surfaced to a human |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-ekj-01 | Elevation of Privilege | `env.py::load_project_env` | high | mitigate | `override=False` — a `.env` file on disk can never shadow a credential already injected by CI/deployment/operator shell; asserted by Task 2's sentinel check |
| T-ekj-02 | Information Disclosure | `.env` in the working tree | high | mitigate | `.gitignore` already covers `.env`; Task 2 verifies with `git check-ignore .env` + `git status --porcelain -- .env` before commit; no task reads or echoes its contents |
| T-ekj-03 | Information Disclosure | `load_project_env()` return value / logs | medium | mitigate | The function returns only a boolean and logs nothing — no variable name or value is ever printed |
| T-ekj-04 | Spoofing (misattribution) | `UploadDropzone` AlertTitle | medium | mitigate | Titles are derived ONLY for the three statuses with a single unambiguous cause (503/413/400); 401 and 500 (two causes each) fall through to a neutral title, so the UI never asserts a cause the server did not report |
| T-ekj-05 | Denial of Service (self-inflicted, cost) | pytest live-API tests | medium | mitigate | Live Claude tests become opt-in via `ASSAYINGEST_LIVE_TESTS=1`, so an auto-loaded key cannot silently turn every `pytest` run into billable network calls |
| T-ekj-SC | Tampering | dependency install (`python-dotenv`) | low | accept | `python-dotenv` is already present in `uv.lock` as a transitive dependency of `uvicorn[standard]` — this plan promotes an already-installed, already-locked package to a direct declaration and pulls in nothing new |
</threat_model>

<verification>
- `cd frontend && npm run test -- --run` — green, including the new `uploadErrorTitle` cases
- `cd frontend && npm run build` — tsc -b passes with the new prop/state shape
- `uv run pytest -q` — green, no live Claude calls
- `uv run uvicorn assayingest.api.app:app --port 8000` (NO `--env-file`) — the mapper works end to end
- `git status --short` — no `.env`, no secret, in the staged set
</verification>

<success_criteria>
- A missing-credentials failure shows a mapper-availability title, not a parse-failure claim; an
  ambiguous failure shows a neutral title with the server's own detail beneath it.
- The README's unmodified Quickstart command starts a working demo server on a fresh clone whose
  `.env` holds the key.
- An exported `ANTHROPIC_API_KEY` is never overwritten by `.env`.
- Both suites green; every pre-existing credential/middleware assertion still present and intact.
</success_criteria>

<output>
Create `.planning/quick/260712-ekj-fix-misleading-upload-error-alert-title-/260712-ekj-SUMMARY.md` when done
</output>
