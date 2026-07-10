"""VAL-01/02/03: the no-LLM safety net. "Lives are at stake" made mechanical
(P1) -- every mapped value, and every one of Claude's ranked alternatives, is
checked against the constraints the *user* declared for that field. A
violation forces `needs_confirmation=True` no matter how confident Claude
reported the field, and regardless of whether the proposal came fresh from
Claude or from an auto-applied confidence-1.0 profile (D-03) -- the caller is
responsible for calling `validate()` on both paths.

Reuses `canonical.assemble()` as its type/date/text-unit engine (Pattern 1):
that function already has no readiness gate, so it is safe to call on an
unclear proposal, and its `CanonicalTable.flagged` already names every field
where a decimal-comma conversion failed, a date didn't match its declared
`date_format`, or a text field's value didn't equal its declared `unit`. The
only genuinely new checks written here are `allowed_values` (case-insensitive,
D-07) and `min`/`max` numeric bounds -- writing a second conversion parser
here would duplicate `canonical.py`'s already-correct, already-tested logic.

The validator is additive-only (Pattern 2/P1): `_apply_objection` may only
ever OR a `True` into `needs_confirmation`, never clear one back to `False`.
This is a deliberate divergence from
`mapping.mapper._cleared_if_optional_and_absent`, which DOES clear a flag
under a specific condition -- do not "fix" this into a symmetric setter. A
field with no declared constraints (VAL-03) is never silently trusted: its
`needs_confirmation` is left exactly as Claude/a human set it, but a
`validator_note` records the EXPLICIT ABSENCE of an objection so the tool's
silence is never mistaken for a check that ran and passed.
"""

from __future__ import annotations

import math
from dataclasses import replace

from .. import canonical
from ..domain.models import FieldMapping, MappingProposal
from ..fields.models import Field, FieldSet
from ..parsing.table import RawTable

#: VAL-03: shown when a field declares none of allowed_values/type/unit/min/max
#: -- distinguishes "the validator ran and found nothing to check" from
#: "the validator ran and found nothing wrong" (see `_NO_VIOLATION_NOTE`).
_NO_CONSTRAINTS_NOTE = "no declared constraints to check"
_NO_VIOLATION_NOTE = "no constraint violation found"

#: D-11: strict (default) scans every row; lenient relaxes row COVERAGE only,
#: never the severity of an in-scope violation (RESEARCH Assumption A1).
_STRICTNESS_VALUES = ("strict", "lenient")
#: Mirrors `mapping.mapper._SAMPLE_ROWS` -- the same "first N rows are enough
#: evidence" idiom already established for the Claude-facing sample.
_LENIENT_SAMPLE_ROWS = 6


def validate(
    table: RawTable,
    proposal: MappingProposal,
    field_set: FieldSet,
    *,
    strictness: str = "strict",
) -> MappingProposal:
    """Check every mapped field -- and every ranked alternative -- against
    its field's declared constraints, forcing `needs_confirmation=True` on
    any objection. Returns a new `MappingProposal`; never mutates the input.
    """
    if strictness not in _STRICTNESS_VALUES:
        raise ValueError(
            f"Cannot validate with strictness='{strictness}': expected one "
            f"of {', '.join(_STRICTNESS_VALUES)}, so the caller cannot "
            "silently relax coverage below the recognised levels."
        )
    fields_by_name = {f.name: f for f in field_set.fields}
    rows = _rows_for_strictness(table, strictness)
    locales = table.column_locales if len(table.column_locales) == len(table.headers) else []

    # Pattern 1: safe pre-confirmation -- assemble() has no readiness gate.
    tidy = canonical.assemble(table, proposal, field_set)

    mappings = [
        _validate_mapping(
            mapping, table.headers, locales, rows, fields_by_name.get(mapping.target_field), tidy.flagged
        )
        for mapping in proposal.field_mappings
    ]
    return replace(proposal, field_mappings=mappings)


def _validate_mapping(
    mapping: FieldMapping,
    headers: list[str],
    locales: list[str],
    rows: list[list[str]],
    target_field: Field | None,
    canonical_flagged: list[str],
) -> FieldMapping:
    """One field's verdict: no declared constraints (VAL-03) short-circuits
    to the explicit-absence note; otherwise every objection source (the
    canonical reuse, and the new allowed_values/min/max checks across every
    candidate column) is combined into one note."""
    if target_field is None or not _has_constraints(target_field):
        return _apply_objection(mapping, False, _NO_CONSTRAINTS_NOTE)

    notes: list[str] = []
    if mapping.target_field in canonical_flagged:
        notes.append(
            "type/date/unit conversion check objected (decimal-comma, date "
            "format, or declared-unit mismatch)"
        )
    notes.extend(_check_candidates(mapping, headers, locales, rows, target_field))

    if notes:
        return _apply_objection(mapping, True, "; ".join(notes))
    return _apply_objection(mapping, False, _NO_VIOLATION_NOTE)


def _has_constraints(f: Field) -> bool:
    """VAL-03: a field is "no declared constraints" only when it carries
    none of the checks the validator (or its canonical-reuse Pattern 1
    engine) can act on."""
    return (
        f.type is not None
        or f.allowed_values is not None
        or f.unit is not None
        or f.min is not None
        or f.max is not None
    )


