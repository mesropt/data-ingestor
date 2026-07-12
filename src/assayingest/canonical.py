"""EXPORT-01: the one canonical tidy table every export format derives from.

Consumes a `MappingProposal` + the source `RawTable` + the `FieldSet` the
mapper was called with, and assembles one record per source row, columns =
the user's field names (D-15). Only conversions the human explicitly
authorised are ever applied: a column Phase 1 already proved is
`decimal_comma` becomes a real number (D-14); a unit is recorded exactly as
written and NEVER converted (D-12) -- the tool has no physics compiled in
and must never guess that "n" means 10⁻⁹. Every conversion failure or
mismatch flags the field instead of rewriting or raising -- one malformed
row never aborts the whole assembly (Pitfall 4/5).

A date is converted to ISO-8601 when a format is RESOLVED for it -- either
detected from the column's own independent evidence (`parsing.structure.
date_order`), chosen by a human answering a per-column question, or (as a
fallback, when nothing was resolved) declared on the field itself and not
contradicted by the data. **D-10-06 supersedes D-13**: a declared
`date_format` alone is no longer unconditional permission to convert -- it
is a claim, and `service.resolve_date_formats` checks it against the
column's own evidence before this module ever sees it. `assemble()`'s new
`date_formats` keyword-only override carries that resolution; it defaults
to `None` so every existing call site (and every fallback case below) keeps
today's exact behavior unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from .domain.models import MappingProposal
from .fields.models import Field, FieldSet
from .parsing.hint import NumericLocale
from .parsing.structure import date_order
from .parsing.table import RawTable


def convert_decimal_comma(raw: str) -> float:
    """Convert a value from a column Phase 1 classified `decimal_comma`.

    Mirrors `structure/locale.py`'s own parsing rule: strip every '.'
    (assumed thousands grouping), then treat the remaining ',' as the
    decimal point. Raises `ValueError` on anything that still doesn't parse
    -- the caller (`assemble`) catches this per-value and flags the field;
    it never propagates to a crash.
    """
    cleaned = raw.strip().replace(".", "").replace(",", ".")
    return float(cleaned)


def convert_date(raw: str, date_format: str) -> tuple[str | None, bool, str | None]:
    """Returns `(iso_value_or_None, needs_confirmation, reason)`.

    A declared `date_format` is permission to convert (D-13); a value that
    doesn't match it is not a crash -- it is exactly what `needs_confirmation`
    exists for.
    """
    try:
        parsed = datetime.strptime(raw.strip(), date_format)
    except ValueError:
        return None, True, (
            f"'{raw}' does not match the declared date_format '{date_format}'"
        )
    return parsed.date().isoformat(), False, None


@dataclass(frozen=True)
class CanonicalTable:
    """The tidy assembly result: one record per source row, columns = the
    field set's field names, plus which fields any row forced a flag on."""

    field_names: list[str]
    records: list[dict[str, str | float | None]]
    flagged: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """A plain JSON-safe dict — the shape the CLI/API prints."""
        return {
            "field_names": self.field_names,
            "records": self.records,
            "flagged": self.flagged,
        }


def assemble(
    table: RawTable,
    proposal: MappingProposal,
    field_set: FieldSet,
    *,
    date_formats: Mapping[str, str] | None = None,
) -> CanonicalTable:
    """Build one canonical record per source row, applying only the
    conversions the field set's declarations authorise.

    `date_formats` (keyword-only, defaulted to `None`) maps a date-typed
    field's name to a RESOLVED strptime format (or `date_order.
    EXCEL_SERIAL_MARKER`) that wins over that field's merely-declared
    `date_format` -- see the module docstring (D-10-06). Omitting it entirely
    preserves every existing call site's exact behavior.
    """
    fields_by_name = {f.name: f for f in field_set.fields}
    column_by_field = _mapped_columns(table, proposal)
    locales = table.column_locales if len(table.column_locales) == len(table.headers) else []

    records: list[dict[str, str | float | None]] = []
    flagged: set[str] = set()
    for row in table.rows:
        record, row_flags = _assemble_record(
            row, field_set.field_names, fields_by_name, column_by_field, locales, date_formats
        )
        records.append(record)
        flagged.update(row_flags)

    return CanonicalTable(
        field_names=list(field_set.field_names), records=records, flagged=sorted(flagged)
    )


def _assemble_record(
    row: list[str],
    field_names: list[str],
    fields_by_name: dict[str, Field],
    column_by_field: dict[str, int | None],
    locales: list[str],
    date_formats: Mapping[str, str] | None,
) -> tuple[dict[str, str | float | None], set[str]]:
    """One record: every field normalised per its own declared type/format."""
    record: dict[str, str | float | None] = {}
    flags: set[str] = set()
    for name in field_names:
        col_index = column_by_field.get(name)
        raw = _cell(row, col_index)
        value, needs_flag = _normalise_cell(
            raw, fields_by_name.get(name), _locale_at(locales, col_index), date_formats
        )
        record[name] = value
        if needs_flag:
            flags.add(name)
    return record, flags


def _mapped_columns(table: RawTable, proposal: MappingProposal) -> dict[str, int | None]:
    """Each field's mapped source-column index, or None when unmapped."""
    return {
        mapping.target_field: _column_index(table, mapping.source_column)
        for mapping in proposal.field_mappings
    }


