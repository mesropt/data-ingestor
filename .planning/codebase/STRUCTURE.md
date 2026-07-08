# Codebase Structure

**Analysis Date:** 2026-07-09

## Directory Layout

```
data-ingestor/
├── .claude/                      # Claude Code settings
│   └── settings.local.json
├── .planning/
│   └── codebase/                # Codebase mapping documents (you are here)
├── data/
│   └── synthetic/               # Test fixtures: CRO files from different labs
│       ├── README.md
│       ├── helixbio_export.csv
│       ├── novascreen_batch01.csv
│       ├── novascreen_batch02.csv
│       ├── crestchem_results.csv
│       ├── pinnacle_labs_export.csv
│       ├── apex_labs_wide_matrix.xlsx
│       ├── bionexus_transposed.xlsx
│       ├── cascade_assays_nounit.xlsx
│       ├── delta_screening_per_target.xlsx
│       ├── helix_genomics_DE.xlsx
│       ├── meridian_cro_codes.xlsx
│       ├── orion_pk_report.xlsx
│       ├── summit_discovery_mixed.xlsx
│       └── zephyr_bio_ZB-2025.xlsx
├── scripts/
│   └── gen_synthetic_pk.py      # Generate synthetic CRO data files
├── src/
│   └── assayingest/             # Main package
│       ├── __init__.py          # Empty
│       ├── cli.py               # Entry point: orchestrate parse → map → output
│       ├── domain/
│       │   ├── __init__.py      # Empty
│       │   ├── models.py        # TargetField, FieldMapping, MappingProposal
│       │   └── reference.py     # Allowed assay types, units, aliases (no LLM)
│       ├── mapping/
│       │   ├── __init__.py      # Empty
│       │   ├── mapper.py        # Claude structured-output orchestration
│       │   └── schema.py        # Pydantic wire models for Claude's JSON
│       └── parsing/
│           ├── __init__.py      # Empty
│           └── table.py         # CSV/Excel → RawTable (strings preserved)
├── tests/
│   ├── __init__.py              # Empty
│   ├── test_cli.py              # CLI rendering (JSON, report, gates)
│   ├── test_cli_run.py          # CLI integration (end-to-end with test fixtures)
│   ├── test_domain.py           # Domain models (enums, properties)
│   ├── test_excel_sheets.py     # Multi-sheet Excel handling
│   ├── test_mapper_boundary.py  # Mapper wire→domain mapping
│   ├── test_parsing.py          # Parser: headers, rows, blank headers
│   └── test_reference.py        # Reference dict: assay types, units, lookups
├── .env.example                 # Environment template (ANTHROPIC_API_KEY required)
├── .gitignore
├── CLAUDE.md                    # Project brief, principles, constraints
├── LICENSE                      # MIT
├── pyproject.toml               # Python package metadata, dependencies
└── uv.lock                      # Locked dependencies (uv package manager)
```

## Directory Purposes

**data/synthetic/:**
- Purpose: Test fixtures representing different CRO labs' output formats (the "messy" input the tool must ingest)
- Contains: 12 CSV + Excel files from 12 fictional labs with different headers, layouts, blank columns, multi-sheet workbooks
- Key files: `helixbio_export.csv` (simple CSV), `novascreen_batch01.csv` (blank unit column), `apex_labs_wide_matrix.xlsx` (wide multi-sheet), `cascade_assays_nounit.xlsx` (missing unit info)
- Purpose: Both for manual testing and automated test fixtures (tests import these files for parsing and mapping tests)

**src/assayingest/:**
- Purpose: Main application package
- Contains: All production code organized by responsibility (parsing, mapping, domain)

**src/assayingest/domain/:**
- Purpose: Pure business logic — no I/O, no external APIs
- Contains: Domain models (`models.py`), reference vocabulary (`reference.py`)
- Key files: `models.py` defines `TargetField` enum, `FieldMapping`, `MappingProposal`, `ColumnCandidate`; `reference.py` defines allowed assay types and units

**src/assayingest/mapping/:**
- Purpose: Orchestrate Claude's structured-output API call and boundary mapping
- Contains: Mapper orchestration (`mapper.py`), Pydantic wire schema (`schema.py`)
- Key files: `mapper.py` contains `propose_mapping()` and the Claude system prompt; `schema.py` defines `WireFieldMapping`, `WireMappingProposal` (JSON schema)

**src/assayingest/parsing/:**
- Purpose: Load CSV/Excel files and expose headers + rows as strings
- Contains: File parsing (`table.py`)
- Key files: `table.py` contains `parse_file()`, `sheet_names()`, `RawTable` dataclass

