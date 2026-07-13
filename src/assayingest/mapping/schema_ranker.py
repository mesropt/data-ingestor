"""The Schema ranker — Claude proposes which governed Schema fits a sheet.

The third and LAST stage of the Schema scorer (D-11-19). The two deterministic
stages — an exact learned-profile hit, then crosswalk alias coverage — always
run first, in pure Python, at zero cost. Only when BOTH return zero coverage
across EVERY governed Schema does a sheet's headers reach this module. That
ordering is the whole point: this is not "LLM first", it is D-10-03's
Python → Claude → human ladder applied to the Schema choice itself, and an LLM
call is only ever spent on what the cheap pass could not resolve.

Three properties hold structurally, not by a guard someone must remember:

  * HEADERS ONLY. The entry point takes a `list[str]`. There is no cell value in
    scope for a request to leak, so `headers_only` cannot change what is sent
    and there is no mode for it to have (D-11-04 / D-10-05, T-11-14).
  * A SCHEMA THE MODEL INVENTS DOES NOT EXIST. The output model is built at
    runtime as a `Literal` over the governed Schema names, so an out-of-set name
    is a schema violation at the SDK boundary — and `_to_domain` drops it AGAIN
    on the way in (T-11-15). A boundary closed once is a boundary closed by luck.
  * IT ONLY PROPOSES. `RankedSchema` carries a name, a reason, and a position.
    There is no `selected`, no `confident`, no `auto_apply` for anything
    downstream to mistake for permission: the human confirms every sheet, and
    nothing here is ever applied on its own (D-11-06, unchanged).

Like `mapper.py`, it carries ZERO compiled-in vocabulary: every Schema name and
every field name rendered into the prompt comes from the `schemas` argument
(D-18). A test greps this module to keep it that way.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, create_model

from ..domain.models import Schema

_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 16000


@dataclass(frozen=True)
class RankedSchema:
    """One governed Schema, ranked by Claude for one sheet's headers.

    `reason` is not decoration. A rank with no reason is a verdict the human
    cannot check, and the panel's "Claude suggests {schema}" line is only honest
    if it can also say why — especially here, where by definition there is no
    crosswalk evidence behind the proposal.

    `rank` is the position among the SURVIVORS of the boundary (1-based), never
    among what the model claimed: an invented name dropped from the head of the
    list must not leave a hole in the ranking.
    """

    schema_name: str
    reason: str
    rank: int


def build_ranking_wire_model(schema_names: list[str]) -> type[BaseModel]:
    """Build a per-request wire model whose `schema_name` is a runtime `Literal`
    over the governed Schema names — the same device `schema.py`'s
    `build_wire_models` uses for field names (D-16).

    This is the FIRST of the two closures on T-11-15: the model structurally
    cannot return a Schema that does not exist, so an out-of-set name is a schema
    violation at the SDK boundary rather than a runtime surprise downstream.
    Names are never sanitised — a space, a dash, or a leading digit all work
    unmodified as `Literal` VALUES; only `create_model`'s own keyword arguments
    need to be valid identifiers.
    """
    wire_ranked_schema = create_model(
        "WireRankedSchema",
        schema_name=(
            Literal[tuple(schema_names)],
            Field(description="The name of one of the listed schemas."),
        ),
        reason=(
            str,
            Field(
                description=(
                    "Short justification a curator can read, in plain English, "
                    "naming which headers led you to this schema."
                )
            ),
        ),
    )
    return create_model(
        "WireSchemaRanking",
        ranking=(
            list[wire_ranked_schema],
            Field(description="The listed schemas, best fit first. Omit any that do not fit at all."),
        ),
    )


def propose_schema_ranking(
    headers: list[str],
    schemas: Sequence[Schema],
    *,
    client: anthropic.Anthropic | None = None,
    sheet_name: str | None = None,
) -> tuple[RankedSchema, ...]:
    """Ask Claude to rank `schemas` for one sheet's HEADERS, and return the
    ranking as domain objects — a proposal, never an application.

    A missing API key surfaces as `anthropic.AuthenticationError` from the SDK;
    the caller decides how to report it. `service.propose_schemas_for_sheet`
    degrades any failure here to "no proposal → propose skip", so an outage
    costs the human a suggestion, never their ability to choose (T-11-16).

    Two inputs make the call meaningless and are refused before it is made,
    rather than sent and hoped over:

      * NO GOVERNED SCHEMA. There is nothing to rank, and a `Literal` over no
        names is not a schema.
      * NO HEADER. A sheet whose header row could not be resolved gives the model
        nothing to rank FROM, and asking anyway is asking for a guess with no
        evidence — the one thing this tool never does.
    """
    if not schemas or not headers:
        return ()
    client = client or anthropic.Anthropic()
    schema_names = [schema.name for schema in schemas]
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_render_system_prompt(schemas),
        messages=[{"role": "user", "content": _render_request(headers, sheet_name)}],
        output_format=build_ranking_wire_model(schema_names),
    )
    wire = response.parsed_output
    if wire is None:
        raise ValueError(
            f"No Schema ranking was produced for sheet "
            f"{sheet_name or '(unnamed)'!r}: the model returned no structured "
            f"proposal (stop reason: {response.stop_reason})."
        )
    return _to_domain(wire, schema_names)


def _render_system_prompt(schemas: Sequence[Schema]) -> str:
    """Build the system prompt entirely from the governed Schemas (D-18).

    The rules are domain-independent and survive verbatim across every Schema
    set; only the "Schemas" section is data-derived, so no vocabulary of any one
    domain is ever compiled into this string.
    """
    blocks = "\n".join(_render_schema_block(schema) for schema in schemas)
    return (
        "You are the schema-matching engine of a tool that ingests messy "
        "tabular files. A worksheet's column headers are given to you, and the "
        "tool's deterministic name-matching pass already found NO match for "
        "them against any of the schemas below. Your job is to rank those "
        "schemas by how well their target fields fit these headers, and to say "
        "why.\n\n"
        f"Schemas (each is listed by name, then by its target field names):\n{blocks}\n\n"
        "Three non-negotiable rules:\n"
        "1. Propose, never decide. Your ranking pre-selects a schema for a "
        "human, who confirms it before anything is ingested. Nothing you return "
        "is applied on its own.\n"
        "2. Never guess silently. Rank a schema ONLY when the headers give you a "
        "real reason to. Omit any schema that does not fit at all — an empty "
        "ranking is a valid, honest answer, and is far better than a plausible "
        "one you cannot justify.\n"
        "3. Say why, in terms the curator can check: name the headers that led "
        "you to a schema, and the target fields you read them as.\n\n"
        "You are shown the column headers and nothing else. There are no data "
        "values, and you must not ask for any.\n"
    )


def _render_schema_block(schema: Schema) -> str:
    """One governed Schema, as its NAME and its FIELD NAMES only — every string
    drawn from the store, none of it from this module.

    Flattened onto one line per schema: a Schema name arrives from a curator's
    store, and a newline inside one would escape this bullet and read as a fresh
    top-level instruction to Claude (`mapper.py::_render_field_line`, same
    hazard, same closure).
    """
    field_names = ", ".join(_one_line(cf.field.name) for cf in schema.fields)
    return f"- {_one_line(schema.name)}: {field_names}"


def _one_line(text: str) -> str:
    """Collapse any run of whitespace — newlines included — into one space."""
    return " ".join(str(text).split())


def _render_request(headers: list[str], sheet_name: str | None) -> str:
    """The user message: this sheet's name and its column headers. There is
    nothing else to send, because there is nothing else in scope (T-11-14)."""
    labelled = [h if h else "(blank header)" for h in headers]
    return (
        f"Worksheet: {sheet_name or '(unnamed)'}\n"
        f"Columns ({len(headers)}): {' | '.join(labelled)}\n"
    )


def _to_domain(wire, schema_names: list[str]) -> tuple[RankedSchema, ...]:
    """Map the validated wire model onto the domain ranking at the boundary.

    The SECOND closure on T-11-15, and the reason it exists: the `Literal` output
    model is the SDK's promise, and this is the tool's own check of it. A name
    outside the governed set is dropped rather than repaired — a Schema that does
    not exist cannot be proposed for ingestion, and a near-miss "corrected" into
    a real Schema would be exactly the silent guess this tool refuses to make.

    A Schema named twice is kept once, at its first position: one Schema cannot
    hold two ranks, and a list output cannot structurally forbid the repeat.

    Ranks are assigned AFTER both filters, so they are always contiguous from 1 —
    a dropped head does not leave a hole in the ranking a caller must reason about.
    """
    governed = set(schema_names)
    kept: dict[str, str] = {}
    for item in wire.ranking:
        if item.schema_name in governed and item.schema_name not in kept:
            kept[item.schema_name] = item.reason
    return tuple(
        RankedSchema(schema_name=name, reason=reason, rank=position)
        for position, (name, reason) in enumerate(kept.items(), start=1)
    )
