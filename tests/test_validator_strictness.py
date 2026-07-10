"""D-11: configurable strictness (fail-closed default) + validator_note
rendered in the CLI review (VAL-03/SC3).

Strict (default) scans every row; lenient relaxes row COVERAGE only -- an
in-scope violation the sample DOES see is still a full objection, never a
softened one (RESEARCH Assumption A1). Signature matching (D-02) is never
touched by strictness -- this module must not import the learning/signature
package at all.
"""

from __future__ import annotations

import inspect

import pytest

from assayingest import cli
from assayingest.domain.models import ColumnCandidate, FieldMapping, MappingProposal
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.table import RawTable
from assayingest.validation import validator as validator_module
from assayingest.validation.validator import validate


def _table(headers: list[str], rows: list[list[str]], locales: list[str] | None = None) -> RawTable:
    return RawTable(
        headers=headers,
        rows=rows,
        source_name="fixture.csv",
        column_locales=locales or [],
    )


def _mapping(target_field: str, source_column: str | None) -> FieldMapping:
    return FieldMapping(
        target_field=target_field,
        source_column=source_column,
        confidence=1.0,
        reasoning="test fixture",
        needs_confirmation=False,
    )


def _proposal(mappings: list[FieldMapping]) -> MappingProposal:
    return MappingProposal(source_columns=[], field_mappings=mappings)


_ALLOWED_H = FieldSet(fields=(Field(name="flag", type="text", allowed_values=("H",)),))


# --- strict default scans every row ------------------------------------------


def test_strict_default_scans_every_row_including_a_late_violation():
    rows = [["H"]] * 6 + [["X"]] + [["H"]]  # violation at row index 6, past a 6-row sample
    table = _table(headers=["Flag"], rows=rows)
    proposal = _proposal([_mapping("flag", "Flag")])

    result = validate(table, proposal, _ALLOWED_H)  # default strictness

    assert result.field_mappings[0].needs_confirmation is True


# --- lenient relaxes coverage only, never severity (RESEARCH A1) ------------


def test_lenient_only_samples_early_rows_and_misses_a_late_violation():
    rows = [["H"]] * 6 + [["X"]]
    table = _table(headers=["Flag"], rows=rows)
    proposal = _proposal([_mapping("flag", "Flag")])

    result = validate(table, proposal, _ALLOWED_H, strictness="lenient")

    assert result.field_mappings[0].needs_confirmation is False


def test_lenient_still_fully_objects_to_a_violation_within_its_sample():
    rows = [["X"]] + [["H"]] * 6
    table = _table(headers=["Flag"], rows=rows)
    proposal = _proposal([_mapping("flag", "Flag")])

    strict_result = validate(table, proposal, _ALLOWED_H, strictness="strict")
    lenient_result = validate(table, proposal, _ALLOWED_H, strictness="lenient")

    assert strict_result.field_mappings[0].needs_confirmation is True
    # Coverage differs; the severity of an in-scope objection never does.
    assert lenient_result.field_mappings[0].needs_confirmation is True


# --- invalid strictness value ------------------------------------------------


def test_invalid_strictness_raises_a_consequence_describing_value_error():
    table = _table(headers=["Flag"], rows=[["H"]])
    proposal = _proposal([_mapping("flag", "Flag")])

    with pytest.raises(ValueError, match="strictness"):
        validate(table, proposal, _ALLOWED_H, strictness="loose")


# --- signature matching is never touched by strictness (D-11) --------------


def test_validator_module_never_imports_the_learning_signature_package():
    source = inspect.getsource(validator_module)
    assert "learning" not in source


# --- render: validator_note surfaces alongside Claude's reasoning (VAL-03) --


def _rendered_mapping(*, needs_confirmation: bool, validator_note: str | None) -> FieldMapping:
    return FieldMapping(
        target_field="flag",
        source_column="Flag",
        confidence=0.5 if needs_confirmation else 1.0,
        reasoning="claude's own reasoning",
        needs_confirmation=needs_confirmation,
        validator_note=validator_note,
        alternatives=[ColumnCandidate(source_column="Other", confidence=0.3)]
        if needs_confirmation
        else [],
    )


def test_render_field_shows_validator_note_for_a_yellow_field():
    mapping = _rendered_mapping(
        needs_confirmation=True,
        validator_note="'X' is not one of the allowed values (H)",
    )

    rendered = cli._render_field(mapping)

    assert "reason: claude's own reasoning" in rendered
    assert "validator_note: 'X' is not one of the allowed values (H)" in rendered
    assert "options:" in rendered  # unrelated existing detail must survive


def test_render_field_shows_validator_note_for_a_clear_field_too():
    mapping = _rendered_mapping(
        needs_confirmation=False,
        validator_note="no declared constraints to check",
    )

    rendered = cli._render_field(mapping)

    assert "validator_note: no declared constraints to check" in rendered


def test_render_field_omits_the_validator_note_line_when_none_is_set():
    mapping = _rendered_mapping(needs_confirmation=False, validator_note=None)

    rendered = cli._render_field(mapping)

    assert "validator_note:" not in rendered
