---
phase: 02-user-defined-fields-dynamic-mapper
reviewed: 2026-07-10T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - src/assayingest/fields/models.py
  - src/assayingest/fields/loader.py
  - src/assayingest/mapping/schema.py
  - src/assayingest/mapping/mapper.py
  - src/assayingest/canonical.py
  - src/assayingest/cli.py
  - src/assayingest/domain/models.py
  - presets/assay-potency.yaml
  - presets/pk-parameters.yaml
  - presets/reagent-inventory.yaml
findings:
  critical: 5
  warning: 2
  info: 0
  total: 7
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-07-10
**Depth:** standard (with targeted empirical verification of the two highest-risk areas — the YAML loader and the canonical assembler — using the actual interpreter)
**Files Reviewed:** 10 (7 source + 3 presets)
**Status:** issues_found

## Summary

This phase's stated thesis is that Claude only ever *proposes* and a human *disposes*, and that nothing silently rewrites a value. Two of the five critical findings below are exactly the kind of defect that thesis exists to prevent: `mapper.py`'s wire→domain boundary trusts an unverified `source_column` and never checks that every declared field actually came back, so a mismatched or omitted field can reach the "green, ready to export" state without a human ever seeing a flag. A third finding shows this isn't theoretical — `canonical.py`'s unit-mismatch check is demonstrably broken for one of the phase's own three shipped presets (`pk-parameters.yaml`): every numeric field that declares a `unit` is *permanently* flagged, defeating the export gate in the opposite (annoying but at least safe) direction. Two more findings are in the untrusted-YAML loader (`fields/loader.py`), which the task brief calls "security-critical": it does use `yaml.safe_load` exclusively (confirmed — no unsafe loader path exists), but it does not validate the *shape* of the parsed document before using it, so a handful of very ordinary malformed or malicious field-set files crash the process with a raw, un-caught traceback (`AttributeError`/`AssertionError`) instead of the named `ValueError` every other loader in this codebase promises.

None of the findings below are style preferences; every one was reproduced against the actual code in this repo (commands/snippets included) before being written up.

## Critical Issues

### CR-01: `mapper.py`'s wire→domain boundary never validates `source_column` against the table's real headers

**File:** `src/assayingest/mapping/mapper.py:159-176`
**Issue:** `_to_domain`/`_to_domain_field` copy `item.source_column` from Claude's structured-output response straight into the domain `FieldMapping` with no check that the string is actually one of `table.headers` (or the empty-string blank-header sentinel). `schema.py`'s `Literal` only constrains `target_field`; `source_column` remains a free `str | None`.

Consequence, traced end-to-end: if Claude returns a `source_column` that doesn't exactly match a header — plausible for this exact domain, e.g. the micro sign `µ` (U+00B5) vs the Greek letter mu `μ` (U+03BC) look identical and both appear in unit columns like "µM" — with `confidence=1.0` and `needs_confirmation=False` (nothing forces the model to flag a match it believes is clean), then:
- `render_report()` prints a **green ✓** for that field — the human reviewer is told it is safe.
- `MappingProposal.is_ready` returns `True` for that field, contributing to a fully "READY" gate.
- `canonical.assemble()` → `_column_index()` fails the `table.headers.index(source_column)` lookup, silently returns `None`, and the resulting cell becomes `None` in the canonical record — with **no flag added** (`_normalise_cell` returns `(raw, False)` when `raw is None`, see `canonical.py:154-155`).

The net effect: a hallucinated/mismatched column reference can produce a canonical record with a silently-missing value, reported as fully confirmed and ready to export. This is precisely the "silent guess" the project's non-negotiable principle #2 forbids, and it slips past the `is_ready` gate that principle #3 relies on.

**Fix:** Validate in the boundary mapper, not just defensively in `canonical.py`:
```python
def _to_domain(wire, headers: list[str]) -> MappingProposal:
    header_set = set(headers)
    mappings = [_to_domain_field(item, header_set) for item in wire.field_mappings]
    return MappingProposal(source_columns=headers, field_mappings=mappings)

def _to_domain_field(item, header_set: set[str]) -> FieldMapping:
    source_column = item.source_column
    needs_confirmation = item.needs_confirmation
    reasoning = item.reasoning
    if source_column is not None and source_column not in header_set:
        needs_confirmation = True
        reasoning = (
            f"{reasoning} [flagged: model returned source_column "
            f"'{source_column}', which is not one of the table's headers]"
        )
    return FieldMapping(
        target_field=item.target_field,
        source_column=source_column,
        confidence=item.confidence,
        reasoning=reasoning,
        needs_confirmation=needs_confirmation,
        ...
    )
```

