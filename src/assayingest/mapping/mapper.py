"""The mapper agent — Claude proposes a column mapping via structured output.

This is the core of the tool. It hands Claude the raw table and the caller's
declared field set, constrains the reply to a runtime-built JSON schema, and
maps the validated wire model onto the domain `MappingProposal`. It never
writes anything: it proposes, a human disposes. It carries zero hardcoded
domain vocabulary — every field name, description, and constraint rendered
into the prompt comes from the `FieldSet` the caller supplies (D-18/D-19).
"""

from __future__ import annotations

from dataclasses import replace

import anthropic

from ..domain.models import ColumnCandidate, FieldMapping, MappingProposal
from ..fields.models import Field, FieldSet
from ..parsing.hint import NumericLocale
from ..parsing.table import RawTable
from .schema import build_wire_models

_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 16000
_SAMPLE_ROWS = 6


def propose_mapping(
    table: RawTable,
    field_set: FieldSet,
    client: anthropic.Anthropic | None = None,
    *,
    headers_only: bool = False,
) -> MappingProposal:
    """Ask Claude for a column mapping and return it as a domain proposal.

    A missing API key surfaces as `anthropic.AuthenticationError` from the SDK;
    the caller decides how to report it.

    `headers_only` (D-10, P2 privacy dial): when True, the request sent to
    Claude carries the column headers and locale evidence only -- zero data
    values. Mapping confidence typically drops (more fields need a human's
    confirmation), but no cell value ever leaves the machine on this path.
    """
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_render_system_prompt(field_set),
        messages=[
            {
                "role": "user",
                "content": _render_request(table, field_set, headers_only=headers_only),
            }
        ],
        output_format=build_wire_models(field_set.field_names),
    )
    wire = response.parsed_output
    if wire is None:
        raise ValueError(
            f"Mapping failed for {table.label}: the model returned no "
            f"structured proposal (stop reason: {response.stop_reason})."
        )
    optional_fields = frozenset(f.name for f in field_set.fields if not f.required)
    return _to_domain(
        wire, table.headers, list(field_set.field_names), optional_fields
    )


def _render_system_prompt(field_set: FieldSet) -> str:
    """Build the system prompt entirely from the caller's field set (D-18).

    The three non-negotiable rules are domain-independent and survive
    verbatim across every field set; only the "Target fields" section is
    field-set-derived, so no assay, unit, or other domain vocabulary is
    ever compiled into this string.
    """
    field_lines = "\n".join(_render_field_line(f) for f in field_set.fields)
    return (
        "You are the mapping engine of a tool that ingests messy tabular "
        "files. Every source file formats its data differently. Your job "
        "is to map the source columns onto the target fields declared "
        "below and report how confident you are in each mapping.\n\n"
        f"Target fields (produce exactly one entry per field):\n{field_lines}\n\n"
        "Three non-negotiable rules:\n"
        "1. Propose, never write. You only return a proposal with per-field "
        "confidence.\n"
        "2. Never guess silently. If a value is missing from every column, "
        "infer it only when the evidence supports it and set "
        "needs_confirmation=true with your reasoning. If a column is "
        "ambiguous, offer 2-3 ranked alternatives instead of a bare "
        "guess.\n"
        "3. Set needs_confirmation=true for any field that is inferred, "
        "ambiguous, or below full certainty. Only a clean, unambiguous "
        "column match is confidence 1.0 with needs_confirmation=false.\n\n"
        "Match source_column to a header verbatim (including an empty "
        'string "" for an unlabelled column). Use inferred_value only '
        "when no column supplies the value.\n"
    )


def _render_field_line(f: Field) -> str:
    """One line describing a declared field's name and every constraint the
    field-set author supplied — nothing about any field is assumed.

    Every part is flattened onto a single line: a field set may arrive from a
    shared file, and a newline inside a name or description would escape this
    bullet and read as a fresh top-level instruction to Claude.
    """
    details = []
    if f.description:
        details.append(_one_line(f.description))
    if f.type:
        details.append(f"type: {f.type}")
    if f.unit:
        details.append(f"unit: {_one_line(f.unit)}")
    if f.allowed_values:
        details.append(f"allowed values: {', '.join(f.allowed_values)}")
    if f.min is not None or f.max is not None:
        lo = f.min if f.min is not None else "-inf"
        hi = f.max if f.max is not None else "+inf"
        details.append(f"range: {lo}-{hi}")
    if not f.required:
        details.append("optional")
    name = _one_line(f.name)
    if not details:
        return f"- {name}"
    return f"- {name}: {'; '.join(details)}"


def _one_line(text: str) -> str:
    """Collapse any run of whitespace — newlines included — into one space."""
    return " ".join(str(text).split())


def _render_request(table: RawTable, field_set: FieldSet, *, headers_only: bool = False) -> str:
    """Build the user message: the field set's target names plus the raw table."""
    names = ", ".join(field_set.field_names)
    return (
        f"Target fields: {names}\n\n"
        f"Source file: {table.label}\n"
        f"{_render_table(table, headers_only=headers_only)}"
    )


