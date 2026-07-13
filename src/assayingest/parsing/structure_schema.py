"""Wire models — the exact JSON shape Claude is constrained to return for a
structural PROPOSAL.

These Pydantic models live at the infrastructure boundary, mirroring
`mapping/schema.py`'s wire/domain split one layer earlier (D-01 layer 2):
`structure_assist.py` validates Claude's output against them and then maps
the validated model onto `parsing.hint.StructuralHint` at the boundary — the
proposal only ever pre-fills a `StructureQuestion`, it is never applied
(D-02).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, create_model

from .structure.layout import LayoutKind

TableShapeName = Literal[
    "row_per_record",
    "wide_matrix",
    "transposed",
    "multiple_tables",
    "unknown",
]


class WireStructureCandidate(BaseModel):
    """One ranked alternative structural reading Claude considered."""

    header_row_index: int | None = Field(
        default=None,
        description="An alternative header row index (0-based, in the raw grid), or null.",
    )
    sheet_name: str | None = Field(
        default=None, description="An alternative data sheet name, or null."
    )
    confidence: float = Field(description="0.0-1.0 confidence for this alternative.")


class WireStructureProposal(BaseModel):
    """Claude's proposed resolution of a file's unresolved structural question.

    Every dimension is optional except `table_shape`, `confidence`, and
    `reasoning` — a single question (e.g. "which row is the header") only
    needs the one field it asked about filled in; the rest stay null.
    """

    header_row_index: int | None = Field(
        description=(
            "0-based row index (in the raw grid) Claude believes is the real "
            "header row, or null if this question is not about the header."
        )
    )
    sheet_name: str | None = Field(
        description=(
            "The data sheet Claude believes holds the real table, or null if "
            "this question is not about sheet selection."
        )
    )
    table_shape: TableShapeName = Field(
        description=(
            "The detected table shape: row_per_record, wide_matrix, "
            "transposed, multiple_tables, or unknown."
        )
    )
    decimal_separator: str | None = Field(
        default=None,
        description=(
            "The decimal separator ('.' or ',') Claude believes this file "
            "uses, or null if this question is not about numeric locale."
        ),
    )
    data_region: str | None = Field(
        default=None,
        description=(
            "A plain-English description of where the real data region is "
            "(e.g. 'rows 5-20, columns A-G'), or null if not applicable."
        ),
    )
    confidence: float = Field(description="0.0-1.0 confidence in this proposal overall.")
    reasoning: str = Field(
        description="Short justification a curator can read, in plain English."
    )
    alternatives: list[WireStructureCandidate] = Field(
        default_factory=list,
        description=(
            "2-3 ranked alternative readings when the structure is "
            "genuinely ambiguous; else empty."
        ),
    )


#: The layout kinds the judge may answer with — derived from `LayoutKind` at
#: import time so the wire vocabulary can never drift from the domain enum.
_LAYOUT_KIND_NAMES = tuple(kind.value for kind in LayoutKind)


class WireKeyValueBlock(BaseModel):
    """One label/value block of a key-value sheet, as INDICES into the raw
    grid — 0-based, rows inclusive. There is no field a cell value could
    occupy (SHAPE-03): the model names positions, Python reads contents."""

    label_column: int = Field(
        description="0-based column index holding the field-name labels."
    )
    value_columns: list[int] = Field(
        description=(
            "0-based column indices holding the labelled values, in order. "
            "More than one means several value columns share the label column."
        )
    )
    first_row: int = Field(
        description="0-based first grid row of this block, inclusive."
    )
    last_row: int = Field(
        description="0-based last grid row of this block, inclusive."
    )


class WireTableBlock(BaseModel):
    """One table on a sheet that stacks several, as INDICES only — 0-based, rows
    inclusive. Same rule as every other block here: the model names positions,
    Python reads contents."""

    header_row_index: int = Field(
        description="0-based grid row holding THIS table's column headers."
    )
    first_data_row: int = Field(
        description="0-based first data row of this table, inclusive."
    )
    last_data_row: int = Field(
        description=(
            "0-based last data row of this table, inclusive — the row before the "
            "next table's section heading or header row, or the last row of the "
            "sheet for the final table."
        )
    )
    title_row_index: int | None = Field(
        default=None,
        description=(
            "0-based row of the SECTION HEADING this table sits under — the lone "
            "label above its header row that names the panel ('Electrolytes', "
            "'Renal Function', 'Liver Panel'). Null when the table has no such "
            "heading. Give the row INDEX only; never the words in it. Do not use "
            "the sheet's overall title banner here — only the heading of THIS "
            "table."
        ),
    )


def build_workbook_layout_wire_model(sheet_names: list[str]) -> type[BaseModel]:
    """Build a per-request wire model for the batched layout verdict whose
    `sheet_name` is a runtime `Literal` over the workbook's REAL sheet names
    — the same device `schema_ranker.build_ranking_wire_model` uses (D-12-14).

    This is the FIRST of the two closures on the verdict boundary: the model
    structurally cannot answer for a sheet that does not exist, so an
    invented name is a schema violation at the SDK boundary rather than a
    runtime surprise downstream (`_to_domain_verdicts` closes it AGAIN).
    Names are never sanitised — a space, a dash, or a leading digit all work
    unmodified as `Literal` VALUES; only `create_model`'s own keyword
    arguments need to be valid identifiers.

    Every verdict field is a `Literal`, an `int`, a `bool`, a `float`, or a
    block of indices; `reasoning` is deliberately the only free string, so
    the wire model has nowhere to put a transcribed cell value (SHAPE-03).
    """
    wire_sheet_layout = create_model(
        "WireSheetLayout",
        sheet_name=(
            Literal[tuple(sheet_names)],
            Field(description="The name of one of the listed worksheets."),
        ),
        kind=(
            Literal[_LAYOUT_KIND_NAMES],
            Field(
                description=(
                    "How this sheet is laid out. Use 'unknown' whenever you "
                    "cannot justify a reading from the grid — an honest "
                    "'unknown' asks a human; a plausible guess misleads one."
                )
            ),
        ),
        confidence=(
            float,
            Field(description="0.0-1.0 confidence in this sheet's verdict."),
        ),
        reasoning=(
            str,
            Field(
                description=(
                    "Short justification a curator can read, in plain "
                    "English, citing the row and column indices that led "
                    "you to this verdict — never cell contents."
                )
            ),
        ),
        header_row_index=(
            int | None,
            Field(
                description=(
                    "For row_per_record: the 0-based grid row holding the "
                    "column headers, else null."
                )
            ),
        ),
        first_data_row=(
            int | None,
            Field(
                description=(
                    "For row_per_record: the 0-based first data row, else "
                    "null. Use it to exclude leading banner rows."
                )
            ),
        ),
        last_data_row=(
            int | None,
            Field(
                description=(
                    "For row_per_record: the 0-based last data row "
                    "(inclusive), else null. Use it to exclude trailing "
                    "notes below the table."
                )
            ),
        ),
        key_value_blocks=(
            list[WireKeyValueBlock],
            Field(
                description=(
                    "For key_value: every label/value block on the sheet "
                    "(side-by-side blocks belonging to one record are "
                    "separate entries). Empty for every other kind."
                )
            ),
        ),
        tables=(
            list[WireTableBlock],
            Field(
                description=(
                    "For multiple_tables ONLY: every table of records on this "
                    "sheet, in grid order, each fenced by its own header row and "
                    "data rows. A sheet holds several tables when a LATER row "
                    "introduces a DIFFERENT set of column names (a second panel "
                    "with its own header row) — not merely because a section "
                    "heading or a blank row interrupts one table. Empty for "
                    "every other kind."
                )
            ),
        ),
        one_record_per_value_column=(
            bool,
            Field(
                description=(
                    "For key_value: true when each value column is its own "
                    "record (a transposed layout); false when every block "
                    "contributes columns to ONE record."
                )
            ),
        ),
    )
    return create_model(
        "WireWorkbookLayout",
        sheets=(
            list[wire_sheet_layout],
            Field(
                description=(
                    "One layout verdict per listed worksheet. Answer for "
                    "EVERY worksheet — a sheet you cannot judge gets kind "
                    "'unknown', never silence."
                )
            ),
        ),
    )