**tests/:**
- Purpose: Test coverage across all layers
- Contains: 8 test modules (~160+ test cases, 32 in core, 1 live integration test)
- Patterns: No mocks for domain/parsing; `test_mapper_boundary.py` uses fake `WireFieldMapping` objects; `test_cli_run.py` runs against real test fixtures (live integration)

**scripts/:**
- Purpose: Utilities for development/demo
- Contains: `gen_synthetic_pk.py` (generate synthetic assay data files)

## Key File Locations

**Entry Points:**
- `src/assayingest/cli.py`: Command-line interface; `main()` parses args, `run()` orchestrates
- Package entry point (from `pyproject.toml`): `assayingest = "assayingest.cli:main"`

**Configuration:**
- `pyproject.toml`: Python package metadata, dependencies (anthropic, pandas, pydantic), test paths
- `.env.example`: Template showing `ANTHROPIC_API_KEY` requirement
- `pyproject.toml` `[tool.pytest.ini_options]`: Test path is `tests/`

**Core Logic:**
- `src/assayingest/domain/models.py`: Target fields and mapping data structures
- `src/assayingest/domain/reference.py`: Allowed assay types and units (the validator's ground truth for Day 2)
- `src/assayingest/mapping/mapper.py`: Claude integration and prompt construction
- `src/assayingest/parsing/table.py`: CSV/Excel parsing

**Testing:**
- `tests/`: Organized by concern (parsing, mapping, CLI, domain)
- Fixtures: Synthetic lab files in `data/synthetic/` imported by tests
- Integration: `test_cli_run.py` runs end-to-end with real test files

## Naming Conventions

**Files:**
- Module files: `snake_case.py` (e.g., `mapper.py`, `table.py`)
- Package directories: `snake_case/` (e.g., `parsing/`, `mapping/`)
- Test files: `test_*.py` (pytest auto-discovery convention)

**Classes/Dataclasses:**
- PascalCase (e.g., `RawTable`, `FieldMapping`, `MappingProposal`, `TargetField`)
- Enums: PascalCase with ALL_CAPS members (e.g., `TargetField.COMPOUND_ID`)

**Functions:**
- snake_case (e.g., `propose_mapping()`, `parse_file()`, `render_report()`)
- Private functions: `_snake_case()` prefix (e.g., `_to_domain()`, `_render_table()`)

**Variables:**
- snake_case (e.g., `source_columns`, `field_mappings`, `confidence`)
- Constants: ALL_CAPS (e.g., `_MODEL = "claude-opus-4-8"`, `_SAMPLE_ROWS = 6`)

**Types:**
- Enum members: ALL_CAPS (e.g., `TargetField.COMPOUND_ID`, `TargetField.ASSAY_TYPE`)
- Type aliases: PascalCase for clarity (e.g., `TargetFieldName = Literal[...]`)

## Where to Add New Code

**New Feature (e.g., validator for Day 2):**
- Primary code: `src/assayingest/domain/validator.py` (no-LLM validation logic, checking against `reference.py`)
- Tests: `tests/test_validator.py`
- Integration point: Call from `mapping/mapper.py` after building the domain proposal (validate before returning)

**New Component/Module (e.g., SQLite lab profile store):**
- Implementation: `src/assayingest/storage/lab_profile.py` (new directory `storage/`)
- Tests: `tests/test_storage.py`
- Integration: Call from CLI after a successful mapping (save profile) and before mapping (check for existing profile)

**Utilities (e.g., helper for formatting):**
- Shared helpers: `src/assayingest/util.py` or `src/assayingest/util/common.py` depending on size
- Tests: `tests/test_util.py`

**CLI subcommands (e.g., `assayingest validate file.csv`):**
- New command: Add to `cli.py` as a separate function (e.g., `validate_cmd()`) and wire in `main()` via argparse subparsers
- Tests: Add to `test_cli.py` or create `test_cli_validate.py`

## Special Directories

**data/synthetic/:**
- Purpose: Demo/test fixture files
- Generated: No (hand-crafted to represent different lab layouts)
- Committed: Yes (essential for tests and demo video)

**.planning/codebase/:**
- Purpose: Codebase mapping documents (produced by `/gsd-map-codebase`)
- Generated: Yes (by analysis)
- Committed: Yes (input to `/gsd-plan-phase` and `/gsd-execute-phase`)

**.env and .env.local:**
- Purpose: Environment variables (ANTHROPIC_API_KEY required at runtime)
- Generated: No (user creates from `.env.example`)
- Committed: No (in `.gitignore` to avoid leaking secrets)

**__pycache__/ and .pytest_cache/:**
- Purpose: Python and pytest cache
- Generated: Yes (automatic)
- Committed: No (in `.gitignore`)

**.venv/:**
- Purpose: Virtual environment
- Generated: Yes (created by `uv venv` or `python -m venv`)
- Committed: No (in `.gitignore`)

---

*Structure analysis: 2026-07-09*
