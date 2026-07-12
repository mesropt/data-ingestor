---
phase: quick-260712-vhj
plan: 01
type: tdd
wave: 1
depends_on: []
autonomous: true
requirements: [PARSE-XLS, PARSE-ENC, PARSE-PREAMBLE, PARSE-RAGGED]
files_modified:
  - pyproject.toml
  - src/assayingest/parsing/structure/grid.py
  - src/assayingest/parsing/structure/encoding.py
  - src/assayingest/parsing/structure/delimiter.py
  - src/assayingest/parsing/structure/csv_structure.py
  - src/assayingest/parsing/hint.py
  - src/assayingest/parsing/table.py
  - src/assayingest/api/routes/upload.py
  - src/assayingest/api/routes/structural_hint.py
  - src/assayingest/api/wire.py
  - src/assayingest/cli.py
  - frontend/src/components/UploadDropzone.tsx
  - tests/test_corpus_triage.py
  - tests/test_legacy_xls.py
  - tests/test_csv_encoding.py
  - tests/test_csv_preamble_ragged.py
  - tests/api/test_upload.py

must_haves:
  truths:
    - "A legacy binary .xls workbook parses through the SAME structural pipeline as .xlsx — sheet ranking, header detection, shape gating, locale gating — with no second code path."
    - "A non-UTF-8 CSV whose encoding is unambiguous decodes correctly and parses; its delimiter is still sniffed AFTER decoding."
    - "A non-UTF-8 CSV whose encoding is genuinely ambiguous (two candidate encodings yield DIFFERENT text) is NEVER silently decoded — it returns a StructureQuestion naming the candidates."
    - "A CSV with report-preamble rows above the real header resolves its header via the EXISTING detect_header, not a second implementation."
    - "A CSV data row with MORE fields than the header is never silently absorbed into a column — it returns a StructureQuestion with answerable_by_hint=False."
    - "A zero-byte CSV still fails loudly with the existing 'the file is empty' ValueError."
    - "Every file that previously returned a StructureQuestion still returns a StructureQuestion — no file silently stopped asking."
    - "Every file that previously parsed to a RawTable still parses to a RawTable."
  artifacts:
    - src/assayingest/parsing/structure/encoding.py
    - src/assayingest/parsing/structure/csv_structure.py
    - tests/test_corpus_triage.py
    - tests/test_legacy_xls.py
    - tests/test_csv_encoding.py
    - tests/test_csv_preamble_ragged.py
  key_links:
    - "grid.load_workbook_any() is the SINGLE workbook-loading choke point — list_worksheets() and therefore rank_sheets() both route through it, so .xls inherits the whole Excel pipeline for free."
    - "csv_structure.diagnose() runs ONLY on the branch where the CSV reader currently raises — the happy path stays byte-for-byte unchanged, which is what structurally guarantees the no-regression invariants."
    - "AmbiguousEncoding and StructuralAmbiguity are ValueError subclasses carrying a StructureQuestion: read_csv_grid() lets them propagate as named ValueErrors (legacy contract preserved), while table.py::_parse_csv_structurally catches them and returns the question (D-05 contract satisfied)."
    - "detect_header() is fed a type-COERCED CSV grid so its native-type signals (str_ratio, type_consistency) are not degenerate — this is what makes 'reuse the Excel detector' real rather than nominal."
---

<objective>
Support legacy binary `.xls`, and close three real CSV parsing gaps (non-UTF-8 encoding,
report preamble above the header, ragged over-wide data rows) — each fixed the
fail-closed way, so that no file that currently asks a human ever silently starts
guessing.

Purpose: 16 of 136 in-scope corpus files are rejected outright today. Every one of the
three lazy fixes for them (decode hopefully, guess the header row, absorb the extra
field) produces a clean-looking table with wrong values — the exact failure this product
exists to prevent.

Output: `.xls` in the existing structural pipeline; a fail-closed encoding detector; a
fail-closed CSV structure diagnoser that reuses the existing header detector; and a named
full-corpus triage gate that makes a silent-guess regression a test failure.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@CLAUDE.md
@.claude/CLAUDE.md
@.planning/STATE.md
@src/assayingest/parsing/table.py
@src/assayingest/parsing/hint.py
@src/assayingest/parsing/structure/grid.py
@src/assayingest/parsing/structure/delimiter.py
@src/assayingest/parsing/structure/header.py
@src/assayingest/parsing/structure/sheets.py
</context>

