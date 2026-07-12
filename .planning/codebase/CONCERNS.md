# Codebase Concerns

**Analysis Date:** 2026-07-09

## Tech Debt

**Hardcoded model and configuration in mapper:**
- Issue: The mapper specifies `_MODEL = "claude-opus-4-8"` and `_MAX_TOKENS = 4096` as module constants with no way to override them.
- Files: `src/assayingest/mapping/mapper.py` (lines 23-24)
- Impact: Cannot easily switch models, experiment with different token budgets, or adapt to API changes. If the model is deprecated or pricing changes, requires code modification and redeployment.
- Fix approach: Move model and token settings to environment variables or a configuration module. Pass them as parameters to `propose_mapping()` if needed.

**Sample rows hardcoded to 6:**
- Issue: `_SAMPLE_ROWS = 6` is a module constant used to limit rows sent to Claude for context.
- Files: `src/assayingest/mapping/mapper.py` (line 25)
- Impact: May be insufficient for very sparse files or too large for wide files; no adaptation to actual table size or column count.
- Fix approach: Make sample size adaptive based on column count and row count, or expose as a configurable parameter.

**API credential resolution is manual:**
- Issue: `_has_credentials()` checks for env vars but doesn't validate the key actually works until the API call fails.
- Files: `src/assayingest/cli.py` (lines 104-106, 134-140)
- Impact: Users don't know if credentials are invalid until after the file is parsed and the mapper is invoked; wasted time and API quota.
- Fix approach: Validate credentials early in `run()` with a lightweight API call (e.g., check API key format or make a minimal request to `messages` endpoint).

**No proposed mapping confirmation mechanism:**
- Issue: The mapper returns a `MappingProposal` with confidence flags and `needs_confirmation` boolean, but there is no code path to accept a curator's confirmation, persist the mapping, or use it.
- Files: `src/assayingest/domain/models.py` (lines 62-79), `src/assayingest/cli.py` (lines 28-101)
- Impact: The three core principles require "Claude proposes, human disposes" (CLAUDE.md), but disposal is not implemented. The CLI just prints the proposal and exits.
- Fix approach: Implement Day 2 work: add SQLite store + confirmation flow (planned but not yet started).

**Reference dictionary not used by mapper:**
- Issue: The mapper sends the reference vocabulary to Claude in the system prompt, but the returned proposal is never validated against the reference dictionary after Claude returns it.
- Files: `src/assayingest/mapping/mapper.py` (lines 85-99), `src/assayingest/domain/reference.py` (lines 26-46)
- Impact: Claude could propose an invalid `assay_type` or `unit` not in `ASSAY_TYPES` or `ALLOWED_UNITS`; no guardrail at the application layer. Planned for Day 2 validator.
- Fix approach: After Claude returns a proposal, validate field mappings against the reference dictionary; downgrade confidence and set `needs_confirmation=true` for any invalid values.

## Known Bugs

**Claude response can fail silently with no output:**
- Symptoms: `ValueError` raised if `response.parsed_output` is `None` when structured output parsing fails.
- Files: `src/assayingest/mapping/mapper.py` (lines 74-79)
- Trigger: If Claude's response does not conform to the `WireMappingProposal` schema (malformed JSON, missing required fields, or incomplete parsing). Can occur under schema violations or model errors.
- Workaround: None; the user must manually re-run with a smaller file or different input. No retry logic exists.
- Fix approach: Add retry logic with exponential backoff; log the failed response for debugging; provide a clearer error message with suggestions for the user.

**Pydantic validation errors from Claude response not caught:**
- Symptoms: If Claude returns a response that Pydantic cannot deserialize (e.g., `confidence` outside 0.0-1.0, malformed alternatives list), a `ValidationError` is raised but not caught.
- Files: `src/assayingest/mapping/mapper.py` (line 65)
- Trigger: Claude returns a structurally valid JSON response that violates Pydantic constraints (e.g., `confidence: 1.5`).
- Workaround: None; exception propagates to CLI as a generic "mapping failed" error.
- Fix approach: Catch `pydantic.ValidationError` explicitly; log the validation errors and the raw response; provide actionable feedback to the user.

