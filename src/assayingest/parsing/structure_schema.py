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

from pydantic import BaseModel, Field

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
