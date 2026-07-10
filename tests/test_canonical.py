"""EXPORT-01: the canonical tidy-table assembly — decimal-comma fixed, dates
ISO only with a declared format, units recorded but never converted.

These run without an API key: `assemble` is pure Python, consuming a
`RawTable` + `MappingProposal` + `FieldSet` built directly as fixtures, the
same "no file I/O, no live Claude call" idiom `test_mapper_boundary.py` uses.
"""

from assayingest.canonical import CanonicalTable, assemble, convert_date, convert_decimal_comma
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.table import RawTable


def _table(headers: list[str], rows: list[list[str]], locales: list[str] | None = None) -> RawTable:
    return RawTable(
        headers=headers,
        rows=rows,
        source_name="fixture.csv",
        column_locales=locales or [],
    )


def _proposal(mapped: dict[str, str]) -> MappingProposal:
    """One clear (needs_confirmation=False) mapping per `{field_name: source_column}` pair."""
    return MappingProposal(
        source_columns=list(mapped.values()),
        field_mappings=[
            FieldMapping(
                target_field=name,
                source_column=column,
                confidence=1.0,
                reasoning="test fixture",
                needs_confirmation=False,
            )
            for name, column in mapped.items()
        ],
    )


# --- convert_decimal_comma (D-14) -------------------------------------------


def test_convert_decimal_comma_matches_the_real_corpus_and_the_missing_synthetic_cases():
    # Real corpus values (pinnacle_labs_export.csv / helix_genomics_DE.xlsx).
    assert convert_decimal_comma("11,076") == 11.076
    assert convert_decimal_comma("446,2") == 446.2
    assert convert_decimal_comma("654,85") == 654.85
    assert convert_decimal_comma("14,771") == 14.771
    # Not present in the corpus, per 02-RESEARCH.md: European thousands+decimal
    # and a negative value.
    assert convert_decimal_comma("1.234,56") == 1234.56
    assert convert_decimal_comma("-5,2") == -5.2


# --- convert_date (D-13) ----------------------------------------------------


def test_convert_date_parses_a_declared_format_to_iso():
    assert convert_date("03/11/2025", "%d/%m/%Y") == ("2025-11-03", False, None)


def test_convert_date_flags_rather_than_raises_on_an_invalid_day():
    iso, needs_confirmation, reason = convert_date("32/01/2025", "%d/%m/%Y")
    assert iso is None
    assert needs_confirmation is True
    assert "32/01/2025" in reason
    assert "%d/%m/%Y" in reason


def test_convert_date_flags_an_excel_native_datetime_string_rather_than_raising():
    # openpyxl reads a real Excel date cell back as a datetime; RawTable's
    # str(cell) shape is "2025-01-01 00:00:00" -- must not crash the run.
    iso, needs_confirmation, reason = convert_date("2025-01-01 00:00:00", "%d/%m/%Y")
    assert iso is None
    assert needs_confirmation is True
    assert reason is not None


# --- assemble: decimal-comma conversion (D-14) ------------------------------


def test_assemble_converts_a_decimal_comma_number_column():
    table = _table(
        headers=["Compound", "Value"],
        rows=[["PIN-010", "11,076"]],
        locales=["non_numeric", "decimal_comma"],
    )
    field_set = FieldSet(
        fields=(Field(name="compound_id", type="text"), Field(name="value", type="number"))
    )
    proposal = _proposal({"compound_id": "Compound", "value": "Value"})

    result = assemble(table, proposal, field_set)

    assert isinstance(result, CanonicalTable)
    assert result.records[0]["value"] == 11.076
    assert "value" not in result.flagged


# --- assemble: unit is recorded verbatim, never converted (D-12) -----------


def test_assemble_records_the_unit_verbatim_and_flags_a_declared_mismatch():
    table = _table(headers=["Unit"], rows=[["µM"]])
    field_set = FieldSet(fields=(Field(name="unit", type="text", unit="nM"),))
    proposal = _proposal({"unit": "Unit"})

    result = assemble(table, proposal, field_set)

    # Recording µM as nM would multiply every value by 1000 -- never rewrite it.
    assert result.records[0]["unit"] == "µM"
    assert "unit" in result.flagged


def test_assemble_does_not_flag_a_unit_that_matches_the_declared_unit():
    table = _table(headers=["Unit"], rows=[["nM"]])
    field_set = FieldSet(fields=(Field(name="unit", type="text", unit="nM"),))
    proposal = _proposal({"unit": "Unit"})

    result = assemble(table, proposal, field_set)

    assert result.records[0]["unit"] == "nM"
    assert "unit" not in result.flagged


# --- assemble: non_numeric locale is never silently converted (Pitfall 4) --


def test_assemble_forces_a_flag_on_a_non_numeric_column_mapped_to_a_number_field():
    table = _table(headers=["Value"], rows=[["not-a-number"]], locales=["non_numeric"])
    field_set = FieldSet(fields=(Field(name="value", type="number"),))
    proposal = _proposal({"value": "Value"})

    result = assemble(table, proposal, field_set)

    assert result.records[0]["value"] == "not-a-number"  # never handed to float()
    assert "value" in result.flagged


# --- assemble: dates only convert with a declared date_format (D-13) -------


def test_assemble_passes_a_date_through_verbatim_and_flags_when_no_format_declared():
    table = _table(headers=["Date"], rows=[["01/01/2025"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal({"assay_date": "Date"})

    result = assemble(table, proposal, field_set)

    assert result.records[0]["assay_date"] == "01/01/2025"
    assert "assay_date" in result.flagged


def test_assemble_converts_a_date_field_with_a_declared_format():
    table = _table(headers=["Date"], rows=[["03/11/2025"]])
    field_set = FieldSet(
        fields=(Field(name="assay_date", type="date", date_format="%d/%m/%Y"),)
    )
    proposal = _proposal({"assay_date": "Date"})

    result = assemble(table, proposal, field_set)

    assert result.records[0]["assay_date"] == "2025-11-03"
    assert "assay_date" not in result.flagged


# --- assemble: never raises, ever (Pitfall 4/5) -----------------------------


def test_assemble_never_raises_on_a_malformed_date_and_a_non_numeric_row():
    table = _table(
        headers=["Date", "Value"],
        rows=[["32/01/2025", "abc"]],
        locales=["non_numeric", "non_numeric"],
    )
    field_set = FieldSet(
        fields=(
            Field(name="assay_date", type="date", date_format="%d/%m/%Y"),
            Field(name="value", type="number"),
        )
    )
    proposal = _proposal({"assay_date": "Date", "value": "Value"})

    result = assemble(table, proposal, field_set)  # must not raise

    assert "assay_date" in result.flagged
    assert "value" in result.flagged


# --- assemble: one canonical record per source row (D-15) ------------------


def test_assemble_produces_one_record_per_source_row_keyed_by_field_names():
    table = _table(
        headers=["Compound", "Value"],
        rows=[
            ["PIN-010", "11,076"],
            ["PIN-011", "28,775"],
            ["PIN-012", "32,378"],
        ],
        locales=["non_numeric", "decimal_comma"],
    )
    field_set = FieldSet(
        fields=(Field(name="compound_id", type="text"), Field(name="value", type="number"))
    )
    proposal = _proposal({"compound_id": "Compound", "value": "Value"})

    result = assemble(table, proposal, field_set)
    serialised = result.to_dict()

    assert len(serialised["records"]) == 3
    assert all(set(r.keys()) == {"compound_id", "value"} for r in serialised["records"])
    assert serialised["records"][0]["value"] == 11.076
    assert serialised["records"][1]["value"] == 28.775