def _check_candidates(
    mapping: FieldMapping,
    headers: list[str],
    locales: list[str],
    rows: list[list[str]],
    target_field: Field,
) -> list[str]:
    """VAL-02: every column Claude named for this field -- the chosen
    `source_column` AND every ranked alternative -- is checked, not only the
    top pick. A violation on any one of them is the field's objection."""
    notes: list[str] = []
    seen: set[str] = set()
    candidates = [mapping.source_column] + [c.source_column for c in mapping.alternatives]
    for source_column in candidates:
        if source_column is None or source_column in seen:
            continue
        seen.add(source_column)
        violation = _check_column(headers, locales, rows, source_column, target_field)
        if violation:
            label = source_column if source_column else "(blank header)"
            notes.append(f"column '{label}': {violation}")
    return notes


def _check_column(
    headers: list[str],
    locales: list[str],
    rows: list[list[str]],
    source_column: str,
    target_field: Field,
) -> str | None:
    """The first constraint violation found in this column across the
    validated rows, or `None` when the column is clean (or unresolvable --
    an alternative naming an unknown header is a mapper concern, not this
    check's, see `mapper._names_a_column_that_does_not_exist`)."""
    col_index = _column_index(headers, source_column)
    if col_index is None:
        return None
    locale = _locale_at(locales, col_index)
    for row in rows:
        raw = _cell(row, col_index)
        if raw is None:
            continue
        violation = _check_value(raw, locale, target_field)
        if violation:
            return violation
    return None


def _check_value(raw: str, locale: str | None, target_field: Field) -> str | None:
    """The two genuinely new checks (VAL-01): allowed_values
    (case-insensitive, D-07) and min/max numeric bounds. Everything else --
    type/date/unit -- is Pattern 1's canonical-reuse job, not this
    function's."""
    if target_field.allowed_values is not None:
        allowed = {v.casefold() for v in target_field.allowed_values}
        if raw.strip().casefold() not in allowed:
            return (
                f"'{raw}' is not one of the allowed values "
                f"({', '.join(target_field.allowed_values)})"
            )
    if target_field.min is not None or target_field.max is not None:
        value = _numeric_value(raw, locale)
        if value is not None:
            if not math.isfinite(value):
                # WR-02: float("nan") parses successfully and every
                # comparison against NaN is False, so a literal nan/NaN
                # cell would otherwise pass the min/max check unflagged --
                # fail open in the "runs on every value" safety net (P1).
                # inf/-inf are already caught by the comparisons below, so
                # only nan needs this explicit reject.
                return f"'{raw}' is not a finite number"
            if target_field.min is not None and value < target_field.min:
                return f"{value} is below the declared minimum {target_field.min}"
            if target_field.max is not None and value > target_field.max:
                return f"{value} is above the declared maximum {target_field.max}"
    return None


def _numeric_value(raw: str, locale: str | None) -> float | None:
    """Coerce a cell to a number for the min/max check only -- reuses
    `canonical.convert_decimal_comma` for a `decimal_comma` column rather
    than re-implementing locale coercion (Don't Hand-Roll). A value that
    still doesn't parse is not this check's concern (Pattern 1's
    canonical-flagged reuse already covers a numeric-field/non-numeric-cell
    mismatch) -- returns `None` so the bounds check is silently skipped."""
    if locale == "decimal_comma":
        try:
            return canonical.convert_decimal_comma(raw)
        except ValueError:
            return None
    try:
        return float(raw.strip())
    except ValueError:
        return None


def _column_index(headers: list[str], source_column: str | None) -> int | None:
    """The header's position in this exact table, or `None` when unmapped or
    unknown. Mirrors `canonical._column_index`'s shape (an empty string is a
    valid header; only `None` means "no column was matched") -- a trivial
    lookup, not a duplicate of any conversion logic."""
    if source_column is None:
        return None
    try:
        return headers.index(source_column)
    except ValueError:
        return None


def _cell(row: list[str], col_index: int) -> str | None:
    if col_index >= len(row):
        return None
    return row[col_index]


def _locale_at(locales: list[str], col_index: int) -> str | None:
    if col_index >= len(locales):
        return None
    return locales[col_index]


def _rows_for_strictness(table: RawTable, strictness: str) -> list[list[str]]:
    """D-11: strict (default) scans every row; lenient relaxes row COVERAGE
    only -- an in-scope violation the sample DOES see is still a full
    objection, never a softened one (RESEARCH Assumption A1)."""
    if strictness == "lenient":
        return table.sample(_LENIENT_SAMPLE_ROWS)
    return table.rows


def _apply_objection(mapping: FieldMapping, objects: bool, note: str) -> FieldMapping:
    """Additive-only (Pattern 2/P1): may only ever OR a `True` into
    `needs_confirmation`, never clear an existing `True` back to `False`.
    Diverges deliberately from `mapper._cleared_if_optional_and_absent`,
    which DOES clear a flag under a specific condition -- do not "fix" this
    into a symmetric setter; VAL-03 depends on the validator's silence never
    being read as "safe to clear"."""
    return replace(
        mapping,
        needs_confirmation=mapping.needs_confirmation or objects,
        validator_note=note,
    )
