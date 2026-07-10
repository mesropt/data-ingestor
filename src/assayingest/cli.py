"""Command-line entry point — the Day-1 demo: messy file in, clean draft out.

Parses a CRO file, asks the mapper for a proposal, and prints both a structured
JSON draft and a human review summary. Export stays blocked while any field is
yellow; the human confirms before anything is trusted.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

import anthropic

#: Env vars the Anthropic SDK resolves credentials from (first match wins).
_CREDENTIAL_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

from .domain.models import FieldMapping, MappingProposal
from .mapping.mapper import propose_mapping
from .parsing.hint import StructuralHint, StructureQuestion
from .parsing.structure_assist import propose_structure
from .parsing.table import RawTable, parse, parse_file, sheet_names

_GREEN = "✓"  # ✓ clear
_YELLOW = "⚠"  # ⚠ needs confirmation


def proposal_to_dict(proposal: MappingProposal) -> dict:
    """Serialise a proposal to the JSON draft a downstream step would consume."""
    return {
        "ready": proposal.is_ready,
        "source_columns": proposal.source_columns,
        "field_mappings": [_field_to_dict(m) for m in proposal.field_mappings],
    }


def _field_to_dict(mapping: FieldMapping) -> dict:
    return {
        "target_field": mapping.target_field.value,
        "source_column": mapping.source_column,
        "confidence": mapping.confidence,
        "reasoning": mapping.reasoning,
        "needs_confirmation": mapping.needs_confirmation,
        "inferred_value": mapping.inferred_value,
        "alternatives": [
            {"source_column": c.source_column, "confidence": c.confidence}
            for c in mapping.alternatives
        ],
    }


def render_report(proposal: MappingProposal) -> str:
    """A colour-coded review summary: one line per field, then the gate."""
    lines = ["Proposed mapping (Claude proposes, you dispose):", ""]
    lines.extend(_render_field(m) for m in proposal.field_mappings)
    lines.append("")
    lines.append(_render_gate(proposal))
    return "\n".join(lines)


def _render_field(mapping: FieldMapping) -> str:
    marker = _YELLOW if mapping.needs_confirmation else _GREEN
    source = _describe_source(mapping)
    head = (
        f"  {marker} {mapping.target_field.value:<13} <- {source}  "
        f"(conf {mapping.confidence:.2f})"
    )
    if not mapping.needs_confirmation:
        return head
    detail = [head, f"      reason: {mapping.reasoning}"]
    if mapping.alternatives:
        options = ", ".join(
            f"{_label(c.source_column)} ({c.confidence:.2f})"
            for c in mapping.alternatives
        )
        detail.append(f"      options: {options}")
    return "\n".join(detail)


def _label(source_column: str) -> str:
    """Render a source header, naming the blank (unlabelled) column explicitly."""
    return source_column if source_column else "(blank header)"


def _describe_source(mapping: FieldMapping) -> str:
    if mapping.source_column is not None:
        return f"'{mapping.source_column}'"
    if mapping.inferred_value is not None:
        return f"inferred '{mapping.inferred_value}' (no column)"
    return "(no match)"


def _render_gate(proposal: MappingProposal) -> str:
    if proposal.is_ready:
        return f"{_GREEN} READY: all fields clear — safe to confirm and export."
    n = len(proposal.unclear_fields)
    names = ", ".join(m.target_field.value for m in proposal.unclear_fields)
    return (
        f"{_YELLOW} BLOCKED: {n} field(s) need confirmation ({names}). "
        f"Export stays disabled until resolved."
    )


def _has_credentials() -> bool:
    """True if the SDK can find a key without us constructing a client first."""
    return any(os.environ.get(var) for var in _CREDENTIAL_ENV_VARS)


def resolve_tables(path: str, sheet: str | None = None) -> list[RawTable]:
    """Decide which tables to ingest — one per Excel sheet, so none is skipped.

    A CSV yields a single table. A one-sheet workbook yields that sheet. A
    multi-sheet workbook yields every sheet (unless `sheet` names just one) —
    the tool never collapses a workbook to its first sheet silently.
    """
    names = sheet_names(path)
    if not names:  # CSV
        return [parse_file(path)]
    if sheet is not None:
        return [parse_file(path, sheet)]
    if len(names) == 1:
        return [parse_file(path, names[0])]
    return [parse_file(path, name) for name in names]


def resolve_or_ask(
    path: str, sheet: str | None = None, hint: StructuralHint | None = None
) -> list[RawTable] | StructureQuestion:
    """Resolve a file's structure — CSV or Excel — or return the human's
    structural question.

    Both file types now run through the same `parsing.table.parse()`
    structural engine end-to-end: CSV delimiter/locale detection, and for
    Excel, sheet selection + header detection + drawing detection (D-05,
    D-08, D-09). v1 targets one chosen table per file (PROJECT.md Out of
    Scope) — `parse()` picks the one data sheet, or asks when genuinely
    ambiguous; it never loops every sheet silently.
    """
    outcome = parse(path, sheet=sheet, hint=hint)
    if isinstance(outcome, StructureQuestion):
        return outcome
    return [outcome]


def run(
    path: str, sheet: str | None = None, hint: StructuralHint | None = None
) -> int:
    """Parse → propose → print, once per sheet. Returns a process exit code."""
    try:
        outcome = resolve_or_ask(path, sheet, hint)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if isinstance(outcome, StructureQuestion):
        return _ask_and_report(outcome)
    tables = outcome

    if not _has_credentials():
        print(
            "error: no Anthropic credentials. Set ANTHROPIC_API_KEY to run the "
            "mapper.",
            file=sys.stderr,
        )
        return 3

    return _map_and_report(tables)


def _ask_and_report(question: StructureQuestion) -> int:
    """Print a structural question instead of crashing or guessing (D-08).

    Asking is the caller's job, not the parser's — the CLI is one possible
    renderer of the same `StructureQuestion` object a future API/UI will
    receive verbatim (D-06). The question is enriched with a Claude pre-fill
    when available (D-01 layer 2), but enrichment only ever sets `proposal`
    — nothing is auto-applied; printing is as far as `run()` goes. Exit code
    4 is dedicated to "structure unresolved", never reused for
    parse/credential/mapping errors (codes 2/3/1).
    """
    question = _enrich_question(question)
    print(json.dumps(question.to_dict(), indent=2, ensure_ascii=False))
    print()
    print(_render_question(question))
    return 4


def _enrich_question(
    question: StructureQuestion, client: anthropic.Anthropic | None = None
) -> StructureQuestion:
    """Pre-fill a not-confident question with a Claude structural proposal
    (D-01 layer 2) — strictly advisory; the human still confirms (D-02).

    Degrades gracefully to the deterministic question, unchanged, whenever
    Claude isn't available: no client and no configured credentials, or the
    SDK call itself fails. Reuses `_map_one`'s AuthenticationError/APIError
    handling shape so a missing key never crashes the CLI (D-04, T-01-10).
    """
    if client is None and not _has_credentials():
        return question
    try:
        proposal = propose_structure(_render_question_evidence(question), client=client)
    except anthropic.AuthenticationError:
        return question
    except (anthropic.APIError, ValueError):
        return question
    return dataclasses.replace(question, proposal=proposal)


def _render_question_evidence(question: StructureQuestion) -> str:
    """Build the Claude request body from a `StructureQuestion`'s own raw
    evidence — the same rows and reasoning a human would read (D-07)."""
    lines = [f"Unsure about: {question.unsure_about}", f"Reason: {question.reason}", ""]
    if question.evidence_rows:
        lines.append("Raw evidence rows:")
        lines.extend(f"  {row}" for row in question.evidence_rows)
    return "\n".join(lines)


def _render_question(question: StructureQuestion) -> str:
    lines = [
        "Structural question — the tool is unsure and needs a hint "
        "(Claude proposes, you dispose):",
        "",
        f"  {_YELLOW} unsure about: {question.unsure_about}",
        f"      reason: {question.reason}",
        f"      confidence: {question.confidence:.2f}",
    ]
    if question.proposal is not None:
        lines.append(f"      proposal: {question.proposal.to_dict()}")
    if question.alternatives:
        options = ", ".join(str(alt.to_dict()) for alt in question.alternatives)
        lines.append(f"      alternatives: {options}")
    if question.evidence_rows:
        lines.append("      evidence rows:")
        lines.extend(f"        {row}" for row in question.evidence_rows[:5])
    lines.append("")
    lines.append(
        f"{_YELLOW} BLOCKED: structure unresolved. Nothing was mapped or exported."
    )
    lines.extend(_render_answer_hint(question))
    return "\n".join(lines)


def _render_answer_hint(question: StructureQuestion) -> list[str]:
    """Show the exact `--hint` flags that answer this question.

    A question the human cannot answer is worse than no question at all — the
    tool must say how to proceed, not merely that it stopped (PARSE-06). When
    nothing can proceed, it says that instead of offering a flag that would
    silently change nothing.
    """
    if not question.answerable_by_hint:
        return ["", "  This file's structure is unsupported in v1 — "
                "no structural hint resolves it."]
    flags = _hint_to_flags(question.proposal)
    if not flags:
        return []
    return ["", f"  To proceed, re-run with: {' '.join(flags)}"]


def _hint_to_flags(hint: StructuralHint | None) -> list[str]:
    """Render only the dimensions a hint actually pins down."""
    if hint is None:
        return []
    values = hint.to_dict()
    return [
        f"--hint {key}={values[attribute]!s}"
        for key, attribute in _HINT_KEYS.items()
        if values.get(attribute) is not None
    ]


def _map_and_report(tables: list[RawTable]) -> int:
    """Map each table and print its draft; worst per-table exit code wins."""
    multi = len(tables) > 1
    worst = 0
    for index, table in enumerate(tables, start=1):
        if multi:
            print(f"===== sheet {index}/{len(tables)}: "
                  f"{table.sheet_name} =====")
        if table.row_count == 0:
            print("  (skipped: sheet has no data rows)\n")
            continue
        worst = max(worst, _map_one(table))
        print()
    return worst


def _map_one(table: RawTable) -> int:
    try:
        proposal = propose_mapping(table)
    except anthropic.AuthenticationError:
        print("error: Anthropic rejected the credentials (check ANTHROPIC_API_KEY).",
              file=sys.stderr)
        return 3
    except (anthropic.APIError, ValueError) as exc:
        print(f"error: mapping failed for {table.label}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(proposal_to_dict(proposal), indent=2, ensure_ascii=False))
    print()
    print(render_report(proposal))
    return 0


#: The structural dimensions `--hint` can pin down, mapped to the
#: `StructuralHint` field each one fills.
_HINT_KEYS = {
    "header-row": "header_row_index",
    "sheet": "sheet_name",
    "delimiter": "delimiter",
    "decimal": "decimal_separator",
}


def _hint_from_args(hints: list[str]) -> StructuralHint | None:
    """Turn repeated `--hint key=value` flags into a `StructuralHint` (PARSE-06).

    This is the CLI's rendering of the answer a browser form will collect in
    Phase 4 — the same `StructuralHint` object travels on either path (D-06,
    D-08). A malformed flag raises `ValueError`; unresolved structure does
    not (D-05).
    """
    if not hints:
        return None
    fields: dict[str, str | int] = {}
    for item in hints:
        key, separator, value = item.partition("=")
        if not separator:
            raise ValueError(f"Cannot apply the hint '{item}': expected key=value")
        if key not in _HINT_KEYS:
            raise ValueError(
                f"Cannot apply an unknown structural hint '{key}' — "
                f"expected one of: {', '.join(sorted(_HINT_KEYS))}"
            )
        fields[_HINT_KEYS[key]] = _coerce_hint_value(key, value)
    return StructuralHint(**fields)


def _coerce_hint_value(key: str, value: str) -> str | int:
    """`header-row` is a 0-based row index; every other dimension is literal."""
    if key != "header-row":
        return value
    try:
        return int(value)
    except ValueError:
        raise ValueError(
            f"Cannot apply the hint header-row='{value}': expected a "
            "0-based row number"
        ) from None


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="assayingest",
        description="Map a CRO assay CSV/Excel file to target fields with Claude.",
    )
    parser.add_argument("file", help="Path to the CSV or Excel file to ingest.")
    parser.add_argument(
        "--sheet",
        default=None,
        help="For a multi-sheet Excel workbook, ingest only this sheet "
        "(default: every sheet).",
    )
    parser.add_argument(
        "--hint",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Answer a structural question so the tool can proceed. Repeatable. "
        f"Keys: {', '.join(sorted(_HINT_KEYS))}. "
        "Example: --hint header-row=4 --hint decimal=,",
    )
    args = parser.parse_args()
    try:
        hint = _hint_from_args(args.hint)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(args.file, args.sheet, hint))


if __name__ == "__main__":
    main()