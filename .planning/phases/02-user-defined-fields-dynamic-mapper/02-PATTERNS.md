# Phase 2: User-Defined Fields + Dynamic Mapper - Pattern Map

**Mapped:** 2026-07-10
**Files analyzed:** 12
**Analogs found:** 12 / 12

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|---------------|
| `src/assayingest/fields/models.py` (new) | model | transform (pure data) | `src/assayingest/parsing/hint.py` (`StructuralHint`) | exact — same "frozen dataclass, optional fields, `to_dict()`" shape |
| `src/assayingest/fields/loader.py` (new) | utility (file I/O → domain) | file-I/O | `src/assayingest/parsing/table.py` (`parse_file`/`sheet_names`) | role-match — file-read → raise-on-bad-input boundary function |
| `src/assayingest/mapping/schema.py` (modified) | service (wire model builder) | transform | itself (current static version) + `src/assayingest/parsing/structure_schema.py` | exact — same wire-model file, `structure_schema.py` shows the sibling wire/domain split at another layer |
| `src/assayingest/mapping/mapper.py` (modified) | service (Claude call) | request-response | itself (current version) + `src/assayingest/parsing/structure_assist.py` | exact — same file; `structure_assist.py` is the newest sibling `propose_*(x, client=None)` implementation |
| `src/assayingest/domain/models.py` (modified: remove `TargetField`, `target_field: str`) | model | transform | itself (current version) | exact |
| `src/assayingest/domain/reference.py` (deleted; content becomes preset data) | config/data | n/a | itself (current version) — becomes `presets/assay-potency.yaml` | exact — the file's *shape* survives as YAML |
| `presets/assay-potency.yaml`, `presets/pk-parameters.yaml`, `presets/reagent-inventory.yaml` (new) | config | file-I/O | `src/assayingest/domain/reference.py`'s `ASSAY_TYPES`/`ALLOWED_UNITS`/`UNIT_VALUE_RANGES` data | role-match — same content, now YAML instead of Python literals |
| `src/assayingest/canonical.py` (new, EXPORT-01 assembly) | service (transform) | transform | `src/assayingest/parsing/structure/locale.py` (`classify_column`/`resolve_ambiguity`) | role-match — pure-function, per-column/per-value classify-then-convert pattern |
| `src/assayingest/cli.py` (modified: `--fields`, `--fields-required`? no — exit code 5, `_hint_from_args`-style `--fields` loader wiring) | controller (CLI entry) | request-response | itself (current version) | exact |
| `tests/test_field_set.py` (new) | test | n/a | `tests/test_hint_and_locale.py` | exact — same "pure dataclass + loader, no API key" test idiom |
| `tests/test_mapper_boundary.py` (modified) | test | n/a | itself (current version) | exact |
| `scripts/gen_synthetic_pk.py` (modified: add 2 fixtures) | utility (data generation) | batch | itself (current version) | exact |

## Pattern Assignments

### `src/assayingest/fields/models.py` (model, transform)

**Analog:** `src/assayingest/parsing/hint.py`

**Frozen-dataclass-with-optional-fields pattern** (lines 47-65):
```python
@dataclass(frozen=True)
class StructuralHint:
    """The structural dimensions a human (or Claude) can pin down.

    Every field is optional so a hint can carry just the one dimension in
    question — e.g. only `header_row_index` when the header row is unclear
    but the delimiter and locale already resolved cleanly (D-06).
    """

    sheet_name: str | None = None
    header_row_index: int | None = None
    delimiter: str | None = None
    decimal_separator: str | None = None
    data_region: str | None = None
    table_shape: TableShape | None = None

    def to_dict(self) -> dict:
        """A plain JSON-safe dict — enum members coerced to their string value."""
        return _jsonable(asdict(self))
```