**No handling for empty or header-only tables:**
- Symptoms: If a table has headers but zero data rows, the CLI prints "(skipped: sheet has no data rows)" but the mapper is never called. This is correct behavior, but there's no validation that the table structure is sound (e.g., at least one column).
- Files: `src/assayingest/cli.py` (lines 153-155)
- Trigger: A valid CSV or Excel file with headers but no data rows, or a file with no columns.
- Workaround: Currently handled gracefully by skipping, but a table with zero columns would pass through unchecked.
- Fix approach: Add explicit validation in `parse_file()` that at least one column exists; raise a clear error for malformed files.

## Security Considerations

**API key exposed via environment variables:**
- Risk: `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` are read directly from the environment (lines 18, 104-106 in `cli.py`). If the process crashes, logs are captured, or the environment is dumped, the key could be leaked.
- Files: `src/assayingest/cli.py` (lines 18, 104-106)
- Current mitigation: None; the code relies on the OS/container runtime to protect env vars.
- Recommendations: 
  - Use a credential file or secret management system (e.g., `~/.config/anthropic/credentials`, AWS Secrets Manager) instead of env vars for production.
  - Mask the key in any logged output (already done implicitly by not logging it).
  - Document the security model for end users.

**No input sanitization on file paths:**
- Risk: File paths are passed directly to `pathlib.Path()` and pandas without validation. A malicious path (e.g., `../../../etc/passwd`) could be used to read arbitrary files.
- Files: `src/assayingest/cli.py` (line 129), `src/assayingest/parsing/table.py` (lines 56, 79)
- Current mitigation: `pathlib.Path.exists()` is checked, preventing non-existent files; pandas respects OS-level file permissions.
- Recommendations:
  - Validate file paths are within an allowed directory (e.g., current working directory or a data folder).
  - Document that the tool should not be used to ingest untrusted files.

**CSV injection via cell values:**
- Risk: The CLI outputs CSV-like data (JSON), so not directly at risk. However, if the React frontend displays raw cell values in a spreadsheet-like view without escaping, CSV injection is possible.
- Files: Not directly in this layer; would be a frontend concern.
- Current mitigation: Not applicable at the backend level.
- Recommendations:
  - When building the React UI (Day 3), ensure cell values are escaped and not interpreted as formulas.

## Performance Bottlenecks

**Single API call per table; no parallelization:**
- Problem: The mapper makes one sequential API call per table. For a workbook with 10 sheets, the CLI blocks on each sheet one by one.
- Files: `src/assayingest/cli.py` (lines 145-158)
- Cause: `_map_and_report()` iterates over tables serially; `propose_mapping()` blocks until the API responds.
- Improvement path: 
  - Add a `--parallel` flag to process multiple sheets concurrently (requires connection pooling and error handling).
  - Implement a batch API endpoint or use `anthropic.Anthropic()` with async/await if the SDK supports it.

**Large file context bloat:**
- Problem: `_render_table()` sends up to `_SAMPLE_ROWS = 6` rows to Claude. For a wide table (100+ columns), the context can be large, increasing token usage and API latency.
- Files: `src/assayingest/mapping/mapper.py` (lines 83-99, 102-109)
- Cause: No column sampling or truncation; all columns are included in the sample.
- Improvement path:
  - Limit the number of columns included in the sample (e.g., first 20 columns).
  - Use column statistics (cardinality, value range) instead of raw rows for wide tables.

**No caching of file parses:**
- Problem: If the same file is ingested twice (e.g., user runs the CLI twice on the same file), the file is re-parsed from disk each time.
- Files: `src/assayingest/cli.py` (line 129)
- Cause: No in-memory or disk cache of parsed tables.
- Improvement path:
  - Implement a simple file-hash-based cache for parsed tables (only useful for repeated runs in the same session).

## Fragile Areas

**Pandas header normalization:**
- Files: `src/assayingest/parsing/table.py` (lines 127-136)
- Why fragile: The `_clean_header()` function relies on pandas' convention that blank headers are named `"Unnamed: <N>"`. If pandas changes this behavior or encounters a file that pandas itself formats differently, the blank header detection fails and a literal `"Unnamed: ..."` string is returned instead of `""`.
- Safe modification: Add tests for edge cases (e.g., files with headers named `"Unnamed: 0"` intentionally); consider reading headers manually before pandas applies its defaults.
- Test coverage: Tests exist for blank headers and leading spaces (test_parsing.py), but not for intentionally-named `"Unnamed: ..."` columns.

