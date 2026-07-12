"""INGEST-04 (D-10-04..08): `service.resolve_date_formats` -- the always-runs,
pure-Python date-order resolver that sits between the mapping stage and the
existing `validate()` call. No API key, no network call: every scenario here
is built directly as `RawTable`/`MappingProposal`/`FieldSet` fixtures, the
same idiom `tests/test_reconcile_service.py` establishes for the service
seam.

Every concrete date value used here is read from a real fixture quoted in
10-RESEARCH.md's "verified ambiguity examples" section (independently
cross-checked against `tests/test_date_order.py`, 10-01's own classifier
tests), never invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from assayingest import service
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.structure.date_order import EXCEL_SERIAL_MARKER, DateOrder
from assayingest.parsing.table import RawTable
from assayingest.validation.validator import validate

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"
HELIXBIO = DATA / "helixbio_export.csv"


def _table(headers: list[str], rows: list[list[str]]) -> RawTable:
    return RawTable(headers=headers, rows=rows, source_name="fixture.csv")


def _mapping(target_field: str, source_column: str | None) -> FieldMapping:
    return FieldMapping(
        target_field=target_field, source_column=source_column, confidence=1.0,
        reasoning="fixture", needs_confirmation=False,
    )


def _proposal(*mappings: FieldMapping) -> MappingProposal:
    return MappingProposal(
        source_columns=[m.source_column for m in mappings if m.source_column],
        field_mappings=list(mappings),
    )


# --- the decision table, one test per row ------------------------------------


def test_unambiguous_no_declared_format_resolves_to_the_detected_format():
    # data/synthetic/pinnacle_labs_export.csv, column "Date" -- "13" proves DAY_FIRST.
    table = _table(["Date"], [["01/01/2025"], ["13/01/2025"], ["14/01/2025"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal(_mapping("assay_date", "Date"))

    resolution = service.resolve_date_formats(table, proposal, field_set)

    assert resolution.formats["assay_date"] == "%d/%m/%Y"
    assert resolution.contradictions == {}
    assert resolution.question.has_conflicts is False


def test_unambiguous_with_a_declared_format_that_agrees_resolves_to_the_detected_format():
    table = _table(["Date"], [["01/01/2025"], ["13/01/2025"], ["14/01/2025"]])
    field_set = FieldSet(
        fields=(Field(name="assay_date", type="date", date_format="%d/%m/%Y"),)
    )
    proposal = _proposal(_mapping("assay_date", "Date"))

    resolution = service.resolve_date_formats(table, proposal, field_set)

    assert resolution.formats["assay_date"] == "%d/%m/%Y"
    assert resolution.contradictions == {}
    assert resolution.question.has_conflicts is False


def test_ambiguous_no_declared_format_raises_a_conflict_naming_everything():
    # data/synthetic/helixbio_export.csv, column "Experiment Date" -- genuinely ambiguous.
    table = _table(
        ["Experiment Date"],
        [["03/11/2025"], ["03/11/2025"], ["04/11/2025"], ["05/11/2025"]],
    )
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal(_mapping("assay_date", "Experiment Date"))

    resolution = service.resolve_date_formats(table, proposal, field_set)

    assert "assay_date" not in resolution.formats
    assert resolution.question.has_conflicts is True
    conflict = resolution.question.conflicts[0]
    assert conflict.target_field == "assay_date"
    assert conflict.source_column == "Experiment Date"
    assert conflict.day_first_format == "%d/%m/%Y"
    assert conflict.month_first_format == "%m/%d/%Y"
    assert conflict.example_values
    assert conflict.ambiguous_row_count > 0


def test_ambiguous_with_a_declared_format_trusts_the_declaration_and_raises_no_question():
    """The asymmetry this test pins explicitly: an ambiguous column has no
    independent evidence to contradict a declaration, so the declaration is
    trusted rather than re-asked -- do NOT "fix" this into always-asking,
    which would nag the curator on a file they already declared correctly."""
    table = _table(["Experiment Date"], [["03/11/2025"], ["04/11/2025"]])
    field_set = FieldSet(
        fields=(Field(name="assay_date", type="date", date_format="%d/%m/%Y"),)
    )
    proposal = _proposal(_mapping("assay_date", "Experiment Date"))

    resolution = service.resolve_date_formats(table, proposal, field_set)

    assert resolution.formats["assay_date"] == "%d/%m/%Y"
    assert resolution.question.has_conflicts is False
    assert resolution.contradictions == {}


def test_unambiguous_evidence_contradicting_a_declared_format_yields_a_contradiction_not_an_override():
    # Every value parses cleanly under its own (correct) %d/%m/%Y format --
    # implied_order of the wrongly-declared %m/%d/%Y provably disagrees with
    # the column's own DAY_FIRST proof (mirrors test_date_order.py's own
    # "dangerous" test).
    table = _table(["Date"], [["03/04/2025"], ["05/06/2025"], ["21/07/2025"]])
    field_set = FieldSet(
        fields=(Field(name="assay_date", type="date", date_format="%m/%d/%Y"),)
    )
    proposal = _proposal(_mapping("assay_date", "Date"))

    resolution = service.resolve_date_formats(table, proposal, field_set)

    assert "assay_date" not in resolution.formats
    assert resolution.contradictions["assay_date"]
    assert resolution.question.has_conflicts is False


def test_excel_serial_column_resolves_to_the_marker_regardless_of_declaration():
    table = _table(["Collection Date"], [["46092"], ["46093"]])
    field_set = FieldSet(
        fields=(Field(name="assay_date", type="date", date_format="%d/%m/%Y"),)
    )
    proposal = _proposal(_mapping("assay_date", "Collection Date"))

    resolution = service.resolve_date_formats(table, proposal, field_set)

    assert resolution.formats["assay_date"] == EXCEL_SERIAL_MARKER
    assert resolution.question.has_conflicts is False


def test_non_date_column_mapped_to_a_date_field_yields_no_resolution_and_the_validator_flags_it():
    table = _table(["Gene"], [["EGFR"], ["JAK2"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal(_mapping("assay_date", "Gene"))

    resolution = service.resolve_date_formats(table, proposal, field_set)

    assert resolution.formats == {}
    assert resolution.contradictions == {}
    assert resolution.question.has_conflicts is False

    validated = validate(
        table, proposal, field_set,
        date_formats=resolution.formats, date_contradictions=resolution.contradictions,
    )
    assert validated.field_mappings[0].needs_confirmation is True


def test_unmapped_date_field_is_skipped_entirely_with_no_crash():
    table = _table(["Other"], [["x"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal(
        FieldMapping(
            target_field="assay_date", source_column=None, confidence=0.0,
            reasoning="no column matched", needs_confirmation=True,
        )
    )

    resolution = service.resolve_date_formats(table, proposal, field_set)

    assert resolution.formats == {}
    assert resolution.question.has_conflicts is False


def test_a_non_date_typed_field_is_never_touched():
    table = _table(["Compound"], [["EGFR-1"]])
    field_set = FieldSet(fields=(Field(name="compound_id", type="text"),))
    proposal = _proposal(_mapping("compound_id", "Compound"))

    resolution = service.resolve_date_formats(table, proposal, field_set)

    assert resolution.formats == {}
    assert resolution.question.has_conflicts is False


# --- human answers (D-10-07) --------------------------------------------------


def test_answered_ambiguous_column_resolves_to_that_columns_own_shape_not_a_hardcoded_format():
    table = _table(["date"], [["1/2/25"], ["2/3/25"], ["3/4/25"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal(_mapping("assay_date", "date"))

    resolution = service.resolve_date_formats(
        table, proposal, field_set, answers={"assay_date": DateOrder.DAY_FIRST},
    )

    assert resolution.formats["assay_date"] == "%d/%m/%y"  # NOT %d/%m/%Y
    assert resolution.question.has_conflicts is False


def test_answers_not_covering_every_ambiguous_column_raises_fail_closed():
    table = _table(["date"], [["1/2/25"], ["2/3/25"], ["3/4/25"]])
    field_set = FieldSet(fields=(Field(name="assay_date", type="date"),))
    proposal = _proposal(_mapping("assay_date", "date"))

    with pytest.raises(service.UnresolvedDateColumnsError) as excinfo:
        service.resolve_date_formats(table, proposal, field_set, answers={})

    assert "assay_date" in str(excinfo.value)


def test_answers_missing_only_one_of_two_ambiguous_columns_still_raises():
    table = _table(
        ["date", "other_date"],
        [["1/2/25", "3/4/25"], ["2/3/25", "5/6/25"]],
    )
    field_set = FieldSet(
        fields=(
            Field(name="assay_date", type="date"),
            Field(name="other_date", type="date"),
        )
    )
    proposal = _proposal(
        _mapping("assay_date", "date"), _mapping("other_date", "other_date")
    )

    with pytest.raises(service.UnresolvedDateColumnsError) as excinfo:
        service.resolve_date_formats(
            table, proposal, field_set, answers={"assay_date": DateOrder.DAY_FIRST},
        )

    assert "other_date" in str(excinfo.value)
    assert "assay_date" not in str(excinfo.value)  # the covered one is not named


# --- THE PRIVACY TEST (D-10-05) -----------------------------------------------


class _FakeParsedItem:
    def __init__(self, target_field: str, source_column: str):
        self.target_field = target_field
        self.source_column = source_column
        self.confidence = 1.0
        self.reasoning = "fake mapper"
        self.needs_confirmation = False
        self.inferred_value = None
        self.alternatives: list = []


class _FakeParsedOutput:
    def __init__(self, field_mappings: list[_FakeParsedItem]):
        self.field_mappings = field_mappings


class _FakeResponse:
    def __init__(self, parsed_output: _FakeParsedOutput):
        self.parsed_output = parsed_output
        self.stop_reason = "end_turn"


class _FakeMessages:
    def __init__(self, captured: dict):
        self._captured = captured

    def parse(self, **kwargs):
        self._captured["content"] = kwargs["messages"][0]["content"]
        return _FakeResponse(
            _FakeParsedOutput(
                [
                    _FakeParsedItem("compound_id", "Compound Name"),
                    _FakeParsedItem("assay_date", "Experiment Date"),
                ]
            )
        )


class _FakeClient:
    def __init__(self, captured: dict):
        self.messages = _FakeMessages(captured)


def test_date_detection_is_identical_under_headers_only(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    field_set = FieldSet(
        fields=(Field(name="compound_id"), Field(name="assay_date", type="date"))
    )

    captured_default: dict = {}
    result_default = service.resolve_or_map(
        str(HELIXBIO), field_set, store=None,
        client=_FakeClient(captured_default), headers_only=False,
    )
    captured_headers_only: dict = {}
    result_headers_only = service.resolve_or_map(
        str(HELIXBIO), field_set, store=None,
        client=_FakeClient(captured_headers_only), headers_only=True,
    )

    # (a) detection is unaffected -- byte-identical DateResolution both ways.
    resolution_default = service.resolve_date_formats(
        result_default.table, result_default.proposal, field_set
    )
    resolution_headers_only = service.resolve_date_formats(
        result_headers_only.table, result_headers_only.proposal, field_set
    )
    assert resolution_default == resolution_headers_only
    assert result_default.date_question == result_headers_only.date_question

    # (b) no cell value ever reaches the outbound request under headers_only.
    assert "03/11/2025" not in captured_headers_only["content"]
    assert "03/11/2025" in captured_default["content"]  # sanity: default path does send values