**Copy for `Field`:** one frozen dataclass per D-05..D-11 (`name`, `description`, `type`, `allowed_values`, `unit`, `required=True`, `min`, `max`, `date_format`), all but `name` optional/defaulted — mirrors `StructuralHint`'s "every field optional but one" shape (here `name` is the one required field, analogous to none being required in `StructuralHint` but the pattern of defaults is identical).

**Copy for `FieldSet`:** a second frozen dataclass wrapping `fields: list[Field]`, with `to_dict()` for the JSON round-trip Phase 4 needs (D-02) — same reason `StructureQuestion.to_dict()` exists: "the shape that travels over HTTP" (`hint.py` line 96).

**`_jsonable` recursive coercion helper** (lines 108-116) — reuse verbatim if `Field`/`FieldSet` need to serialise nested lists (`allowed_values`) cleanly; already handles list/dict/Enum recursion.

**Docstring precedent for "pure Python, no SDK dependency" invariant** (lines 1-11): copy the framing — *"Pure Python dataclasses with no dependency on pandas, the Anthropic SDK, or any wire format... the deterministic layer must be testable without an API key."* This is the exact invariant CONTEXT.md's Claude's Discretion section implies for the field-set model.

---

### `src/assayingest/fields/loader.py` (utility, file-I/O)

**Analog:** `src/assayingest/parsing/table.py` (`parse_file`, `sheet_names`)

**Raise-on-bad-input pattern** (lines 57-75):
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

**Copy for `load(path) -> FieldSet`:** same `Path`-normalise → `.exists()` check → dispatch-on-suffix → raise-named-error shape. Dispatch on `.yaml`/`.yml` vs `.json` (D-02) the same way `parse_file` dispatches on `.csv` vs `.xlsx`. Error messages must describe the consequence ("Cannot ingest ... expected a .csv or .xlsx file, got X"), not the symptom — mirror this exactly for an unsupported field-set extension and for the D-04 50-field cap: `f"Field set exceeds the 50-field limit ({count} fields declared)."`

**Security-critical deviation — do NOT copy `pd.read_*`'s default loader:** the loader must call `yaml.safe_load`, never `yaml.load` (D-03). There is no existing YAML-loading analog in the codebase; this is a new leaf import. Cite `parsing/table.py`'s framing that a raised error (not a returned "question") is correct for *broken* input, matching `parsing/table.py`'s docstring: *"only a genuinely broken file (missing path, unsupported extension, unknown sheet) still raises."* A malformed field-set file is broken input in exactly this sense (RESEARCH.md, `code_context`).

---

### `src/assayingest/mapping/schema.py` (service — wire model builder, transform)

**Analog:** itself (current static version) + `src/assayingest/parsing/structure_schema.py`

**Current static shape to replace** (lines 14-22, full file at `mapping/schema.py:1-64`):
```python
TargetFieldName = Literal[
    "compound_id", "assay_type", "value", "unit", "target",
    "n_replicates", "assay_date",
]


class WireFieldMapping(BaseModel):
    target_field: TargetFieldName
    source_column: str | None = Field(...)
    confidence: float = Field(...)
    reasoning: str = Field(...)
    needs_confirmation: bool = Field(...)
    inferred_value: str | None = Field(default=None)
    alternatives: list[WireCandidate] = Field(default_factory=list, ...)
```

**Sibling wire-model docstring convention to preserve** (`structure_schema.py` lines 1-10):
```python
"""Wire models — the exact JSON shape Claude is constrained to return for a
structural PROPOSAL.

These Pydantic models live at the infrastructure boundary, mirroring
`mapping/schema.py`'s wire/domain split one layer earlier (D-01 layer 2):
`structure_assist.py` validates Claude's output against them and then maps
the validated model onto `parsing.hint.StructuralHint` at the boundary...
"""
```

**Copy for the new `build_wire_models(field_set)`:** RESEARCH.md's Pattern 2 (`create_model` + `Literal[tuple(field_names)]`) is the exact code to use — cite it directly (RESEARCH.md lines 263-309). Keep every field name in `WireFieldMapping` identical (`source_column`, `confidence`, `reasoning`, `needs_confirmation`, `inferred_value`, `alternatives`) per D-17 — only `target_field`'s *type* becomes a runtime `Literal`. `WireCandidate` stays fully static (it never referenced `TargetFieldName`).

