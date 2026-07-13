"""EXPORT-02/03/04: CSV/xlsx/JSON writers + the provenance manifest builder
(D-09/D-15). Every writer takes only a `canonical.CanonicalTable` -- never
re-derives records from a `RawTable`/`MappingProposal` -- and Unicode unit
symbols (µM, %) must survive every format (ensure_ascii=False throughout).
"""

from __future__ import annotations

import csv
import json

import openpyxl

from assayingest.canonical import SOURCE_SHEET_COLUMN, CanonicalTable
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.export.writers import build_manifest, write_csv, write_json, write_xlsx
from assayingest.fields.models import Field, FieldSet


def _tidy() -> CanonicalTable:
    return CanonicalTable(
        field_names=["compound_id", "value", "unit"],
        records=[
            {"compound_id": "NVS-1", "value": 12.5, "unit": "µM"},
            {"compound_id": "NVS-2", "value": None, "unit": "%"},
        ],
        flagged=[],
    )


def _tidy_with_sources(sheet: str = "Week 1") -> CanonicalTable:
    """The same table, plus SHEET-03 row provenance (`record_sources` is
    parallel to `records`, never a key inside one)."""
    base = _tidy()
    return CanonicalTable(
        field_names=base.field_names,
        records=base.records,
        flagged=base.flagged,
        record_sources=[sheet] * len(base.records),
    )


# --- write_csv (EXPORT-02) --------------------------------------------------


def test_write_csv_header_row_is_field_names_and_none_becomes_empty_string(tmp_path):
    path = tmp_path / "out.csv"
    write_csv(_tidy(), path)

    with path.open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))

    assert rows[0] == ["compound_id", "value", "unit"]
    assert rows[1] == ["NVS-1", "12.5", "µM"]
    assert rows[2] == ["NVS-2", "", "%"]  # None -> "" automatically


# --- write_xlsx (EXPORT-02, first openpyxl WRITE use in this project) ------


def test_write_xlsx_is_reopenable_with_field_names_header_and_record_values(tmp_path):
    path = tmp_path / "out.xlsx"
    write_xlsx(_tidy(), path)

    workbook = openpyxl.load_workbook(path)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))

    assert rows[0] == ("compound_id", "value", "unit")
    assert rows[1] == ("NVS-1", 12.5, "µM")
    assert rows[2] == ("NVS-2", None, "%")


# --- write_json (EXPORT-03) --------------------------------------------------


def test_write_json_is_exactly_the_records_array_with_unicode_preserved(tmp_path):
    path = tmp_path / "out.json"
    write_json(_tidy(), path)

    raw = path.read_text(encoding="utf-8")
    assert "µM" in raw  # ensure_ascii=False -- not escaped to µM
    assert json.loads(raw) == _tidy().records


# --- build_manifest (EXPORT-04, D-09) ---------------------------------------


def _field_set() -> FieldSet:
    return FieldSet(fields=(Field(name="compound_id"), Field(name="value", type="number")))


def _proposal() -> MappingProposal:
    return MappingProposal(
        source_columns=["cmpd", "val"],
        field_mappings=[
            FieldMapping(
                target_field="compound_id", source_column="cmpd", confidence=1.0,
                reasoning="exact", needs_confirmation=False,
            ),
            FieldMapping(
                target_field="value", source_column="val", confidence=0.8,
                reasoning="likely", needs_confirmation=True,
            ),
        ],
    )


def test_build_manifest_shares_the_saved_profile_shape_plus_provenance_strictness_and_exported_at():
    field_set = _field_set()
    proposal = _proposal()

    manifest = build_manifest(
        field_set, ["cmpd", "val"], proposal, provenance="fresh-claude", strictness="strict"
    )

    assert manifest["field_set_signature"] == field_set.signature
    assert manifest["column_signature"]  # a real hash, non-empty
    assert manifest["provenance"] == "fresh-claude"
    assert manifest["strictness"] == "strict"
    assert manifest["exported_at"]  # ISO-8601 string present

    by_field = {m["target_field"]: m for m in manifest["field_mappings"]}
    assert by_field["compound_id"]["source_column_normalised"] == "cmpd"
    assert by_field["compound_id"]["confidence"] == 1.0
    assert by_field["compound_id"]["confirmed"] is True
    assert by_field["value"]["confidence"] == 0.8
    assert by_field["value"]["confirmed"] is False


def test_build_manifest_records_auto_applied_provenance_given_an_auto_applied_proposal():
    manifest = build_manifest(
        _field_set(), ["cmpd", "val"], _proposal(),
        provenance="auto-applied-from-profile", strictness="strict",
    )
    assert manifest["provenance"] == "auto-applied-from-profile"