---

### CR-02: `mapper.py`/`canonical.py` never verify every declared field came back — an omitted field silently vanishes from the gate

**File:** `src/assayingest/mapping/mapper.py:159-162`, `src/assayingest/canonical.py:114-119`
**Issue:** `_to_domain(wire, headers)` builds a `MappingProposal` from whatever `wire.field_mappings` happens to contain — it does not take the `FieldSet` it was called with, so it has no way to check that Claude actually returned exactly one entry per declared field. The system prompt asks for "exactly one entry per field" (`mapper.py:67`), but nothing in the schema or the boundary code enforces it (`WireMappingProposal.field_mappings` is an unconstrained `list[...]`, verified in `schema.py:88-91`).

If a field is entirely missing from Claude's response (a well-documented LLM failure mode with long field lists, and this loader supports up to 50 fields), two independent things go wrong silently:
1. `MappingProposal.is_ready` (`domain/models.py:65-68`) is `all(m.is_clear for m in self.field_mappings)` — a field that was never appended to the list doesn't count against readiness, so the proposal can report **READY** while a whole target field was never addressed.
2. `canonical.assemble()`'s `_mapped_columns()` (`canonical.py:114-119`) builds `column_by_field` only from `proposal.field_mappings`; a name absent from that dict resolves via `.get(name)` → `None` → `_cell()` returns `None` → `_normalise_cell()` returns `(None, False)` (`canonical.py:154-155`) — again, **no flag**.

Verified this is not merely theoretical: `tests/test_mapper_boundary.py` only ever constructs wire responses with exactly one entry for exactly one declared field; there is no test anywhere in the phase's own test suite that exercises a partial/omitted response.

**Fix:** Pass `field_set` into `_to_domain` and reconcile:
```python
def _to_domain(wire, headers: list[str], field_set: FieldSet) -> MappingProposal:
    by_name = {m.target_field: m for m in (_to_domain_field(i, set(headers)) for i in wire.field_mappings)}
    mappings = [
        by_name.get(name) or _missing_field_mapping(name)
        for name in field_set.field_names
    ]
    return MappingProposal(source_columns=headers, field_mappings=mappings)

def _missing_field_mapping(name: str) -> FieldMapping:
    return FieldMapping(
        target_field=name, source_column=None, confidence=0.0,
        reasoning="The model did not return a mapping for this field.",
        needs_confirmation=True,
    )
```

---

### CR-03: `canonical._unit_mismatch` misapplies D-12 to numeric fields and permanently blocks the phase's own `pk-parameters.yaml` preset

**File:** `src/assayingest/canonical.py:194-199`
**Issue:**
```python
def _unit_mismatch(raw: str, target_field: Field) -> bool:
    return target_field.unit is not None and raw.strip() != target_field.unit
```
This assumes a field's mapped *cell value itself* is the unit string (correct for `assay-potency.yaml`'s `unit` field, whose column literally contains `"µM"`/`"nM"`). But `unit` is a general `Field` attribute any field can declare to document its measurement unit — and `pk-parameters.yaml` (shipped in this same phase) uses it exactly that way: `cmax` is `type: number, unit: ng/mL`, and the mapped column contains numbers like `"125.3"`, not the string `"ng/mL"`. `_unit_mismatch` compares `"125.3" != "ng/mL"` → always `True` → **every one of `cmax`, `tmax`, `auc`, `half_life`, `clearance`, `dose` is force-flagged on every row, unconditionally.**