<measured_ground_truth>
The planner ran the real parser over all 136 in-scope files and inspected the raw bytes of
every failing one. These are MEASUREMENTS, not assumptions. Three of them contradict the
task brief — trust these, and re-verify before changing anything.

**Baseline (confirmed): 136 files = 60 OK / 60 ASK / 16 RAISE.** The 16 raises are 8 unique
files, each present in both `data/synthetic/lab_corpus/edge/` and `data/synthetic_second/`.

| File | What it ACTUALLY is | Honest outcome |
|------|--------------------|----------------|
| `umbra_cbc.xls`, `umbra_cbc_1.xls` | Real OLE2/BIFF. xlrd 2.0.2 opens both. One sheet `Results`, 5 cols x 18 rows, clean. | → **OK** |
| `foxglove_cmp.xls` | Real OLE2/BIFF. **THREE sheets: `Part 1`, `Part 2`, `Part 3`.** Once readable it enters multi-sheet ranking. | → **OK or ASK — MEASURE, do not force** |
| `bluecrest_cmp.csv` | **cp1251** (Cyrillic), `;` delimiter, `#` comment lines, decimal comma (`0,80`). charset-normalizer returns exactly ONE candidate: cp1251. Uniform 5 cols x 20 rows. | → **OK** |
| `silvarea_immuno.csv` | **NOT windows-1251 — the brief is wrong.** It is latin-1/cp1252 ("Nuñez-Fernández, José María"). charset-normalizer's `best()` returns **cp1250, which is WRONG** (yields "Nuńez"), with chaos=0.0. It offers 5 candidates. It ALSO has a preamble row AND comma-decimals inside a comma-delimited file (`4,4`), making its rows irreducibly ambiguous. | → **ASK (encoding)** |
| `cinder_tumor.csv` | Preamble (rows 0-5) + real header at row 6 (5 cols) + **three over-wide rows** (`PSA, Total` — an unquoted comma inside a value → 6 fields) + a footer. Preamble is real; the over-wide rows are not fixable without guessing. | → **ASK (ragged)** |
| `redwood_coag.csv` | **NOT a preamble file — the brief is wrong.** Header is row 0. It is purely ragged: 3 short rows (n=3) and **2 over-wide rows (n=8, containing a literal `extra_col_value`)** against a 6-col header. | → **ASK (ragged)** |
| `tidewater_empty.csv` | Literally 0 bytes. Current refusal is CORRECT. | → **RAISE (unchanged)** |

**Consequences for the target numbers.** The brief's "76 OK / 60 ASK / 2 RAISE" is not
achievable honestly (and does not sum to 136). Three of these files CANNOT become OK
without silently guessing. The planner's predicted end state is **~66 OK / ~68 ASK /
2 RAISE**, but the plan does not hard-code that: the executor MEASURES the outcome and
pins it. What is hard-coded are the INVARIANTS below, which are the real safety property.

**The four invariants (these are the gate, not the counts):**
- **INV-1 (no silent-guess regression):** every one of the 60 files that ASKS today still ASKS. A formerly-RAISING file may newly join the ASK set — that is an improvement, not a regression. Expressed as set containment, never as an equality on the count.
- **INV-2 (no regression):** every one of the 60 files that is OK today is still OK.
- **INV-3:** the RAISE set is EXACTLY the two `tidewater_empty.csv` copies.
- **INV-4:** OK + ASK + RAISE == 136, and nothing leaks a raw library traceback.
</measured_ground_truth>

<architecture_decisions>
Three decisions carry this plan. Deviating from them re-introduces the bugs.

