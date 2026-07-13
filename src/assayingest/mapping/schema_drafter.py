"""The Schema drafter — Claude proposes a BRAND-NEW Schema for a sheet no
governed Schema fits.

The end of the escalation ladder, one rung past `schema_ranker.py`. The ranker
answers "which of these Schemas is this sheet?" and, when the honest answer is
"none of them" (zero crosswalk coverage in every Schema, and headers the ranker
can find no real reason to rank), the curator was left with a dropdown of
Schemas that all describe some other file. This module answers the question they
actually have: "then what Schema WOULD this sheet be?"

It drafts one — a name, and one canonical field per column — and drafts it as a
PROPOSAL. Nothing here creates anything. The draft is rendered into an editable
form; the human renames fields, changes types, drops columns they do not want,
and only their POST to `/api/schemas` creates a Schema. Claude proposes, the
human disposes — the product's first principle, applied to the one artefact that
had, until now, no proposal behind it at all.

Two properties hold structurally, not by a guard someone must remember:

  * A COLUMN THE MODEL INVENTS DOES NOT EXIST. A drafted field names its source
    column by INDEX, never by copying its text, and `_to_domain` drops any index
    outside the real header list. The model cannot draft a field for a column the
    sheet does not have, and cannot rename a header on the way past.
  * TYPES ARE PROPOSED, NEVER ENFORCED. `type` is a `Literal` over `FIELD_TYPES`
    — the same four the validator knows — so a draft cannot carry a type the
    validator would later choke on. Which of the four is a guess, and it is
    labelled as one: the form shows it as an editable control, pre-filled.

Sample VALUES are sent when the curator has not asked for headers-only: a header
called `Run 1` is a number or a free-text note depending entirely on what is
under it, and refusing to look is not caution, it is a worse guess (the
`headers_only` toggle remains the curator's, and under it this module sends
column names alone — a draft from headers is still far better than no draft).
The model never returns a value: the wire model has nowhere to put one.

Like `mapper.py` and `schema_ranker.py`, it carries ZERO compiled-in vocabulary:
every name in the prompt comes from the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, create_model

from ..fields.models import FIELD_TYPES

_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 8000

#: How many data rows the drafter is shown per column. Enough to tell a number
#: from a label and a date from an id; far too few to be an extraction.
SAMPLE_ROWS = 5


@dataclass(frozen=True)
class DraftField:
    """One proposed canonical field, and the source column it was read from.

    `source_header` is the file's OWN header text, read back out of the header
    list by index — never a string the model produced. `reason` is what makes
    the type checkable: a curator cannot confirm `number` without being told it
    was concluded from what sits under the header.
    """

    source_header: str
    name: str
    type: str
    required: bool
    reason: str


@dataclass(frozen=True)
class SchemaDraft:
    """A whole proposed Schema: a name and its fields, in column order.

    Nothing about this is a Schema yet. It has no id, no store row, no aliases
    and no provenance — those exist only once a human posts it to
    `/api/schemas`, where the actor is recorded as theirs, because the decision
    was.
    """

    name: str
    fields: tuple[DraftField, ...]


def build_draft_wire_model(column_count: int) -> type[BaseModel]:
    """Build a per-request wire model whose `type` is a `Literal` over the four
    validator-known field types and whose `column_index` is a plain int, bounded
    by `_to_domain` against the real header list.

    The index — rather than a `Literal` over the header texts — is deliberate:
    headers repeat, and headers go blank, and neither is a legal `Literal` value
    set. An index cannot collide, and it gives the model no way to hand back a
    header's TEXT, which is the property this boundary is really protecting.
    """
    wire_draft_field = create_model(
        "WireDraftField",
        column_index=(
            int,
            Field(
                description=(
                    f"Which column this field reads, 0-based, in the order the "
                    f"columns were listed (0 to {max(column_count - 1, 0)})."
                )
            ),
        ),
        name=(
            str,
            Field(
                description=(
                    "The canonical field name: lower_snake_case, no spaces. "
                    "Name what the column MEANS, in the file's own vocabulary — "
                    "never a term from another domain."
                )
            ),
        ),
        type=(
            Literal[FIELD_TYPES],
            Field(
                description=(
                    "The field's type. 'number' for measurements, 'integer' for "
                    "counts, 'date' for dates, 'text' for anything else — "
                    "including codes and ids that merely look numeric."
                )
            ),
        ),
        required=(
            bool,
            Field(
                description=(
                    "True ONLY for a column with a value in every sampled row "
                    "AND without which a record would be meaningless. When in "
                    "doubt, false: a wrongly-required field blocks a whole file."
                )
            ),
        ),
        reason=(
            str,
            Field(
                description=(
                    "One short line a curator can check, naming what in the "
                    "column led you to this type — never quoting a cell value."
                )
            ),
        ),
    )
    return create_model(
        "WireSchemaDraft",
        schema_name=(
            str,
            Field(
                description=(
                    "A short lower-kebab-case name for the Schema this sheet "
                    "would need, e.g. the kind of data it holds."
                )
            ),
        ),
        fields=(
            list[wire_draft_field],
            Field(
                description=(
                    "One field per column worth keeping, in column order. Omit a "
                    "column that carries no data of its own (a blank spacer, a "
                    "repeated label); never omit one merely because you are "
                    "unsure of its type — propose the type you can defend."
                )
            ),
        ),
    )


def propose_schema_draft(
    headers: list[str],
    sample_rows: list[list[str]],
    *,
    sheet_name: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> SchemaDraft:
    """Ask Claude to draft a Schema for one sheet's columns, and return it as a
    domain proposal — never a created Schema.

    `sample_rows` is what the CALLER decided this sheet may show (the empty list
    under `headers_only`); this module sends what it is handed and adds nothing.
    A missing API key surfaces as `anthropic.AuthenticationError` from the SDK
    and a missing draft as `ValueError` — the route reports both; neither is
    logged here.
    """
    if not headers:
        raise ValueError(
            "No Schema could be drafted for this sheet: its columns were never "
            "resolved, so there is nothing to draft fields from."
        )
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": _render_request(headers, sample_rows, sheet_name)}
        ],
        output_format=build_draft_wire_model(len(headers)),
    )
    wire = response.parsed_output
    if wire is None:
        raise ValueError(
            f"No Schema draft was produced for sheet {sheet_name or '(unnamed)'!r}: "
            f"the model returned no structured proposal "
            f"(stop reason: {response.stop_reason})."
        )
    return _to_domain(wire, headers)


_SYSTEM_PROMPT = (
    "You are the schema-drafting engine of a tool that ingests messy tabular "
    "files. A worksheet's columns are given to you, and the tool has already "
    "established that NONE of the curator's existing schemas fit them. Your job "
    "is to draft the schema this sheet would need: a name, and one canonical "
    "field per column worth keeping.\n\n"
    "Three non-negotiable rules:\n"
    "1. Propose, never decide. Your draft pre-fills a form a human edits and "
    "submits. Nothing you return creates anything.\n"
    "2. Never guess silently. Every field carries a reason naming what in the "
    "column led you to its type. A type you cannot defend from the evidence is "
    "'text' — the type that asserts the least.\n"
    "3. Return indices and names, never cell contents. The tool reads every "
    "value from the file itself; you name positions and propose vocabulary.\n\n"
    "Name fields in the FILE's own vocabulary, not a domain you assume: this "
    "tool ingests any tabular file, and a field named for a domain the curator "
    "does not work in is worse than no draft at all.\n"
)


def _render_request(
    headers: list[str], sample_rows: list[list[str]], sheet_name: str | None
) -> str:
    """The user message: the sheet's name, its columns (indexed, so the model
    answers in indices), and — only if the caller supplied any — a few rows of
    evidence under them."""
    columns = "\n".join(
        f"  [{index}] {header if header.strip() else '(blank header)'}"
        for index, header in enumerate(headers)
    )
    request = (
        f"Worksheet: {sheet_name or '(unnamed)'}\n"
        f"Columns ({len(headers)}):\n{columns}\n"
    )
    if not sample_rows:
        return (
            f"{request}\n"
            "No sample values are available for this sheet (the curator has "
            "headers-only privacy mode on). Draft from the column names alone, "
            "and prefer 'text' wherever the name does not settle the type.\n"
        )
    rows = "\n".join(
        "  | ".join(_one_line(cell) for cell in row) for row in sample_rows
    )
    return f"{request}\nFirst {len(sample_rows)} data rows, in column order:\n{rows}\n"


def _one_line(text: str) -> str:
    """Collapse any run of whitespace — newlines included — into one space."""
    return " ".join(str(text).split())


def _to_domain(wire, headers: list[str]) -> SchemaDraft:
    """Map the validated wire draft onto the domain proposal at the boundary.

    Three closures, each one a way the draft could otherwise lie about the file:

      * An index outside the real header list is DROPPED, never clamped — a
        field drafted for a column that does not exist is not repairable into a
        field for the column next door.
      * A column drafted TWICE keeps its first field: one column is one field
        here, and a list output cannot structurally forbid the repeat.
      * A field NAME used twice is dropped on its second use — `fields.loader`
        would reject the whole draft for it, and losing one field beats losing
        the draft.

    `source_header` is read from `headers` by index, so it is always the file's
    own text — the model's own copy of a header, had it made one, could not
    reach this far.
    """
    seen_columns: set[int] = set()
    seen_names: set[str] = set()
    fields: list[DraftField] = []
    for item in wire.fields:
        index = item.column_index
        name = item.name.strip()
        if not 0 <= index < len(headers) or index in seen_columns:
            continue
        if not name or name in seen_names:
            continue
        seen_columns.add(index)
        seen_names.add(name)
        fields.append(
            DraftField(
                source_header=headers[index],
                name=name,
                type=item.type,
                required=item.required,
                reason=item.reason,
            )
        )
    return SchemaDraft(name=wire.schema_name.strip(), fields=tuple(fields))