**Excel sheet name extraction:**
- Files: `src/assayingest/parsing/table.py` (lines 50-68)
- Why fragile: `pd.ExcelFile(path)` is opened, read, and closed in a context manager. If a file is corrupted or uses an unsupported Excel format, the error message may be cryptic.
- Safe modification: Catch `openpyxl` exceptions explicitly and re-raise with clearer messages.
- Test coverage: No tests for corrupted Excel files or unsupported formats.

**Mapper wire-to-domain mapping:**
- Files: `src/assayingest/mapping/mapper.py` (lines 112-129)
- Why fragile: The `_to_domain_field()` function assumes `TargetField(item.target_field)` exists and matches one of the enum values. If Claude returns an unexpected `target_field` value, `ValueError` is raised silently (not caught by the wire parsing).
- Safe modification: Validate `target_field` is a known enum value before mapping; catch and log any mismatches.
- Test coverage: Tests exist for the boundary (test_mapper_boundary.py), but only with valid enum values. No tests for invalid `target_field` strings.

## Scaling Limits

**CSV memory footprint:**
- Current capacity: The code loads entire files into memory as pandas DataFrames, then iterates rows. For a 1 GB CSV, this can consume significant memory.
- Limit: pandas will fail with a MemoryError if the file exceeds available RAM.
- Scaling path:
  - Implement streaming CSV parsing that reads in chunks and processes each chunk with the mapper.
  - For Excel, use `openpyxl` in read-only mode to avoid loading the entire sheet into memory.

**API context window:**
- Current capacity: The mapper sends table headers and 6 sample rows to Claude, plus reference vocabulary and system prompt. For a table with 200 columns and 6 rows, this is roughly 5,000-10,000 tokens.
- Limit: If `max_tokens = 4096`, the response space is limited. A very large proposal (many alternatives per field) could overflow. Additionally, if the model's context window is exhausted by other requests, this one fails.
- Scaling path:
  - Monitor token usage and adjust `_SAMPLE_ROWS` dynamically.
  - Use a model with a larger context window if needed.

**Synthetic data coverage:**
- Current capacity: CLAUDE.md says "10 more vendors" are planned (data/synthetic/README.md lists extended vendor set). Currently, `data/synthetic/` contains ~15 files demonstrating different format challenges.
- Limit: Real-world CRO files may have formats not represented in the synthetic set. If a real file format is not encountered during development, the mapper may fail or misclassify columns.
- Scaling path:
  - Collect real examples from partner labs (with consent) and test against them before deployment.
  - Add adversarial test cases: files with missing columns, unusual data types, extreme ranges.

## Dependencies at Risk

**Anthropic SDK version pinning:**
- Risk: `pyproject.toml` specifies `anthropic>=0.69`, which is a loose lower bound. A future major version (e.g., `anthropic>=1.0`) could introduce breaking API changes.
- Impact: Structured output format, error types, or method signatures could change, causing the mapper to break.
- Migration plan:
  - Pin to a specific minor version (e.g., `anthropic>=0.69,<1.0`) to prevent major version jumps.
  - Add integration tests that run against the pinned version.
  - Monitor the Anthropic SDK changelog and test upgrades in a staging environment.

**Pandas version changes:**
- Risk: `pandas>=2.2` is pinned loosely. Changes to CSV/Excel reading behavior, header handling, or dataframe iteration could affect parsing.
- Impact: Files that parse correctly now could fail or be misinterpreted if pandas changes its defaults.
- Migration plan:
  - Pin to a specific minor version (e.g., `pandas>=2.2,<2.3`).
  - Test with the next minor version before upgrading.

**Pydantic validation strictness:**
- Risk: `pydantic>=2.9` is used for wire models. Pydantic's validation rules are strict by default (e.g., coercion is limited). A future version could enforce stricter validation.
- Impact: If Claude returns a response that currently passes Pydantic but would fail in a stricter version, the mapper would break unexpectedly.
- Migration plan:
  - Explicitly configure validation behavior in Pydantic models (e.g., `model_config = ConfigDict(str_strip_whitespace=True)`).
  - Pin to a specific version until validation rules are reviewed and tested.