---

### `src/assayingest/mapping/mapper.py` (service — Claude call, request-response)

**Analog:** itself (current version) + `src/assayingest/parsing/structure_assist.py`

**Optional-client injection seam to preserve exactly** (lines 56-64):
```python
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
```

**New signature (D-18/D-22):** `propose_mapping(table: RawTable, field_set: FieldSet, client: anthropic.Anthropic | None = None) -> MappingProposal` — same `client = client or anthropic.Anthropic()` line, same `response.parsed_output is None` guard (lines 75-79), same error message shape (`f"Mapping failed for {table.label}: the model returned no structured proposal (stop reason: {response.stop_reason})."`).

**`_SYSTEM_PROMPT` and `_render_request` — the two sites to empty per D-19** (lines 27-53, 83-99):
```python
_SYSTEM_PROMPT = """\
You are the mapping engine of Data Ingestor ...
Target fields (produce exactly one entry per field):
- compound_id: the tested compound's identifier
...
"""

def _render_request(table: RawTable) -> str:
    """Build the user message: the reference vocabulary plus the raw table."""
    assay_lines = "\n".join(
        f"  - {a.canonical}: units {', '.join(a.compatible_units)}"
        for a in ASSAY_TYPES
    )
    range_lines = "\n".join(
        f"  - {unit}: {lo}–{hi}" for unit, (lo, hi) in UNIT_VALUE_RANGES.items()
    )
    return (
        f"Allowed assay types and their units:\n{assay_lines}\n\n"
        f"Allowed units: {', '.join(ALLOWED_UNITS)}\n\n"
        f"Typical value ranges by unit ...\n{range_lines}\n\n"
        f"Source file: {table.label}\n"
        f"{_render_table(table)}"
    )
```
Both must be rewritten to build purely from `field_set` (D-18) — the prompt's *structure* (rules 1-3 about propose/never-guess/needs_confirmation) is domain-independent and should survive verbatim; only the "Target fields" bullet list and the assay/unit vocabulary lines are field-set-derived.

