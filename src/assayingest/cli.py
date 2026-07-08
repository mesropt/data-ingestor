"""Command-line entry point — the Day-1 demo: messy file in, clean draft out.

Parses a CRO file, asks the mapper for a proposal, and prints both a structured
JSON draft and a human review summary. Export stays blocked while any field is
yellow; the human confirms before anything is trusted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import anthropic

#: Env vars the Anthropic SDK resolves credentials from (first match wins).
_CREDENTIAL_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

from .domain.models import FieldMapping, MappingProposal
from .mapping.mapper import propose_mapping
from .parsing.table import RawTable, parse_file, sheet_names

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


def run(path: str, sheet: str | None = None) -> int:
    """Parse → propose → print, once per sheet. Returns a process exit code."""
    try:
        tables = resolve_tables(path, sheet)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not _has_credentials():
        print(
            "error: no Anthropic credentials. Set ANTHROPIC_API_KEY to run the "
            "mapper.",
            file=sys.stderr,
        )
        return 3

    return _map_and_report(tables)


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
    args = parser.parse_args()
    sys.exit(run(args.file, args.sheet))


if __name__ == "__main__":
    main()