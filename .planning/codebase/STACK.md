# Technology Stack

**Analysis Date:** 2026-07-09

## Languages

**Primary:**
- Python 3.13+ - Core application (backend CLI, data processing, mapping logic)

## Runtime

**Environment:**
- CPython 3.13+

**Package Manager:**
- uv - Lock file: `uv.lock` (present)

## Frameworks

**Core:**
- Anthropic SDK 0.69+ - Claude API integration for structured output mapping
- Pydantic 2.9+ - Data validation and schema definition for wire/domain models
- pandas 2.2+ - Tabular data parsing and in-memory processing
- openpyxl 3.1+ - Excel file parsing and generation

**Testing:**
- pytest 8.3+ - Unit and integration test runner

**Build/Dev:**
- hatchling - Python package build backend

## Key Dependencies

**Critical:**
- `anthropic` 0.69+ - Anthropic SDK; used for `.messages.parse()` with structured output (Pydantic models) and adaptive thinking mode
- `pandas` 2.2+ - CSV/Excel parsing via `pd.read_csv()` and `pd.read_excel()`
- `openpyxl` 3.1+ - Excel workbook introspection and multi-sheet handling
- `pydantic` 2.9+ - Wire model schema (`WireFieldMapping`, `WireMappingProposal`) and domain model validation

**Development:**
- `pytest` 8.3+ - Test discovery and execution

## Configuration

**Environment:**
- Anthropic credentials: `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` (resolved by SDK)
- Default config file: `.env.example` (credentials and API keys pattern — not committed)

**Build:**
- `pyproject.toml` - Package metadata, dependencies, pytest config, build backend

## Platform Requirements

**Development:**
- Python 3.13+ interpreter
- uv package manager
- SQLite (future — not yet integrated; Day 2 planned for lab profile store)

**Production:**
- Python 3.13+ runtime
- No external server/database required (CLI-only, standalone)

---

*Stack analysis: 2026-07-09*
