"""The mapper agent — Claude proposes a column mapping via structured output.

This is the core of AssayIngest. It hands Claude the raw table and the allowed
vocabulary, constrains the reply to a JSON schema, and maps the validated wire
model onto the domain `MappingProposal`. It never writes anything: it proposes,
a human disposes.
"""

from __future__ import annotations

import anthropic

from ..domain.models import (
    ColumnCandidate,
    FieldMapping,
    MappingProposal,
    TargetField,
)
from ..domain.reference import ALLOWED_UNITS, ASSAY_TYPES, UNIT_VALUE_RANGES
from ..parsing.table import RawTable
from .schema import WireFieldMapping, WireMappingProposal

_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 4096
_SAMPLE_ROWS = 6

_SYSTEM_PROMPT = """\
You are the mapping engine of AssayIngest, a tool that ingests assay result \
files from contract research organisations (CROs). Every lab formats its file \
differently. Your job is to map the source columns onto a fixed set of target \
fields and report how confident you are in each mapping.

Target fields (produce exactly one entry per field):
- compound_id: the tested compound's identifier
- assay_type: one of IC50, EC50, Ki, Kd, %inhibition (normalise the label)
- value: the numeric measurement
- unit: one of µM, nM, %
- target: the biological target (e.g. EGFR, JAK2, MET)
- n_replicates: number of replicates
- assay_date: the date the assay was run

Three non-negotiable rules:
1. Propose, never write. You only return a proposal with per-field confidence.
2. Never guess silently. If a unit column is missing, infer the unit from the \
value range and set needs_confirmation=true with your reasoning. If a column is \
ambiguous, offer 2-3 ranked alternatives instead of a bare guess.
3. Set needs_confirmation=true for any field that is inferred, ambiguous, or \
below full certainty. Only a clean, unambiguous column match is confidence 1.0 \
with needs_confirmation=false.

Match source_column to a header verbatim (including an empty string "" for an \
unlabelled column). Use inferred_value only when no column supplies the value.
"""


def propose_mapping(
    table: RawTable, client: anthropic.Anthropic | None = None
) -> MappingProposal:
    """Ask Claude for a column mapping and return it as a domain proposal.

    A missing API key surfaces as `anthropic.AuthenticationError` from the SDK;
    the caller decides how to report it.
    """
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _render_request(table)}],
        output_format=WireMappingProposal,
    )
    wire = response.parsed_output
    if wire is None:
        raise ValueError(
            f"Mapping failed for {table.label}: the model returned no "
            f"structured proposal (stop reason: {response.stop_reason})."
        )
    return _to_domain(wire, table.headers)


def _render_request(table: RawTable) -> str:
    """Build the user message: the reference vocabulary plus the raw table."""
    assay_lines = "\n".join(
        f"  - {a.canonical}: units {', '.join(a.compatible_units)}"
        for a in ASSAY_TYPES
    )
    range_lines = "\n".join(
        f"  - {unit}: {lo}–{hi}" for unit, (lo, hi) in UNIT_VALUE_RANGES.items()
    )
    return (
        f"Allowed assay types and their units:\n{assay_lines}\n\n"
        f"Allowed units: {', '.join(ALLOWED_UNITS)}\n\n"
        f"Typical value ranges by unit (overlapping — never guess a unit "
        f"silently):\n{range_lines}\n\n"
        f"Source file: {table.label}\n"
        f"{_render_table(table)}"
    )


def _render_table(table: RawTable) -> str:
    labelled = [h if h else "(blank header)" for h in table.headers]
    lines = [f"Columns ({len(table.headers)}): {' | '.join(labelled)}", ""]
    lines.append(f"First {min(_SAMPLE_ROWS, table.row_count)} of "
                 f"{table.row_count} rows:")
    for row in table.sample(_SAMPLE_ROWS):
        lines.append("  " + " | ".join(cell if cell else "(empty)" for cell in row))
    return "\n".join(lines)


def _to_domain(wire: WireMappingProposal, headers: list[str]) -> MappingProposal:
    """Map the validated wire model onto the domain proposal at the boundary."""
    mappings = [_to_domain_field(item) for item in wire.field_mappings]
    return MappingProposal(source_columns=headers, field_mappings=mappings)


def _to_domain_field(item: WireFieldMapping) -> FieldMapping:
    return FieldMapping(
        target_field=TargetField(item.target_field),
        source_column=item.source_column,
        confidence=item.confidence,
        reasoning=item.reasoning,
        needs_confirmation=item.needs_confirmation,
        inferred_value=item.inferred_value,
        alternatives=[
            ColumnCandidate(c.source_column, c.confidence) for c in item.alternatives
        ],
    )