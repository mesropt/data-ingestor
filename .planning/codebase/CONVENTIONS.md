# Coding Conventions

**Analysis Date:** 2026-07-09

## Naming Patterns

**Files:**
- Lowercase with underscores: `models.py`, `test_parsing.py`, `cli.py`
- Test files: `test_<module>.py` (e.g., `test_domain.py`, `test_parsing.py`)

**Functions:**
- camelCase in function bodies, but function definitions use snake_case: `parse_file()`, `propose_mapping()`, `_clean_header()`
- Private functions prefixed with underscore: `_parse_excel_sheet()`, `_to_domain()`, `_render_table()`

**Variables:**
- snake_case: `source_column`, `field_mappings`, `confidence`, `row_count`
- Module-level constants: SCREAMING_SNAKE_CASE: `_MODEL`, `_MAX_TOKENS`, `ALLOWED_UNITS`, `ASSAY_TYPES`

**Types:**
- PascalCase: `TargetField`, `FieldMapping`, `MappingProposal`, `RawTable`, `ColumnCandidate`
- Enum: inherits from `str` and `Enum` to make string values (e.g., `class TargetField(str, Enum)`)
- Dataclass conventions: frozen for immutable value objects, mutable for aggregates

**Classes:**
```python
# Immutable value object
@dataclass(frozen=True)
class ColumnCandidate:
    source_column: str
    confidence: float

# Mutable aggregate with computed properties
@dataclass
class FieldMapping:
    target_field: TargetField
    source_column: str | None
    confidence: float
    needs_confirmation: bool
    
    @property
    def is_clear(self) -> bool:
        return not self.needs_confirmation
```

## Code Style

**Formatting:**
- Black-style implicit (120 char lines observed, but no config file)
- Double quotes for strings (not single)
- Type hints on all function signatures and class attributes

**Linting:**
- No `.eslintrc` or `pyproject.toml` ruff config visible
- Inferred standards: clean imports, no unused variables (enforced by test rigor)

## Import Organization

**Order:**
1. `from __future__ import annotations` (Python 3.10+ postponed evaluation)
2. Standard library imports (e.g., `import argparse`, `import json`, `from pathlib import Path`)
3. Third-party imports (e.g., `import pandas as pd`, `import anthropic`, `from pydantic import BaseModel`)
4. Local/relative imports (e.g., `from ..domain.models import FieldMapping`)

**Example from `src/assayingest/mapping/mapper.py`:**
```python
from __future__ import annotations

import anthropic

from ..domain.models import (
    ColumnCandidate,
    FieldMapping,
    MappingProposal,
    TargetField,
)
from ..domain.reference import ALLOWED_UNITS, ASSAY_TYPES
from ..parsing.table import RawTable
from .schema import WireFieldMapping, WireMappingProposal
```

**Absolute vs. relative imports:**
- `src/assayingest/__init__.py`: absolute imports within the package
- Internal files (e.g., `mapping/mapper.py`): relative imports pointing to sibling/parent modules

## Error Handling

**Strategy:** Specific exception types, descriptive messages describing consequences.

**Pattern:**
- Raise `FileNotFoundError` with message describing what is missing: `"Cannot ingest: no file at {path}"`
- Raise `ValueError` for unsupported input (format, range): `"Cannot ingest {path.name}: expected a .csv or .xlsx file, got '{path.suffix}'"`
- Raise `ValueError` for invalid mapped data: `"Mapping failed for {table.label}: the model returned no structured proposal"`
- Log-or-raise, never both: if raising, don't also log the same error

**Example from `src/assayingest/parsing/table.py`:**
```python
def parse_file(path: str | Path, sheet: str | None = None) -> RawTable:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot ingest: no file at {path}")
    
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, dtype=str, skipinitialspace=False)
        return _to_raw_table(frame, source_name=path.name)
```

**In CLI (`src/assayingest/cli.py`):**
```python
def run(path: str, sheet: str | None = None) -> int:
    try:
        tables = resolve_tables(path, sheet)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
```

## Logging

**Framework:** `print()` to stdout/stderr (no logging library)

**Patterns:**
- CLI output to `stdout` (normal flow): `print(json.dumps(...))`
- Error messages to `stderr`: `print(f"error: {exc}", file=sys.stderr)`
- JSON output remains ASCII-safe: `ensure_ascii=False` for Unicode (µM, %, etc.)

