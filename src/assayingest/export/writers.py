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

from ..canonical import CanonicalTable
from ..domain.models import FieldMapping, MappingProposal
from ..fields.models import FieldSet
from ..learning.reconstruct import stored_mapping_from
from ..learning.signature import column_signature


def write_csv(tidy: CanonicalTable, path: Path) -> None:
    """EXPORT-02: header row = field names; `csv.DictWriter` writes a
    missing/`None` cell as an empty string automatically -- no manual
    coercion needed."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=tidy.field_names)
        writer.writeheader()
        writer.writerows(tidy.records)


def write_xlsx(tidy: CanonicalTable, path: Path) -> None:
    """EXPORT-02: first row = field names, one row per record in field
    order -- the project's first `openpyxl` WRITE use (it has only ever
    read Excel until this phase)."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(tidy.field_names)
    for record in tidy.records:
        sheet.append([record.get(name) for name in tidy.field_names])
    workbook.save(path)


def write_json(tidy: CanonicalTable, path: Path) -> None:
    """EXPORT-03: exactly `tidy.records`, `ensure_ascii=False` so a unit
    symbol like µM survives unescaped (T-03-12)."""
    path.write_text(
        json.dumps(tidy.records, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def build_manifest(
    field_set: FieldSet,
    headers: list[str],
    proposal: MappingProposal,
    *,
    provenance: str,
    strictness: str,
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
    """
    return {
        "field_set_signature": field_set.signature,
        "column_signature": column_signature(headers),
        "field_mappings": [_manifest_field(m, headers) for m in proposal.field_mappings],
        "provenance": provenance,
        "strictness": strictness,
        "exported_at": datetime.now(UTC).isoformat(),
    }


def _manifest_field(mapping: FieldMapping, headers: list[str]) -> dict:
    """Base dict + extra keys idiom (mirrors `cli.py::_field_to_dict`):
    `StoredFieldMapping.to_dict()` (the learning loop's save-time shape) is
    the base; `confidence`/`confirmed` are the two keys a stored profile
    never needs (it is only ever saved fully clear) but an export manifest
    always must."""
    stored = stored_mapping_from(mapping, headers)
    base = stored.to_dict()
    base["confidence"] = mapping.confidence
    base["confirmed"] = not mapping.needs_confirmation
    return base
