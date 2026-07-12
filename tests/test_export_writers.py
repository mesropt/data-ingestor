"""EXPORT-02/03/04: CSV/xlsx/JSON writers + the provenance manifest builder
(D-09/D-15). Every writer takes only a `canonical.CanonicalTable` -- never
re-derives records from a `RawTable`/`MappingProposal` -- and Unicode unit
symbols (µM, %) must survive every format (ensure_ascii=False throughout).
"""

from __future__ import annotations

import csv
import json

import openpyxl

from assayingest.canonical import CanonicalTable
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
