"""SHEET-03/D-11-12: the canonical table carries a per-row source WITHOUT
`source_sheet` ever becoming a `Field` in the `FieldSet`.

The load-bearing reason (D-11-13): a `source_sheet` field would change
`FieldSet.signature`, and EVERY previously learned profile would silently
stop matching — the learning loop, the product's differentiator, would
quietly break. It would also make the validator and the mapper treat a
bookkeeping column as a target field to map and validate.

So the provenance travels as a PARALLEL LIST (`CanonicalTable.record_sources`),
never as a key inside `records`. That is also what keeps `write_csv` working:
its `DictWriter` RAISES on a record key absent from `fieldnames` (D-11-14),
so an extra key smuggled into `records` would blow up the CSV export.

Mirrors `tests/test_canonical.py`'s fixture idiom (pure Python, no API key).
"""

from __future__ import annotations

from assayingest.canonical import SOURCE_SHEET_COLUMN, assemble
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.table import RawTable


def _table() -> RawTable:
    return RawTable(
        headers=["cmpd", "potency"],
        rows=[["NVS-1", "12.5"], ["NVS-2", "34.0"]],
        source_name="fixture.xlsx",
        column_locales=["non_numeric", "decimal_point"],
    )


def _field_set() -> FieldSet:
    return FieldSet(fields=(Field(name="compound_id"), Field(name="value", type="number")))


def _proposal() -> MappingProposal:
    return MappingProposal(
        source_columns=["cmpd", "potency"],
        field_mappings=[
            FieldMapping(
                target_field="compound_id", source_column="cmpd", confidence=1.0,
                reasoning="test fixture", needs_confirmation=False,
            ),
            FieldMapping(
                target_field="value", source_column="potency", confidence=1.0,
                reasoning="test fixture", needs_confirmation=False,
            ),
        ],
    )


# --- the reserved column name -----------------------------------------------


def test_source_sheet_column_is_reserved_and_cannot_collide_with_a_field_name():
    """A leading double underscore is not a name any canonical field carries
    (a field name is a curator's own header-ish label), so the meta column
    can never shadow a real field."""
    assert SOURCE_SHEET_COLUMN == "__source_sheet"
    assert SOURCE_SHEET_COLUMN.startswith("__")
    assert SOURCE_SHEET_COLUMN not in _field_set().field_names


# --- the CLI/validator path: omitting source_sheet changes NOTHING -----------


def test_assemble_without_source_sheet_records_no_sources_and_identical_records():
    """The keyword is defaulted precisely so the two untouched call sites
    (`cli.py`, `validation/validator.py`) keep today's exact behaviour."""
    tidy = assemble(_table(), _proposal(), _field_set())

    assert tidy.record_sources == []
    assert tidy.records == [
        {"compound_id": "NVS-1", "value": 12.5},
        {"compound_id": "NVS-2", "value": 34.0},
    ]


# --- with a source_sheet: one entry per record, parallel to `records` --------


def test_assemble_with_source_sheet_fills_one_source_per_record():
    tidy = assemble(_table(), _proposal(), _field_set(), source_sheet="Week 1")

    assert len(tidy.record_sources) == len(tidy.records)
    assert tidy.record_sources == ["Week 1", "Week 1"]


def test_records_never_gain_a_source_sheet_key_in_either_case():
    """The provenance is a parallel list, NOT a record key (D-11-12/14). An
    extra key inside `records` would make `write_csv`'s `DictWriter` raise
    and `write_xlsx` silently drop it — the three writers must each thread
    the column deliberately instead."""
    with_sheet = assemble(_table(), _proposal(), _field_set(), source_sheet="Week 1")
    without = assemble(_table(), _proposal(), _field_set())

    for tidy in (with_sheet, without):
        for record in tidy.records:
            assert SOURCE_SHEET_COLUMN not in record
        assert SOURCE_SHEET_COLUMN not in tidy.field_names


# --- the validator's behaviour cannot shift ---------------------------------


def test_flagged_is_identical_with_and_without_a_source_sheet():
    """`validation/validator.py` reuses `assemble()` as its type/date engine
    and reads `flagged` off it. If provenance could change what is flagged,
    the gate itself would depend on which sheet a row came from."""
    table = RawTable(
        headers=["cmpd", "potency"],
        rows=[["NVS-1", "not-a-number"]],
        source_name="fixture.xlsx",
        column_locales=["non_numeric", "non_numeric"],
    )

    without = assemble(table, _proposal(), _field_set())
    with_sheet = assemble(table, _proposal(), _field_set(), source_sheet="Week 1")

    assert with_sheet.flagged == without.flagged
    assert with_sheet.records == without.records
