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
import re
from datetime import UTC, datetime
from pathlib import Path

import openpyxl

from ..canonical import ABSENT, SOURCE_SHEET_COLUMN, CanonicalTable, value_source
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
    source_file: str | None = None,
    schema_name: str | None = None,
    vendor: str | None = None,
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
        # WHAT this is and WHERE it came from, first -- a manifest a curator
        # cannot trace back to a file, a table, a Schema and a person is an audit
        # trail with no audit in it. `source_sheet` alone was all this carried,
        # and on a workbook whose one worksheet holds four tables that named the
        # sheet for all four: the rows said `Lab Results` and nothing said WHICH.
        "source_file": source_file,
        "source_sheet": source_sheet,
        "schema_name": schema_name,
        "vendor": vendor,
        "confirmed_by": confirmed_by,
        "exported_at": datetime.now(UTC).isoformat(),
        "provenance": provenance,
        "strictness": strictness,
        "field_set_signature": field_set.signature,
        "column_signature": column_signature(headers),
        "field_mappings": [_manifest_field(m, headers) for m in proposal.field_mappings],
        "fields_absent_from_source": _fields_absent_from_source(proposal),
        "columns_not_in_schema": _columns_not_in_schema(headers, proposal),
        "source_columns": list(headers),
    }


def _fields_absent_from_source(proposal: MappingProposal) -> list[str]:
    """The schema fields the source file had NO column for — the file-level fact
    that a bare `null` in a record cannot express.

    In the exported data, a field with no column and a field whose cell happened
    to be empty BOTH read as `null`, and for clinical data those are not the same
    claim: "this measurement was never taken" is not "it was taken and the value
    is missing". The difference is a property of the FILE, identical for every
    row — so it is recorded ONCE, here, and not smuggled into each record where
    it would be repeated N times and still be ambiguous.

    Reading the two together is exact: a field named here was never in the file;
    a `null` under any OTHER field is a genuinely empty cell. `value_source` is
    the same function `assemble()` uses to decide what actually lands, so the
    manifest cannot claim a field was absent while the data carries a value for
    it (a field Claude inferred and a human accepted reports `inferred`, not
    `absent`, and is deliberately NOT listed here — it is in the file's data even
    though it was in no column).
    """
    return [
        mapping.target_field
        for mapping in proposal.field_mappings
        if value_source(mapping) == ABSENT
    ]


def _columns_not_in_schema(headers: list[str], proposal: MappingProposal) -> list[str]:
    """The source columns NO field claimed — data the curator brought that this
    export does not carry.

    The more dangerous half of a mismatch, and until now the silent one: a
    missing field leaves a visible hole in the output, while an unclaimed column
    is simply dropped, and nothing in the audit trail said it had ever been
    there. Anyone reconciling the export against the original file can now see
    exactly what was left behind, instead of having to diff the two by hand.

    Blank headers are excluded: an unnamed column is not one a reader could act
    on, and listing `""` would be noise, not provenance.
    """
    claimed = {m.source_column for m in proposal.field_mappings if m.source_column is not None}
    return [header for header in headers if header.strip() and header not in claimed]


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


#: Everything a filename may hold. Anything else — a slash, a colon, an em-dash,
#: a space — becomes a hyphen, so a vendor's or a worksheet's own punctuation can
#: never reach the filesystem or a Content-Disposition header as itself.
_SLUG_DISALLOWED = re.compile(r"[^a-z0-9]+")


def _slug(text: str | None) -> str:
    return "" if not text else _SLUG_DISALLOWED.sub("-", text.lower()).strip("-")


def export_basename(manifest: dict) -> str:
    """What to CALL this dataset's files, built from the manifest that describes
    them: vendor, source file, worksheet, and — when the worksheet held several —
    the table within it.

    `export.csv` was the name of every dataset's every file. Four tables of one
    workbook produced four `export.csv`s, and a curator downloading them one at a
    time got `export.csv`, `export (1).csv`, `export (2).csv` in their Downloads
    folder, with nothing on the outside of any of them saying which lab, which
    file, or which panel it held. A file whose identity lives only inside it is a
    file that will be filed under the wrong thing.

    Derived from the manifest rather than passed in, so the name and the audit
    trail cannot disagree: whatever the manifest claims this data IS, is what the
    file is called.
    """
    source_file = manifest.get("source_file") or ""
    source_sheet = manifest.get("source_sheet") or ""
    # A CSV has no worksheets, so its "sheet" IS the file (`service.describe_csv`
    # names it so). Repeating it would spell the same word twice.
    sheet = "" if source_sheet == source_file else _slug(source_sheet)
    parts = [_slug(manifest.get("vendor")), _slug(Path(source_file).stem), sheet]
    return "__".join(part for part in parts if part) or "export"