def test_build_manifest_is_json_serialisable_with_unicode_preserved():
    field_set = FieldSet(fields=(Field(name="unit", allowed_values=("µM", "nM")),))
    proposal = MappingProposal(
        source_columns=["u"],
        field_mappings=[
            FieldMapping(
                target_field="unit", source_column=None, confidence=0.9,
                reasoning="inferred", needs_confirmation=False, inferred_value="µM",
            )
        ],
    )
    manifest = build_manifest(
        field_set, ["u"], proposal, provenance="fresh-claude", strictness="strict"
    )
    rendered = json.dumps(manifest, ensure_ascii=False)
    assert "µM" in rendered


# --- SHEET-03: the reserved __source_sheet column, threaded per writer -------
#
# The trap this section exists to close (D-11-14): an extra key smuggled into
# `records` behaves THREE different ways -- `write_csv`'s `DictWriter` RAISES,
# `write_xlsx` SILENTLY DROPS it (`record.get(name)`), and `write_json` keeps
# it. So each writer must opt in deliberately, and each must stay byte-
# identical when there is no provenance to write.


def test_write_csv_appends_the_reserved_source_sheet_column_and_does_not_raise(tmp_path):
    """The loud failure mode, pinned explicitly: `csv.DictWriter` raises a
    `ValueError` on a record key absent from `fieldnames`. If the provenance
    were ever smuggled into `records`, THIS is the test that would catch it."""
    path = tmp_path / "out.csv"
    write_csv(_tidy_with_sources(), path)  # must not raise

    with path.open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))

    assert rows[0] == ["compound_id", "value", "unit", SOURCE_SHEET_COLUMN]
    assert rows[1] == ["NVS-1", "12.5", "µM", "Week 1"]
    assert rows[2] == ["NVS-2", "", "%", "Week 1"]  # None -> "" still automatic


def test_write_csv_without_record_sources_is_byte_identical_to_today(tmp_path):
    path = tmp_path / "out.csv"
    write_csv(_tidy(), path)

    with path.open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))

    assert rows[0] == ["compound_id", "value", "unit"]  # nothing extra
    assert all(SOURCE_SHEET_COLUMN not in row for row in rows)


def test_write_xlsx_carries_the_source_sheet_in_its_header_row_and_every_row(tmp_path):
    """`write_xlsx` reads `record.get(name)` per field name, so an extra key
    in `records` would be SILENTLY DROPPED -- the quiet failure mode."""
    path = tmp_path / "out.xlsx"
    write_xlsx(_tidy_with_sources(), path)

    rows = list(openpyxl.load_workbook(path).active.iter_rows(values_only=True))

    assert rows[0] == ("compound_id", "value", "unit", SOURCE_SHEET_COLUMN)
    assert rows[1] == ("NVS-1", 12.5, "µM", "Week 1")
    assert rows[2] == ("NVS-2", None, "%", "Week 1")


def test_write_xlsx_without_record_sources_is_byte_identical_to_today(tmp_path):
    path = tmp_path / "out.xlsx"
    write_xlsx(_tidy(), path)

    rows = list(openpyxl.load_workbook(path).active.iter_rows(values_only=True))

    assert rows[0] == ("compound_id", "value", "unit")
    assert rows[1] == ("NVS-1", 12.5, "µM")


def test_write_json_emits_the_source_sheet_on_every_record_with_unicode_intact(tmp_path):
    path = tmp_path / "out.json"
    write_json(_tidy_with_sources(), path)

    raw = path.read_text(encoding="utf-8")
    assert "µM" in raw  # ensure_ascii=False survives the extra column
    records = json.loads(raw)
    assert [r[SOURCE_SHEET_COLUMN] for r in records] == ["Week 1", "Week 1"]
    assert records[0]["compound_id"] == "NVS-1"


def test_write_json_without_record_sources_is_exactly_the_records_array(tmp_path):
    path = tmp_path / "out.json"
    write_json(_tidy(), path)

    assert json.loads(path.read_text(encoding="utf-8")) == _tidy().records


def test_build_manifest_records_the_source_sheet_and_defaults_it_to_none():
    manifest = build_manifest(
        _field_set(), ["cmpd", "val"], _proposal(),
        provenance="fresh-claude", strictness="strict", source_sheet="Week 1",
    )
    assert manifest["source_sheet"] == "Week 1"

    without = build_manifest(
        _field_set(), ["cmpd", "val"], _proposal(),
        provenance="fresh-claude", strictness="strict",
    )
    assert without["source_sheet"] is None
