"""Wire models — the exact JSON shape Claude is constrained to return.

These Pydantic models live at the infrastructure boundary. They mirror the API
response, not the domain: the mapper validates Claude's output against them and
then maps them onto the domain `MappingProposal`.

`build_wire_models` builds the per-request pair (`WireFieldMapping`,
`WireMappingProposal`) at runtime from the user's field-set names, using
`pydantic.create_model` with `target_field` typed as `Literal[tuple(names)]`
(D-16). This constrains Claude at the schema level, so it structurally
cannot return a field the user did not declare — a free `str` validated
afterwards would let the model invent names and turn a schema guarantee
into a runtime check. Field names are never sanitised: spaces, the µ sign,
and a leading digit all work unmodified as `Literal` *values* — only
`create_model`'s own keyword arguments (`target_field`, `source_column`,
...) need to be valid identifiers, never the user-supplied strings inside
the `Literal` (RESEARCH.md Pattern 1, verified empirically).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, create_model


class WireCandidate(BaseModel):
    """One ranked alternative column for an ambiguous field."""

    source_column: str = Field(description="A source header that could match.")
    confidence: float = Field(description="0.0-1.0 confidence for this option.")


def build_wire_models(field_names: list[str]) -> type[BaseModel]:
    """Build a per-request `WireMappingProposal` class whose `target_field`
    is a runtime `Literal` over the user's declared field names (D-16/D-17).

    Rebuilt per field set — cheap, since the Anthropic SDK re-derives its
    JSON Schema fresh on every `messages.parse()` call anyway (no cross-call
    schema cache to invalidate). Every wire field name and description
    besides `target_field`'s type is identical to the phase's Day-1 static
    shape (D-17).
    """
    target_field_type = Literal[tuple(field_names)]

    wire_field_mapping = create_model(
        "WireFieldMapping",
        target_field=(target_field_type, ...),
        source_column=(
            str | None,
            Field(
                description="Matching source header verbatim, or null if no column matches."
            ),
        ),
        confidence=(float, Field(description="0.0-1.0 confidence in this mapping.")),
        reasoning=(
            str,
            Field(description="Short justification a curator can read, in plain English."),
        ),
        needs_confirmation=(
            bool,
            Field(
                description=(
                    "True whenever a human must confirm before this field is trusted: "
                    "missing/inferred value, ambiguity, or confidence below certainty."
                )
            ),
        ),
        inferred_value=(
            str | None,
            Field(
                default=None,
                description=(
                    "A value inferred when no column exists (e.g. unit inferred from "
                    "the value range). Null when a source_column supplies the value."
                ),
            ),
        ),
        alternatives=(
            list[WireCandidate],
            Field(
                default_factory=list,
                description="2-3 ranked options when the column is ambiguous; else empty.",
            ),
        ),
    )

    wire_mapping_proposal = create_model(
        "WireMappingProposal",
        field_mappings=(list[wire_field_mapping], ...),
    )
    return wire_mapping_proposal
