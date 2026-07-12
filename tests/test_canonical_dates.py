"""INGEST-04 (D-10-06): `canonical.assemble()`/`validation.validator.validate()`
gain a keyword-only, defaulted `date_formats`/`date_contradictions` override so
a RESOLVED format (detected from a column's own evidence, or chosen by a
human) wins over a merely-declared one — the declaration is a human claim to
be checked, never unconditional permission to convert (D-10-06 supersedes
D-13). Every existing call site keeps today's exact behavior when the new
kwargs are omitted; that backward compatibility is pinned explicitly below,
not merely assumed.

Built directly as fixtures, the same "no file I/O, no live Claude call" idiom
`test_canonical.py`/`test_validator.py` use.
"""

from __future__ import annotations

from assayingest.canonical import CanonicalTable, assemble
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.structure.date_order import EXCEL_SERIAL_MARKER
from assayingest.parsing.table import RawTable
from assayingest.validation.validator import validate


def _table(headers: list[str], rows: list[list[str]], locales: list[str] | None = None) -> RawTable:
    return RawTable(headers=headers, rows=rows, source_name="fixture.csv", column_locales=locales or [])


def _proposal(mapped: dict[str, str]) -> MappingProposal:
    return MappingProposal(
        source_columns=list(mapped.values()),
        field_mappings=[
            FieldMapping(
                target_field=name, source_column=column, confidence=1.0,
                reasoning="test fixture", needs_confirmation=False,
            )
            for name, column in mapped.items()
        ],
    )


# --- canonical.assemble: the resolved-format override (D-10-06) -------------


