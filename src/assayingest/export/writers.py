"""EXPORT-02/03/04: writers that turn the one Phase 2 canonical table into
CSV, `.xlsx`, and JSON on disk, plus the manifest builder every export ships
alongside its data (D-09).

Every writer takes only a `canonical.CanonicalTable` -- none re-derives
records from a `RawTable`/`MappingProposal` directly; that duplication is
exactly what `canonical.assemble()` (D-15) exists to prevent (key_link).
`write_xlsx` is this project's first use of `openpyxl`'s WRITE API -- the
package has only ever been used to *read* Excel until now.

`build_manifest` shares its shape with `learning.profile.LearnedProfile`
(D-09): it reuses `learning.reconstruct.stored_mapping_from`/
`learning.signature.column_signature` -- the identical save-time functions
the learning loop already established -- rather than re-deriving a second,
possibly-drifting notion of "this field's resolved column". `provenance` is
a value the CALLER supplies (the `_resolve_proposal` return value 03-01
already threads through `cli.py`) -- this module never re-detects
auto-applied vs fresh-Claude itself.

JSON output is always `ensure_ascii=False` -- a unit symbol like µM must
survive every export format unescaped (T-03-12).
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import openpyxl

from ..canonical import SOURCE_SHEET_COLUMN, CanonicalTable, value_source
from ..domain.models import FieldMapping, MappingProposal
from ..fields.models import FieldSet
from ..learning.reconstruct import stored_mapping_from
from ..learning.signature import column_signature


def _export_columns(tidy: CanonicalTable) -> list[str]:
    """The columns this table actually exports: the field names, plus the
    reserved provenance column ONLY when there is provenance to write.

    SHEET-03/D-11-14: `record_sources` is a list parallel to `records`, never
    a key inside one, precisely because the three writers below disagree about
    an unexpected record key -- `write_csv`'s `DictWriter` RAISES on it,
    `write_xlsx` SILENTLY DROPS it, `write_json` KEEPS it. So each writer opts
    the column in deliberately, through this one function, and every writer's
    output is byte-identical to its pre-SHEET-03 self when `record_sources` is
    empty (the CLI path, and any assembly with no source sheet).
    """
    if not tidy.record_sources:
        return list(tidy.field_names)
    return [*tidy.field_names, SOURCE_SHEET_COLUMN]


def _rows_with_sources(tidy: CanonicalTable) -> list[dict[str, str | float | None]]:
    """Each record merged with its own source sheet -- a NEW dict per record;
    `tidy.records` is never mutated, so the canonical table stays the one
    unchanged representation every format derives from (D-15)."""
    if not tidy.record_sources:
        return list(tidy.records)
    return [
        {**record, SOURCE_SHEET_COLUMN: source}
        for record, source in zip(tidy.records, tidy.record_sources, strict=True)
    ]


def write_csv(tidy: CanonicalTable, path: Path) -> None:
    """EXPORT-02: header row = field names (+ the reserved `__source_sheet`
    when SHEET-03 provenance is present); `csv.DictWriter` writes a
    missing/`None` cell as an empty string automatically -- no manual
    coercion needed."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_export_columns(tidy))
        writer.writeheader()
        writer.writerows(_rows_with_sources(tidy))


def write_xlsx(tidy: CanonicalTable, path: Path) -> None:
    """EXPORT-02: first row = field names (+ the reserved `__source_sheet`
    when SHEET-03 provenance is present), one row per record in column
    order -- the project's first `openpyxl` WRITE use (it has only ever
    read Excel until this phase)."""
    columns = _export_columns(tidy)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(columns)
    for record in _rows_with_sources(tidy):
        sheet.append([record.get(name) for name in columns])
    workbook.save(path)


def write_json(tidy: CanonicalTable, path: Path) -> None:
    """EXPORT-03: exactly `tidy.records` (each carrying its reserved
    `__source_sheet` when SHEET-03 provenance is present),
    `ensure_ascii=False` so a unit symbol like µM survives unescaped
    (T-03-12)."""
    path.write_text(
        json.dumps(_rows_with_sources(tidy), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def build_manifest(
    field_set: FieldSet,
    headers: list[str],
    proposal: MappingProposal,
    *,
    provenance: str,
    strictness: str,
    confirmed_by: str | None = None,
    source_sheet: str | None = None,
) -> dict:
    """EXPORT-04/D-09: a manifest sharing `LearnedProfile.to_dict()`'s shape
    (field set signature, column signature, field->source mapping) plus the
    per-field confidence/confirmed flags a saved profile itself never
    carries (a profile is only ever saved once fully clear -- D-06 -- so it
    has no yellow field to describe), and `provenance`/`strictness`/
    `exported_at` on top.

    `provenance` is a value the caller supplies, never re-derived here --
    `cli.py::_resolve_proposal` already returns "auto-applied-from-profile"
    or "fresh-claude" per table (03-01), and this function's whole point is
    to record that decision, not repeat it.

    `confirmed_by` (AUTH-04) is the authenticated curator's email on the API
    confirm path, or `None` on the CLI path (which has no signed-in user) --
    the identity is always supplied by the caller from a server-resolved
    `User`, never read from a client body (T-06-07).

    `source_sheet` (SHEET-03, keyword-only, defaulted `None`) is the worksheet
    (or, for a sheet-less CSV, the uploaded file) every exported row came
    from -- the same value the data files carry in their reserved
    `__source_sheet` column. `service.export` reads it off the very
    `CanonicalTable` the writers wrote, never re-derives it, so the audit
    trail cannot claim one source while the data ships another (the discipline
    `value_source` already enforces for the column-vs-inference question).
    """
    return {
        "field_set_signature": field_set.signature,
        "column_signature": column_signature(headers),
        "field_mappings": [_manifest_field(m, headers) for m in proposal.field_mappings],
        "provenance": provenance,
        "strictness": strictness,
        "confirmed_by": confirmed_by,
        "source_sheet": source_sheet,
        "exported_at": datetime.now(UTC).isoformat(),
    }


def _manifest_field(mapping: FieldMapping, headers: list[str]) -> dict:
    """Base dict + extra keys idiom (mirrors `cli.py::_field_to_dict`):
    `StoredFieldMapping.to_dict()` (the learning loop's save-time shape) is
    the base; `confidence`/`confirmed` are the two keys a stored profile
    never needs (it is only ever saved fully clear) but an export manifest
    always must.

    `value_source` is the audit answer to "did the FILE contain this value, or
    did Claude infer it and a human accept it?" (MAP-02/D-02b). It is read from
    `canonical.value_source` -- the same function `canonical.assemble` uses to
    decide which input actually lands -- so the manifest can never claim a
    value came from a column while the exported data carries the inference, or
    vice versa. A mapping carrying both a `source_column` and an
    `inferred_value` reports `column`: that is the one that was written.
    """
    stored = stored_mapping_from(mapping, headers)
    base = stored.to_dict()
    base["confidence"] = mapping.confidence
    base["confirmed"] = not mapping.needs_confirmation
    base["value_source"] = value_source(mapping)
    return base
