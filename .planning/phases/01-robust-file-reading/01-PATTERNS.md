# Phase 1: Robust File Reading - Pattern Map

**Mapped:** 2026-07-10
**Files analyzed:** 11 (new/modified)
**Analogs found:** 11 / 11

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `src/assayingest/parsing/hint.py` (`StructuralHint`, `StructureQuestion`) | model | request-response (proposal object) | `src/assayingest/domain/models.py` (`FieldMapping`, `MappingProposal`) | exact |
| `src/assayingest/parsing/structure/grid.py` | utility | file-I/O (raw-grid read) | `src/assayingest/parsing/table.py` (`_parse_excel_sheet`, `sheet_names`) | role-match |
| `src/assayingest/parsing/structure/header.py` | utility | transform (scoring) | `src/assayingest/parsing/table.py` (`_clean_header`, single-level-of-abstraction helpers) | role-match |
| `src/assayingest/parsing/structure/delimiter.py` | utility | transform | `src/assayingest/parsing/table.py` (`parse_file` CSV branch) | role-match |
| `src/assayingest/parsing/structure/locale.py` | utility | transform | `src/assayingest/domain/reference.py` (pure classification/reference tables, no I/O) | role-match |
| `src/assayingest/parsing/structure/sheets.py` | utility | transform (ranking) | `src/assayingest/parsing/table.py` (`sheet_names`) | role-match |
| `src/assayingest/parsing/structure/shape.py` | utility | transform (classification) | `src/assayingest/domain/reference.py` (classification predicates) | role-match |
| `src/assayingest/parsing/structure_assist.py` | service | request-response (Claude call) | `src/assayingest/mapping/mapper.py` (`propose_mapping`, wire→domain boundary) | exact |
| `src/assayingest/parsing/table.py` (modified) | model/service | file-I/O | itself (existing `parse_file`/`RawTable`) — extend, don't replace | exact |
| `src/assayingest/cli.py` (modified) | controller | request-response | itself (existing `run`/`_map_and_report`) — add the "ask" branch | exact |
| `scripts/gen_synthetic_pk.py` (modified — add drawing fixtures) | utility (fixture gen) | file-I/O (batch) | itself (existing `gen_zephyr`, `save`, `gen_pinnacle_csv`) | exact |

## Pattern Assignments

### `src/assayingest/parsing/hint.py` (model, request-response)

**Analog:** `src/assayingest/domain/models.py`

**Imports pattern** (lines 1-11):
```python
"""Domain models — the target shape Data Ingestor maps every CRO file into.

These are pure Python dataclasses with no dependency on pandas, the Anthropic
SDK, or any wire format. Infrastructure layers (parsing, mapping) map their own
models onto these at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
```

**Core "propose + confidence + gate" pattern to imitate** (lines 26-58) — `FieldMapping` is the direct template for `StructureQuestion`:
```python
@dataclass(frozen=True)
class ColumnCandidate:
    """One alternative the mapper considered for a target field."""
    source_column: str
    confidence: float


@dataclass
class FieldMapping:
    target_field: TargetField
    source_column: str | None
    confidence: float
    reasoning: str
    needs_confirmation: bool
    inferred_value: str | None = None
    alternatives: list[ColumnCandidate] = field(default_factory=list)

    @property
    def is_clear(self) -> bool:
        """A field is clear (green) only when nothing needs a human's eyes."""
        return not self.needs_confirmation
```

**Aggregate + readiness-gate pattern** (lines 61-79) — `MappingProposal.is_ready` is the template for a hypothetical multi-question aggregate, and the per-instance gate (`is_clear`) is exactly D-07's shape (reason, confidence, alternatives, `needs_confirmation`):
```python
@dataclass
class MappingProposal:
    source_columns: list[str]
    field_mappings: list[FieldMapping]

    @property
    def is_ready(self) -> bool:
        return all(m.is_clear for m in self.field_mappings)

    @property
    def unclear_fields(self) -> list[FieldMapping]:
        return [m for m in self.field_mappings if not m.is_clear]
```