def _render_table(table: RawTable, *, headers_only: bool = False) -> str:
    """The one send site D-10's privacy dial gates: `headers_only=True`
    stops after the column list and locale evidence -- the "First N of M
    rows" sample block, and every value in it, is skipped entirely so no
    cell value ever reaches the request (P2)."""
    labelled = [h if h else "(blank header)" for h in table.headers]
    lines = [f"Columns ({len(table.headers)}): {' | '.join(labelled)}", ""]
    lines.extend(_render_locale_lines(table))
    if headers_only:
        return "\n".join(lines)
    lines.append(
        f"First {min(_SAMPLE_ROWS, table.row_count)} of {table.row_count} rows:"
    )
    for row in table.sample(_SAMPLE_ROWS):
        lines.append("  " + " | ".join(cell if cell else "(empty)" for cell in row))
    return "\n".join(lines)


def _render_locale_lines(table: RawTable) -> list[str]:
    """Evidence lines naming what the parser already resolved about a
    column's decimal locale (D-22) — evidence, not a verdict.

    Only `decimal_comma` is named: it is the one locale Phase 1 resolves
    with certainty, and the one Claude used to keep re-flagging as
    ambiguous despite the parser already having settled it. An `ambiguous`
    column produces no line here, so Claude still flags it — the prompt
    states what the parser read, never what Claude should conclude.
    Guards on the lengths matching (Pitfall 3): `column_locales` is empty
    for a table that never went through structural detection (the legacy
    `parse_file()` path).
    """
    if len(table.column_locales) != len(table.headers):
        return []
    lines = []
    for header, locale in zip(table.headers, table.column_locales):
        if locale == NumericLocale.DECIMAL_COMMA.value:
            label = header if header else "(blank header)"
            lines.append(
                f"  Parser evidence: column '{label}' was read as "
                "decimal_comma (the comma is that column's decimal "
                "separator)."
            )
    if lines:
        lines.append("")
    return lines


def _to_domain(
    wire,
    headers: list[str],
    field_names: list[str],
    optional_fields: frozenset[str] = frozenset(),
) -> MappingProposal:
    """Map the validated wire model onto the domain proposal at the boundary.

    The schema constrains which field names Claude may return, but nothing
    constrains the `source_column` it names, nor guarantees it answers for
    every declared field. Both gaps let an unverifiable claim reach the
    export gate wearing a green flag, so both are closed here — at the
    boundary, before any domain object exists.

    `optional_fields` are the fields the author marked `required: false`
    (D-09): one that no column supplies is left cleanly empty rather than
    yellow, so a missing optional field can never block export forever. An
    optional field Claude *did* map to a non-existent column is still a
    hallucination and stays flagged.
    """
    proposed = {item.target_field: item for item in wire.field_mappings}
    mappings = [
        _to_domain_field(proposed[name], headers)
        if name in proposed
        else _unanswered_field(name)
        for name in field_names
    ]
    mappings = [
        _cleared_if_optional_and_absent(m, optional_fields) for m in mappings
    ]
    return MappingProposal(source_columns=headers, field_mappings=mappings)


def _cleared_if_optional_and_absent(
    mapping: FieldMapping, optional_fields: frozenset[str]
) -> FieldMapping:
    """An optional field with no column and no inferred value is a legitimate
    blank (D-09) — clear it so it cannot hold the export gate shut."""
    is_absent = mapping.source_column is None and mapping.inferred_value is None
    if mapping.target_field in optional_fields and is_absent:
        return replace(mapping, needs_confirmation=False)
    return mapping


def _to_domain_field(item, headers: list[str]) -> FieldMapping:
    hallucinated = _names_a_column_that_does_not_exist(item.source_column, headers)
    return FieldMapping(
        target_field=item.target_field,
        source_column=item.source_column,
        confidence=item.confidence,
        reasoning=_with_hallucination_note(item.reasoning, item.source_column)
        if hallucinated
        else item.reasoning,
        needs_confirmation=item.needs_confirmation or hallucinated,
        inferred_value=item.inferred_value,
        alternatives=[
            ColumnCandidate(c.source_column, c.confidence) for c in item.alternatives
        ],
    )


def _names_a_column_that_does_not_exist(
    source_column: str | None, headers: list[str]
) -> bool:
    """`None` is Claude honestly reporting no match; a name absent from the
    file's own headers is a column it invented."""
    return source_column is not None and source_column not in headers


def _with_hallucination_note(reasoning: str, source_column: str) -> str:
    return (
        f"{reasoning} [Flagged by the tool: no column named "
        f"'{source_column}' exists in this file.]"
    )


def _unanswered_field(name: str) -> FieldMapping:
    """A field the model never answered for. Its absence must be visible and
    must block export — silence is not a clean mapping."""
    return FieldMapping(
        target_field=name,
        source_column=None,
        confidence=0.0,
        reasoning="The model returned no mapping for this field.",
        needs_confirmation=True,
    )
