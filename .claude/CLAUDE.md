<!-- GSD:project-start source:PROJECT.md -->

## Project

**AssayIngest**

An AI ingest tool for contract-research-organisation (CRO) assay files. A data curator uploads any lab's messy Excel/CSV — every lab formats differently — and Claude maps its columns onto a fixed set of target fields on its own, returning a structured draft with per-field confidence and yellow flags on anything uncertain. The human reviews and confirms; only then is anything written. It turns manual reformatting into a one-click review.

**Core Value:** Claude proposes a column mapping with honest per-field confidence, and a human disposes — nothing is trusted or saved until every uncertain field is cleared. "Trust the numbers": the LLM never touches production truth directly.

### Constraints

- **Timeline**: Submissions due Mon 2026-07-13, 9:00 PM ET — ~4 working days. Prioritise the demo money-shot early.
- **Tech stack**: Anthropic personal org (UUID `474eb356-d20a-4417-997d-0c59c21e897a`), not employer's — competition rule.
- **Licensing**: Open-source, MIT (in LICENSE); new work only, fresh repo — competition rules.
- **Process**: gsd-core is the project process (Discuss → Plan → Execute → Verify → Ship) with living artifacts under `.planning/`.
- **Coding conventions**: Clean Architecture; single level of abstraction per function; log-or-raise never both; error messages describe the consequence, not the symptom. See `CLAUDE.md` and `.planning/codebase/CONVENTIONS.md`.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3.13+ - Core application (backend CLI, data processing, mapping logic)

## Runtime

- CPython 3.13+
- uv - Lock file: `uv.lock` (present)

## Frameworks

- Anthropic SDK 0.69+ - Claude API integration for structured output mapping
- Pydantic 2.9+ - Data validation and schema definition for wire/domain models
- pandas 2.2+ - Tabular data parsing and in-memory processing
- openpyxl 3.1+ - Excel file parsing and generation
- pytest 8.3+ - Unit and integration test runner
- hatchling - Python package build backend

## Key Dependencies

- `anthropic` 0.69+ - Anthropic SDK; used for `.messages.parse()` with structured output (Pydantic models) and adaptive thinking mode
- `pandas` 2.2+ - CSV/Excel parsing via `pd.read_csv()` and `pd.read_excel()`
- `openpyxl` 3.1+ - Excel workbook introspection and multi-sheet handling
- `pydantic` 2.9+ - Wire model schema (`WireFieldMapping`, `WireMappingProposal`) and domain model validation
- `pytest` 8.3+ - Test discovery and execution

## Configuration

- Anthropic credentials: `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` (resolved by SDK)
- Default config file: `.env.example` (credentials and API keys pattern — not committed)
- `pyproject.toml` - Package metadata, dependencies, pytest config, build backend

## Platform Requirements

- Python 3.13+ interpreter
- uv package manager
- SQLite (future — not yet integrated; Day 2 planned for lab profile store)
- Python 3.13+ runtime
- No external server/database required (CLI-only, standalone)

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Naming Patterns

- Lowercase with underscores: `models.py`, `test_parsing.py`, `cli.py`
- Test files: `test_<module>.py` (e.g., `test_domain.py`, `test_parsing.py`)
- camelCase in function bodies, but function definitions use snake_case: `parse_file()`, `propose_mapping()`, `_clean_header()`
- Private functions prefixed with underscore: `_parse_excel_sheet()`, `_to_domain()`, `_render_table()`
- snake_case: `source_column`, `field_mappings`, `confidence`, `row_count`
- Module-level constants: SCREAMING_SNAKE_CASE: `_MODEL`, `_MAX_TOKENS`, `ALLOWED_UNITS`, `ASSAY_TYPES`
- PascalCase: `TargetField`, `FieldMapping`, `MappingProposal`, `RawTable`, `ColumnCandidate`
- Enum: inherits from `str` and `Enum` to make string values (e.g., `class TargetField(str, Enum)`)
- Dataclass conventions: frozen for immutable value objects, mutable for aggregates

## Code Style

- Black-style implicit (120 char lines observed, but no config file)
- Double quotes for strings (not single)
- Type hints on all function signatures and class attributes
- No `.eslintrc` or `pyproject.toml` ruff config visible
- Inferred standards: clean imports, no unused variables (enforced by test rigor)

