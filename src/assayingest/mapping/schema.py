"""Wire models — the exact JSON shape Claude is constrained to return.

These Pydantic models live at the infrastructure boundary. They mirror the API
response, not the domain: the mapper validates Claude's output against them and
then maps them onto the domain `MappingProposal`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TargetFieldName = Literal[
    "compound_id",
    "assay_type",
    "value",
    "unit",
    "target",
    "n_replicates",
    "assay_date",
]


class WireCandidate(BaseModel):
    """One ranked alternative column for an ambiguous field."""

    source_column: str = Field(description="A source header that could match.")
    confidence: float = Field(description="0.0-1.0 confidence for this option.")


class WireFieldMapping(BaseModel):
    """Claude's proposed resolution of a single target field."""

    target_field: TargetFieldName
    source_column: str | None = Field(
        description="Matching source header verbatim, or null if no column matches."
    )
    confidence: float = Field(description="0.0-1.0 confidence in this mapping.")
    reasoning: str = Field(
        description="Short justification a curator can read, in plain English."
    )
    needs_confirmation: bool = Field(
        description=(
            "True whenever a human must confirm before this field is trusted: "
            "missing/inferred value, ambiguity, or confidence below certainty."
        )
    )
    inferred_value: str | None = Field(
        default=None,
        description=(
            "A value inferred when no column exists (e.g. unit inferred from the "
            "value range). Null when a source_column supplies the value."
        ),
    )
    alternatives: list[WireCandidate] = Field(
        default_factory=list,
        description="2-3 ranked options when the column is ambiguous; else empty.",
    )


class WireMappingProposal(BaseModel):
    """The complete proposed mapping — one entry per target field."""

    field_mappings: list[WireFieldMapping]