**Mapping to D-06/D-07 fields:**
- `StructuralHint` (frozen, JSON-round-trippable) mirrors `ColumnCandidate`'s frozen-value-object shape but with more fields: `sheet_name`, `header_row_index`, `delimiter`, `decimal_separator`, `data_region`, `table_shape`.
- `StructureQuestion` mirrors `FieldMapping`: `reason` (~`reasoning`), `confidence`, `proposal: StructuralHint | None` (~`inferred_value`), `alternatives: list[StructuralHint]` (~`alternatives: list[ColumnCandidate]`), plus D-07's "raw-grid evidence" field with no existing analog (new).
- Since `StructuralHint`/`StructureQuestion` must be JSON-serialisable (D-06) and reused by Claude's wire model too, follow the enum convention `class TableShape(str, Enum)` exactly as `TargetField(str, Enum)` does.

---

### `src/assayingest/parsing/structure/header.py`, `delimiter.py`, `locale.py`, `shape.py` (utility, transform)

**Analog:** `src/assayingest/parsing/table.py` (`_clean_header`) for docstring/SLA style; `src/assayingest/domain/reference.py` for "pure, no I/O, reference/classification table" style.

**Single-level-of-abstraction + "why" docstring pattern** (table.py lines 127-136):
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
Apply this same shape to `locale.classify_column()`: one-line summary, then the *why* (per RESEARCH.md Pattern 3 — ambiguity is evidence-of-variance, not per-cell), private helpers for each regex predicate rather than one long function (SLA discipline).

**Note:** `src/assayingest/domain/reference.py` was not read this session (not in the required-reading list and no line budget concern arose), but is cited by CONTEXT.md/CLAUDE.md as the existing "no-LLM reference dictionary" pattern — the planner should confirm its exact shape (`ALLOWED_UNITS`, `ASSAY_TYPES`, `UNIT_VALUE_RANGES` module-level constants, `SCREAMING_SNAKE_CASE`, imported directly by `mapper.py`) before writing `locale.py`'s `ALLOWED_...` constants, since `locale.py`/`shape.py` are the closest new files to that "constants + pure classification" role.

---

### `src/assayingest/parsing/structure/grid.py`, `sheets.py` (utility, file-I/O)

**Analog:** `src/assayingest/parsing/table.py` (`sheet_names`, `_parse_excel_sheet`)

**Error-handling pattern to copy verbatim** (table.py lines 50-68):
```python
def sheet_names(path: str | Path) -> list[str]:
    """List an Excel workbook's sheet names; empty list for a CSV.

    Raises `FileNotFoundError` if the path is missing so a bad path is reported
    the same way for every file type, and `ValueError` for an unsupported one.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot ingest: no file at {path}")
    suffix = path.suffix.lower()
    if suffix in _EXCEL_SUFFIXES:
        with pd.ExcelFile(path) as workbook:
            return [str(name) for name in workbook.sheet_names]
    if suffix == ".csv":
        return []
    raise ValueError(
        f"Cannot ingest {path.name}: expected a .csv or .xlsx file, "
        f"got '{path.suffix}'"
    )
```
`grid.py`'s Excel reader must diverge from this analog in one deliberate way per RESEARCH.md Pitfall 2/3: use `openpyxl.load_workbook(path)` in **normal** mode (never `read_only=True`, never `pd.read_excel(..., dtype=str)`) so `_charts`/`_images`/`_rels` and native cell types survive — reuse the `FileNotFoundError`/`ValueError` messages and control flow, not the pandas call itself.

**Sheet iteration — the new mandatory pattern (RESEARCH.md Pattern 4/7), not present in current code, must replace any `wb.sheetnames` + `wb[name]` habit:**
```python
# Source: this repo, empirical probe + openpyxl 3.1.5 source (see 01-RESEARCH.md Pattern 7b)
wb = openpyxl.load_workbook(path)   # NORMAL mode — required for _charts/_images/_rels
for ws in wb.worksheets:             # structurally excludes Chartsheet instances
    rows = list(ws.iter_rows(values_only=True))
```

---