## Import Organization

- `src/assayingest/__init__.py`: absolute imports within the package
- Internal files (e.g., `mapping/mapper.py`): relative imports pointing to sibling/parent modules

## Error Handling

- Raise `FileNotFoundError` with message describing what is missing: `"Cannot ingest: no file at {path}"`
- Raise `ValueError` for unsupported input (format, range): `"Cannot ingest {path.name}: expected a .csv or .xlsx file, got '{path.suffix}'"`
- Raise `ValueError` for invalid mapped data: `"Mapping failed for {table.label}: the model returned no structured proposal"`
- Log-or-raise, never both: if raising, don't also log the same error

## Logging

- CLI output to `stdout` (normal flow): `print(json.dumps(...))`
- Error messages to `stderr`: `print(f"error: {exc}", file=sys.stderr)`
- JSON output remains ASCII-safe: `ensure_ascii=False` for Unicode (µM, %, etc.)

## Comments

- Non-obvious logic or design decisions
- Explain the *why*, not the *what* (code is readable; reasoning is not)
- Docstring on every module, class, and public function
- Module-level: brief description of purpose
- Class: description of responsibility and invariants
- Function: one-line summary, then parameter/return explanation if non-obvious
- Use docstrings to pin intent and edge cases, not repeat code

## Function Design

- Positional args for required inputs
- Keyword-only args (after `*`) for optional configuration
- Type hints always present
- Return domain models, not infrastructure models (wire models stay at boundary)
- Use `str | None` syntax (Python 3.10+ union syntax)
- Properties for computed values (`@property def is_clear`)

## Module Design

- Public API is everything not prefixed with `_`
- Use `__all__` rarely; rely on naming convention instead
- `src/assayingest/__init__.py`: imports main entry points (minimal)
- Each layer has `__init__.py` (can be empty)

## Type Hints

- Union syntax: `str | None` (not `Optional[str]`)
- Collections with generic args: `list[str]`, `dict[str, tuple[float, float]]`
- Literal for fixed string values: `Literal["compound_id", "assay_type", ...]`
- Type aliases for complex shapes: `TargetFieldName = Literal[...]`

## Dataclass Patterns

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| CLI Entry Point | Orchestrate file parsing, mapping, and output rendering | `src/assayingest/cli.py` |
| Parser | Load CSV/Excel into memory as structured table (strings only) | `src/assayingest/parsing/table.py` |
| Mapper | Call Claude structured-output API; validate & map response to domain | `src/assayingest/mapping/mapper.py` |
| Schema (Wire) | Pydantic models defining Claude's JSON output contract | `src/assayingest/mapping/schema.py` |
| Domain Models | Target fields, mapping proposal, confidence gates | `src/assayingest/domain/models.py` |
| Reference Dict | Allowed assay types, units, aliases (no LLM) | `src/assayingest/domain/reference.py` |

## Pattern Overview

- **Layered**: Parsing → Mapping → Domain → Output
- **Boundary mapping**: Wire models (Pydantic, API shape) map to domain models (pure Python) at layer edges
- **Single responsibility**: Parser parses; mapper maps; domain knows nothing of APIs or files
- **Immutable snapshots**: Domain models are frozen dataclasses; wire models validate constraints

## Layers

- Purpose: Read messy CRO files (CSV/Excel) and expose headers + rows as strings
- Location: `src/assayingest/parsing/table.py`
- Contains: `parse_file()`, `sheet_names()`, `RawTable` (frozen dataclass)
- Depends on: `pandas`, `openpyxl` (via pandas for Excel)
- Used by: CLI entry point
- Purpose: Call Claude with structured-output schema; validate, parse, and map wire response to domain
- Location: `src/assayingest/mapping/mapper.py` + `src/assayingest/mapping/schema.py`
- Contains: `propose_mapping()`, Claude prompt, schema validation, boundary mapping
- Depends on: Anthropic SDK, Pydantic, domain models, reference dict
- Used by: CLI entry point
- **Critical invariant**: Never modifies external state; returns a proposal only
- Purpose: Define the semantic truth — target fields, confidence gates, reference vocabulary
- Location: `src/assayingest/domain/models.py` + `src/assayingest/domain/reference.py`
- Contains: `TargetField`, `FieldMapping`, `MappingProposal`, allowed assay types + units
- Depends on: Python stdlib only (dataclasses, enum)
- Used by: Mapping layer (for mapping), CLI (for rendering)
- **Critical invariant**: Pure data structures; no I/O, no API calls
- Purpose: Serialize proposals to JSON and render human-readable review summary
- Location: `src/assayingest/cli.py` (functions `proposal_to_dict()`, `render_report()`)
- Contains: JSON serialization, colour-coded report with confidence scores, readiness gate
- Depends on: Domain models
- Used by: CLI main loop