**AD-1 — `.xls` is converted at the CONTAINER boundary, not given its own path.**
`grid.py` gains ONE workbook-loading choke point, `load_workbook_any(path)`. For `.xlsx` it
calls `openpyxl.load_workbook` exactly as today. For `.xls` it reads the BIFF cells with
`xlrd` and materialises them into an **in-memory `openpyxl.Workbook`** with the same sheet
titles and order and native Python cell values. Everything downstream — `list_worksheets`,
`rank_sheets`, `detect_header`, `classify_shape`, `is_drawing_only_sheet`, locale
annotation — then operates on the identical object graph it already uses for `.xlsx`. There
is structurally no second pipeline to diverge.

**AD-2 — every new CSV code path runs ONLY where the current code already raises.**
`delimiter.py::_read_or_name_the_failure` keeps its happy path byte-for-byte: UTF-8 strict
decode, comment strip, `pd.read_csv`. The encoding detector is reached only from the
`except UnicodeDecodeError` branch; the structure diagnoser only from the
`except (ParserError, csv.Error)` branch. This is what makes INV-1 and INV-2 structural
guarantees rather than things we merely test for.

**AD-3 — the two new failures are `ValueError` subclasses carrying a `StructureQuestion`.**
`AmbiguousEncoding(ValueError)` and `StructuralAmbiguity(ValueError)` each hold a
`.question`. `read_csv_grid()` lets them propagate — they ARE named `ValueError`s whose
messages start with "Cannot ingest", so every existing test and the legacy `parse_file`
contract stay green. `table.py::_parse_csv_structurally` catches them and RETURNS
`exc.question`, satisfying D-05 ("structural uncertainty is a returned StructureQuestion,
never an exception") on the structural path. One raise site; both contracts honoured.
</architecture_decisions>

<dependencies>
Two new runtime dependencies. Both were installed and EXECUTED against the real corpus
files during planning — this is verification, not assumption:

- **`xlrd>=2.0.1`** (verified: 2.0.2 opened all three `.xls` files and returned native cell
  types). xlrd 2.x **dropped `.xlsx` support and reads ONLY `.xls`** — precisely the scope
  wanted; openpyxl keeps `.xlsx`. Not a typosquat: it is the long-standing pandas Excel
  engine (`pypi.org/project/xlrd`).
- **`charset-normalizer>=3.4`** (verified: 3.4.9 detected cp1251 for bluecrest and exposed
  the 5-way candidate list for silvarea). Chosen over `chardet` for two reasons: `chardet`
  is LGPL-2.1, a licensing hazard in an MIT repo, whereas charset-normalizer is MIT and is
  the encoding detector `requests` itself moved to; and — decisively — it exposes the FULL
  ranked candidate list, which is the only thing that makes the fail-closed ambiguity gate
  in Task 3 possible at all. Not a typosquat (`pypi.org/project/charset-normalizer`).

Record both facts in the module docstrings that use them.
</dependencies>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Freeze the corpus baseline as a named triage gate (characterization test)</name>
  <files>tests/test_corpus_triage.py</files>
  <behavior>
    Written FIRST, against the CURRENT unmodified code, and green immediately — this is a
    characterization test. Its whole job is to make a silent-guess regression in Tasks 2-4
    impossible to miss.

    - Discovers every `.csv`/`.xlsx`/`.xls` file under `data/` → asserts EXACTLY 136.
    - Classifies each via `parse()`: RawTable → OK, StructureQuestion → ASK, named
      ValueError/FileNotFoundError → RAISE. Any other exception is an outright failure.
    - Test INV-1: every path in the frozen `_BASELINE_ASK` list still classifies as ASK.
    - Test INV-2: every path in the frozen `_BASELINE_OK` list still classifies as OK.
    - Test INV-3: the RAISE set equals exactly the two `tidewater_empty.csv` paths. (This
      assertion FAILS on current code — mark it `xfail(strict=True)` in this task and flip
      it to a hard assertion in Task 4, so the gate turns green only when the work is done.)
    - Test INV-4: OK + ASK + RAISE == 136.
    - Test: the zero-byte `tidewater_empty.csv` still raises a ValueError matching /empty/i.
      A future contributor must not be able to "fix" it into a silently-empty table.
  </behavior>
  <action>
    Capture the baseline from the CURRENT code before touching any source file. Run
    `parse()` over every in-scope file under `data/` and record the three sets of relative
    paths. The planner already measured this: 60 OK / 60 ASK / 16 RAISE out of 136 — your
    run MUST reproduce those counts; if it does not, stop and report, because the ground
    the whole plan stands on has moved.

    Write the two baseline sets into `tests/test_corpus_triage.py` as explicit, sorted,
    literal path lists named `_BASELINE_OK` and `_BASELINE_ASK`. They must be literals
    committed to the file, NOT recomputed at test time — a gate that recomputes its own
    expectation proves nothing.

    Note in the module docstring that INV-1 is deliberately set containment, not count
    equality: a file that RAISES today may legitimately become an ASK (that is a strictly
    better outcome — a question is visible and answerable in the UI, an exception is a dead
    end), but a file that ASKS today must NEVER become an OK, because that is precisely the
    silent guess this product forbids.
  </action>
  <verify>
    <automated>uv run pytest tests/test_corpus_triage.py -q</automated>
  </verify>
  <done>The triage gate exists, is green against unmodified code (INV-3 xfail-strict), and pins 60 OK / 60 ASK / 16 RAISE as committed literals.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Read legacy .xls through the SAME structural pipeline (AD-1)</name>
  <files>pyproject.toml, src/assayingest/parsing/structure/grid.py, src/assayingest/parsing/table.py, src/assayingest/api/routes/upload.py, frontend/src/components/UploadDropzone.tsx, tests/test_legacy_xls.py, tests/api/test_upload.py, tests/test_corpus_triage.py</files>
  <behavior>
    RED first — `tests/test_legacy_xls.py`:
    - `umbra_cbc.xls` parses to a RawTable with headers exactly
      `["Analyte", "Result", "Units", "Reference", "Flag"]` and 17 data rows.
    - The `.xls` RawTable is byte-identical in shape to what the `.xlsx` pipeline produces:
      `column_locales` is populated (proving it went through locale annotation, i.e. the
      real pipeline, not a shortcut).
    - `foxglove_cmp.xls` (3 sheets) goes through sheet ranking: assert only that the result
      is a RawTable OR a StructureQuestion, then MEASURE which and pin the measured outcome
      with a comment recording the ranker's scores. Do NOT force it to be OK.
    - `sheet_names("foxglove_cmp.xls")` returns `["Part 1", "Part 2", "Part 3"]`.
    - An explicit `sheet="Part 2"` selects that sheet.
    - A `.docx`/`.pdf` path still raises the unsupported-extension ValueError.
    - `tests/api/test_upload.py`: INVERT `test_upload_rejects_legacy_xls_with_a_400_not_a_500`
      into an accepts-test. This is an intentional, load-bearing behaviour change — rename
      it and rewrite its docstring to say why, do not leave a stale name.
  </behavior>
  <action>
    Add `xlrd>=2.0.1` to `pyproject.toml` runtime dependencies with a comment recording that
    xlrd 2.x reads ONLY `.xls` (it dropped `.xlsx`), which is exactly the split we want.
    Run `uv sync`.

    In `grid.py`, introduce `load_workbook_any(path) -> openpyxl.Workbook` as the single
    workbook-loading choke point, and route `list_worksheets()` through it (which routes
    `rank_sheets()` through it too, since it already calls `list_worksheets`). For `.xlsx`
    it must call `openpyxl.load_workbook(path)` in NORMAL mode exactly as today — no
    behaviour change on the existing path. For `.xls` add a private
    `_workbook_from_legacy_xls(path)` that opens the book with `xlrd.open_workbook`, creates
    an in-memory `openpyxl.Workbook`, and for each xlrd sheet (same title, same order)
    writes each cell as a native Python value: empty and blank cell types become None, text
    stays str, number becomes int or float, boolean becomes bool, date is converted with
    `xlrd.xldate_as_datetime` using the book's datemode, and error cells become None. Verify
    xlrd's current cell-type constants and the `xldate_as_datetime` signature against the
    installed version before relying on them.

    Document in the docstring WHY the conversion happens at the container boundary: every
    downstream structural consumer then sees the identical openpyxl object graph, so there
    is no second pipeline that can drift. Also document the one honest limitation: an
    in-memory workbook has no drawing relationships, so `is_drawing_only_sheet()` cannot
    detect an image pasted into an `.xls`; such a sheet has no cell content and therefore
    falls through to the shape gate as unknown, which still asks rather than reporting "no
    data" — fail-closed, just less specifically.

    In `table.py`, delete `_reject_legacy_excel` and `_LEGACY_EXCEL_SUFFIXES` entirely, add
    `.xls` to `_EXCEL_SUFFIXES`, and update the three unsupported-extension messages to name
    all three accepted formats. Route `sheet_names()` through `grid.list_worksheets` so
    there is one sheet-listing truth rather than a second one via `pd.ExcelFile`.

    In `api/routes/upload.py`, add `.xls` to `_ALLOWED_EXTENSIONS`, delete
    `_LEGACY_EXCEL_SUFFIXES` and its 400 branch, and rewrite the now-false comment block
    that claims the parser refuses `.xls`.

    In `frontend/src/components/UploadDropzone.tsx`, extend `ACCEPTED_EXTENSIONS` and the
    visible format label to include `.xls`, and delete the stale comment asserting the
    backend refuses it. Shipping `.xls` support behind a dropzone that still rejects `.xls`
    would make the feature invisible to the only user who matters.

    Update the Task 1 triage gate's expectations for the six `.xls` entries to whatever you
    MEASURED — never to what you hoped.
  </action>
  <verify>
    <automated>uv run pytest tests/test_legacy_xls.py tests/api/test_upload.py tests/test_corpus_triage.py -q && cd frontend && npm test -- --run && npm run build</automated>
  </verify>
  <done>All three `.xls` files parse through the structural pipeline; the six `.xls` corpus entries no longer RAISE; INV-1 and INV-2 hold; frontend tests and build are green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Detect CSV encoding — and refuse to guess when it is ambiguous (AD-2, AD-3)</name>
  <files>src/assayingest/parsing/structure/encoding.py, src/assayingest/parsing/structure/delimiter.py, src/assayingest/parsing/hint.py, src/assayingest/parsing/table.py, src/assayingest/api/wire.py, src/assayingest/api/routes/structural_hint.py, src/assayingest/cli.py, tests/test_csv_encoding.py, tests/test_corpus_triage.py</files>
  <behavior>
    RED first — `tests/test_csv_encoding.py`:
    - `bluecrest_cmp.csv` (cp1251, single candidate) parses to a RawTable. Headers are the
      real Cyrillic strings `["Показатель", "Результат", "Ед.изм.", "Норма", "Флаг"]`, and
      there are 20 data rows. This proves the `;` delimiter is still sniffed AFTER decoding.
    - `silvarea_immuno.csv` returns a **StructureQuestion**, NOT a RawTable. Its
      `unsure_about` names the encoding; its `reason` names mojibake as the consequence; its
      `alternatives` carry at least two distinct candidate encodings.
    - The mojibake regression test, stated as the point of the whole task: assert that
      parsing `silvarea_immuno.csv` does NOT produce a RawTable containing the string
      `Nuńez` (charset-normalizer's own `best()` answer, cp1250, which is WRONG). The
      correct text is `Nuñez` under cp1252. A detector trusted blindly corrupts a patient
      name at chaos=0.0 "confidence".
    - Given `StructuralHint(encoding="cp1252")`, `silvarea_immuno.csv` decodes correctly —
      assert the decoded text contains `Nuñez-Fernández` and `José María`. (It will then go
      on to hit the Task 4 ragged gate; assert on the decode, not on a RawTable.)
    - Every UTF-8 file in the corpus is untouched: the fast path never calls the detector.
    - The existing `tests/test_structure_delimiter.py::test_non_utf8_bytes_raise_valueerror_matching_utf8`
      must STILL PASS unchanged — the ambiguous-encoding ValueError message must therefore
      still contain the token "UTF-8".
  </behavior>
  <action>
    Add `charset-normalizer>=3.4` to `pyproject.toml` (see the dependencies block for the
    licence and candidate-list rationale — put it in the module docstring). Run `uv sync`.

    Create `src/assayingest/parsing/structure/encoding.py` — a pure infrastructure module.
    It exposes `AmbiguousEncoding(ValueError)` carrying a `.candidates` list, and
    `decode_non_utf8(path) -> str`. The function reads the bytes, runs
    `charset_normalizer.from_bytes`, and then applies the fail-closed gate: strict-decode
    the bytes with EVERY returned candidate encoding, and collect the set of DISTINCT
    resulting texts. If exactly one distinct text results, the detection is unambiguous —
    return it. If two or more candidates yield different text, raise `AmbiguousEncoding`.
    Also raise it when the detector returns nothing at all.

    This candidate-count gate is the entire safety property, so justify it in the docstring
    with the measured evidence: bluecrest yields exactly one candidate (cp1251) and is
    therefore safe to decode; silvarea yields five, whose texts differ in the patient's name
    (`ñ` under cp1252, `ń` under cp1250), and charset-normalizer's own `best()` picks the
    wrong one with a perfect chaos score. Trusting `best()` is precisely the "wrong-but-
    plausible decode produces mojibake that looks like data" failure. The message must
    describe the consequence and must contain the token "UTF-8" (an existing test pins it).

    Also expose an honoured-hint path: when an encoding is supplied, strict-decode with it
    and let a genuine failure surface as a named ValueError — an explicit human answer is
    always honoured (the existing PARSE-06 proceed-on-hint rule).

    Wire it in `delimiter.py` at exactly ONE place: the existing `except UnicodeDecodeError`
    branch of `_read_or_name_the_failure`, which today raises. It now calls
    `decode_non_utf8()` and continues with the decoded text through the unchanged comment
    strip / D-01 guard / `pd.read_csv` sequence. The UTF-8 happy path is not touched. Thread
    an `encoding` parameter down from `read_csv_grid`.

    Add `encoding: str | None = None` to `StructuralHint` in `hint.py`, and carry it through
    the three plumbing sites: `api/wire.py::StructuralHintIn`,
    `api/routes/structural_hint.py::_to_domain_hint`, and `cli.py::_HINT_KEYS`. Without this
    field an encoding question is unanswerable and silvarea is a permanent dead end — with
    it, the ask-the-human loop works for encoding exactly as it already does for every other
    structural dimension.

    In `table.py::_parse_csv_structurally`, catch `AmbiguousEncoding` and return a
    `StructureQuestion` built from it (AD-3): `unsure_about` names the file and the
    encoding; `reason` explains that several encodings decode the bytes into DIFFERENT text
    and that picking one would silently rewrite names and values into plausible-looking
    wrong characters that no later step could detect; `proposal` and `alternatives` carry
    the candidates as `StructuralHint(encoding=...)`; `evidence_rows` shows the first lines
    as decoded under the leading candidate. Pass `hint.encoding` into `read_csv_grid`.

    Update the triage gate for the four bluecrest/silvarea entries to the MEASURED outcome.
  </action>
  <verify>
    <automated>uv run pytest tests/test_csv_encoding.py tests/test_structure_delimiter.py tests/test_corpus_triage.py -q</automated>
  </verify>
  <done>bluecrest parses with Cyrillic headers and a `;` delimiter; silvarea returns an encoding StructureQuestion and never yields the cp1250 mojibake; an explicit encoding hint decodes it correctly; INV-1 and INV-2 hold.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Resolve CSV preamble with the EXISTING header detector; refuse over-wide rows (AD-2, AD-3)</name>
  <files>src/assayingest/parsing/structure/csv_structure.py, src/assayingest/parsing/structure/delimiter.py, src/assayingest/parsing/table.py, tests/test_csv_preamble_ragged.py, tests/test_corpus_triage.py</files>
  <behavior>
    RED first — `tests/test_csv_preamble_ragged.py`:
    - **The positive preamble proof (synthetic, tmp_path):** a CSV of four junk report lines,
      a blank line, a proper 5-column header, and three uniform data rows parses to a
      RawTable whose headers are the real header row and whose rows exclude every preamble
      line. No real corpus file is a clean-preamble-only case (cinder is contaminated with
      over-wide rows), so without this fixture the preamble fix has no green proof.
    - `redwood_coag.csv` returns a StructureQuestion, NOT a RawTable. Assert explicitly that
      no RawTable containing the literal `extra_col_value` is ever produced — an 8-field row
      against a 6-field header must never be absorbed. `answerable_by_hint` is False.
    - `cinder_tumor.csv` returns a StructureQuestion. Its reason names the offending row
      widths (6 fields against a 5-field header).
    - The question's `reason` names the CONSEQUENCE: an extra value cannot be assigned to a
      column without guessing which one, which shifts every value in that row into the wrong
      field.
    - Short rows keep being padded, exactly as pandas does today: a CSV with trailing-empty
      short rows still parses to a RawTable. Changing that would flip currently-OK files into
      ASK and break INV-2.
    - `tidewater_empty.csv` still raises the /empty/i ValueError.
    - Flip the Task 1 INV-3 assertion from `xfail(strict=True)` to a hard assertion.
  </behavior>
  <action>
    Create `src/assayingest/parsing/structure/csv_structure.py`, a pure module exposing
    `StructuralAmbiguity(ValueError)` (carrying a `.question`) and a `diagnose()` entry
    point. Per AD-2 it is called from exactly ONE place: the existing
    `except (pd.errors.ParserError, csv.Error)` branch of
    `delimiter.py::_read_or_name_the_failure` — the branch that today raises the generic
    "the rows do not form a single consistent table" message. The happy path never reaches
    it, which is what keeps INV-2 structurally true.

    `diagnose()` takes the already-decoded, already-comment-stripped text plus the resolved
    delimiter, and does four things in order.

    First, build a raw record grid with `csv.reader`, tracking each record's starting LINE
    index via a counting line iterator — a multi-line quoted cell consumes several lines, so
    a naive line index would desync the slice and shift the header.

    Second, coerce each cell to a native-ish Python type — a numeric-looking string becomes
    int or float, everything else stays str. This is load-bearing and must be explained in
    the docstring: `detect_header` computes its `str_ratio` and `type_consistency` signals
    from NATIVE cell types, which openpyxl hands it for free on the Excel path. Raw CSV
    cells are all `str`, which would flatten both signals to a constant and make the
    detector degenerate — it would score every row identically. Coercion reconstructs the
    same type signal, so the SAME detector is fed an equivalent grid. This is what makes
    "reuse the existing detection, do not write a second one" real rather than nominal.

    Third, run the existing `structure.header.detect_header` on the coerced grid. Do not
    write a second header heuristic; two implementations that can disagree is a bug factory.
    If it is not confident, raise `StructuralAmbiguity` carrying the SAME
    header-uncertain question shape `table.py` already builds for Excel — extract that
    builder so both branches call one function rather than cloning it.

    Fourth, with the header record resolved, check the data region below it. Any record with
    MORE fields than the header is irreducibly ambiguous: raise `StructuralAmbiguity`
    carrying a question that names the offending row numbers and their field counts, sets
    `answerable_by_hint` to False (no `StructuralHint` dimension can resolve which column an
    extra value belongs to — follow the existing unsupported-shape precedent), and carries
    the header plus the offending rows as evidence. Records with FEWER fields than the
    header are left alone: pandas already pads them today, and changing that would flip
    currently-OK files into ASK.

    If the header sits below line 0 and no record is over-wide, that is the preamble case —
    re-read with pandas from the header's line offset and return the frame. Ensure the
    existing D-01 dropped-comment-line guard still runs against the re-read frame.

    In `table.py::_parse_csv_structurally`, catch `StructuralAmbiguity` and return
    `exc.question` (AD-3).

    Note as a follow-up, do not fix here: a preamble whose junk lines happen to split into
    the same field count as the table is width-uniform, so it never reaches this diagnostic
    branch and is silently parsed with the wrong header today. Closing that needs header
    detection on the happy path, which cannot be done without risking INV-2, and is a
    separate task.
  </action>
  <verify>
    <automated>uv run pytest tests/test_csv_preamble_ragged.py tests/test_corpus_triage.py -q</automated>
  </verify>
  <done>A clean-preamble CSV parses with the right header via the existing detector; cinder and redwood return evidence-carrying ragged questions and never absorb an extra field; the zero-byte file still raises; INV-1, INV-2, INV-3 and INV-4 all hold as hard assertions.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| uploaded file → parser | Wholly untrusted bytes from a stranger's lab cross into pandas, openpyxl, xlrd and charset-normalizer |
| detector output → domain values | A decoded string is trusted as truth by every later layer; corruption here is undetectable downstream |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-VHJ-01 | Tampering | `encoding.py` — wrong-encoding decode | high | mitigate | Task 3's candidate-count gate: decode is refused whenever two candidate encodings yield different text. Measured: charset-normalizer's own `best()` corrupts a patient's name (`Nuñez` → `Nuńez`) at chaos=0.0. The gate, not the detector, is the safety property. |
| T-VHJ-02 | Tampering | `csv_structure.py` — over-wide data row | high | mitigate | Task 4: a row with more fields than the header returns an unanswerable StructureQuestion; it is never truncated, and never absorbed into a column. |
| T-VHJ-03 | Denial of Service | `xlrd` on hostile OLE2 input | medium | mitigate | The existing upload size bound (`_write_bounded_temp_file`) still applies — `.xls` joins the allowlist, it does not bypass the bound. xlrd 2.x is pure-Python, evaluates no formulas and executes no macros. |
| T-VHJ-04 | Tampering | Header detection on a coerced CSV grid | medium | mitigate | Task 4 reuses `detect_header`, whose confidence margin already routes a near-tie to a StructureQuestion rather than a guess. No second heuristic is introduced. |
| T-VHJ-SC | Tampering | Supply chain — new `xlrd`, `charset-normalizer` deps | high | mitigate | Both packages were installed and executed against the real corpus during planning (xlrd 2.0.2 opened all three `.xls`; charset-normalizer 3.4.9 returned the candidate lists). Both are long-established, non-typosquat names. Version floors are pinned in `pyproject.toml`. |
</threat_model>

<verification>
Run after all four tasks.

**Gate 1 — the named full-corpus triage probe (the load-bearing gate).**
`uv run pytest tests/test_corpus_triage.py -q` must be green with INV-3 as a hard
assertion. It proves: 136 files classified; the 60 baseline ASK files ALL still ASK (INV-1
— if a single one silently became OK, the task has FAILED even with every other test
green); the 60 baseline OK files ALL still parse (INV-2); the RAISE set is exactly the two
`tidewater_empty.csv` copies (INV-3); the three sets partition 136 (INV-4).

Record the measured after-counts in the commit message. The planner predicts ~66 OK /
~68 ASK / 2 RAISE. Do not force the counts to a target — report what you measure, and if
the shape is wildly different from the prediction, stop and explain why.

**Gate 2 — the full backend suite.**
`sg docker -c "docker compose up -d"` then `uv run pytest`. Must be green with EXACTLY 4
skipped. The 4 skips are the live-Claude tests; `ASSAYINGEST_LIVE_TESTS` must NEVER be set
(they cost real money). Baseline was 634 passed — the new tests add to it, none are lost.

**Gate 3 — frontend not regressed.**
`cd frontend && npm test -- --run` (141 passed) and `npm run build` (clean). The dropzone's
accepted-extension change is the only frontend edit.

**Gate 4 — the three defects, on the real corpus files.**
`uv run pytest tests/test_legacy_xls.py tests/test_csv_encoding.py tests/test_csv_preamble_ragged.py -q`
</verification>

<success_criteria>
- All three `.xls` files parse through the SAME structural pipeline as `.xlsx` — one loader, no divergent path.
- bluecrest decodes as cp1251, keeps its `;` delimiter and its Cyrillic headers.
- silvarea NEVER silently decodes; it asks, and an explicit encoding hint resolves it to the correct `Nuñez-Fernández`.
- cinder's preamble is resolved by the EXISTING `detect_header`; its over-wide rows are refused, not absorbed.
- redwood's `extra_col_value` never lands in a column.
- The zero-byte file still fails loudly, pinned by a test.
- INV-1 holds: not one of the 60 currently-asking files silently stopped asking.
- 4 skipped tests, still skipped. `.env` never read. Frontend green.
</success_criteria>

<output>
Commit each task atomically (English, capitalized, one imperative line, ≤150 chars).
Report the measured after-triage counts.
</output>