def test_assemble_resolved_format_converts_even_with_no_declared_format():
    table = _table(headers=["Date"], rows=[["21/07/2025"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal({"assay_date": "Date"})

    result = assemble(table, proposal, field_set, date_formats={"assay_date": "%d/%m/%Y"})

    assert isinstance(result, CanonicalTable)
    assert result.records[0]["assay_date"] == "2025-07-21"
    assert "assay_date" not in result.flagged


def test_assemble_excel_serial_marker_converts_a_bare_serial():
    # data/synthetic/lab_corpus/wild/10_genelab_date_disaster.xlsx, row 6 --
    # the exact serial 10-01's own test_iso_from_excel_serial_converts_a_real_serial
    # asserts converts to "2026-03-11".
    table = _table(headers=["Collection Date"], rows=[["46092"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal({"assay_date": "Collection Date"})

    result = assemble(
        table, proposal, field_set, date_formats={"assay_date": EXCEL_SERIAL_MARKER}
    )

    assert result.records[0]["assay_date"] == "2026-03-11"
    assert "assay_date" not in result.flagged


def test_assemble_excel_serial_marker_flags_and_falls_back_to_the_raw_string_on_a_non_serial():
    table = _table(headers=["Collection Date"], rows=[["not-a-serial"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal({"assay_date": "Collection Date"})

    result = assemble(
        table, proposal, field_set, date_formats={"assay_date": EXCEL_SERIAL_MARKER}
    )

    assert result.records[0]["assay_date"] == "not-a-serial"  # never None, never a crash
    assert "assay_date" in result.flagged


def test_assemble_resolved_format_wins_over_a_wrongly_declared_format():
    # Declared %m/%d/%Y is wrong for this column; the resolved override
    # (derived from the column's own evidence) is the correct %d/%m/%Y and
    # must win -- the declaration is only a claim (D-10-06).
    table = _table(headers=["Date"], rows=[["21/07/2025"]])
    field_set = FieldSet(
        fields=(Field(name="assay_date", type="date", date_format="%m/%d/%Y"),)
    )
    proposal = _proposal({"assay_date": "Date"})

    result = assemble(table, proposal, field_set, date_formats={"assay_date": "%d/%m/%Y"})

    assert result.records[0]["assay_date"] == "2025-07-21"
    assert "assay_date" not in result.flagged


def test_assemble_with_no_date_formats_kwarg_is_byte_identical_to_todays_behavior():
    """BACKWARD COMPATIBILITY: the exact case from
    tests/test_canonical.py::test_assemble_passes_a_date_through_verbatim_and_flags_when_no_format_declared.
    No `date_formats` argument at all -- not even `None` explicitly -- must
    produce the identical result today's callers already depend on."""
    table = _table(headers=["Date"], rows=[["01/01/2025"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal({"assay_date": "Date"})

    result = assemble(table, proposal, field_set)

    assert result.records[0]["assay_date"] == "01/01/2025"
    assert "assay_date" in result.flagged


def test_assemble_with_no_date_formats_kwarg_still_honours_a_declared_format():
    """BACKWARD COMPATIBILITY: the exact case from
    tests/test_canonical.py::test_assemble_converts_a_date_field_with_a_declared_format."""
    table = _table(headers=["Date"], rows=[["03/11/2025"]])
    field_set = FieldSet(
        fields=(Field(name="assay_date", type="date", date_format="%d/%m/%Y"),)
    )
    proposal = _proposal({"assay_date": "Date"})

    result = assemble(table, proposal, field_set)

    assert result.records[0]["assay_date"] == "2025-11-03"
    assert "assay_date" not in result.flagged


# --- validation.validator.validate: date_contradictions (D-10-06) -----------


def test_validate_flags_a_contradicted_declared_format_with_an_actionable_note():
    table = _table(headers=["Date"], rows=[["21/07/2025"]])
    field_set = FieldSet(
        fields=(Field(name="assay_date", type="date", date_format="%m/%d/%Y"),)
    )
    proposal = _proposal({"assay_date": "Date"})

    result = validate(
        table, proposal, field_set,
        date_contradictions={"assay_date": "21/07/2025"},
    )

    mapping = result.field_mappings[0]
    assert mapping.needs_confirmation is True
    note = mapping.validator_note or ""
    assert "%m/%d/%Y" in note  # names the declared format
    assert "21/07/2025" in note  # names a contradicting value
    assert "Schemas page" in note  # the UI-SPEC's exact copy shape


def test_a_cleanly_parsing_but_wrong_order_declared_format_still_flags():
    """The load-bearing test this task exists to prove: every row parses
    cleanly under the WRONGLY declared format (`%m/%d/%Y` never raises on
    any of these values), yet the field must still be flagged because the
    column's own independent evidence (a component > 12) proves DAY_FIRST,
    contradicting the declaration. A bare parse-failure scan would miss
    this entirely (10-RESEARCH.md Pitfall 3 / D-10-06)."""
    from datetime import datetime

    values = ["03/04/2025", "05/06/2025", "21/07/2025"]
    for value in values:
        datetime.strptime(value, "%m/%d/%Y")  # must not raise -- proves the danger

    table = _table(headers=["Date"], rows=[[v] for v in values])
    field_set = FieldSet(
        fields=(Field(name="assay_date", type="date", date_format="%m/%d/%Y"),)
    )
    proposal = _proposal({"assay_date": "Date"})

    result = validate(
        table, proposal, field_set,
        date_contradictions={"assay_date": "21/07/2025"},
    )

    mapping = result.field_mappings[0]
    assert mapping.needs_confirmation is True
    assert "%m/%d/%Y" in (mapping.validator_note or "")


def test_date_formats_override_reaches_validate_and_clears_the_no_format_flag():
    table = _table(headers=["Date"], rows=[["21/07/2025"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal({"assay_date": "Date"})

    result = validate(
        table, proposal, field_set,
        date_formats={"assay_date": "%d/%m/%Y"},
    )

    mapping = result.field_mappings[0]
    assert mapping.needs_confirmation is False


def test_contradiction_objection_is_additive_with_another_violation():
    """A field already amber for another reason (allowed_values) stays amber
    when a date contradiction ALSO applies, and its note carries BOTH
    objections, semicolon-joined -- matching `_validate_mapping`'s existing
    additive-only convention (`_apply_objection` may only ever OR in a
    `True`, never clear one)."""
    table = _table(headers=["Date"], rows=[["21/07/2025"]])
    field_set = FieldSet(
        fields=(
            Field(
                name="assay_date", type="date", date_format="%m/%d/%Y",
                allowed_values=("only-this-value",),
            ),
        )
    )
    proposal = _proposal({"assay_date": "Date"})

    result = validate(
        table, proposal, field_set,
        date_contradictions={"assay_date": "21/07/2025"},
    )

    mapping = result.field_mappings[0]
    assert mapping.needs_confirmation is True
    note = mapping.validator_note or ""
    assert "Schemas page" in note  # the contradiction objection
    assert "not one of the allowed values" in note  # the allowed_values objection
    assert "; " in note  # semicolon-joined, both present


def test_validate_with_neither_new_kwarg_is_byte_identical_to_todays_behavior():
    """BACKWARD COMPATIBILITY: the exact case from
    tests/test_validator.py::test_a_date_field_without_a_declared_format_gets_an_actionable_note
    (`tests/test_validator.py:197`) -- this is the Phase-4 UAT trap the
    original note exists to prevent, and it must keep passing unmodified."""
    table = _table(headers=["Date"], rows=[["2025-01-15"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date", date_format=None),))
    proposal = _proposal({"assay_date": "Date"})

    result = validate(table, proposal, field_set)

    mapping = result.field_mappings[0]
    assert mapping.needs_confirmation is True
    note = mapping.validator_note or ""
    assert "date_format" in note
    assert "definition" in note


def test_validate_with_neither_new_kwarg_still_flags_a_declared_format_mismatch():
    """BACKWARD COMPATIBILITY: the exact case from
    tests/test_validator.py::test_a_date_format_mismatch_flagged_by_canonical_forces_confirmation."""
    table = _table(headers=["Date"], rows=[["32/01/2025"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date", date_format="%d/%m/%Y"),))
    proposal = _proposal({"assay_date": "Date"})

    result = validate(table, proposal, field_set)

    assert result.field_mappings[0].needs_confirmation is True
