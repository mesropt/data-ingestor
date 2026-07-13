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

import re
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
class TableBlock:
    """One table WITHIN a sheet that holds several. Indices are 0-based into the
    raw grid; `first_data_row`/`last_data_row` are inclusive.

    A real lab sheet routinely stacks panels down one worksheet — `Electrolytes`,
    `Renal Function`, `Liver Panel` — and each panel brings ITS OWN header row
    with its own column names, in its own order. `Flg` sits in column 2 of the
    first panel and `Unts` sits in column 2 of the second.

    Read as one table, the later header rows arrive as DATA and their words land
    under the first table's columns: the validator's real complaint on
    sequoia_cmp was "column 'Flg': 'Unts' is not one of the allowed values". So a
    sheet is not one table just because its tables touch, and the fences here are
    what let Python read each one on its own terms.
    """

    header_row_index: int
    first_data_row: int
    last_data_row: int
    #: The row of the section heading this table sits under (`Electrolytes`,
    #: `Renal Function`) -- an INDEX, never the words. The judge names the row;
    #: Python reads what is written there. That keeps SHAPE-03 intact: there is
    #: still no field on this contract a transcribed cell could occupy, and the
    #: title the curator sees is the file's own text, typo and all, rather than
    #: the model's recollection of it.
    title_row_index: int | None = None


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
    #: Every table on a MULTIPLE_TABLES sheet, fenced. Empty on a sheet that
    #: holds one table — `header_row_index` and the data fences above already
    #: describe it, and a one-element `tables` would be a second way to say the
    #: same thing. The manifest turns each of these into its OWN entry, so the
    #: human ticks a table exactly as they tick a sheet.
    tables: tuple[TableBlock, ...] = ()

    @classmethod
    def from_dict(cls, data: dict) -> SheetLayout:
        """Rebuild a verdict from its JSON-safe dict (the learning store's
        persisted shape, `StructuralHint.to_dict()`'s inverse for this field).

        JSON has no tuples, so `value_columns` and `key_value_blocks` come
        back as lists and are re-frozen here; `kind` comes back as its wire
        string and is re-anchored to the enum.
        """
        blocks = tuple(
            KeyValueBlock(
                label_column=block["label_column"],
                value_columns=tuple(block["value_columns"]),
                first_row=block["first_row"],
                last_row=block["last_row"],
            )
            for block in data.get("key_value_blocks", ())
        )
        tables = tuple(
            TableBlock(
                header_row_index=table["header_row_index"],
                first_data_row=table["first_data_row"],
                last_data_row=table["last_data_row"],
                title_row_index=table.get("title_row_index"),
            )
            for table in data.get("tables", ())
        )
        return cls(
            kind=LayoutKind(data["kind"]),
            confidence=data["confidence"],
            reasoning=data["reasoning"],
            header_row_index=data.get("header_row_index"),
            first_data_row=data.get("first_data_row"),
            last_data_row=data.get("last_data_row"),
            key_value_blocks=blocks,
            one_record_per_value_column=data.get("one_record_per_value_column", False),
            tables=tables,
        )

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


#: `R10`, `row 10`, `rows 0-4` -- the forms the judge writes a row in. Column
#: references (`C0`, `C0-C4`) are deliberately NOT matched: they are not rows,
#: and a spreadsheet names its columns with letters anyway.
_ROW_SPAN = re.compile(r"\brows\s+(\d+)\s*[-–—]\s*(\d+)", re.IGNORECASE)
_ROW_WORD = re.compile(r"\brow\s+(\d+)", re.IGNORECASE)
_ROW_SHORT = re.compile(r"\bR(\d+)\b")


def in_spreadsheet_rows(reasoning: str) -> str:
    """The judge's reasoning with every row number shifted into the numbering the
    curator's spreadsheet uses.

    The judge counts rows from zero, as the grid it is given does, and as every
    index on `SheetLayout` does. A curator counts from one, because that is what
    Excel puts down the side of their screen. Both are right, and the screen was
    showing BOTH AT ONCE -- "the header is at R10" over a grid whose header row
    Excel calls 11 -- which reads as an off-by-one bug in the tool and destroys
    the one thing the reasoning is for: being checkable against the open file.

    Only the DISPLAY text is renumbered. `header_row_index` and its siblings stay
    zero-based all the way to `parse()`; nothing that reads a cell learns a new
    convention here.
    """
    text = _ROW_SPAN.sub(lambda m: f"rows {int(m[1]) + 1}-{int(m[2]) + 1}", reasoning)
    text = _ROW_WORD.sub(lambda m: f"row {int(m[1]) + 1}", text)
    return _ROW_SHORT.sub(lambda m: f"row {int(m[1]) + 1}", text)