Reproduced directly:
```python
table = RawTable(headers=["Compound", "Cmax (ng/mL)"], rows=[["CPD-1", "125.3"]],
                  source_name="fixture.csv", column_locales=["non_numeric", "decimal_point"])
field_set = FieldSet(fields=(Field(name="compound_id", type="text"),
                              Field(name="cmax", type="number", unit="ng/mL")))
# ... assemble() ...
# => {'compound_id': 'CPD-1', 'cmax': '125.3'}, flagged=['cmax']
```
`cmax` is flagged even though the mapping is perfect and unambiguous. Because 6 of `pk-parameters.yaml`'s 7 fields declare `unit`, loading that preset makes the canonical table's export gate effectively unsatisfiable no matter how clean the source file is — this breaks one of the three demo presets this phase shipped.

**Fix:** `_unit_mismatch` should only run for fields whose *value itself* is the unit (i.e., fields with no numeric/date type, or a new explicit marker), or the check should be dropped from `_convert_by_type`'s callers entirely for `number`/`integer`/`date`-typed fields:
```python
def _unit_mismatch(raw: str, target_field: Field) -> bool:
    if target_field.type in ("number", "integer", "date"):
        return False  # `unit` here documents the value's unit, it is not the cell's content
    return target_field.unit is not None and raw.strip() != target_field.unit
```

---

### CR-04: `fields/loader.py` assumes the parsed document is always a `dict` — a handful of ordinary malformed files crash with a raw traceback instead of a named error

**File:** `src/assayingest/fields/loader.py:58-67`
**Issue:** `_build_field_set(raw)` calls `raw.get("fields", [])` unconditionally. `raw` is whatever `yaml.safe_load`/`json.loads` returned, which — for perfectly ordinary malformed input a curator or an attacker could easily submit — is not guaranteed to be a `dict`:
- an **empty file** → `yaml.safe_load("")` returns `None` → `AttributeError: 'NoneType' object has no attribute 'get'`
- a **top-level YAML/JSON list** (e.g. `- a\n- b`) → `AttributeError: 'list' object has no attribute 'get'`
- a **`fields:` key that is itself a mapping instead of a list** → `len(field_specs)` silently succeeds (counts dict keys) but then `tuple(_build_field(spec) for spec in field_specs)` iterates the dict's *keys* (strings), and `_build_field` does `raw.get("name")` on a string → `AttributeError: 'str' object has no attribute 'get'`

Reproduced directly against `loader.load()`:
```
empty file           -> AttributeError: 'NoneType' object has no attribute 'get'
top-level list        -> AttributeError: 'list' object has no attribute 'get'
```
None of these is caught by `cli.main()`, which only catches `(FileNotFoundError, ValueError)` around `load_field_set(args.fields)` (`cli.py:405-410`) — so the CLI exits with an unhandled Python traceback rather than the `error: ...` / exit-code-2 contract every other malformed-input path in this codebase uses. This directly contradicts the project convention "raise a named error for anything broken" that this module's own docstring commits to, and it is precisely the class of input this loader is documented to be hardened against (an untrusted file from a stranger).

**Fix:** Validate the top-level shape before using it:
```python
def _build_field_set(raw: object) -> FieldSet:
    if not isinstance(raw, dict):
        raise ValueError(
            "Cannot load field set: expected a mapping with a 'fields' list "
            f"at the top level, got {type(raw).__name__}."
        )
    field_specs = raw.get("fields", [])
    if not isinstance(field_specs, list):
        raise ValueError(
            f"Cannot load field set: 'fields' must be a list, got {type(field_specs).__name__}."
        )
    ...
```

---

### CR-05: `fields/loader.py` never validates `name`'s type — YAML's implicit typing silently turns some field names into booleans/numbers, and always crashes `FieldSet.signature`

**File:** `src/assayingest/fields/loader.py:74-79`, `src/assayingest/fields/models.py:86-102`
**Issue:** `_build_field` does `name = raw.get("name")` then `if not name: raise ValueError(...)`. This only rejects *falsy* values (`None`, `""`, `0`, `False`). YAML 1.1's implicit typing (which `yaml.safe_load` applies) turns unquoted `yes`/`no`/`true`/`on`/`off` into Python `bool`, and unquoted numerals into `int`/`float` — a field declared `name: yes` or `name: 42` (both entirely plausible, unquoted, human-written YAML — nobody remembers to quote `yes`) is accepted as a field whose `.name` is `True` or `42`, not the string `"yes"`/`"42"`.

