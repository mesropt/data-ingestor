"""parsing/structure/layout.py — the pure verdict contract (SHAPE-03, D-12-13).

Written test-first (TDD RED). Two guards here are load-bearing beyond the
usual field checks:

* the purity guard — parametrized over BOTH new pure modules (`layout.py`
  and `unpivot.py`), the Wave-C re-point of
  `tests/test_structure_shape.py::test_classify_shape_module_imports_no_anthropic_or_pandas`,
  written fresh so it exists before the old file dies;
* the type-shape guard — SHAPE-03 as a test: the only `str`-typed field on
  the verdict types is `reasoning`, so the model structurally has nowhere
  to put a transcribed cell value (D-12-03/D-12-10).
"""

from __future__ import annotations

import typing
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from assayingest.parsing.structure.layout import KeyValueBlock, LayoutKind, SheetLayout


def _kv_layout(**overrides) -> SheetLayout:
    base = dict(kind=LayoutKind.KEY_VALUE, confidence=1.0, reasoning="test layout")
    base.update(overrides)
    return SheetLayout(**base)


# --- LayoutKind ---------------------------------------------------------------


def test_layout_kind_has_exactly_the_six_verdict_members():
    assert {member.value for member in LayoutKind} == {
        "row_per_record",
        "key_value",
        "wide_matrix",
        "multiple_tables",
        "not_a_table",
        "unknown",
    }


def test_layout_kind_members_are_strings():
    # str-Enum, same idiom as `TableShape` -- the value IS the wire string.
    assert LayoutKind.KEY_VALUE == "key_value"
    assert LayoutKind.UNKNOWN == "unknown"


# --- KeyValueBlock ------------------------------------------------------------


def test_key_value_block_carries_indices_only():
    block = KeyValueBlock(label_column=0, value_columns=(1,), first_row=1, last_row=10)
    assert block.label_column == 0
    assert block.value_columns == (1,)
    assert block.first_row == 1
    assert block.last_row == 10


def test_key_value_block_is_frozen():
    block = KeyValueBlock(label_column=0, value_columns=(1,), first_row=1, last_row=10)
    with pytest.raises(FrozenInstanceError):
        block.label_column = 3


# --- SheetLayout --------------------------------------------------------------


def test_sheet_layout_defaults_carry_no_dimensions():
    layout = SheetLayout(kind=LayoutKind.UNKNOWN, confidence=0.0, reasoning="no verdict")
    assert layout.header_row_index is None
    assert layout.first_data_row is None
    assert layout.last_data_row is None
    assert layout.key_value_blocks == ()
    assert layout.one_record_per_value_column is False


def test_sheet_layout_is_frozen():
    layout = _kv_layout()
    with pytest.raises(FrozenInstanceError):
        layout.confidence = 0.5


def test_needs_confirmation_below_the_confidently_wrong_bar():
    # 0.9 is D-12-17's "confidently wrong" line: the server sets the gate,
    # the client only renders it.
    assert _kv_layout(confidence=0.89).needs_confirmation is True
    assert _kv_layout(confidence=0.9).needs_confirmation is False
    assert _kv_layout(confidence=0.95).needs_confirmation is False


def test_record_count_is_one_for_a_plain_key_value_sheet():
    layout = _kv_layout(
        key_value_blocks=(
            KeyValueBlock(label_column=0, value_columns=(1,), first_row=7, last_row=12),
            KeyValueBlock(label_column=4, value_columns=(5,), first_row=7, last_row=12),
        ),
    )
    assert layout.record_count == 1


def test_record_count_counts_value_columns_when_one_record_per_value_column():
    layout = _kv_layout(
        key_value_blocks=(
            KeyValueBlock(label_column=0, value_columns=(1,), first_row=0, last_row=4),
            KeyValueBlock(label_column=3, value_columns=(4, 5), first_row=0, last_row=4),
        ),
        one_record_per_value_column=True,
    )
    assert layout.record_count == 3


def test_record_count_is_none_for_non_key_value_kinds():
    # Row count is not the layout's to know for a row-per-record table.
    for kind in (
        LayoutKind.ROW_PER_RECORD,
        LayoutKind.WIDE_MATRIX,
        LayoutKind.MULTIPLE_TABLES,
        LayoutKind.NOT_A_TABLE,
        LayoutKind.UNKNOWN,
    ):
        layout = SheetLayout(kind=kind, confidence=1.0, reasoning="test")
        assert layout.record_count is None, kind


# --- SHAPE-03 as a type: the only str field is `reasoning` ---------------------


def _str_typed_field_names(cls: type) -> set[str]:
    """Field names whose resolved annotation is `str` or a union containing it."""
    hints = typing.get_type_hints(cls)
    flagged = set()
    for field in fields(cls):
        hint = hints[field.name]
        if hint is str or str in typing.get_args(hint):
            flagged.add(field.name)
    return flagged


def test_the_only_str_typed_field_on_the_verdict_is_reasoning():
    # A second free-string field would be a hole where a cell value could be
    # transcribed (12-PATTERNS §1 field-naming rule) -- SHAPE-03 enforced
    # structurally, not by promise.
    assert _str_typed_field_names(SheetLayout) == {"reasoning"}
    assert _str_typed_field_names(KeyValueBlock) == set()


# --- Purity guard (both new pure modules) --------------------------------------


@pytest.mark.parametrize("module_name", ["layout.py", "unpivot.py"])
def test_structure_verdict_modules_import_no_anthropic_pandas_or_openpyxl(module_name):
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "assayingest"
        / "parsing"
        / "structure"
        / module_name
    )
    text = source.read_text()
    import_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    assert not any("anthropic" in line for line in import_lines)
    assert not any("pandas" in line for line in import_lines)
    assert not any("openpyxl" in line for line in import_lines)