**Example from `src/assayingest/cli.py`:**
```python
print(f"error: {exc}", file=sys.stderr)
print(json.dumps(proposal_to_dict(proposal), indent=2, ensure_ascii=False))
print(render_report(proposal))
```

## Comments

**When to Comment:**
- Non-obvious logic or design decisions
- Explain the *why*, not the *what* (code is readable; reasoning is not)
- Docstring on every module, class, and public function

**Example from `src/assayingest/parsing/table.py`:**
```python
def _clean_header(header: object) -> str:
    """Strip surrounding whitespace; keep blank headers as empty strings.

    A blank header is signal, not noise — NovaScreen ships its unit column with
    no name, and the mapper must be told the column exists but is unlabelled.
    """
    text = "" if header is None else str(header)
    if text.startswith("Unnamed:"):  # pandas' placeholder for a blank header
        return ""
    return text.strip()
```

**Docstring Format:**
- Module-level: brief description of purpose
- Class: description of responsibility and invariants
- Function: one-line summary, then parameter/return explanation if non-obvious
- Use docstrings to pin intent and edge cases, not repeat code

## Function Design

**Size:** Single level of abstraction per function. Extract low-level detail into named private methods.

**Parameters:** 
- Positional args for required inputs
- Keyword-only args (after `*`) for optional configuration
- Type hints always present

**Example from `src/assayingest/domain/models.py`:**
```python
def _mapping(field: TargetField, *, clear: bool) -> FieldMapping:
    return FieldMapping(
        target_field=field,
        source_column="col" if clear else None,
        confidence=1.0 if clear else 0.5,
        reasoning="",
        needs_confirmation=not clear,
    )
```

**Return Values:**
- Return domain models, not infrastructure models (wire models stay at boundary)
- Use `str | None` syntax (Python 3.10+ union syntax)
- Properties for computed values (`@property def is_clear`)

## Module Design

**Exports:**
- Public API is everything not prefixed with `_`
- Use `__all__` rarely; rely on naming convention instead

**Barrel Files:**
- `src/assayingest/__init__.py`: imports main entry points (minimal)
- Each layer has `__init__.py` (can be empty)

**Example structure:**
```
src/assayingest/
├── __init__.py                 # Empty or minimal public API
├── cli.py                      # Entry point; CLI rendering
├── domain/
│   ├── __init__.py            # Empty
│   ├── models.py              # Domain dataclasses
│   └── reference.py           # Reference dictionary (no-LLM ground truth)
├── mapping/
│   ├── __init__.py            # Empty
│   ├── mapper.py              # Claude mapper agent (core)
│   └── schema.py              # Pydantic wire models (boundary)
└── parsing/
    ├── __init__.py            # Empty
    └── table.py               # CSV/Excel parser → RawTable
```

## Type Hints

**Usage:** Mandatory on all functions and class attributes.

**Patterns:**
- Union syntax: `str | None` (not `Optional[str]`)
- Collections with generic args: `list[str]`, `dict[str, tuple[float, float]]`
- Literal for fixed string values: `Literal["compound_id", "assay_type", ...]`
- Type aliases for complex shapes: `TargetFieldName = Literal[...]`

**Example from `src/assayingest/mapping/schema.py`:**
```python
TargetFieldName = Literal[
    "compound_id",
    "assay_type",
    "value",
    "unit",
    "target",
    "n_replicates",
    "assay_date",
]

class WireFieldMapping(BaseModel):
    target_field: TargetFieldName
    source_column: str | None
    confidence: float
    alternatives: list[WireCandidate]
```

## Dataclass Patterns

**Immutable Value Objects:**
```python
@dataclass(frozen=True)
class ColumnCandidate:
    source_column: str
    confidence: float
```

**Mutable Aggregates:**
```python
@dataclass
class FieldMapping:
    target_field: TargetField
    source_column: str | None
    confidence: float
    needs_confirmation: bool
    inferred_value: str | None = None
    alternatives: list[ColumnCandidate] = field(default_factory=list)
```

**Never use mutable defaults without `field(default_factory=...)`:**
```python
# ✓ CORRECT
attributes: list[str] = field(default_factory=list)

# ✗ WRONG
attributes: list[str] = []  # Would be shared across instances
```

---

*Convention analysis: 2026-07-09*