**`_render_table` — keep verbatim, no change needed** (lines 102-109) — it already reads only `table.headers`/`table.sample()`, nothing domain-specific. Extend to also emit `table.column_locales` per column (D-22) — same list-zip idiom already used elsewhere in the codebase (`parsing/table.py`'s `annotate_columns`), guarding on `len(column_locales) == len(headers)` per RESEARCH.md Pitfall 3.

**`_to_domain`/`_to_domain_field` boundary split — keep the split, drop the enum coercion** (lines 112-129):
```python
def _to_domain(wire: WireMappingProposal, headers: list[str]) -> MappingProposal:
    mappings = [_to_domain_field(item) for item in wire.field_mappings]
    return MappingProposal(source_columns=headers, field_mappings=mappings)

def _to_domain_field(item: WireFieldMapping) -> FieldMapping:
    return FieldMapping(
        target_field=TargetField(item.target_field),   # <-- DELETE the TargetField(...) call
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
RESEARCH.md's Code Examples section already has the exact post-D-19 version of `_to_domain_field` (RESEARCH.md lines 450-461) — `target_field=item.target_field` (plain str, no coercion).

**Sibling `propose_structure` for the "propose, never write" docstring convention** (`structure_assist.py` lines 43-54) — same framing to reuse in the updated `propose_mapping` docstring: *"This function only ever builds a ... for pre-filling... no code path here applies it... A missing API key surfaces as `anthropic.AuthenticationError` from the SDK; the caller decides how to report it (mirrors `mapping/mapper.py::propose_mapping`'s existing contract)."*

**`_MAX_TOKENS` change (Pitfall 2):** raise from `4096` to `16000` — a one-line module-constant change, same `SCREAMING_SNAKE_CASE` convention (`_MODEL`, `_MAX_TOKENS`, `_SAMPLE_ROWS`, line 23-25).

---

### `src/assayingest/domain/models.py` (model, transform)

**Analog:** itself (current version)

**`TargetField` enum to delete entirely** (lines 14-23) per D-19.

**`FieldMapping`/`MappingProposal` — keep the dataclass shape, only retype `target_field`** (lines 38-59):
```python
@dataclass
class FieldMapping:
    target_field: TargetField      # <-- becomes: target_field: str
    source_column: str | None
    confidence: float
    reasoning: str
    needs_confirmation: bool
    inferred_value: str | None = None
    alternatives: list[ColumnCandidate] = field(default_factory=list)

    @property
    def is_clear(self) -> bool:
        return not self.needs_confirmation
```

**`MappingProposal.is_ready`/`unclear_fields` — keep verbatim** (lines 61-79) — no change needed; both properties are field-count-agnostic already.

---

### `src/assayingest/domain/reference.py` → `presets/assay-potency.yaml` (config, deleted-as-code / reborn-as-data)

**Analog:** itself (current version)

**The exact vocabulary to migrate into YAML preset form** (lines 26-46):
```python
ASSAY_TYPES: tuple[AssayType, ...] = (
    AssayType("IC50", _CONCENTRATION_UNITS, aliases=("ic50", "ic-50")),
    AssayType("EC50", _CONCENTRATION_UNITS, aliases=("ec50", "ec-50")),
    AssayType("Ki", _CONCENTRATION_UNITS, aliases=("ki",)),
    AssayType("Kd", _CONCENTRATION_UNITS, aliases=("kd",)),
    AssayType("%inhibition", ("%",), aliases=(...)),
)
ALLOWED_UNITS: tuple[str, ...] = ("µM", "nM", "%")
UNIT_VALUE_RANGES: dict[str, tuple[float, float]] = {
    "nM": (0.1, 1000.0),
    "µM": (0.001, 100.0),
    "%": (0.0, 100.0),
}
```
Maps to a per-field `allowed_values` list (D-07, case-insensitive match against `assay_type`'s aliases collapses into `allowed_values: [IC50, EC50, Ki, Kd, "%inhibition"]`) and per-field `min`/`max` (D-10 — `UNIT_VALUE_RANGES`'s per-unit ranges become the potency field's `min`/`max`, though D-10 frames this as one range per *field* not per unit — note this generalisation loses the per-unit granularity `UNIT_VALUE_RANGES` had; the planner should decide whether that's an acceptable simplification or whether `unit`-conditional `min`/`max` needs a follow-up).

**File-level docstring framing to reuse in the preset YAML's header comment** (lines 1-6): *"This is the ground truth the mapper's proposals are checked against... a plain data structure on purpose."* — same intent, now literally data instead of code.

---

### `src/assayingest/canonical.py` (new — EXPORT-01 assembly, transform)

**Analog:** `src/assayingest/parsing/structure/locale.py`

**Classify-then-convert pure-function pattern** (lines 27-39, 50-76):
```python
def classify_column(values: list[str]) -> NumericLocale:
    """Classify one column's decimal locale from the variance across its values.

    Never per-cell (D-13) — a single 3-digit-group value has no way to
    disambiguate itself and is treated as ambiguous, not as evidence.
    """
    ...

def locale_from_separator(separator: str) -> NumericLocale:
    """Turn a human's answer to an ambiguity question into a column locale.

    Raises `ValueError` for anything that is not `,` or `.` — a malformed
    hint is a broken input, not structural uncertainty, so it raises rather
    than returning another question (D-05).
    """
    ...

def resolve_ambiguity(
    locales: list[NumericLocale], separator: str
) -> list[NumericLocale]:
    """Replace every `AMBIGUOUS` column with the locale the human chose.

    Confidently-classified columns are left alone: the hint answers the
    question that was asked, it does not override evidence.
    """
    ...
```

**Copy this shape for `convert_decimal_comma`/`convert_date`:** RESEARCH.md's Code Examples section already has both functions written and verified against the real corpus (RESEARCH.md lines 396-440) — use them verbatim as the starting implementation:
```python
def convert_decimal_comma(raw: str) -> float:
    cleaned = raw.strip().replace(".", "").replace(",", ".")
    return float(cleaned)  # raises ValueError on genuine garbage

def convert_date(raw: str, date_format: str) -> tuple[str | None, bool, str | None]:
    try:
        parsed = datetime.strptime(raw.strip(), date_format)
    except ValueError:
        return None, True, f"'{raw}' does not match the declared date_format '{date_format}'"
    return parsed.date().isoformat(), False, None
```

**"Never per-cell, per-value try/except, never a hard crash" convention to reuse for Pitfall 4/5:** `classify_column`'s docstring framing (*"a single 3-digit-group value has no way to disambiguate itself"*) is the same posture the date/decimal converters need — catch `ValueError` per-value, flag the field, never let it propagate to a crash (RESEARCH.md Pitfall 5, "Confirmed via CONTEXT.md D-13: the mechanism is a flag, not a raise").

**D-12 "never convert units" — the precedent for declining to act is `_ambiguous_locale_question`'s reasoning field** (`parsing/table.py` lines 218-236): *"guessing risks corrupting the value by 1000x."* The canonical-assembly code should flag a unit mismatch with an equally concrete, consequence-describing reason, not a bare "unit mismatch."

---

### `src/assayingest/cli.py` (controller, request-response)

**Analog:** itself (current version)

**`--hint` flag parsing — the closest analog for `--fields`** (lines 320-341, 357-384):
```python
def _hint_from_args(hints: list[str]) -> StructuralHint | None:
    """Turn repeated `--hint key=value` flags into a `StructuralHint` (PARSE-06).
    ...
    A malformed flag raises `ValueError`; unresolved structure does not (D-05).
    """
    if not hints:
        return None
    ...

def main() -> None:
    parser = argparse.ArgumentParser(...)
    parser.add_argument("file", help="...")
    parser.add_argument("--sheet", default=None, help="...")
    parser.add_argument("--hint", action="append", default=[], metavar="KEY=VALUE", help="...")
    args = parser.parse_args()
    try:
        hint = _hint_from_args(args.hint)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(args.file, args.sheet, hint))