### `src/assayingest/parsing/structure_assist.py` (service, request-response)

**Analog:** `src/assayingest/mapping/mapper.py` (entire file — this is a near-exact template)

**Imports pattern** (mapper.py lines 1-21):
```python
from __future__ import annotations

import anthropic

from ..domain.models import (
    ColumnCandidate,
    FieldMapping,
    MappingProposal,
    TargetField,
)
from ..domain.reference import ALLOWED_UNITS, ASSAY_TYPES, UNIT_VALUE_RANGES
from ..parsing.table import RawTable
from .schema import WireFieldMapping, WireMappingProposal
```
For `structure_assist.py`: swap `..domain.models` imports for `.hint` (`StructuralHint`, `StructureQuestion`), and the wire schema import for a new `WireStructureProposal` in a sibling `structure_schema.py` (mirroring `mapping/schema.py`'s wire/domain split at this new layer boundary).

**Optional-client-injection + structured-output call pattern to copy exactly** (mapper.py lines 56-80):
```python
_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 4096

def propose_mapping(
    table: RawTable, client: anthropic.Anthropic | None = None
) -> MappingProposal:
    """Ask Claude for a column mapping and return it as a domain proposal.

    A missing API key surfaces as `anthropic.AuthenticationError` from the SDK;
    the caller decides how to report it.
    """
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _render_request(table)}],
        output_format=WireMappingProposal,
    )
    wire = response.parsed_output
    if wire is None:
        raise ValueError(
            f"Mapping failed for {table.label}: the model returned no "
            f"structured proposal (stop reason: {response.stop_reason})."
        )
    return _to_domain(wire, table.headers)
```
This is the exact seam D-04 requires ("Claude layer is a separate module so deterministic tests never touch the SDK") and the exact optional-`client` injection point tests already rely on (see `test_mapper_boundary.py`, which imports `_render_table`/`_to_domain` and never constructs a real `anthropic.Anthropic()`).

**Wire→domain boundary mapping pattern** (mapper.py lines 112-129):
```python
def _to_domain(wire: WireMappingProposal, headers: list[str]) -> MappingProposal:
    """Map the validated wire model onto the domain proposal at the boundary."""
    mappings = [_to_domain_field(item) for item in wire.field_mappings]
    return MappingProposal(source_columns=headers, field_mappings=mappings)


def _to_domain_field(item: WireFieldMapping) -> FieldMapping:
    return FieldMapping(
        target_field=TargetField(item.target_field),
        source_column=item.source_column,
        confidence=item.confidence,
        reasoning=item.reasoning,
        needs_confirmation=item.needs_confirmation,
        inferred_value=item.inferred_value,
        alternatives=[
            ColumnCandidate(c.source_column, c.confidence) for c in item.alternatives
        ],
    )
```
`structure_assist.py` needs the identical two-function split (`_to_domain` / `_to_domain_field`) mapping a `WireStructureProposal` onto `StructureQuestion`'s `proposal: StructuralHint` field — **never applies it** (D-02): this function only ever *pre-fills* a question object, it must not return a bare `StructuralHint`.

**Wire schema pattern** (`mapping/schema.py`, entire file, lines 1-64) — template for the new `structure_schema.py`:
```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

class WireCandidate(BaseModel):
    """One ranked alternative column for an ambiguous field."""
    source_column: str = Field(description="A source header that could match.")
    confidence: float = Field(description="0.0-1.0 confidence for this option.")

class WireFieldMapping(BaseModel):
    """Claude's proposed resolution of a single target field."""
    target_field: TargetFieldName
    source_column: str | None = Field(...)
    confidence: float = Field(...)
    reasoning: str = Field(...)
    needs_confirmation: bool = Field(...)
    inferred_value: str | None = Field(default=None, ...)
    alternatives: list[WireCandidate] = Field(default_factory=list, ...)
```
Reuse this exact `Field(description=...)` documentation-in-schema idiom — the SDK relies on these descriptions to steer the model.

---

### `src/assayingest/parsing/table.py` (modified — extend, do not replace)

**Analog:** itself — CONTEXT.md D-06 leaves it Claude's Discretion whether `parse_file()` stays a thin wrapper or is migrated; CONTEXT.md explicitly says backward compatibility is *not* required, a clean boundary is. `RawTable`'s docstring invariant (lines 15-24, quoted verbatim in D-12) must be preserved unchanged regardless of how `parse_file()` is restructured:
```python
@dataclass(frozen=True)
class RawTable:
    """A parsed source sheet: cleaned headers plus every row as strings.

    Values are kept as strings so the mapper sees them exactly as written
    (e.g. `03/11/2025`, `0.045`) without pandas coercing types and hiding the
    ambiguity the curator needs to resolve. `sheet_name` is set only for Excel
    workbooks with more than one sheet — a single CSV or one-sheet workbook
    leaves it None.
    """
```
The new top-level entry point (whatever it's named — `parse()`, or `parse_file()` itself widened) must return `RawTable | StructureQuestion` per D-05 ("returning a result object, not raising"). Keep `FileNotFoundError`/`ValueError` exactly as today for genuinely broken files (missing path, unreadable workbook) — those remain exceptions; only *structural uncertainty* becomes a returned value.

---

### `src/assayingest/cli.py` (modified — add the "ask" branch)

**Analog:** itself — `_map_and_report` / `_map_one` (lines 145-176) is the template for the new "ask" branch (D-08: asking is the caller's job).

**Existing per-item dispatch + exit-code-tracking pattern to extend:**
```python
def _map_and_report(tables: list[RawTable]) -> int:
    """Map each table and print its draft; worst per-table exit code wins."""
    multi = len(tables) > 1
    worst = 0
    for index, table in enumerate(tables, start=1):
        if multi:
            print(f"===== sheet {index}/{len(tables)}: "
                  f"{table.sheet_name} =====")
        if table.row_count == 0:
            print("  (skipped: sheet has no data rows)\n")
            continue
        worst = max(worst, _map_one(table))
        print()
    return worst
```
Per D-18/Pitfall 5, the `table.row_count == 0` skip branch is exactly the bug the phase must fix: a drawing-only sheet must not fall into this silent-skip path any more — it must route to a printed `StructureQuestion` instead. The new CLI branch should mirror `_map_one`'s try/except-and-print shape:
```python
def _map_one(table: RawTable) -> int:
    try:
        proposal = propose_mapping(table)
    except anthropic.AuthenticationError:
        print("error: Anthropic rejected the credentials (check ANTHROPIC_API_KEY).",
              file=sys.stderr)
        return 3
    except (anthropic.APIError, ValueError) as exc:
        print(f"error: mapping failed for {table.label}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(proposal_to_dict(proposal), indent=2, ensure_ascii=False))
    print()
    print(render_report(proposal))
    return 0
```
A new `_ask_and_report(question: StructureQuestion) -> StructuralHint` (or similar) should follow the same JSON-print + human-readable-report-print + return-exit-code shape as `render_report`/`proposal_to_dict`, using `input()` for the actual terminal prompt (CLI-only; D-08 says the *object* stays presentation-agnostic, only the CLI's rendering of it is terminal-specific).

---

### `scripts/gen_synthetic_pk.py` (modified — add 3 drawing fixtures)

**Analog:** itself — `gen_zephyr()` (banner-rows-above-header pattern, lines 67-96) and `gen_pinnacle_csv()` (lines 320-341) are the two closest existing generator functions; `save()` (lines 58-61) is the shared write helper to reuse unchanged.

**Function-per-fixture + shared `save()` pattern:**
```python
def save(wb: Workbook, name: str) -> None:
    path = OUT / name
    wb.save(path)
    print(f"  wrote {path.relative_to(OUT.parent.parent)}  ({len(wb.sheetnames)} sheet(s))")
```
```python
def main() -> None:
    print("Generating messy synthetic PK/assay files ->", OUT)
    gen_zephyr()
    gen_meridian()
    ...
    gen_pinnacle_csv()
    print("Done. 10 new files.")
```
The three new fixtures (D-19's requirement) should be added as `gen_chart_embedded()`, `gen_chartsheet()`, `gen_image_only_sheet()` (or one `gen_drawings()` producing a single multi-sheet workbook, per RESEARCH.md's own throwaway-fixture shape: `Data` / `DataWithChart` / `ChartOnly` / `Empty`/`ImageOnly` sheets) and appended to `main()`'s call list, updating the trailing count message. `openpyxl.chart.BarChart` + `ws.add_chart(chart, "E2")` for the embedded-chart case; `wb.create_chartsheet()` for the chartsheet case; `openpyxl.drawing.image.Image` (requires the new **dev-only** `Pillow` dependency — `uv add --dev pillow`, never imported from `src/assayingest/`) for the image-only case, per RESEARCH.md's verified `uv add --dev pillow` command and D-19's runtime/dev split.

---

## Shared Patterns

### Frozen dataclass + `@property` gate (domain-model shape)
**Source:** `src/assayingest/domain/models.py` lines 26-58
**Apply to:** `StructuralHint` (frozen value object), `StructureQuestion` (mutable aggregate with `@property` computed fields if any are needed, mirroring `FieldMapping.is_clear`)

### Wire model boundary split (Pydantic wire → stdlib domain)
**Source:** `src/assayingest/mapping/schema.py` (whole file) + `mapper.py::_to_domain`/`_to_domain_field`
**Apply to:** `structure_schema.py` (new) + `structure_assist.py::_to_domain`/`_to_domain_field`

### Error handling: `FileNotFoundError` / `ValueError`, consequence-described messages
**Source:** `src/assayingest/parsing/table.py` lines 50-68, 71-93
**Apply to:** `grid.py`, `sheets.py`, and any modified `table.py` entry point — genuinely broken files still raise; structural *uncertainty* returns a value (D-05), never raises

### Optional-client-injection seam for Anthropic calls (testability)
**Source:** `src/assayingest/mapping/mapper.py` line 56-57 (`client: anthropic.Anthropic | None = None`)
**Apply to:** `structure_assist.py`'s Claude-proposal function — required so its tests can inject a fake/mock client exactly as `test_mapper_boundary.py` avoids touching the SDK for pure-boundary tests

### Module docstring + "why, not what" comment style
**Source:** `src/assayingest/parsing/table.py` lines 1-5, 127-136; `CLAUDE.md`/`CONVENTIONS.md` §Comments
**Apply to:** every new module in `parsing/structure/`, `hint.py`, `structure_assist.py`

### Import ordering: `__future__` → stdlib → third-party → relative
**Source:** `.planning/codebase/CONVENTIONS.md` §Import Organization, exemplified in `mapper.py` lines 1-21
**Apply to:** all new files

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/assayingest/parsing/structure/grid.py`'s drawing-detection helper (`is_drawing_only_sheet`) | utility | event-driven-ish (drawing presence check) | No existing code touches `ws._charts`/`ws._images`/`ws._rels` at all — Day-1 parser never opened a workbook in normal mode for anything but `pd.read_excel`. RESEARCH.md's Pattern 7 predicate (verified this session, quoted above) is the closest thing to an analog and should be used directly as the implementation seed. |
| `multiple_tables` shape-classification branch | utility | transform | RESEARCH.md itself flags this as a corpus gap with no fixture — no code or fixture analog exists anywhere in the repo; implement defensively per RESEARCH.md Pattern 5's note and mark low-confidence until a fixture exists. |

## Metadata

**Analog search scope:** `src/assayingest/` (parsing/, domain/, mapping/, cli.py), `tests/`, `scripts/gen_synthetic_pk.py`
**Files scanned:** `parsing/table.py`, `domain/models.py`, `mapping/schema.py`, `mapping/mapper.py`, `cli.py`, `tests/test_parsing.py`, `tests/test_excel_sheets.py`, `tests/test_mapper_boundary.py`, `scripts/gen_synthetic_pk.py` (head + tail), `.planning/codebase/CONVENTIONS.md`
**Pattern extraction date:** 2026-07-10