## Missing Critical Features

**No learning store:**
- Problem: The app has no SQLite learning store to save lab profiles or apply learned mappings. CLAUDE.md (lines 17-19) identifies this as "the differentiator" — but it's not implemented.
- Blocks: The learning-loop demo (novascreen_batch02.csv should auto-map on second file) cannot be shown.
- Impact: Without this, the app is just a one-shot mapper with no memory; not compelling as a production tool.
- Status: Planned for Day 2 (not started).

**No confirmation workflow:**
- Problem: The mapper returns a proposal with confidence flags, but there's no UI or workflow for a curator to confirm, modify, or reject the mapping before export.
- Blocks: Principle 1 ("Claude proposes, human disposes") is not enforced; principle 3 (export is blocked while uncertain fields remain) cannot be implemented without a UI.
- Status: Planned for Day 3 React UI (not started).

**No validation against reference dictionary:**
- Problem: The mapper's proposal is never checked to ensure assay_type and unit values are in the reference dictionary.
- Blocks: If Claude proposes an invalid assay type (e.g., "inhibition" instead of "%inhibition"), it passes through uncaught.
- Status: Planned for Day 2 validator (not started).

**No export format:**
- Problem: There's no code to export a confirmed mapping as structured data (JSON, CSV, or database record).
- Blocks: Without export, there's no way to persist ingested data or feed it downstream.
- Status: Not mentioned in CLAUDE.md; likely a Day 3 or 4 task.

**No batch processing:**
- Problem: The CLI processes one file or one sheet at a time; no batch mode to ingest multiple files.
- Blocks: Real-world workflows often involve processing a folder of files daily.
- Status: Not mentioned in CLAUDE.md; likely post-hackathon.

## Test Coverage Gaps

**Corrupted or malformed Excel files:**
- What's not tested: Files with missing sheets, invalid opcodes, or corrupted cell data.
- Files: `src/assayingest/parsing/table.py`
- Risk: If a real Excel file is corrupted, the parser crashes with an openpyxl error instead of a user-friendly message.
- Priority: Medium (real files could be corrupted in transit).

**API errors beyond AuthenticationError:**
- What's not tested: Rate limiting (429), server errors (500), timeouts, or network failures.
- Files: `src/assayingest/mapping/mapper.py` (lines 56-80), `src/assayingest/cli.py` (lines 161-170)
- Risk: If the API is temporarily unavailable, the CLI fails with a generic error message instead of suggesting a retry.
- Priority: High (production deployment needs graceful degradation).

**Extreme table sizes:**
- What's not tested: Very small tables (1 row, 1 column), very wide tables (1000 columns), or very tall tables (100,000 rows).
- Files: `src/assayingest/parsing/table.py`, `src/assayingest/mapping/mapper.py`
- Risk: Extreme sizes could cause memory issues, context window overflow, or unexpected behavior (e.g., no sample rows for 1-row table).
- Priority: Medium (synthetic data doesn't cover these extremes).

**Pydantic validation errors from Claude:**
- What's not tested: Invalid confidence values (e.g., 1.5 or -0.1), malformed alternatives lists, or missing required fields.
- Files: `src/assayingest/mapping/mapper.py` (line 65)
- Risk: If Claude returns invalid data, Pydantic raises `ValidationError` which is not caught.
- Priority: High (Claude can make mistakes; app should handle gracefully).

**Files with no headers:**
- What's not tested: A CSV or Excel file with only data rows and no header row.
- Files: `src/assayingest/parsing/table.py`
- Risk: Pandas would treat the first data row as headers; the mapper would see nonsensical column names.
- Priority: Medium (real CRO files should have headers, but not guaranteed).

**Unicode and encoding edge cases:**
- What's not tested: Files with non-ASCII characters, mixed encodings, or unusual Unicode sequences (e.g., right-to-left text).
- Files: `src/assayingest/parsing/table.py` (line 84 reads CSV; line 105 reads Excel)
- Risk: Pandas may misinterpret encoding; Claude may be confused by unusual characters.
- Priority: Low (synthetic data is ASCII; real-world risk depends on lab origin).

---

*Concerns audit: 2026-07-09*
