"""A confirmed `inferred_value` must reach the exported data (MAP-02, D-02b).

The cardinal sin this file exists to prevent: the human sees `unit ->
(inferred) nM` on the Review screen, clicks Accept, the gate passes -- and the
exported `unit` column comes out empty. What the human confirmed and what the
tool saved were not the same thing, and nothing said so.

Written test-first (TDD RED). Every test here is pure Python: no API key, no
live Claude call -- the same `RawTable`/`FieldSet` fixture idiom
`test_canonical.py` established.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime

import openpyxl
import pytest

from assayingest import canonical, service
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.export.writers import build_manifest
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.profile import LearnedProfile
from assayingest.learning.reconstruct import reconstruct_proposal, stored_mapping_from
from assayingest.learning.signature import column_signature
from assayingest.parsing.table import RawTable

_POTENCY = FieldSet(
    name="assay-potency",
    fields=(
        Field(name="value", type="number", min=0.0, max=1000.0),
        Field(name="unit", type="text", allowed_values=("µM", "nM", "%")),
    ),
)


def _table(headers: list[str], rows: list[list[str]], locales: list[str] | None = None) -> RawTable:
    return RawTable(
        headers=headers,
        rows=rows,
        source_name="cascade.xlsx",
        column_locales=locales or [],
    )


def _clear(target_field: str, source_column: str | None, inferred: str | None = None) -> FieldMapping:
    return FieldMapping(
        target_field=target_field,
        source_column=source_column,
        confidence=0.9,
        reasoning="test fixture",
        needs_confirmation=False,
        inferred_value=inferred,
    )


# --- the reproduction (MAP-02) ----------------------------------------------


def test_confirm_lands_the_confirmed_inferred_value_on_every_record():
    """The file has no unit column; Claude inferred 'nM' from the value range
    and the human accepted it. That value is a fact about the whole file, so it
    belongs on EVERY row -- never `None`."""
    table = _table(["potency"], [["507.735"], ["163.2"]])
    result = service.confirm(
        table,
        [_clear("value", "potency"), _clear("unit", None, inferred="nM")],
        _POTENCY,
    )

    assert [r["unit"] for r in result.tidy.records] == ["nM", "nM"]


def test_an_inferred_value_goes_through_the_same_type_conversion_as_a_cell():
    """An inferred '3' on an `integer` field lands as the int 3 -- an inferred
    value is not a raw passthrough that skips the conversion pipeline."""
    field_set = FieldSet(
        name="replicates",
        fields=(Field(name="n_replicates", type="integer", min=1.0, max=10.0),),
    )
    table = _table(["cmpd"], [["NVS-1"], ["NVS-2"]])
    result = service.confirm(
        table, [_clear("n_replicates", None, inferred="3")], field_set
    )

    assert [r["n_replicates"] for r in result.tidy.records] == [3, 3]
    assert all(isinstance(r["n_replicates"], int) for r in result.tidy.records)


def test_a_field_with_neither_a_column_nor_an_inferred_value_stays_none():
    """Unchanged behavior: nothing to read and nothing confirmed means None,
    never an invented value."""
    field_set = FieldSet(
        name="optional",
        fields=(Field(name="value", type="number"), Field(name="note", required=False)),
    )
    table = _table(["potency"], [["5.0"]])
    result = service.confirm(
        table, [_clear("value", "potency"), _clear("note", None)], field_set
    )

    assert result.tidy.records[0]["note"] is None


# --- precedence: a real column is evidence, an inference is a guess ----------


def test_a_source_column_wins_over_an_inferred_value_on_the_same_field():
    """A field can never have BOTH reach the export. The column is evidence the
    file actually contains; the inference is a guess about it -- so the column
    wins, at every stage (assembly and manifest alike)."""
    table = _table(["potency", "units"], [["507.735", "µM"]])
    result = service.confirm(
        table,
        [_clear("value", "potency"), _clear("unit", "units", inferred="nM")],
        _POTENCY,
    )

    assert result.tidy.records[0]["unit"] == "µM"
    by_field = {m["target_field"]: m for m in result.manifest["field_mappings"]}
    assert by_field["unit"]["value_source"] == canonical.COLUMN


def test_value_source_is_the_one_place_precedence_is_decided():
    assert canonical.value_source(_clear("unit", "units", inferred="nM")) == canonical.COLUMN
    assert canonical.value_source(_clear("unit", None, inferred="nM")) == canonical.INFERRED
    assert canonical.value_source(_clear("unit", None)) == canonical.ABSENT


# --- provenance in the audit manifest (EXPORT-04/D-09) ----------------------


def test_the_manifest_tells_an_auditor_which_values_claude_invented():
    """An auditor must be able to tell a value the file CONTAINED from a value
    Claude INFERRED and a human accepted."""
    table = _table(["potency"], [["507.735"]])
    proposal = MappingProposal(
        source_columns=table.headers,
        field_mappings=[_clear("value", "potency"), _clear("unit", None, inferred="nM")],
    )
    manifest = build_manifest(
        _POTENCY, table.headers, proposal, provenance="fresh-claude", strictness="strict"
    )

    by_field = {m["target_field"]: m for m in manifest["field_mappings"]}
    assert by_field["value"]["value_source"] == canonical.COLUMN
    assert by_field["unit"]["value_source"] == canonical.INFERRED
    assert by_field["unit"]["inferred_value"] == "nM"


# --- every export format (EXPORT-02/03) -------------------------------------


def test_the_inferred_value_reaches_csv_xlsx_and_json(tmp_path):
    table = _table(["potency"], [["507.735"], ["163.2"]])
    result = service.confirm(
        table,
        [_clear("value", "potency"), _clear("unit", None, inferred="nM")],
        _POTENCY,
    )
    manifest = service.export(
        tmp_path, table, _POTENCY, result.proposal, result.tidy,
        provenance="fresh-claude", strictness="strict",
    )

    with (tmp_path / "export.csv").open(encoding="utf-8") as fh:
        assert [row["unit"] for row in csv.DictReader(fh)] == ["nM", "nM"]

    sheet = openpyxl.load_workbook(tmp_path / "export.xlsx").active
    assert [row[1] for row in sheet.iter_rows(min_row=2, values_only=True)] == ["nM", "nM"]

    records = json.loads((tmp_path / "export.json").read_text(encoding="utf-8"))
    assert [r["unit"] for r in records] == ["nM", "nM"]

    by_field = {m["target_field"]: m for m in manifest["field_mappings"]}
    assert by_field["unit"]["value_source"] == canonical.INFERRED


# --- the learning loop (LEARN-02/03) ----------------------------------------


def test_a_saved_profile_reproduces_the_inferred_value_on_the_next_file():
    """A profile learned from a confirm whose field was inferred carries that
    value, and re-applying it to the next file with the same column signature
    reproduces it in the assembled data -- never silently drops it, and never
    presents it as a value read from the new file."""
    first = _table(["potency"], [["507.735"]])
    confirmed = MappingProposal(
        source_columns=first.headers,
        field_mappings=[_clear("value", "potency"), _clear("unit", None, inferred="nM")],
    )
    profile = LearnedProfile(
        profile_id="p1",
        field_set_signature=_POTENCY.signature,
        column_signature=column_signature(first.headers),
        field_mappings=tuple(
            stored_mapping_from(m, first.headers) for m in confirmed.field_mappings
        ),
        structural_hint=None,
        created_at=datetime.now(UTC).isoformat(),
    )

    second = _table(["Potency"], [["901.0"], ["45.5"]])
    replayed = reconstruct_proposal(profile, second.headers)
    tidy = canonical.assemble(second, replayed, _POTENCY)

    assert [r["unit"] for r in tidy.records] == ["nM", "nM"]
    unit = next(m for m in replayed.field_mappings if m.target_field == "unit")
    assert unit.inferred_value == "nM"
    # Never mistakable for a value this file actually contained.
    assert "inferred" in unit.reasoning.lower()


@pytest.mark.parametrize("inferred", ["uM", "1500"])
def test_a_constraint_violating_inferred_value_never_reaches_the_export(inferred):
    """VAL-01 is not regressed by making the value land: an inferred ASCII 'uM'
    against an allowed set of µM/nM/%, or an out-of-bounds number, still blocks
    the confirm."""
    field_set = FieldSet(
        name="assay-potency",
        fields=(
            Field(name="value", type="number", min=0.0, max=1000.0),
            Field(name="unit", type="text", allowed_values=("µM", "nM", "%")),
        ),
    )
    target = "unit" if inferred == "uM" else "value"
    table = _table(["potency"], [["507.735"]])
    mappings = [
        _clear("value", "potency" if target == "unit" else None, inferred=None if target == "unit" else inferred),
        _clear("unit", None, inferred=inferred if target == "unit" else "nM"),
    ]

    with pytest.raises(service.NotReadyError):
        service.confirm(table, mappings, field_set)
