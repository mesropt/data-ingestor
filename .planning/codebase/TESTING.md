# Testing Patterns

**Analysis Date:** 2026-07-09

## Test Framework

**Runner:**
- pytest 8.3+
- Config: `pyproject.toml` with `[tool.pytest.ini_options] testpaths = ["tests"]`

**Assertion Library:**
- pytest's native `assert` statements

**Run Commands:**
```bash
pytest                         # Run all tests
pytest -v                      # Verbose output
pytest tests/test_domain.py    # Run one module
pytest -k "test_clear"         # Run tests matching pattern
pytest --co                    # Show test collection
```

## Test File Organization

**Location:**
- Co-located in `tests/` directory (parallel to `src/`)
- One test module per source module (e.g., `test_domain.py` tests `src/assayingest/domain/models.py`)

**Naming:**
- Test file: `test_<module>.py`
- Test function: `test_<behavior_or_unit>`
- Test fixture: same as usage (e.g., `@pytest.fixture def workbook()`)

**Structure:**
```
tests/
├── __init__.py                      # Empty
├── test_domain.py                   # Domain model behavior
├── test_parsing.py                  # CSV/Excel parsing
├── test_reference.py                # Reference dict behavior
├── test_mapper_boundary.py          # Mapper wire→domain conversion
├── test_cli.py                      # CLI rendering (no API call)
├── test_cli_run.py                  # CLI exit codes + live mapper test
└── test_excel_sheets.py             # Multi-sheet workbook handling
```

## Test Structure

**Suite Organization:**
Each test file starts with a module docstring describing what is being tested:

```python
"""Domain gating: nothing is ready while any field still needs confirmation."""

from assayingest.domain.models import (
    FieldMapping,
    MappingProposal,
    TargetField,
)


def _mapping(field: TargetField, *, clear: bool) -> FieldMapping:
    """Helper to construct test fixtures quickly."""
    return FieldMapping(
        target_field=field,
        source_column="col" if clear else None,
        confidence=1.0 if clear else 0.5,
        reasoning="",
        needs_confirmation=not clear,
    )


def test_clear_field_has_no_confirmation():
    assert _mapping(TargetField.VALUE, clear=True).is_clear


def test_proposal_ready_only_when_all_clear():
    proposal = MappingProposal(
        source_columns=["a", "b"],
        field_mappings=[
            _mapping(TargetField.VALUE, clear=True),
            _mapping(TargetField.UNIT, clear=True),
        ],
    )
    assert proposal.is_ready
    assert proposal.unclear_fields == []
```

**Patterns:**

1. **Module docstring:** Describes the test's scope and intent.

2. **Helper functions:** Private functions (prefixed `_`) construct fixtures inline.

3. **Assertion style:** Direct `assert` statements (not `self.assertEqual`).

4. **One behavior per test:** Test name describes what is being verified, not implementation.

5. **No setup/teardown:** Tests are self-contained; complex setups use fixtures (see below).

## Exception Testing

**Pattern using `pytest.raises()`:**

```python
def test_missing_file_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        parse_file(DATA / "does_not_exist.csv")


def test_unsupported_extension_raises_valueerror(tmp_path):
    junk = tmp_path / "notes.txt"
    junk.write_text("hello")
    with pytest.raises(ValueError, match="csv or .xlsx"):
        parse_file(junk)
```

**Pattern:** Use `match=` to verify error message contains a keyword.

## Fixtures and Test Data

**Built-in Fixtures (pytest standard):**
- `tmp_path`: Temporary directory (auto-cleanup)
- `capsys`: Capture stdout/stderr
- `monkeypatch`: Mock environment variables, object attributes

**Custom Fixtures:**
```python
@pytest.fixture
def workbook(tmp_path):
    """A two-sheet workbook: 'IC50' and 'Inhibition', plus one empty sheet."""
    wb = Workbook()
    first = wb.active
    first.title = "IC50"
    first.append(["cmpd", "potency", "target_gene"])
    first.append(["NVS-1", "12.5", "EGFR"])
    first.append(["NVS-2", "340", "EGFR"])

    second = wb.create_sheet("Inhibition")
    second.append(["ID", "Inhibition %", "Target"])
    second.append(["CC-1", "82.5", "JAK2"])

    wb.create_sheet("Notes")  # deliberately empty

    path = tmp_path / "multi.xlsx"
    wb.save(path)
    return path
```

**Test Data:**
- External files in `data/synthetic/`: CSV and Excel workbooks used as fixtures
- Accessed via Path: `DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"`
- Example files:
  - `helixbio_export.csv`: Typical potency format
  - `novascreen_batch01.csv`: Missing unit column (triggers inference test)
  - `crestchem_results.csv`: Messy headers with leading spaces

**No Conftest:**
- No `conftest.py` file; tests stay self-contained and simple
- Fixtures defined in test files themselves when needed

## Mocking