```
Copy this exact shape for `--fields <path>` (D-01): a single positional-like required option, parsed via `fields.loader.load(path)`, with the same `try/except ValueError → print to stderr → sys.exit(2)` wrapping used for `_hint_from_args`.

**Exit-code convention — the precedent for D-23's new code 5** (lines 148-171, 293-307):
```python
def run(path: str, sheet: str | None = None, hint: StructuralHint | None = None) -> int:
    try:
        outcome = resolve_or_ask(path, sheet, hint)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if isinstance(outcome, StructureQuestion):
        return _ask_and_report(outcome)   # returns 4
    ...
    return _map_and_report(tables)         # returns 0 today, must become 0-or-5

def _map_one(table: RawTable) -> int:
    try:
        proposal = propose_mapping(table)
    except anthropic.AuthenticationError:
        ...
        return 3
    except (anthropic.APIError, ValueError) as exc:
        ...
        return 1
    print(...)
    return 0   # <-- must become: 0 if proposal.is_ready else 5 (D-23)
```
The existing multi-table "worst exit code wins" reducer (`_map_and_report`, `worst = max(worst, _map_one(table))`) already composes correctly with a new code 5 — no change needed to the reduction logic itself, only to what `_map_one` returns on success.

**`_render_gate`'s BLOCKED/READY framing — reuse verbatim for the exit-code docstring** (lines 96-104):
```python
def _render_gate(proposal: MappingProposal) -> str:
    if proposal.is_ready:
        return f"{_GREEN} READY: all fields clear — safe to confirm and export."
    n = len(proposal.unclear_fields)
    names = ", ".join(m.target_field.value for m in proposal.unclear_fields)
    return (
        f"{_YELLOW} BLOCKED: {n} field(s) need confirmation ({names}). "
        f"Export stays disabled until resolved."
    )