Reproduced:
```
>>> yaml.safe_load("fields:\n  - name: yes\n    type: text\n  - name: 42\n    type: number\n")
{'fields': [{'name': True, 'type': 'text'}, {'name': 42, 'type': 'number'}]}
>>> _build_field_set(...).signature
AttributeError: 'bool' object has no attribute 'lower'
```
Two distinct consequences:
1. **Silent corruption of the very identity the user declared.** The field the author named "yes" is rendered into the system prompt as `- True` (`mapper.py:104`, `f"- {f.name}"`), used to build `Literal[True, ...]` in the runtime schema, and shown to Claude and the CLI as `True` — not `"yes"`. Nothing in the pipeline ever tells the user their field name was silently reinterpreted.
2. **`FieldSet.signature` (`fields/models.py:66-79`) crashes unconditionally** on any such field via `f.name.lower()` in `_normalise_field`. This property is documented as "this project's stable identity hook for Phase 3's learning-loop key" — the very first real use of it will raise an uncaught `AttributeError`.

**Fix:** Require and coerce `name` to be a non-empty string explicitly:
```python
name = raw.get("name")
if not isinstance(name, str) or not name.strip():
    raise ValueError(
        f"Cannot load field set: every field requires a string 'name' "
        f"(got {name!r})."
    )
```

## Warnings

### WR-01: `_convert_numeric` only ever converts `decimal_comma` columns — the common `decimal_point`/plain-number case stays a string

**File:** `src/assayingest/canonical.py:171-182`
**Issue:** `_convert_numeric` converts to `float` only when `locale == NumericLocale.DECIMAL_COMMA`; for `DECIMAL_POINT` (the ordinary Western `1234.56` format — the majority case for most CRO files), `AMBIGUOUS`, or no locale info at all, the raw string passes through unconverted and unflagged. A field declared `type: number` whose source column is entirely ordinary, unambiguous decimal-point numbers still ends up as a JSON *string* (`"125.3"`) rather than a JSON number (`125.3`) in the canonical export, with no flag to indicate anything is off (because nothing structurally is — it's just never converted). This appears to be an intentional scope decision (the accompanying comments only ever discuss D-14/decimal_comma), but it means `type: number` does not actually deliver numeric output for the common case, which will surprise any downstream consumer (e.g. Phase 4's UI/API) expecting `type: number` fields to be numbers.
**Fix:** Extend the safe, unambiguous case: `DECIMAL_POINT` values can be converted with a plain `float(raw)` (no locale disambiguation needed — there's nothing ambiguous about it), falling back to a flag only on an actual `ValueError`:
```python
def _convert_numeric(raw: str, locale: str | None) -> tuple[str | float, bool]:
    if locale == NumericLocale.NON_NUMERIC.value:
        return raw, True
    if locale in (NumericLocale.DECIMAL_COMMA.value, NumericLocale.DECIMAL_POINT.value):
        try:
            return (convert_decimal_comma(raw) if locale == NumericLocale.DECIMAL_COMMA.value
                    else float(raw.strip())), False
        except ValueError:
            return raw, True
    return raw, False
```

### WR-02: `resolve_tables()` in `cli.py` is dead in the actual run path but still tested as if it were live

**File:** `src/assayingest/cli.py:115-129`
**Issue:** `run()` calls `resolve_or_ask()` (which uses the structural `parse()` engine), not `resolve_tables()`. `resolve_tables()` — which uses the legacy `parse_file()`/`sheet_names()` path with no structural detection, no locale annotation, and no ambiguity gating — is only referenced from `tests/test_excel_sheets.py`, never from `main()`/`run()`. It's not itself a bug, but it's easy to mistake for the live sheet-resolution path when reading this file, and any future change to `run()`'s sheet-selection semantics won't be exercised by the tests that call `resolve_tables()` directly.
**Fix:** Either remove `resolve_tables()` if it's superseded by `resolve_or_ask()`, or add a one-line comment noting it's the pre-structural-detection legacy path kept only for the Excel-sheet-listing tests, so a future reader doesn't assume it's on the `run()` call path.

---

_Reviewed: 2026-07-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