## Data Flow

### Primary Request Path

- Stateless per table: parsing produces `RawTable`, mapping produces `MappingProposal`, both are immutable
- No learning loop yet (Day 2): future SQLite lab profile will cache successful mappings keyed by column signature
- No mutation: every function returns a new object; no side effects except file I/O (read-only)

## Key Abstractions

- Purpose: Represent the source file as a clean in-memory table without losing information
- Examples: `src/assayingest/parsing/table.py` (frozen dataclass)
- Pattern: Immutable snapshot of parsed file; headers + rows as strings; preserves ambiguity
- Purpose: Claude's proposal for one target field, with confidence and alternatives
- Examples: `src/assayingest/domain/models.py`
- Pattern: Contains source column, confidence score (0.0-1.0), reasoning (human-readable), boolean gate (`needs_confirmation`)
- Purpose: Complete mapping for a file; gates export on clarity
- Examples: `src/assayingest/domain/models.py`
- Pattern: List of 7 `FieldMapping` objects (one per target field); `is_ready` property checks all are clear
- Purpose: Define the fixed set of fields every assay record must resolve to
- Examples: `COMPOUND_ID`, `ASSAY_TYPE`, `VALUE`, `UNIT`, `TARGET`, `N_REPLICATES`, `ASSAY_DATE`
- Pattern: String enum; used as the source of truth for required fields

## Entry Points

- Location: `src/assayingest/cli.py:main()`
- Triggers: User runs `assayingest file.csv` or via Python `-m assayingest.cli`
- Responsibilities: Parse command-line args, call `run()`, set exit code
- Location: `src/assayingest/cli.py:run(path, sheet=None)`
- Triggers: Called by `main()`; tests call it directly
- Responsibilities: Resolve file → tables, check credentials, orchestrate per-table mapping and rendering

```bash

```

## Architectural Constraints

- **Threading:** Single-threaded, synchronous event loop. No worker threads or async/await; Anthropic SDK blocks on network call.
- **Global state:** Minimal; no module-level singletons. Anthropic client is instantiated per call (or passed as optional parameter for testing).
- **Circular imports:** None detected. Parsing has no dependency on mapping or domain; mapping depends on domain; CLI depends on all.
- **Mutable state:** None in the critical path. Domain models are frozen; `RawTable` is frozen. Only mutable state is the Anthropic client's connection pool (internal SDK detail).
- **Multi-file handling:** CLI handles multiple sheets in one workbook by looping per sheet and calling the mapper once per sheet; all exit codes tracked and worst wins.

## Anti-Patterns

### Guessing with Confidence 1.0

### Silently Coercing Values

### Mixing Wire and Domain Models

## Error Handling

- Missing file: `FileNotFoundError` raised by `parse_file()` → CLI catches and prints to stderr, returns exit code 2
- Invalid credentials: `anthropic.AuthenticationError` raised by SDK → CLI catches and prints "check ANTHROPIC_API_KEY", returns exit code 3
- API error (transient, malformed response): `anthropic.APIError` or `ValueError` → CLI catches and prints "mapping failed", returns exit code 1
- Unsupported file type: `ValueError` raised by `sheet_names()` or `parse_file()` → CLI catches and prints the file type issue, returns exit code 2
- Invalid schema response (no structured output): `ValueError` raised by `propose_mapping()` if `parsed_output` is None → CLI catches and prints the stop reason, returns exit code 1

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