```
Note `m.target_field.value` (line 100) — must become `m.target_field` (plain str) once `TargetField` is removed (same fix needed at `_field_to_dict` line 42 and `_render_field` line 68).

---

### `tests/test_field_set.py` (new, TDD-first)

**Analog:** `tests/test_hint_and_locale.py` (not read in full this pass, but confirmed present in repo as the idiom for pure-dataclass + loader testing) and `tests/test_mapper_boundary.py`

**Pure-boundary-logic test idiom to copy** (`test_mapper_boundary.py` lines 1-13, 16-35):
```python
"""The mapper's pure boundary logic — wire→domain and prompt rendering.

These run without an API key; the live call is exercised separately.
"""

from assayingest.domain.models import TargetField
from assayingest.mapping.mapper import _render_table, _to_domain
from assayingest.mapping.schema import (
    WireCandidate, WireFieldMapping, WireMappingProposal,
)
from assayingest.parsing.table import RawTable


def test_wire_maps_to_domain_field_with_alternatives():
    wire = WireMappingProposal(field_mappings=[...])
    proposal = _to_domain(wire, headers=["assay", "type"])
    field = proposal.field_mappings[0]
    assert field.target_field is TargetField.ASSAY_TYPE
    ...
```
Same module docstring convention ("These run without an API key") and same bare-assertion style — no test framework beyond `pytest`'s auto-discovery. `tests/test_field_set.py` should test: `Field`/`FieldSet` construction, `load()` dispatch on `.yaml`/`.json`, the D-04 50-field-cap error, and `yaml.safe_load` (not `yaml.load`) being the call made (mock/patch or inspect source, per D-03's "not optional" framing).

---

### `scripts/gen_synthetic_pk.py` (modified — add 2 fixtures)

**Analog:** itself (current version)

**Existing value-generation helper pattern to extend** (lines 30-40):
```python
def conc_value(unit: str) -> float:
    """A plausible potency for the given unit's typical magnitude."""
    if unit == "nM":
        return round(RNG.uniform(0.2, 950.0), RNG.choice([1, 2, 3]))
    if unit in ("µM", "uM"):
        return round(RNG.uniform(0.003, 40.0), 3)
    return round(RNG.uniform(5.0, 98.0), 1)  # % inhibition

