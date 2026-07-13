"""The structural verdict contract — what a sheet's layout IS, as pure types
(SHAPE-03, D-12-13).

Pure module: no I/O, no `pandas`, no `openpyxl`, no `anthropic` import —
every consumer works from plain frozen dataclasses, so this module is fully
testable without a file on disk (the same purity contract
`structure/shape.py` states, inherited deliberately).

The phase's rule, as a type: the verdict carries INDICES into a grid that
Python reads; it can never carry a value (D-12-03/D-12-10). Every field is
an `int`, a `bool`, a `float`, an enum member, a tuple of blocks, or the
free-text `reasoning` a curator checks the verdict against. There is no
field a transcribed cell value could occupy — "the model never writes a
value" is enforced by the shape of the contract, not by a promise
(`tests/test_structure_layout.py` pins this with a type-shape guard).

This module holds types only — no thresholds, no homogeneity math, nothing
corpus-tuned. The judgment that fills these types is Claude's (a later plan);
the transform that consumes them is `structure/unpivot.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: The confidence below which a verdict must be confirmed by a human — the
#: same 0.9 line D-12-17's "confidently wrong" bar draws. The server sets
#: the gate; the client only renders it (12-UI-SPEC Discretion §1).
_CONFIRMATION_BAR = 0.9


class LayoutKind(str, Enum):
    """The layouts a worksheet can be judged as — the parse gate's vocabulary.

    Only `ROW_PER_RECORD` and `KEY_VALUE` ever produce a `RawTable`:
    `row_per_record` is read the ordinary way (header row, one record per
    row), and `key_value` is un-pivoted deterministically by Python per the
    confirmed `SheetLayout`. Every other member is a reason to ask, never to
    read: `wide_matrix` and `multiple_tables` name layouts v1 does not
    reshape, `not_a_table` names a banner/chart/notes sheet with nothing to
    ingest, and `unknown` is the honest fail-closed answer — no verdict, or
    a verdict the tool cannot trust, always asks the human (D-12-16).
    """

    ROW_PER_RECORD = "row_per_record"
    KEY_VALUE = "key_value"
    WIDE_MATRIX = "wide_matrix"
    MULTIPLE_TABLES = "multiple_tables"
    NOT_A_TABLE = "not_a_table"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class KeyValueBlock:
    """One label/value block of a key-value sheet. Indices are 0-based into
    the RAW grid; `first_row`/`last_row` are inclusive.

    A tuple of these lives on `SheetLayout` because one record routinely
    spans SEVERAL side-by-side blocks (both driving sheets of the phase carry
    two — labels in column 0 and again in column 3/4), so a single
    `label_column: int` verdict is wrong on the very first file (D-12-13).
    `value_columns` is itself a tuple: several value columns under one label
    column is the transposed layout, one record per value column.
    """

    label_column: int
    value_columns: tuple[int, ...]
    first_row: int
    last_row: int


@dataclass(frozen=True)
class SheetLayout:
    """The structural verdict for one worksheet (D-12-13, copied verbatim
    from 12-CONTEXT).

    `header_row_index`/`first_data_row`/`last_data_row` are meaningful for
    `ROW_PER_RECORD` only (the row range is what makes a real table followed
    by trailing prose ingestible); `key_value_blocks` and
    `one_record_per_value_column` are meaningful for `KEY_VALUE` only.
    `reasoning` is deliberately the ONLY free-text field — a curator must be
    able to check the verdict, and nothing else may carry a transcribed cell.
    """

    kind: LayoutKind
    confidence: float
    reasoning: str
    header_row_index: int | None = None
    first_data_row: int | None = None
    last_data_row: int | None = None
    key_value_blocks: tuple[KeyValueBlock, ...] = ()
    #: False ⇒ every block contributes COLUMNS to ONE record; True ⇒ each
    #: value column is its own record (the transposed melt, D-12-13).
    one_record_per_value_column: bool = False

    @property
    def needs_confirmation(self) -> bool:
        """True when the verdict is not confident enough to act on unasked."""
        return self.confidence < _CONFIRMATION_BAR

    @property
    def record_count(self) -> int | None:
        """How many records a KEY_VALUE layout yields — `None` otherwise
        (a row-per-record table's row count is not the layout's to know)."""
        if self.kind is not LayoutKind.KEY_VALUE:
            return None
        if self.one_record_per_value_column:
            return sum(len(block.value_columns) for block in self.key_value_blocks)
        return 1