**Strategy:** Minimize mocking; use pytest built-ins for infrastructure concerns.

**Environment Variable Mocking (monkeypatch):**
```python
def test_run_reports_missing_credentials(monkeypatch, capsys):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    assert run(str(DATA / "novascreen_batch01.csv")) == 3
    assert "credentials" in capsys.readouterr().err
```

**What to Mock:**
- Environment variables (credentials, API keys) using `monkeypatch`
- Stderr/stdout capture using `capsys`
- Temporary files using `tmp_path`

**What NOT to Mock:**
- Business logic (parsing, mapping, validation) — test the real code
- Data structures (dataclasses, enums) — too simple to mock
- File I/O for CSV/Excel — test real file reading
- Domain functions (reference dict lookup) — no external dependencies

## Live Integration Tests

**Conditional on API Key:**
```python
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="live mapper test requires ANTHROPIC_API_KEY",
)
def test_mapper_flags_missing_unit_on_novascreen():
    # The money shot: NovaScreen's first file has no unit column, so the mapper
    # must infer nM from the value range and flag it for confirmation.
    table = parse_file(DATA / "novascreen_batch01.csv")
    proposal = propose_mapping(table)

    assert {m.target_field for m in proposal.field_mappings} == set(TargetField)
    unit = next(m for m in proposal.field_mappings
                if m.target_field is TargetField.UNIT)
    assert unit.needs_confirmation
    assert not proposal.is_ready
```

**Pattern:**
- Use `@pytest.mark.skipif()` to skip when credentials absent
- Test the actual Claude mapper call once per phase/module
- Pin critical behaviors (e.g., unit inference, confidence flags)

## Test Types

**Unit Tests (Domain & Parsing):**
- Location: `test_domain.py`, `test_parsing.py`, `test_reference.py`
- Scope: Single module, no I/O beyond file reading from fixtures
- Example: `test_clear_field_has_no_confirmation()` verifies domain property
- No API calls or external services

**Boundary Tests (Wire→Domain Conversion):**
- Location: `test_mapper_boundary.py`
- Scope: Mapper's boundary logic without calling Claude
- Tests mock wire models and verify domain conversion
- Example: `test_wire_maps_to_domain_field_with_alternatives()` checks Pydantic→domain mapping

**Integration Tests (CLI Exit Codes):**
- Location: `test_cli_run.py`, `test_cli.py`
- Scope: CLI argument parsing, error handling, output rendering
- No API call by default; live test skipped without credentials
- Example: `test_run_reports_missing_file()` verifies exit code and stderr

**Live Integration Tests:**
- Location: `test_cli_run.py::test_mapper_flags_missing_unit_on_novascreen`
- Scope: End-to-end file → parser → Claude mapper → proposal
- Requires: ANTHROPIC_API_KEY environment variable
- Marked with `@pytest.mark.skipif` for optional execution

## Coverage

**Requirements:** No explicit coverage target in config.

**View Coverage:**
```bash
pytest --cov=src/assayingest --cov-report=term-missing
```

**Observed Coverage:**
- Domain models, parsing, reference dict: 100% (simple, well-tested)
- CLI rendering: 100% (test_cli.py tests JSON and human output)
- Mapper boundary: 100% (test_mapper_boundary.py tests wire conversion)
- Live mapper: 1 test (conditional on API key) verifying end-to-end behavior

## Test Execution in CI

**Command:**
```bash
pytest
```

**Exit Codes:**
- `0`: All tests passed
- `1`: Test failure
- `2`: File not found / bad argument
- `3`: Missing credentials (expected for CI; skipped live tests)

**CI Behavior:**
- Live mapper test skipped (no ANTHROPIC_API_KEY in CI environment by default)
- All boundary and unit tests run
- Exit code 0 on all passing (live test skipped, not failed)

## Async Testing

Not used — project is synchronous Python (no async/await).

## Error Testing Pattern

**Comprehensive exception testing:**
```python
def test_parse_unknown_sheet_raises_with_available_names(workbook):
    """Verify error message names the available sheets, helping the user."""
    with pytest.raises(ValueError, match="IC50"):
        parse_file(workbook, sheet="Nope")
```

**Pattern:**
- Test the exception type (e.g., `ValueError`, `FileNotFoundError`)
- Verify the message is helpful (use `match=` regex)
- Test both the happy path and the failure path for every function

## Common Patterns

**Parametrized Tests (Not Used):**
- Project does not use `@pytest.mark.parametrize`
- Instead, write discrete test functions or helper methods

**Fixtures vs. Helpers:**
- Use `@pytest.fixture` for complex setup (e.g., `workbook` with tmp_path)
- Use private `_helper()` functions for simple test data (e.g., `_mapping()`)

**Test Independence:**
- Each test is independent; no shared state between tests
- Order of test execution is irrelevant
- Fixtures handle cleanup automatically (e.g., `tmp_path` deletes on exit)

---

*Testing analysis: 2026-07-09*