def _column_index(table: RawTable, source_column: str | None) -> int | None:
    """The header's position, or None for an unmapped field / unknown header.

    An empty string is a valid `source_column` (an unlabelled column, per
    `parsing/table.py`'s blank-header convention) -- only `None` means "no
    column was matched".
    """
    if source_column is None:
        return None
    try:
        return table.headers.index(source_column)
    except ValueError:
        return None


def _cell(row: list[str], col_index: int | None) -> str | None:
    if col_index is None or col_index >= len(row):
        return None
    return row[col_index]


def _locale_at(locales: list[str], col_index: int | None) -> str | None:
    if col_index is None or col_index >= len(locales):
        return None
    return locales[col_index]


def _normalise_cell(
    raw: str | None,
    target_field: Field | None,
    locale: str | None,
    date_formats: Mapping[str, str] | None,
) -> tuple[str | float | None, bool]:
    """Apply the one conversion the field's declared type authorises, then
    check the D-12 unit-never-converted guard independently of type."""
    if target_field is None or raw is None:
        return raw, False

    value, type_flagged = _convert_by_type(raw, target_field, locale, date_formats)
    return value, type_flagged or _unit_mismatch(raw, target_field)


def _convert_by_type(
    raw: str, target_field: Field, locale: str | None, date_formats: Mapping[str, str] | None
) -> tuple[str | float | int, bool]:
    if target_field.type == "integer":
        return _narrow_to_integer(*_convert_numeric(raw, locale))
    if target_field.type == "number":
        return _convert_numeric(raw, locale)
    if target_field.type == "date":
        resolved_format = (date_formats or {}).get(target_field.name)
        return _convert_field_date(raw, target_field.date_format, resolved_format)
    return raw, False


def _narrow_to_integer(
    value: str | float, flagged: bool
) -> tuple[str | float | int, bool]:
    """A field declared `integer` yields an int, never `3.0`. A number with a
    real fractional part is not silently truncated — it is flagged, because
    losing `2.5` replicates is exactly the kind of plausible-looking wrong
    answer this tool exists to prevent."""
    if flagged or not isinstance(value, float):
        return value, flagged
    if value.is_integer():
        return int(value), False
    return value, True


def _convert_numeric(raw: str, locale: str | None) -> tuple[str | float, bool]:
    """Both resolved numeric locales convert to a real number; non_numeric
    force-flags without calling `float()` (Pitfall 4); an unresolved locale
    (ambiguous, or no locale info) passes through unconverted.

    decimal_point converts too: the canonical table is the single
    representation every export derives from (D-15), so a number must not be
    a float in one column and a string in the next.
    """
    if locale == NumericLocale.NON_NUMERIC.value:
        return raw, True
    if locale == NumericLocale.DECIMAL_COMMA.value:
        try:
            return convert_decimal_comma(raw), False
        except ValueError:
            return raw, True
    if locale == NumericLocale.DECIMAL_POINT.value:
        try:
            return float(raw.strip()), False
        except ValueError:
            return raw, True
    return raw, False


def _convert_field_date(
    raw: str, declared_format: str | None, resolved_format: str | None = None
) -> tuple[str | None, bool]:
    """A RESOLVED format always wins over a merely-declared one (D-10-06):
    the resolution is derived from the column's own evidence (or a human's
    answer), while the declaration is only ever a claim.

    `resolved_format == date_order.EXCEL_SERIAL_MARKER` converts through
    `date_order.iso_from_excel_serial` (never a hand-rolled epoch formula);
    `None` back from that call flags the field and keeps the raw string --
    never a crash, never a silent `None`. Any other non-`None`
    `resolved_format` converts via `convert_date`. With no resolution at all
    (the default), today's exact D-13 fallback applies unchanged: a declared
    `date_format` converts; no declared format passes through verbatim and
    flags -- a field-set-level decision, not a per-value one.
    """
    if resolved_format == date_order.EXCEL_SERIAL_MARKER:
        iso = date_order.iso_from_excel_serial(raw)
        return (iso if iso is not None else raw), iso is None
    if resolved_format is not None:
        iso, needs_confirmation, _reason = convert_date(raw, resolved_format)
        return (iso if iso is not None else raw), needs_confirmation
    if declared_format is None:
        return raw, True
    iso, needs_confirmation, _reason = convert_date(raw, declared_format)
    return (iso if iso is not None else raw), needs_confirmation


def _unit_mismatch(raw: str, target_field: Field) -> bool:
    """D-12: the field's declared unit is never enforced by rewriting the
    value -- only checked. A mismatch flags the field; the cell itself is
    never touched here (see `_convert_by_type`, the only function that ever
    changes `value`).

    The comparison is only meaningful where the cell *is* the unit token, as
    in `assay-potency.yaml`'s `unit` field. On a numeric field, `unit:`
    declares what the number is measured in (`auc`, `ng*h/mL`), so the cell
    can never equal it and comparing the two would flag every row of a clean
    file. Cross-checking a number against a unit carried in some *other*
    column is the Phase 3 validator's job, not this function's.
    """
    if target_field.type not in (None, "text"):
        return False
    return target_field.unit is not None and raw.strip() != target_field.unit
