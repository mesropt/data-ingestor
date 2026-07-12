<!-- refreshed: 2026-07-09 -->
# Architecture

**Analysis Date:** 2026-07-09

## System Overview

```text
┌──────────────────────────────────────────────────────────────┐
│                      CLI Entry Point                          │
│                    `src/assayingest/cli.py`                   │
│        (parse file → map columns → render JSON + report)      │
└──────────────────────────┬───────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌─────────────────┐  ┌─────────────────┐   ┌──────────────────┐
│  Parsing Layer  │  │  Mapping Layer  │   │   Domain Layer   │
│                 │  │                 │   │                  │
│ parsing/table.py│  │  mapping/mapper │   │ domain/models.py │
│                 │  │  mapping/schema │   │ domain/reference │
│ CSV/Excel →     │  │                 │   │                  │
│ RawTable        │  │ Claude proposes │   │ Pure business    │
│                 │  │ (structured     │   │ logic (enums,    │
│                 │  │  output JSON)   │   │ dataclasses,     │
│                 │  │                 │   │ validation rules)│
└────────┬────────┘  └────────┬────────┘   └──────────────────┘
         │                    │
         └────────┬───────────┘
                  │
                  ▼
        ┌──────────────────────────┐
        │   Anthropic SDK          │
        │   (Claude API via HTTP)  │
        └──────────────────────────┘
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

**Overall:** Clean Architecture with infrastructure at the edges, domain logic at the core.

**Key Characteristics:**
- **Layered**: Parsing → Mapping → Domain → Output
- **Boundary mapping**: Wire models (Pydantic, API shape) map to domain models (pure Python) at layer edges
- **Single responsibility**: Parser parses; mapper maps; domain knows nothing of APIs or files
- **Immutable snapshots**: Domain models are frozen dataclasses; wire models validate constraints

## Layers

**Parsing Layer:**
- Purpose: Read messy CRO files (CSV/Excel) and expose headers + rows as strings
- Location: `src/assayingest/parsing/table.py`
- Contains: `parse_file()`, `sheet_names()`, `RawTable` (frozen dataclass)
- Depends on: `pandas`, `openpyxl` (via pandas for Excel)
- Used by: CLI entry point

**Mapping Layer:**
- Purpose: Call Claude with structured-output schema; validate, parse, and map wire response to domain
- Location: `src/assayingest/mapping/mapper.py` + `src/assayingest/mapping/schema.py`
- Contains: `propose_mapping()`, Claude prompt, schema validation, boundary mapping
- Depends on: Anthropic SDK, Pydantic, domain models, reference dict
- Used by: CLI entry point
- **Critical invariant**: Never modifies external state; returns a proposal only

**Domain Layer:**
- Purpose: Define the semantic truth — target fields, confidence gates, reference vocabulary
- Location: `src/assayingest/domain/models.py` + `src/assayingest/domain/reference.py`
- Contains: `TargetField`, `FieldMapping`, `MappingProposal`, allowed assay types + units
- Depends on: Python stdlib only (dataclasses, enum)
- Used by: Mapping layer (for mapping), CLI (for rendering)
- **Critical invariant**: Pure data structures; no I/O, no API calls

**Output Layer:**
- Purpose: Serialize proposals to JSON and render human-readable review summary
- Location: `src/assayingest/cli.py` (functions `proposal_to_dict()`, `render_report()`)
- Contains: JSON serialization, colour-coded report with confidence scores, readiness gate
- Depends on: Domain models
- Used by: CLI main loop

## Data Flow

### Primary Request Path

1. **File reception** (`cli.py:run()`, line 126)
   - User provides file path and optional sheet name
   - CLI resolves which table(s) to ingest (handles multi-sheet Excel)

2. **Parsing** (`cli.py:_map_and_report()`, line 145 → `parsing/table.py:parse_file()`)
   - File loaded via pandas (CSV or Excel via openpyxl)
   - Headers cleaned (strip spaces, blank headers preserved as `""`)
   - All values kept as strings to preserve ambiguity (dates, numbers, etc.)
   - Returns `RawTable(headers, rows, source_name, sheet_name)`

3. **Mapping proposal** (`cli.py:_map_one()`, line 161 → `mapping/mapper.py:propose_mapping()`)
   - Build Claude prompt: reference vocabulary + table sample
   - Call `client.messages.parse()` with `WireMappingProposal` schema (Pydantic)
   - Claude returns constrained JSON: 7 field mappings, per-field confidence, alternatives
   - Validate wire response against schema (raises on invalid JSON)
   - Map wire `WireFieldMapping` → domain `FieldMapping` at boundary (`_to_domain()`)

4. **Output & gating** (`cli.py:_map_one()`, line 172-174)
   - Serialize domain proposal to JSON (uses `proposal_to_dict()`)
   - Print JSON draft (downstream tools can parse this)
   - Render human review report with colour codes and readiness gate
   - If any field has `needs_confirmation=true`, gate blocks export

**State Management:**
- Stateless per table: parsing produces `RawTable`, mapping produces `MappingProposal`, both are immutable
- No learning loop yet (Day 2): future SQLite lab profile will cache successful mappings keyed by column signature
- No mutation: every function returns a new object; no side effects except file I/O (read-only)

## Key Abstractions

**RawTable:**
- Purpose: Represent the source file as a clean in-memory table without losing information
- Examples: `src/assayingest/parsing/table.py` (frozen dataclass)
- Pattern: Immutable snapshot of parsed file; headers + rows as strings; preserves ambiguity

**FieldMapping:**
- Purpose: Claude's proposal for one target field, with confidence and alternatives
- Examples: `src/assayingest/domain/models.py`
- Pattern: Contains source column, confidence score (0.0-1.0), reasoning (human-readable), boolean gate (`needs_confirmation`)

**MappingProposal:**
- Purpose: Complete mapping for a file; gates export on clarity
- Examples: `src/assayingest/domain/models.py`
- Pattern: List of 7 `FieldMapping` objects (one per target field); `is_ready` property checks all are clear

**TargetField (Enum):**
- Purpose: Define the fixed set of fields every assay record must resolve to
- Examples: `COMPOUND_ID`, `ASSAY_TYPE`, `VALUE`, `UNIT`, `TARGET`, `N_REPLICATES`, `ASSAY_DATE`
- Pattern: String enum; used as the source of truth for required fields

## Entry Points

**CLI Main:**
- Location: `src/assayingest/cli.py:main()`
- Triggers: User runs `assayingest file.csv` or via Python `-m assayingest.cli`
- Responsibilities: Parse command-line args, call `run()`, set exit code

**Run Function:**
- Location: `src/assayingest/cli.py:run(path, sheet=None)`
- Triggers: Called by `main()`; tests call it directly
- Responsibilities: Resolve file → tables, check credentials, orchestrate per-table mapping and rendering

**Module Script:**
```bash
python -m assayingest.cli /path/to/file.csv
# or
assayingest /path/to/file.csv [--sheet SheetName]
```

## Architectural Constraints

- **Threading:** Single-threaded, synchronous event loop. No worker threads or async/await; Anthropic SDK blocks on network call.
- **Global state:** Minimal; no module-level singletons. Anthropic client is instantiated per call (or passed as optional parameter for testing).
- **Circular imports:** None detected. Parsing has no dependency on mapping or domain; mapping depends on domain; CLI depends on all.
- **Mutable state:** None in the critical path. Domain models are frozen; `RawTable` is frozen. Only mutable state is the Anthropic client's connection pool (internal SDK detail).
- **Multi-file handling:** CLI handles multiple sheets in one workbook by looping per sheet and calling the mapper once per sheet; all exit codes tracked and worst wins.

## Anti-Patterns

### Guessing with Confidence 1.0

**What happens:** If Claude returns a field with `confidence: 1.0` but `needs_confirmation: true`, that's internally inconsistent and must never reach production. The system treats confidence as independent of the gate.

**Why it's wrong:** Gating logic depends on `needs_confirmation`; confidence is advisory. If a user sees confidence 1.0 they expect no gate; but if `needs_confirmation=true` the gate blocks them. Confusion and trust erosion.

**Do this instead:** Ensure Claude's system prompt (`src/assayingest/mapping/mapper.py`, line 27-52) enforces: *only* an unambiguous, exact column match sets `confidence=1.0` AND `needs_confirmation=false`. Anything inferred, ambiguous, or uncertain gets `needs_confirmation=true` regardless of confidence.

### Silently Coercing Values

**What happens:** Parser uses `dtype=str` in pandas to keep all values as strings (correct). But if a downstream validator (Day 2) tries to parse dates/numbers and silently defaults on failure, ambiguity is hidden.

**Why it's wrong:** The whole point is *never guess silently*. A date like `03/11/2025` could be MM/DD or DD/MM depending on the lab. If validation silently defaults to MM/DD, the curator never sees the ambiguity.

**Do this instead:** When Day 2 adds a validator, ensure it reports *both* possible interpretations with a confidence score per interpretation. Let the curator choose. Example: unit `µM` vs `uM` (ASCII "u") — don't normalize silently; flag both and let the human confirm.

### Mixing Wire and Domain Models

**What happens:** If `WireFieldMapping` (Pydantic) is used directly in output or tests instead of mapping to `FieldMapping`, then the domain layer becomes coupled to the API schema.

**Why it's wrong:** API schema might change (e.g., Claude adds a new field to the response); domain should stay stable. Tests become brittle to API changes.

**Do this instead:** Always map wire → domain at the boundary (`src/assayingest/mapping/mapper.py:_to_domain_field()`, line 118-128). Domain models are the API contract for the rest of the system.

## Error Handling

**Strategy:** Log-or-raise, never both. Keep try blocks minimal; success-path logic in else.

**Patterns:**
- Missing file: `FileNotFoundError` raised by `parse_file()` → CLI catches and prints to stderr, returns exit code 2
- Invalid credentials: `anthropic.AuthenticationError` raised by SDK → CLI catches and prints "check ANTHROPIC_API_KEY", returns exit code 3
- API error (transient, malformed response): `anthropic.APIError` or `ValueError` → CLI catches and prints "mapping failed", returns exit code 1
- Unsupported file type: `ValueError` raised by `sheet_names()` or `parse_file()` → CLI catches and prints the file type issue, returns exit code 2
- Invalid schema response (no structured output): `ValueError` raised by `propose_mapping()` if `parsed_output` is None → CLI catches and prints the stop reason, returns exit code 1

**No custom exceptions yet** — using stdlib + Anthropic SDK exceptions. If Day 2 adds validators, create `src/assayingest/domain/exceptions.py` for domain-level errors (e.g., `InvalidAssayType`).

## Cross-Cutting Concerns

**Logging:** Currently `print()` to stdout/stderr only. No logger configured. For Day 2+, add `import logging` and use `logging.getLogger(__name__).debug(...)` in each module; configure via `pytest` fixtures and CLI `--verbose` flag.

**Validation:** No validation layer yet (Day 2 scope). Reference dict (`src/assayingest/domain/reference.py`) is the ground truth; when Day 2 adds a validator, it will check Claude's proposals against `ASSAY_TYPES`, `ALLOWED_UNITS`, and `UNIT_VALUE_RANGES` and flag mismatches.

**Authentication:** Anthropic API key resolved by SDK from `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` env var. CLI checks for credentials upfront (`_has_credentials()`, line 104-106) so users see a clear error, not a cryptic SDK error at mapping time.

---

*Architecture analysis: 2026-07-09*