def date_iso(day: int) -> tuple[int, int, int]:
    """A (y, m, d) tuple in early 2025, cycling days for variety."""
    d = 1 + (day % 27)
    m = 1 + (day // 27) % 12
    return (2025, m, d)
```
Add a sibling helper, e.g. `european_thousands_decimal(value: float) -> str` producing `"1.234,56"`-style strings (RESEARCH.md's missing-fixture gap: "the classic European thousands + decimal pattern does not exist anywhere in the ten-file corpus"), and a fixture that writes a real `datetime.date`/`datetime` object via `ws.cell(...).value = date(...)` (not `f"{d:02d}.{m:02d}.{y}"`) so at least one column is Excel-native-date-typed (RESEARCH.md Pitfall 6). Use the same `RNG = random.Random(20260709)` deterministic seed already declared at module level (line 27) for reproducibility — do not introduce a second RNG instance.

**`save(wb, name)` helper (line ~40 onward, not fully shown)** — reuse as-is for the two new fixture workbooks; every existing fixture already funnels through it.

---

## Shared Patterns

### Optional-client injection for testability
**Source:** `src/assayingest/mapping/mapper.py:56-64`, mirrored in `src/assayingest/parsing/structure_assist.py:43-55`
**Apply to:** `propose_mapping(table, field_set, client=None)` — the signature must keep `client: anthropic.Anthropic | None = None` as the last parameter and `client = client or anthropic.Anthropic()` as the first line of the body. This is the single mechanism that keeps the entire mapping layer testable without an API key (CONTEXT.md `code_context` explicitly calls this out: "do not lose it").
```python
def propose_mapping(
    table: RawTable, client: anthropic.Anthropic | None = None
) -> MappingProposal:
    client = client or anthropic.Anthropic()
    response = client.messages.parse(...)
```

### Wire model / domain model boundary split
**Source:** `src/assayingest/mapping/mapper.py:112-129` (`_to_domain`/`_to_domain_field`), mirrored by `src/assayingest/parsing/structure_assist.py:74-99`
**Apply to:** All new mapping code. Wire models are Pydantic (`mapping/schema.py`), live at the infrastructure boundary; domain models are plain/frozen dataclasses (`domain/models.py`) with zero SDK/Pydantic imports. A `_to_domain(wire) -> Domain` function is the sole conversion point — never let a Pydantic model leak past the mapper module.

### Log-or-raise, never both / error messages describe the consequence
**Source:** `src/assayingest/parsing/table.py:57-75` (`sheet_names`), `src/assayingest/mapping/mapper.py:75-79`
**Apply to:** `fields/loader.py`'s D-03/D-04 errors. Example to mirror:
```python
raise ValueError(
    f"Cannot ingest {path.name}: expected a .csv or .xlsx file, "
    f"got '{path.suffix}'"
)
```
The 50-field-cap error (D-04) must name the count and the limit, e.g. `f"Cannot load field set: {count} fields declared, exceeds the 50-field limit."` — describing the consequence (why it's rejected), not the raw fact.

### "Propose, never guess silently" / needs_confirmation gate
**Source:** `src/assayingest/domain/models.py:38-59` (`FieldMapping.is_clear`, `MappingProposal.is_ready`), `src/assayingest/parsing/hint.py:69-93` (`StructureQuestion.answerable_by_hint`)
**Apply to:** `canonical.py`'s D-12 unit-never-converted and D-13 date-only-with-format-declared logic — both are new instances of the same "flag, don't guess" gate `FieldMapping.needs_confirmation` already embodies. `answerable_by_hint`'s precedent ("say plainly when no remedy exists") applies directly to D-12: when a unit mismatch has no possible tool-side resolution, say so, don't offer a fake remedy.

### Module-level constants, docstring, and import conventions
**Source:** `src/assayingest/mapping/mapper.py:1-25`
**Apply to:** All new modules. `from __future__ import annotations` first; module docstring stating purpose and the "propose, never write" invariant where applicable; `SCREAMING_SNAKE_CASE` constants (`_MODEL`, `_MAX_TOKENS`, `_SAMPLE_ROWS`); relative imports for internal modules (`from ..domain.models import ...`), absolute imports only in `__init__.py` files (per `CLAUDE.md`/`CONVENTIONS.md`).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| YAML-loading code inside `fields/loader.py` (`yaml.safe_load` call site specifically) | utility | file-I/O | No existing YAML dependency or loader in the codebase (project has only ever consumed CSV/Excel via pandas/openpyxl); RESEARCH.md's Code Examples and Security Domain sections are the primary reference instead of a codebase analog. |

## Metadata

**Analog search scope:** `src/assayingest/` (all four layers: parsing, mapping, domain, cli), `tests/`, `scripts/`, `pyproject.toml`
**Files scanned:** `parsing/table.py`, `parsing/hint.py`, `parsing/structure_assist.py`, `parsing/structure_schema.py`, `parsing/structure/locale.py`, `mapping/schema.py`, `mapping/mapper.py`, `domain/models.py`, `domain/reference.py`, `cli.py`, `tests/test_mapper_boundary.py`, `scripts/gen_synthetic_pk.py`, `pyproject.toml`
**Pattern extraction date:** 2026-07-10
